# ─── RANGER V3 START: 16-report-map ───
"""Report tests reuse the satellite scene fixtures rather than copying them.

Re-exported, not redefined: one definition of a test scene in the repo. The
rasterio import stays inside those factories, so collecting this module does
not load GDAL.
"""
from satellite_integration.conftest import (  # noqa: F401
    FOROLE_FOOTPRINT,
    geotiff_bytes,
    l9,
    make_scene,
    s2,
)
# ─── RANGER V3 END: 16-report-map ───
