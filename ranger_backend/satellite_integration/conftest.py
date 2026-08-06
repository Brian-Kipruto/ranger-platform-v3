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
# ─── RANGER V3 END: satellite test fixtures ───
