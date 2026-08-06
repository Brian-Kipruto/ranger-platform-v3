# ─── RANGER V3 START: satellite api tests ───
"""
Satellite EO read endpoints (F10.2 CP6).

The centrepiece is TestTenancy. SatelliteImage has no organization field —
it inherits one through its query — and that indirection is exactly the kind
of thing that looks correct in a code review and leaks in production. Every
endpoint is asserted from a second tenant's session, and every one must come
back empty or 404.

The other assertions worth reading are TestLeakage (cog_path must never reach
a client) and TestProvenanceFields (the SITE/REGIONAL distinction must survive
serialization). Both protect claims rather than convenience.
"""
import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from core.geo import polygon_from_bbox
from satellite_integration.models import (
    SatelliteDataset,
    SatelliteImage,
    SatelliteQuery,
)

# Forole, buffered — the AOI fetch_scenes actually queries.
FOROLE_AOI = (37.9623, 3.71148, 37.9723, 3.72202)
FOROLE_FOOTPRINT = (37.96226, 3.71139, 37.97233, 3.72208)
# Nairobi: unambiguously outside the AOI, for bbox-filter assertions.
ELSEWHERE = (36.82, -1.295, 36.825, -1.29)


# ── fixtures ─────────────────────────────────────────────────────────────


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
        scale=SatelliteDataset.Scale.SITE,
        bands=["B4", "B8"],
        is_verified=True,
    )


@pytest.fixture
def smap(db):
    """A REGIONAL product: one pixel covers every survey site at once."""
    return SatelliteDataset.objects.create(
        name="SMAP L4 (test)",
        code="smap",
        provider=SatelliteDataset.Provider.NASA,
        gee_collection_id="NASA/SMAP/SPL4SMGP/007",
        cloud_property="",
        resolution_m=11000,
        temporal_resolution_days=3,
        scale=SatelliteDataset.Scale.REGIONAL,
        bands=["sm_surface"],
    )


@pytest.fixture
def retired(db):
    return SatelliteDataset.objects.create(
        name="Retired product",
        code="old",
        provider=SatelliteDataset.Provider.USGS,
        gee_collection_id="FAKE/RETIRED",
        resolution_m=30,
        temporal_resolution_days=16,
        is_active=False,
    )


@pytest.fixture
def make_scene(db):
    """Factory: a COMPLETE query with one image, for a given org."""
    def _make(organization, dataset, *, footprint=FOROLE_FOOTPRINT,
              asset_id="COPERNICUS/S2_SR_HARMONIZED/TEST", acquired=None,
              cog_path="knra/s2/test.tif"):
        query = SatelliteQuery.objects.create(
            organization=organization,
            dataset=dataset,
            geometry=polygon_from_bbox(*FOROLE_AOI),
            label="forole-s2-202601",
            start_date=dt.date(2026, 1, 1),
            end_date=dt.date(2026, 7, 1),
            max_cloud_pct=20,
            status=SatelliteQuery.Status.COMPLETE,
            scene_count=1,
        )
        image = SatelliteImage.objects.create(
            query=query,
            dataset=dataset,
            gee_asset_id=asset_id,
            acquisition_date=acquired or dt.datetime(
                2026, 1, 18, 7, 32, tzinfo=dt.timezone.utc
            ),
            cloud_cover_pct=4.2,
            geometry=polygon_from_bbox(*footprint),
            cog_path=cog_path,
            size_bytes=123813,
            bands=["B4", "B8"],
            properties={"MGRS_TILE": "37NCE"},
        )
        return query, image
    return _make


@pytest.fixture
def other_client(db, other_org):
    """An authenticated session belonging to the SECOND tenant."""
    user = get_user_model().objects.create_user(
        username="other-tenant-user",
        password="OtherPassword1234!",
        organization=other_org,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ── catalog ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestDatasetCatalog:

    def test_lists_active_datasets(self, authed_client, s2, smap):
        response = authed_client.get(reverse("satellite-dataset-list"))

        assert response.status_code == 200
        assert {d["code"] for d in response.data} == {"s2", "smap"}

    def test_inactive_are_hidden_but_retrievable(self, authed_client, s2, retired):
        url = reverse("satellite-dataset-list")

        assert {d["code"] for d in authed_client.get(url).data} == {"s2"}
        assert {
            d["code"] for d in authed_client.get(url, {"include_inactive": "true"}).data
        } == {"s2", "old"}

    def test_catalog_is_global_not_tenant_scoped(self, authed_client, other_client, s2):
        """Sentinel-2 is Sentinel-2 for everyone.

        The catalog is reference data like SensorType. Scoping it per-org
        would imply each tenant has a private view of the sky.
        """
        url = reverse("satellite-dataset-list")
        mine = {d["code"] for d in authed_client.get(url).data}
        theirs = {d["code"] for d in other_client.get(url).data}

        assert mine == theirs == {"s2"}

    def test_verified_filter(self, authed_client, s2, smap):
        url = reverse("satellite-dataset-list")

        verified = authed_client.get(url, {"verified": "true"}).data
        unverified = authed_client.get(url, {"verified": "false"}).data

        assert [d["code"] for d in verified] == ["s2"]
        assert [d["code"] for d in unverified] == ["smap"]

    def test_cloud_filter_is_exposed_as_a_boolean(self, authed_client, s2, smap):
        """The client needs to know not to offer a cloud slider for radar.

        It does not need the property NAME — that is a GEE implementation
        detail, and exposing it would invite a client to send it back.
        """
        by_code = {
            d["code"]: d for d in authed_client.get(reverse("satellite-dataset-list")).data
        }

        assert by_code["s2"]["has_cloud_filter"] is True
        assert by_code["smap"]["has_cloud_filter"] is False
        assert "cloud_property" not in by_code["s2"]


# ── tenancy ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.geo
class TestTenancy:
    """SatelliteImage has no organization field. Prove the indirection holds."""

    def test_queries_are_org_scoped(self, authed_client, other_client, org, s2, make_scene):
        make_scene(org, s2)
        url = reverse("satellite-query-list")

        assert authed_client.get(url).data["count"] == 1
        assert other_client.get(url).data["count"] == 0

    def test_images_scope_through_their_query(
        self, authed_client, other_client, org, s2, make_scene
    ):
        make_scene(org, s2)
        url = reverse("satellite-image-list")

        assert authed_client.get(url).data["count"] == 1
        assert other_client.get(url).data["count"] == 0

    def test_coverage_is_org_scoped(self, authed_client, other_client, org, s2, make_scene):
        make_scene(org, s2)
        url = reverse("satellite-coverage")

        assert len(authed_client.get(url).data["features"]) == 1
        assert other_client.get(url).data["features"] == []

    def test_another_tenants_query_404s_rather_than_403s(
        self, other_client, org, s2, make_scene
    ):
        """404, not 403: a 403 confirms the id exists."""
        query, _ = make_scene(org, s2)

        assert other_client.get(
            reverse("satellite-query-detail", args=[query.pk])
        ).status_code == 404

    def test_another_tenants_image_404s(self, other_client, org, s2, make_scene):
        _, image = make_scene(org, s2)

        assert other_client.get(
            reverse("satellite-image-detail", args=[image.pk])
        ).status_code == 404

    def test_a_user_with_no_org_sees_nothing(self, api_client, org, s2, make_scene):
        """Not everything. A misconfigured account must not gain god-mode."""
        make_scene(org, s2)
        orphan = get_user_model().objects.create_user(
            username="orphan", password="OrphanPassword1234!", organization=None
        )
        api_client.force_authenticate(user=orphan)

        assert api_client.get(reverse("satellite-image-list")).data["count"] == 0
        assert api_client.get(reverse("satellite-query-list")).data["count"] == 0

    def test_endpoints_require_authentication(self, api_client, org, s2, make_scene):
        make_scene(org, s2)

        for name in (
            "satellite-dataset-list",
            "satellite-query-list",
            "satellite-image-list",
            "satellite-coverage",
        ):
            assert api_client.get(reverse(name)).status_code in (401, 403), name


# ── what must not leak ───────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.geo
class TestLeakage:

    def test_cog_path_is_never_serialized(self, authed_client, org, s2, make_scene):
        """A filesystem path is not a URL.

        Emitting it invites a client to fetch /media/satellite/<org>/... and
        read another tenant's rasters straight off disk, bypassing every
        queryset in this module.
        """
        _, image = make_scene(org, s2)

        for payload in (
            authed_client.get(reverse("satellite-image-list")).data["results"][0],
            authed_client.get(reverse("satellite-image-detail", args=[image.pk])).data,
        ):
            assert "cog_path" not in payload
            assert "knra/s2/test.tif" not in str(payload)

    def test_has_cog_is_exposed_instead(self, authed_client, org, s2, make_scene):
        _, image = make_scene(org, s2)
        payload = authed_client.get(
            reverse("satellite-image-detail", args=[image.pk])
        ).data

        assert payload["has_cog"] is True
        assert payload["size_bytes"] == 123813


@pytest.mark.django_db
@pytest.mark.geo
class TestProvenanceFields:
    """SITE vs REGIONAL must survive the API boundary.

    The distinction is what separates "Sentinel-2 resolves this 300 m site"
    from "one SMAP pixel covers the whole county". A frontend should have to
    ignore a field to get this wrong.
    """

    def test_scale_rides_on_every_image(self, authed_client, org, s2, smap, make_scene):
        make_scene(org, s2)
        make_scene(org, smap, asset_id="NASA/SMAP/TEST")

        by_dataset = {
            i["dataset_code"]: i
            for i in authed_client.get(reverse("satellite-image-list")).data["results"]
        }

        assert by_dataset["s2"]["scale"] == "SITE"
        assert by_dataset["smap"]["scale"] == "REGIONAL"
        assert by_dataset["smap"]["resolution_m"] == 11000

    def test_scale_rides_on_coverage_features(self, authed_client, org, smap, make_scene):
        make_scene(org, smap, asset_id="NASA/SMAP/TEST")
        feature = authed_client.get(reverse("satellite-coverage")).data["features"][0]

        assert feature["properties"]["scale"] == "REGIONAL"

    def test_tile_staleness_is_visible(self, authed_client, org, s2, make_scene):
        """No cached tile URL means stale — not "no imagery"."""
        _, image = make_scene(org, s2)
        payload = authed_client.get(
            reverse("satellite-image-detail", args=[image.pk])
        ).data

        assert payload["tiles_stale"] is True


# ── filters ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.geo
class TestImageFilters:

    def test_filter_by_dataset_code(self, authed_client, org, s2, smap, make_scene):
        make_scene(org, s2)
        make_scene(org, smap, asset_id="NASA/SMAP/TEST")
        url = reverse("satellite-image-list")

        assert authed_client.get(url, {"dataset": "s2"}).data["count"] == 1
        assert authed_client.get(url, {"dataset": "nonsense"}).data["count"] == 0

    def test_filter_by_acquisition_date(self, authed_client, org, s2, make_scene):
        make_scene(org, s2)
        url = reverse("satellite-image-list")

        assert authed_client.get(url, {"date_start": "2026-01-01"}).data["count"] == 1
        assert authed_client.get(url, {"date_start": "2026-06-01"}).data["count"] == 0
        # The scene's own day must match an inclusive end bound.
        assert authed_client.get(url, {"date_end": "2026-01-18"}).data["count"] == 1

    def test_bbox_intersection(self, authed_client, org, s2, make_scene):
        make_scene(org, s2)
        url = reverse("satellite-image-list")

        assert authed_client.get(
            url, {"bbox": "37.96,3.71,37.98,3.73"}
        ).data["count"] == 1
        assert authed_client.get(
            url, {"bbox": "36.80,-1.30,36.83,-1.28"}
        ).data["count"] == 0

    def test_malformed_bbox_returns_nothing_not_everything(
        self, authed_client, org, s2, make_scene
    ):
        """A dropped spatial filter would show imagery from somewhere the user
        did not ask about, on a map, looking authoritative.

        Unlike the date filters, which ignore bad input, this fails closed.
        """
        make_scene(org, s2)
        url = reverse("satellite-image-list")

        for bad in ("nonsense", "1,2,3", "37.98,3.73,37.96,3.71", "a,b,c,d"):
            response = authed_client.get(url, {"bbox": bad})
            assert response.status_code == 200, bad
            assert response.data["count"] == 0, bad

    def test_bad_query_id_is_empty_not_a_500(self, authed_client, org, s2, make_scene):
        make_scene(org, s2)
        response = authed_client.get(reverse("satellite-image-list"), {"query": "abc"})

        assert response.status_code == 200
        assert response.data["count"] == 0


# ── shapes ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.geo
class TestPayloadShapes:

    def test_query_detail_nests_its_images(self, authed_client, org, s2, make_scene):
        query, image = make_scene(org, s2)
        payload = authed_client.get(
            reverse("satellite-query-detail", args=[query.pk])
        ).data

        assert payload["dataset_code"] == "s2"
        assert payload["image_count"] == 1
        assert len(payload["images"]) == 1
        assert payload["images"][0]["gee_asset_id"] == image.gee_asset_id

    def test_bbox_is_west_south_east_north(self, authed_client, org, s2, make_scene):
        """The order MapLibre's ImageSource and every bounds check expect."""
        _, image = make_scene(org, s2)
        bbox = authed_client.get(
            reverse("satellite-image-detail", args=[image.pk])
        ).data["bbox"]

        west, south, east, north = bbox
        assert west < east and south < north
        assert west == pytest.approx(FOROLE_FOOTPRINT[0], abs=1e-5)
        assert north == pytest.approx(FOROLE_FOOTPRINT[3], abs=1e-5)

    def test_coverage_emits_real_polygons(self, authed_client, org, s2, make_scene):
        make_scene(org, s2)
        payload = authed_client.get(reverse("satellite-coverage")).data

        assert payload["type"] == "FeatureCollection"
        feature = payload["features"][0]
        assert feature["geometry"]["type"] == "Polygon"
        # GeoJSON rings are [lng, lat] — which is PostGIS (x, y), no flip.
        lng, lat = feature["geometry"]["coordinates"][0][0]
        assert 37 < lng < 38 and 3 < lat < 4

    def test_image_count_reflects_reality_not_the_stored_count(
        self, authed_client, org, s2, make_scene
    ):
        """scene_count is what the run reported; image_count is what survived."""
        query, image = make_scene(org, s2)
        image.delete()
        payload = authed_client.get(reverse("satellite-query-list")).data["results"][0]

        assert payload["scene_count"] == 1
        assert payload["image_count"] == 0

    def test_list_is_paginated(self, authed_client, org, s2, make_scene):
        make_scene(org, s2)
        payload = authed_client.get(reverse("satellite-image-list")).data

        assert set(payload) >= {"count", "next", "previous", "results"}
# ─── RANGER V3 END: satellite api tests ───
