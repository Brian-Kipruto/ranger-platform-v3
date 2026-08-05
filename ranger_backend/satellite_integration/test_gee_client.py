# ─── RANGER V3 START: gee client tests ───
"""GEE client wrapper tests (F10.2 CP4).

Earth Engine is MOCKED throughout. CI must never depend on Google being up,
on a service-account key existing, or on quota being available. One
integration test at the bottom talks to the real API and skips itself unless
credentials are configured.

The mock is a hand-rolled fake rather than MagicMock: the client's contract
with `ee` is small and specific (ImageCollection -> filterBounds -> filterDate
-> filter -> sort -> limit -> getInfo), and a fake that enforces that shape
catches a broken call chain, where a MagicMock would happily accept anything.
"""
import sys
import types
from datetime import date, datetime, timezone

import pytest
from django.contrib.gis.geos import Polygon

from core.geo import polygon_from_bbox
from satellite_integration import gee_client
from satellite_integration.gee_client import (
    GEEAuthenticationError,
    GEECollectionError,
    GEEConfigurationError,
    GEEError,
    GEEQuotaError,
    SceneMetadata,
)

FOROLE_BBOX = (37.9668, 3.7160, 37.9678, 3.7175)

SCENE_FEATURE = {
    "id": "COPERNICUS/S2_SR_HARMONIZED/20260115T073241_20260115T075312_T37PCM",
    "bands": [{"id": "B4"}, {"id": "B8"}],
    "properties": {
        "system:time_start": 1768460000000,
        "system:footprint": {
            "type": "Polygon",
            "coordinates": [[
                [37.960, 3.710], [37.975, 3.710],
                [37.975, 3.725], [37.960, 3.725], [37.960, 3.710],
            ]],
        },
        "CLOUDY_PIXEL_PERCENTAGE": 4.2,
        "MGRS_TILE": "37PCM",
    },
}


class FakeCollection:
    """Records the call chain so tests can assert on it."""

    def __init__(self, collection_id, features, raises=None):
        self.collection_id = collection_id
        self._features = features
        self._raises = raises
        self.calls = []

    def _chain(self, name, *args):
        self.calls.append((name, args))
        return self

    def filterBounds(self, geom): return self._chain("filterBounds", geom)
    def filterDate(self, start, end): return self._chain("filterDate", start, end)
    def filter(self, f): return self._chain("filter", f)
    def sort(self, key, asc=True): return self._chain("sort", key, asc)
    def limit(self, n): return self._chain("limit", n)

    def size(self):
        if self._raises:
            raise self._raises
        return self

    def getInfo(self):
        if self._raises:
            raise self._raises
        return {"features": self._features}


@pytest.fixture
def fake_ee(monkeypatch):
    """Install a fake `ee` module and pretend initialization succeeded."""
    state = {"collections": [], "features": [SCENE_FEATURE], "raises": None}

    def ImageCollection(collection_id):
        col = FakeCollection(collection_id, state["features"], state["raises"])
        state["collections"].append(col)
        return col

    fake = types.ModuleType("ee")
    fake.ImageCollection = ImageCollection
    fake.Geometry = lambda geojson: {"__ee_geometry__": geojson}
    fake.Filter = types.SimpleNamespace(lte=lambda prop, val: ("lte", prop, val))
    fake.ServiceAccountCredentials = lambda email, key: object()
    fake.Initialize = lambda creds, project=None: None

    monkeypatch.setitem(sys.modules, "ee", fake)
    monkeypatch.setattr(gee_client, "_initialized", True)
    return state


@pytest.fixture
def aoi():
    return polygon_from_bbox(*FOROLE_BBOX)


class TestConfiguration:

    def test_is_configured_false_when_settings_missing(self, settings):
        settings.GEE_PROJECT_ID = ""
        assert gee_client.is_configured() is False

    def test_is_configured_true_when_all_present(self, settings):
        settings.GEE_PROJECT_ID = "ranger-eo"
        settings.GEE_SERVICE_ACCOUNT_EMAIL = "x@y.iam.gserviceaccount.com"
        settings.GEE_KEY_PATH = "/tmp/key.json"
        assert gee_client.is_configured() is True

    def test_initialize_names_the_missing_settings(self, settings, monkeypatch):
        monkeypatch.setattr(gee_client, "_initialized", False)
        settings.GEE_PROJECT_ID = ""
        settings.GEE_SERVICE_ACCOUNT_EMAIL = ""
        settings.GEE_KEY_PATH = ""

        with pytest.raises(GEEConfigurationError) as exc:
            gee_client.initialize(force=True)
        # A useful error tells you WHICH setting, not just "not configured".
        assert "GEE_PROJECT_ID" in str(exc.value)

    def test_import_does_not_require_credentials(self):
        """The rule that keeps manage.py and the test suite working: importing
        this module must never touch Earth Engine.

        Loads a SEPARATE module object rather than reload()ing the shared one —
        reload rebuilds the exception classes, and every later isinstance()
        check in this file would then compare against stale class objects.
        """
        import importlib.util

        spec = importlib.util.find_spec("satellite_integration.gee_client")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # must not raise
        assert module.is_configured is not None


class TestErrorTranslation:
    """EEException carries prose, not codes. Callers need types."""

    @pytest.mark.parametrize("message,expected", [
        ("Caller does not have required permission to use project ranger-eo",
         GEEAuthenticationError),
        ("Permission denied on resource", GEEAuthenticationError),
        ("invalid_grant: account not found", GEEAuthenticationError),
        ("User memory limit exceeded: quota", GEEQuotaError),
        ("429 Too Many Requests", GEEQuotaError),
        ("ImageCollection.load: collection not found", GEECollectionError),
        ("Project is not signed up for Earth Engine", GEEConfigurationError),
        ("something else entirely", GEEError),
    ])
    def test_translates_by_message(self, message, expected):
        assert isinstance(gee_client._translate(Exception(message)), expected)

    def test_auth_error_mentions_the_roles(self):
        """The CP0 failure was missing IAM roles, not a bad key. The error
        should say so, because the two look identical from the traceback."""
        err = gee_client._translate(Exception("403 caller does not have permission"))
        assert "Service Usage Consumer" in str(err)


@pytest.mark.geo
class TestSearchScenes:

    def test_returns_normalized_scene_metadata(self, fake_ee, aoi):
        scenes = gee_client.search_scenes(
            "COPERNICUS/S2_SR_HARMONIZED", aoi,
            date(2026, 1, 1), date(2026, 8, 1),
            max_cloud=20, cloud_property="CLOUDY_PIXEL_PERCENTAGE",
        )
        assert len(scenes) == 1
        scene = scenes[0]
        assert isinstance(scene, SceneMetadata)
        assert scene.asset_id.startswith("COPERNICUS/S2_SR_HARMONIZED/")
        assert scene.cloud_cover_pct == pytest.approx(4.2)
        assert scene.bands == ["B4", "B8"]

    def test_acquisition_date_is_utc_aware(self, fake_ee, aoi):
        scene = gee_client.search_scenes(
            "C", aoi, date(2026, 1, 1), date(2026, 8, 1))[0]
        assert scene.acquisition_date.tzinfo is not None
        assert scene.acquisition_date.tzinfo == timezone.utc

    def test_footprint_is_a_4326_polygon(self, fake_ee, aoi):
        scene = gee_client.search_scenes(
            "C", aoi, date(2026, 1, 1), date(2026, 8, 1))[0]
        assert isinstance(scene.footprint, Polygon)
        assert scene.footprint.srid == 4326

    def test_footprint_intersects_the_aoi(self, fake_ee, aoi):
        """A scene that does not overlap what we asked for means the geometry
        handoff is broken — the F10.1 lesson, applied to a new boundary."""
        scene = gee_client.search_scenes(
            "C", aoi, date(2026, 1, 1), date(2026, 8, 1))[0]
        assert scene.footprint.intersects(aoi)

    def test_falls_back_to_the_aoi_when_footprint_missing(self, fake_ee, aoi):
        feature = {**SCENE_FEATURE, "properties": {
            "system:time_start": 1768460000000}}
        fake_ee["features"] = [feature]

        scene = gee_client.search_scenes(
            "C", aoi, date(2026, 1, 1), date(2026, 8, 1))[0]
        assert scene.footprint.equals(aoi)

    def test_scene_without_timestamp_is_skipped_not_fatal(self, fake_ee, aoi):
        fake_ee["features"] = [{"id": "X", "properties": {}}]
        assert gee_client.search_scenes(
            "C", aoi, date(2026, 1, 1), date(2026, 8, 1)) == []

    def test_empty_result_is_not_an_error(self, fake_ee, aoi):
        fake_ee["features"] = []
        assert gee_client.search_scenes(
            "C", aoi, date(2026, 1, 1), date(2026, 8, 1)) == []

    def test_cloud_filter_applied_when_property_given(self, fake_ee, aoi):
        gee_client.search_scenes(
            "C", aoi, date(2026, 1, 1), date(2026, 8, 1),
            max_cloud=20, cloud_property="CLOUDY_PIXEL_PERCENTAGE")
        names = [c[0] for c in fake_ee["collections"][0].calls]
        assert "filter" in names

    def test_cloud_filter_skipped_without_property(self, fake_ee, aoi):
        """Sentinel-1 has no cloud metadata. Filtering anyway returns an empty
        collection — which reads as 'no scenes here' and is a silent lie."""
        gee_client.search_scenes(
            "C", aoi, date(2026, 1, 1), date(2026, 8, 1),
            max_cloud=20, cloud_property="")
        names = [c[0] for c in fake_ee["collections"][0].calls]
        assert "filter" not in names

    def test_cloud_cover_is_none_without_property(self, fake_ee, aoi):
        scene = gee_client.search_scenes(
            "C", aoi, date(2026, 1, 1), date(2026, 8, 1))[0]
        assert scene.cloud_cover_pct is None

    def test_makes_exactly_one_collection_call(self, fake_ee, aoi):
        """Every getInfo() spends EECU. One search must be one round trip."""
        gee_client.search_scenes("C", aoi, date(2026, 1, 1), date(2026, 8, 1))
        assert len(fake_ee["collections"]) == 1

    def test_limit_is_passed_through(self, fake_ee, aoi):
        gee_client.search_scenes(
            "C", aoi, date(2026, 1, 1), date(2026, 8, 1), limit=7)
        limits = [c for c in fake_ee["collections"][0].calls if c[0] == "limit"]
        assert limits[0][1][0] == 7

    def test_system_properties_are_stripped_but_others_kept(self, fake_ee, aoi):
        scene = gee_client.search_scenes(
            "C", aoi, date(2026, 1, 1), date(2026, 8, 1))[0]
        assert "MGRS_TILE" in scene.properties
        assert not any(k.startswith("system:") for k in scene.properties)

    def test_api_errors_surface_as_typed_exceptions(self, fake_ee, aoi):
        fake_ee["raises"] = Exception("Caller does not have required permission")
        with pytest.raises(GEEAuthenticationError):
            gee_client.search_scenes("C", aoi, date(2026, 1, 1), date(2026, 8, 1))


class TestCollectionExists:

    def test_true_for_a_resolvable_collection(self, fake_ee, aoi):
        assert gee_client.collection_exists("COPERNICUS/S2_SR_HARMONIZED") is True

    def test_false_for_a_typo(self, fake_ee):
        fake_ee["raises"] = Exception("ImageCollection.load: collection not found")
        assert gee_client.collection_exists("COPERNICUS/TYPO") is False

    def test_auth_errors_still_raise(self, fake_ee):
        """A permissions failure must not be reported as 'does not exist' —
        that would send you hunting a typo that isn't there."""
        fake_ee["raises"] = Exception("Caller does not have required permission")
        with pytest.raises(GEEAuthenticationError):
            gee_client.collection_exists("COPERNICUS/S2_SR_HARMONIZED")


@pytest.mark.integration
@pytest.mark.skipif(
    not gee_client.is_configured(),
    reason="Earth Engine credentials not configured",
)
class TestRealEarthEngine:
    """Talks to Google. Skipped without credentials; never required in CI."""

    def test_finds_real_sentinel2_scenes_over_forole(self):
        scenes = gee_client.search_scenes(
            "COPERNICUS/S2_SR_HARMONIZED",
            polygon_from_bbox(*FOROLE_BBOX),
            date(2026, 1, 1), date(2026, 8, 1),
            max_cloud=20, cloud_property="CLOUDY_PIXEL_PERCENTAGE",
            limit=5,
        )
        assert scenes, "expected Sentinel-2 coverage over Forole"
        for scene in scenes:
            assert scene.footprint.intersects(polygon_from_bbox(*FOROLE_BBOX))
            assert scene.cloud_cover_pct <= 20

    def test_landsat5_brackets_the_1985_drilling(self):
        """Amoco Laga Balal #1 was drilled 22 December 1985.

        Landsat 5 has NO coverage of this site between 1985-04-15 and
        1986-01-12, so no image of the drilling itself exists. What does exist
        is better for change detection: cloud-free scenes on either side, both
        in January, holding sun angle and season constant.
        """
        from core.marsabit import site_bbox

        aoi = polygon_from_bbox(*site_bbox("dukana-w1"))
        drilling = datetime(1985, 12, 22, tzinfo=timezone.utc)

        scenes = gee_client.search_scenes(
            "LANDSAT/LT05/C02/T1_L2", aoi,
            date(1984, 1, 1), date(1987, 1, 1),
            cloud_property="CLOUD_COVER", limit=60,
        )
        before = [s for s in scenes if s.acquisition_date < drilling]
        after = [s for s in scenes if s.acquisition_date > drilling]

        assert before, "no pre-drilling imagery of Laga Balal"
        assert after, "no post-drilling imagery of Laga Balal"
        assert min(s.cloud_cover_pct for s in before) <= 5, "no clear pre-drilling scene"
        assert min(s.cloud_cover_pct for s in after) <= 5, "no clear post-drilling scene"
# ─── RANGER V3 END: gee client tests ───
