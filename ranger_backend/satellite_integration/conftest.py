# ─── RANGER V3 START: satellite test fixtures ───
"""Fixtures for the COG and retrieval tests (F10.2 CP5).

App-local rather than in the project conftest, deliberately: the factory below
imports rasterio, and rasterio drags a bundled GDAL in with it. Putting that
import in `ranger_backend/conftest.py` would make every test in the repo —
including the ones that never touch a raster — pay for it at collection time,
and would make the whole suite uncollectable on a machine where the raster
wheels failed to install.

The import lives inside the factory function for the same reason: collecting
this module must not require rasterio, only calling the fixture must.
"""
import pytest

# Forole, the survey's anomaly site. Tests use real coordinates so a failure
# reads as a place rather than as arbitrary numbers.
FOROLE_BOUNDS = (37.9668, 3.7160, 37.9678, 3.7175)
# Somewhere unambiguously else, for the "footprint is not where it claims"
# assertion. Nairobi is ~500 km south-west.
ELSEWHERE_BOUNDS = (36.8200, -1.2950, 36.8250, -1.2900)


@pytest.fixture
def geotiff_bytes():
    """Factory: an in-memory GeoTIFF with real georeferencing.

    Usage:
        raw = geotiff_bytes()                                  # Forole, 2 bands
        raw = geotiff_bytes(bounds=ELSEWHERE_BOUNDS)
        raw = geotiff_bytes(crs="EPSG:32637", bounds=(383000, 410000, ...))

    Returns raw bytes, matching what `download_clipped_geotiff` hands back, so
    the tests exercise the same entry point production does.
    """
    def _make(
        bounds=FOROLE_BOUNDS,
        *,
        width=64,
        height=64,
        band_names=("B4", "B8"),
        crs="EPSG:4326",
        dtype="int16",
    ):
        import numpy as np
        from rasterio.io import MemoryFile
        from rasterio.transform import from_bounds

        count = len(band_names)
        # Deterministic, non-constant values: a constant raster would let a
        # band-ordering bug pass unnoticed.
        data = np.arange(count * height * width, dtype=dtype).reshape(
            count, height, width
        )
        profile = {
            "driver": "GTiff",
            "width": width,
            "height": height,
            "count": count,
            "dtype": dtype,
            "crs": crs,
            "transform": from_bounds(*bounds, width, height),
        }
        with MemoryFile() as memfile:
            with memfile.open(**profile) as dst:
                dst.write(data)
                dst.descriptions = tuple(band_names)
            return memfile.read()

    return _make

# ── shared scene fixtures (promoted here in F10.3 CP1) ───────────────
# These were local to test_api.py until test_render.py needed them too.
# test_api.py still defines its own copies, which SHADOW these inside that
# module — so it is unaffected, and the promotion carries no risk to the
# existing suite. Delete the local copies when someone is next in there.

FOROLE_AOI = (37.9623, 3.71148, 37.9723, 3.72202)
FOROLE_FOOTPRINT = (37.96226, 3.71139, 37.97233, 3.72208)


@pytest.fixture
def s2(db):
    from satellite_integration.models import SatelliteDataset

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
def l9(db):
    """Landsat 9 C02 L2 — the product whose calibration carries an offset."""
    from satellite_integration.models import SatelliteDataset

    return SatelliteDataset.objects.create(
        name="Landsat 9 C02 L2 (test)",
        code="l9",
        provider=SatelliteDataset.Provider.USGS,
        gee_collection_id="LANDSAT/LC09/C02/T1_L2",
        cloud_property="CLOUD_COVER",
        resolution_m=30,
        temporal_resolution_days=16,
        scale=SatelliteDataset.Scale.SITE,
        bands=["SR_B4", "SR_B5", "ST_B10"],
        is_verified=True,
    )


@pytest.fixture
def make_scene(db):
    """Factory: a COMPLETE query with one image, for a given org."""
    import datetime as dt

    from core.geo import polygon_from_bbox
    from satellite_integration.models import SatelliteImage, SatelliteQuery

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
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    user = get_user_model().objects.create_user(
        username="other-tenant-render-user",
        password="OtherPassword1234!",
        organization=other_org,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client

# ─── RANGER V3 END: satellite test fixtures ───