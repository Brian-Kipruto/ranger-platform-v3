# ─── RANGER V3 START: fetch_scenes tests ───
"""Scene retrieval command (F10.2 CP5).

Earth Engine is replaced at two seams — `search_scenes` and
`download_clipped_geotiff` — and nothing else is faked. Everything downstream
of those two calls is the real thing: real rasterio, real rio-cogeo, real
PostGIS. That is deliberate. The failures worth catching here are in the
translation, the storage layout, and the spatial assertion, not in a mock of
Google's API.

The load-bearing test is `test_footprint_outside_aoi_fails_the_query`. Every
other assertion here protects convenience; that one protects the claim that a
stored scene actually covers the ground it says it covers.
"""
import datetime as dt
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.marsabit import SITES_BY_CODE
from satellite_integration import gee_client
from satellite_integration.conftest import ELSEWHERE_BOUNDS, FOROLE_BOUNDS
from satellite_integration.management.commands import fetch_scenes
from satellite_integration.models import (
    SatelliteDataset,
    SatelliteImage,
    SatelliteQuery,
)

ASSET_ID = "COPERNICUS/S2_SR_HARMONIZED/20260118T073211_20260118T074530_T37PCP"


# ── fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def s2(db):
    return SatelliteDataset.objects.create(
        name="Sentinel-2 SR (test)",
        code="s2",
        provider=SatelliteDataset.Provider.ESA,
        gee_collection_id="COPERNICUS/S2_SR_HARMONIZED",
        cloud_property="CLOUDY_PIXEL_PERCENTAGE",
        resolution_m=10,
        temporal_resolution_days=5,
        bands=["B4", "B8"],
    )


@pytest.fixture
def s1(db):
    """A radar product: no cloud property at all."""
    return SatelliteDataset.objects.create(
        name="Sentinel-1 GRD (test)",
        code="s1",
        provider=SatelliteDataset.Provider.ESA,
        gee_collection_id="COPERNICUS/S1_GRD",
        cloud_property="",
        resolution_m=10,
        temporal_resolution_days=6,
        bands=["VV", "VH"],
    )


@pytest.fixture
def scene():
    from core.geo import polygon_from_bbox

    return gee_client.SceneMetadata(
        asset_id=ASSET_ID,
        acquisition_date=dt.datetime(2026, 1, 18, 7, 32, tzinfo=dt.timezone.utc),
        # Scene-level footprint: a whole S2 tile, far larger than what we clip.
        footprint=polygon_from_bbox(37.5, 3.0, 38.5, 4.0),
        cloud_cover_pct=4.2,
        bands=["B4", "B8"],
        properties={"MGRS_TILE": "37PCP", "SPACECRAFT_NAME": "Sentinel-2A"},
    )


@pytest.fixture
def fake_gee(monkeypatch, geotiff_bytes, scene):
    """Patch both Earth Engine seams and record what the command asked for."""
    calls = {"search": [], "download": []}

    def _search(**kwargs):
        calls["search"].append(kwargs)
        return calls.get("scenes", [scene])

    def _download(**kwargs):
        calls["download"].append(kwargs)
        return geotiff_bytes(bounds=calls.get("bounds", FOROLE_BOUNDS))

    monkeypatch.setattr(gee_client, "search_scenes", _search)
    monkeypatch.setattr(gee_client, "download_clipped_geotiff", _download)
    return calls


def run(*args):
    out = StringIO()
    call_command(
        "fetch_scenes",
        "--site", "forole",
        "--dataset", "s2",
        "--start", "2026-01-01",
        "--end", "2026-07-01",
        *args,
        stdout=out,
        stderr=out,
    )
    return out.getvalue()


# ── the AOI ──────────────────────────────────────────────────────────────


class TestBufferedAoi:

    def test_buffer_expands_the_site_bbox(self):
        bbox = SITES_BY_CODE["forole"]["bbox"]
        aoi = fetch_scenes.buffered_aoi(bbox, 500.0)
        west, south, east, north = aoi.extent

        assert west < bbox[0] and south < bbox[1]
        assert east > bbox[2] and north > bbox[3]
        assert aoi.srid == 4326

    def test_buffer_is_metric_not_degrees(self):
        """~500 m is ~0.0045 degrees of latitude, not 500 of anything."""
        aoi = fetch_scenes.buffered_aoi((37.0, 3.0, 37.001, 3.001), 500.0)
        _, south, _, north = aoi.extent

        assert north - 3.001 == pytest.approx(0.00452, abs=1e-4)
        assert 3.0 - south == pytest.approx(0.00452, abs=1e-4)

    def test_zero_buffer_is_the_bare_bbox(self):
        bbox = SITES_BY_CODE["forole"]["bbox"]
        assert fetch_scenes.buffered_aoi(bbox, 0).extent == pytest.approx(bbox)


# ── the happy path ───────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.geo
class TestRetrieval:

    def test_stores_a_scene_with_a_cog_on_disk(self, org, s2, fake_gee, media_root):
        run("--org", org.slug)

        query = SatelliteQuery.objects.get()
        image = SatelliteImage.objects.get()

        assert query.status == SatelliteQuery.Status.COMPLETE
        assert query.scene_count == 1
        assert query.completed_at is not None
        assert image.gee_asset_id == ASSET_ID
        assert image.dataset == s2
        assert image.cloud_cover_pct == pytest.approx(4.2)
        assert image.bands == ["B4", "B8"]
        assert image.properties["MGRS_TILE"] == "37PCP"
        assert image.downloaded_at is not None
        assert image.size_bytes > 0

        from satellite_integration.cog import absolute_cog_path
        assert absolute_cog_path(image.cog_path).exists()
        assert image.has_cog

    def test_footprint_is_the_clip_not_the_scene(self, org, s2, fake_gee, media_root):
        """The stored footprint must be what is on disk, not what GEE reported.

        The fixture scene claims a 1x1 degree tile; the raster covers ten
        thousandths of that. Storing the former would assert coverage over
        ground nobody downloaded.
        """
        run("--org", org.slug)
        image = SatelliteImage.objects.get()

        for actual, expected in zip(image.geometry.extent, FOROLE_BOUNDS):
            assert actual == pytest.approx(expected, abs=1e-5)

    def test_clips_to_the_queried_aoi(self, org, s2, fake_gee, media_root):
        run("--org", org.slug, "--buffer-m", "500")

        download = fake_gee["download"][0]
        query = SatelliteQuery.objects.get()

        assert download["geometry"].equals(query.geometry)
        assert download["bands"] == ["B4", "B8"]
        assert download["scale_m"] == 10

    def test_links_the_seeded_mission_when_one_exists(
        self, org, robot, s2, fake_gee, media_root
    ):
        from missions.models import Mission

        mission = Mission.objects.create(
            organization=org, robot=robot, name="Forole Hills foothills",
            metadata={"site_code": "forole"},
        )
        run("--org", org.slug)

        assert SatelliteQuery.objects.get().mission == mission

    def test_marks_the_dataset_verified(self, org, s2, fake_gee, media_root):
        assert s2.is_verified is False
        run("--org", org.slug)
        s2.refresh_from_db()

        assert s2.is_verified is True

    def test_tile_url_stays_empty_and_therefore_stale(
        self, org, s2, fake_gee, media_root
    ):
        """CP5 does not cache tile URLs. Anything reading one must see it stale."""
        run("--org", org.slug)
        image = SatelliteImage.objects.get()

        assert image.tile_url == ""
        assert image.tiles_are_stale() is True


# ── the assertion that matters ───────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.geo
class TestSpatialVerification:

    def test_footprint_outside_aoi_fails_the_query(
        self, org, s2, fake_gee, media_root
    ):
        """A raster that is not where it claims must never be persisted.

        This is the check that does not trust `filterBounds`. If GEE's filter,
        our clip region, or the CRS handling ever disagree, the row is rolled
        back and the query is FAILED rather than silently recording imagery
        over the wrong county.
        """
        fake_gee["bounds"] = ELSEWHERE_BOUNDS

        with pytest.raises(CommandError):
            run("--org", org.slug)

        query = SatelliteQuery.objects.get()
        assert query.status == SatelliteQuery.Status.FAILED
        assert query.scene_count == 0
        assert "does not intersect" in query.error_message
        assert not SatelliteImage.objects.exists()

    def test_intersection_holds_for_a_real_clip(self, org, s2, fake_gee, media_root):
        run("--org", org.slug)
        query = SatelliteQuery.objects.get()

        assert SatelliteImage.objects.filter(
            geometry__intersects=query.geometry
        ).count() == 1


# ── search outcomes ──────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.geo
class TestSearchOutcomes:

    def test_no_scenes_is_empty_not_failed(self, org, s2, fake_gee, media_root):
        fake_gee["scenes"] = []
        output = run("--org", org.slug)

        query = SatelliteQuery.objects.get()
        assert query.status == SatelliteQuery.Status.EMPTY
        assert query.scene_count == 0
        assert not SatelliteImage.objects.exists()
        assert "No scenes matched" in output

        s2.refresh_from_db()
        assert s2.is_verified is False, "nothing landed, nothing is verified"

    def test_gee_failure_records_the_reason(self, org, s2, monkeypatch, media_root):
        def _boom(**kwargs):
            raise gee_client.GEEQuotaError("EECU quota exhausted")

        monkeypatch.setattr(gee_client, "search_scenes", _boom)

        with pytest.raises(CommandError, match="quota"):
            run("--org", org.slug)

        query = SatelliteQuery.objects.get()
        assert query.status == SatelliteQuery.Status.FAILED
        assert "EECU quota exhausted" in query.error_message


# ── flags and guards ─────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.geo
class TestFlags:

    def test_dry_run_writes_nothing(self, org, s2, fake_gee, media_root):
        output = run("--org", org.slug, "--dry-run")

        assert not SatelliteQuery.objects.exists()
        assert not SatelliteImage.objects.exists()
        assert fake_gee["download"] == []
        assert list(media_root.rglob("*.tif")) == []
        assert "Nothing written" in output

    def test_existing_cog_is_reused_not_redownloaded(
        self, org, s2, fake_gee, media_root
    ):
        run("--org", org.slug)
        run("--org", org.slug)

        assert len(fake_gee["download"]) == 1, "the second run re-downloaded"
        assert SatelliteQuery.objects.count() == 2
        assert SatelliteImage.objects.count() == 2

    def test_overwrite_forces_a_redownload(self, org, s2, fake_gee, media_root):
        run("--org", org.slug)
        run("--org", org.slug, "--overwrite")

        assert len(fake_gee["download"]) == 2

    def test_cloud_filter_is_dropped_for_radar(self, org, s1, fake_gee, media_root):
        """Filtering on an absent property returns an empty collection.

        That looks exactly like "no scenes over this AOI", which is the most
        expensive kind of wrong answer: it sends you looking at the AOI.
        """
        out = StringIO()
        call_command(
            "fetch_scenes", "--site", "forole", "--dataset", "s1",
            "--start", "2026-01-01", "--end", "2026-07-01",
            "--max-cloud", "10", "--org", org.slug,
            stdout=out, stderr=out,
        )

        assert fake_gee["search"][0]["max_cloud"] is None
        assert SatelliteQuery.objects.get().max_cloud_pct is None
        assert "ignored" in out.getvalue()

    def test_cloud_filter_is_passed_through_for_optical(
        self, org, s2, fake_gee, media_root
    ):
        run("--org", org.slug, "--max-cloud", "10")

        assert fake_gee["search"][0]["max_cloud"] == 10
        assert fake_gee["search"][0]["cloud_property"] == "CLOUDY_PIXEL_PERCENTAGE"

    def test_limit_is_forwarded_to_the_search(self, org, s2, fake_gee, media_root):
        run("--org", org.slug, "--limit", "2")
        assert fake_gee["search"][0]["limit"] == 2

    def test_default_limit_is_conservative(self):
        """An exploratory run must not be able to spend an afternoon of quota."""
        assert fetch_scenes.DEFAULT_LIMIT <= 5


@pytest.mark.django_db
@pytest.mark.geo
class TestArgumentGuards:

    def test_unknown_site_lists_the_known_ones(self, org, s2, fake_gee, media_root):
        with pytest.raises(CommandError, match="forole"):
            call_command(
                "fetch_scenes", "--site", "atlantis", "--dataset", "s2",
                "--start", "2026-01-01", stdout=StringIO(),
            )

    def test_unknown_dataset_is_rejected(self, org, s2, fake_gee, media_root):
        with pytest.raises(CommandError, match="No active dataset"):
            call_command(
                "fetch_scenes", "--site", "forole", "--dataset", "landsat-99",
                "--start", "2026-01-01", stdout=StringIO(),
            )

    def test_end_before_start_is_rejected(self, org, s2, fake_gee, media_root):
        with pytest.raises(CommandError, match="must be after"):
            call_command(
                "fetch_scenes", "--site", "forole", "--dataset", "s2",
                "--start", "2026-07-01", "--end", "2026-01-01", stdout=StringIO(),
            )

    def test_malformed_date_is_rejected(self, org, s2, fake_gee, media_root):
        with pytest.raises(CommandError, match="YYYY-MM-DD"):
            call_command(
                "fetch_scenes", "--site", "forole", "--dataset", "s2",
                "--start", "18/01/2026", stdout=StringIO(),
            )

    def test_ambiguous_org_is_rejected(
        self, org, other_org, s2, fake_gee, media_root
    ):
        with pytest.raises(CommandError, match="--org is required"):
            run()

    def test_single_org_is_inferred(self, org, s2, fake_gee, media_root):
        run()
        assert SatelliteQuery.objects.get().organization == org


# ── size estimation ──────────────────────────────────────────────────────


class TestDownloadEstimate:
    """The 32 MB ceiling is a hard wall with an opaque error behind it.

    These assertions exist so the failure names the real problem — too much
    area, too fine a scale, too many bands — before a request is ever made.
    """

    def test_a_buffered_site_is_far_under_the_ceiling(self):
        aoi = fetch_scenes.buffered_aoi(SITES_BY_CODE["forole"]["bbox"], 500)
        estimate = gee_client.estimate_download_bytes(
            geometry=aoi, scale_m=10, band_count=7
        )

        assert estimate < gee_client.MAX_DOWNLOAD_BYTES / 10

    def test_a_county_sized_aoi_is_over_it(self):
        from core.geo import polygon_from_bbox

        marsabit = polygon_from_bbox(36.0, 1.5, 39.0, 4.5)
        estimate = gee_client.estimate_download_bytes(
            geometry=marsabit, scale_m=10, band_count=7
        )

        assert estimate > gee_client.MAX_DOWNLOAD_BYTES

    def test_estimate_scales_with_resolution(self):
        aoi = fetch_scenes.buffered_aoi(SITES_BY_CODE["forole"]["bbox"], 500)
        fine = gee_client.estimate_download_bytes(
            geometry=aoi, scale_m=10, band_count=1
        )
        coarse = gee_client.estimate_download_bytes(
            geometry=aoi, scale_m=30, band_count=1
        )

        assert fine > coarse * 8  # ~9x, allowing for ceil() at these sizes

@pytest.mark.django_db
class TestCloudProperty:
    """cloud_property is load-bearing and easy to lose.

    A blank value silently disables cloud filtering: `search_scenes` skips the
    filter entirely, every scene reports cloud n/a, and --max-cloud becomes a
    no-op that still looks like it worked. The catalog spec had the right
    values for months while the database rows were empty, because nothing
    asserted the two agreed.
    """

    def test_optical_products_carry_a_cloud_property(self):
        call_command("seed_datasets", stdout=StringIO())

        for code, expected in (
            ("s2", "CLOUDY_PIXEL_PERCENTAGE"),
            ("l5", "CLOUD_COVER"),
            ("l8", "CLOUD_COVER"),
            ("l9", "CLOUD_COVER"),
        ):
            dataset = SatelliteDataset.objects.get(code=code)
            assert dataset.cloud_property == expected, (
                f"{code} lost its cloud property — --max-cloud would silently "
                "do nothing"
            )

    def test_non_optical_products_deliberately_have_none(self):
        """Blank here is meaningful, not missing."""
        call_command("seed_datasets", stdout=StringIO())

        for code in ("s1", "chirps", "era5_land", "smap", "s5p_no2", "modis_lst"):
            assert SatelliteDataset.objects.get(code=code).cloud_property == ""

    def test_reseeding_repairs_a_blanked_row(self):
        """The exact drift that shipped: the row exists but the field is empty."""
        call_command("seed_datasets", stdout=StringIO())
        SatelliteDataset.objects.filter(code="s2").update(cloud_property="")

        call_command("seed_datasets", stdout=StringIO())

        assert SatelliteDataset.objects.get(code="s2").cloud_property == (
            "CLOUDY_PIXEL_PERCENTAGE"
        )
# ─── RANGER V3 END: fetch_scenes tests ───
