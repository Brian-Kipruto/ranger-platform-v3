# ─── RANGER V3 START: raster rendering ───
"""
Rendering COGs to PNG for browser display (F10.3 CP1).

Why PNG-from-our-own-COG, and not the two alternatives
------------------------------------------------------
GEE tile URLs expire after a few days. A demo built on them works today,
works tomorrow, and fails silently on the day that matters with no error
anywhere — which is why `SatelliteImage.tiles_are_stale()` exists.

A real XYZ tile server (rio-tiler / titiler) is the correct answer at scale
and badly overbuilt for 300 m sites: our two scenes are 112x119 px and
38x41 px. A whole new service to serve fourteen thousand pixels.

So: render the bands we already hold on disk into a PNG, cache it beside the
COG, and pin it to its bbox corners with MapLibre's ImageSource. Our COGs are
already EPSG:4326 (F10.2 CP5), so corner-pinning is geometrically exact with
no reprojection step.

The thing this module exists to prevent
---------------------------------------
A layer is NOT a name. It is a (dataset, layer) pair, because the SAME index
computed the SAME way is correct over one product and wrong over another.

Sentinel-2 SR Harmonized calibrates purely multiplicatively:

    rho = 1e-4 * DN

so in a normalised ratio the factor cancels exactly:

    NDVI = (1e-4*B8 - 1e-4*B4) / (1e-4*B8 + 1e-4*B4) = (B8-B4)/(B8+B4)

Landsat 9 Collection 2 Level 2 carries an ADDITIVE offset:

    rho = 2.75e-5 * DN - 0.2

and an offset does not cancel:

    NDVI = (2.75e-5*(B5-B4)) / (2.75e-5*(B5+B4) - 0.4)
                                                ^^^^^ survives

NDVI computed from raw Landsat DNs is not NDVI. It is a number between -1 and
1 that renders as a completely convincing image over a 38x41 px scene and is
wrong. Nothing downstream can detect it.

Hence: every registry entry declares its calibration, the renderer applies it
before any band math, and an unregistered (dataset, layer) pair is a 404 —
never a fallback to another product's recipe, which is exactly the mistake
above with extra steps.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ── errors ──────────────────────────────────────────────────────────


class RenderError(Exception):
    """Base for render failures."""


class UnknownLayer(RenderError):
    """No registry entry for this (dataset, layer) pair."""


class MissingBands(RenderError):
    """The scene on disk lacks a band the layer needs."""


# ── calibration ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class Calibration:
    """DN -> physical units.

    `offset` is the entire reason this class exists rather than a float.
    A purely multiplicative calibration cancels in a normalised ratio; an
    additive one does not. Storing the two together, per dataset, is what
    makes the difference impossible to forget at the call site.
    """

    scale: float
    offset: float = 0.0

    @property
    def cancels_in_a_ratio(self) -> bool:
        """True when (a*x - a*y)/(a*x + a*y) == (x-y)/(x+y)."""
        return self.offset == 0.0

    def apply(self, array):
        return array * self.scale + self.offset


# Sentinel-2 SR Harmonized. The "harmonized" collection shifts post-2022-01-25
# scenes back into the pre-2022 range, which is why there is no offset here —
# on the UNharmonized collection there would be, and this would be a different
# number. Do not copy this entry to another S2 collection without checking.
S2_SR = Calibration(scale=1e-4)

# Landsat Collection 2 Level 2 surface reflectance.
L9_SR = Calibration(scale=2.75e-5, offset=-0.2)

# Landsat Collection 2 Level 2 surface temperature -> Kelvin.
L9_ST = Calibration(scale=3.41802e-3, offset=149.0)


# ── layers ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Layer:
    """One renderable layer for one dataset."""

    key: str
    label: str
    bands: tuple[str, ...]
    kind: str  # "rgb" | "index" | "scalar"
    calibration: Calibration | None = None
    #: Applied before band math. False ONLY where the maths provably cancels
    #: it — and then `calibration` documents what was cancelled rather than
    #: being left None, so the claim is auditable.
    apply_calibration: bool = True
    #: Shown under the panel. Says what the number IS and what it is not.
    caption: str = ""
    #: Display range for index/scalar layers, after any calibration.
    domain: tuple[float, float] = (-1.0, 1.0)
    units: str = ""
    palette: str = "rdylgn"
    notes: tuple[str, ...] = field(default_factory=tuple)


#: (dataset_code, layer_key) -> Layer.
#:
#: Keyed on the PAIR. There is no dataset-agnostic "ndvi" and there must not
#: be one; see the module docstring.
LAYERS: dict[tuple[str, str], Layer] = {
    # ── Sentinel-2 ──
    ("s2", "truecolor"): Layer(
        key="truecolor",
        label="True colour",
        bands=("B4", "B3", "B2"),
        kind="rgb",
        calibration=S2_SR,
        # A percentile stretch is a display transform. Applying the
        # reflectance scale first would change nothing a viewer can see and
        # would imply the output is calibrated reflectance. It is not.
        apply_calibration=False,
        caption=(
            "Sentinel-2 B4/B3/B2 · 2–98% display stretch · "
            "NOT calibrated reflectance"
        ),
    ),
    ("s2", "ndvi"): Layer(
        key="ndvi",
        label="NDVI",
        bands=("B8", "B4"),
        kind="index",
        calibration=S2_SR,
        # Correct from raw DN: S2 SR Harmonized is scale-only, so the factor
        # cancels exactly in the normalised ratio. Recorded rather than
        # omitted so the reasoning is visible next to the l9 entry below.
        apply_calibration=False,
        caption="(B8−B4)/(B8+B4) · normalised ratio, scale-invariant",
        domain=(-1.0, 1.0),
    ),
    ("s2", "bsi"): Layer(
        key="bsi",
        label="Bare soil",
        bands=("B11", "B4", "B8", "B2"),
        kind="index",
        calibration=S2_SR,
        apply_calibration=False,  # normalised ratio again
        caption=(
            "((B11+B4)−(B8+B2))/((B11+B4)+(B8+B2)) · surface brightness and "
            "dryness proxy · B11 resampled 20→10 m at download · "
            "NOT a salinity measurement"
        ),
        domain=(-1.0, 1.0),
        palette="bare",
        notes=(
            "No optical index measures salinity. BSI separates bright, dry, "
            "unvegetated surfaces from everything else; over the Chalbi that "
            "is the salt crust. 'Sentinel-2 salinity index' overclaims.",
        ),
    ),
    # ── Landsat 9 ──
    ("l9", "truecolor"): Layer(
        key="truecolor",
        label="True colour",
        bands=("SR_B4", "SR_B3", "SR_B2"),
        kind="rgb",
        calibration=L9_SR,
        apply_calibration=False,  # display stretch only
        caption=(
            "Landsat 9 SR_B4/B3/B2 · 2–98% display stretch · "
            "NOT calibrated reflectance"
        ),
    ),
    ("l9", "ndvi"): Layer(
        key="ndvi",
        label="NDVI",
        bands=("SR_B5", "SR_B4"),
        kind="index",
        calibration=L9_SR,
        # TRUE, and the single most important flag in this file. Landsat C2
        # L2 carries an additive offset, which does NOT cancel in a ratio.
        # Flip this to False and the layer still renders, still looks
        # plausible, and is wrong.
        apply_calibration=True,
        caption=(
            "(SR_B5−SR_B4)/(SR_B5+SR_B4) · Collection 2 scale AND offset "
            "applied before the ratio — the offset does not cancel"
        ),
        domain=(-1.0, 1.0),
    ),
    ("l9", "thermal"): Layer(
        key="thermal",
        label="Surface temp",
        bands=("ST_B10",),
        kind="scalar",
        calibration=L9_ST,
        apply_calibration=True,
        caption=(
            "Landsat ST_B10 · scale + offset applied · land SURFACE "
            "temperature, not air temperature"
        ),
        domain=(15.0, 55.0),
        units="°C",
        palette="thermal",
    ),
}


def layers_for(dataset_code: str) -> list[Layer]:
    """Every layer this dataset can render, in registry order."""
    return [
        layer
        for (code, _key), layer in LAYERS.items()
        if code == dataset_code
    ]


def get_layer(dataset_code: str, layer_key: str) -> Layer:
    try:
        return LAYERS[(dataset_code, layer_key)]
    except KeyError:
        valid = sorted(l.key for l in layers_for(dataset_code))
        raise UnknownLayer(
            f"No layer {layer_key!r} for dataset {dataset_code!r}. "
            f"Available: {', '.join(valid) if valid else 'none'}."
        ) from None


# ── rendering ───────────────────────────────────────────────────────


def _band_index(available: list[str], name: str) -> int:
    """1-based rasterio band index for a NAMED band.

    By name, never by position. A band-order change under positional indexing
    produces wrong colours that look like a rendering preference rather than
    a bug — and F10.2 CP5 stamps the names into the file precisely so this
    lookup is possible.
    """
    try:
        return available.index(name) + 1
    except ValueError:
        raise MissingBands(
            f"Band {name!r} is not in this scene (has: "
            f"{', '.join(available) or 'none'})."
        ) from None


def _stretch(array, lo_pct=2.0, hi_pct=98.0):
    """Percentile stretch to 0-255, ignoring nodata."""
    import numpy as np

    valid = array[np.isfinite(array)]
    if valid.size == 0:
        return np.zeros(array.shape, dtype="uint8")
    lo, hi = np.percentile(valid, [lo_pct, hi_pct])
    if hi <= lo:
        hi = lo + 1.0
    scaled = (array - lo) / (hi - lo)
    return (np.clip(scaled, 0.0, 1.0) * 255).astype("uint8")


def _ramp(array, domain, palette):
    """Map a scalar field onto an RGB ramp. Returns (h, w, 3) uint8."""
    import numpy as np

    lo, hi = domain
    t = np.clip((array - lo) / (hi - lo if hi > lo else 1.0), 0.0, 1.0)

    if palette == "thermal":
        stops = [(0.0, (8, 24, 92)), (0.5, (222, 96, 40)), (1.0, (255, 244, 190))]
    elif palette == "bare":
        stops = [(0.0, (26, 62, 34)), (0.5, (196, 172, 120)), (1.0, (250, 248, 240))]
    else:  # rdylgn — the NDVI default
        stops = [(0.0, (166, 54, 42)), (0.5, (246, 232, 160)), (1.0, (26, 122, 52))]

    out = np.zeros(t.shape + (3,), dtype="float64")
    for channel in range(3):
        out[..., channel] = np.interp(
            t, [s[0] for s in stops], [s[1][channel] for s in stops]
        )
    return out.astype("uint8")


def render_png(cog_path: Path, layer: Layer, dest: Path) -> Path:
    """Render one layer of a COG to an RGBA PNG at `dest`.

    Nodata becomes alpha 0 rather than black: an opaque rectangle painted
    over the basemap outside the clip reads as data.

    Written atomically (temp file + os.replace), the same discipline cog.py
    uses — a half-written cache file is indistinguishable from a valid one on
    the next request.
    """
    import numpy as np
    import rasterio
    from PIL import Image

    with rasterio.open(cog_path) as src:
        available = [
            (src.descriptions[i] or f"band{i + 1}") for i in range(src.count)
        ]
        indexes = [_band_index(available, name) for name in layer.bands]
        raw = src.read(indexes, masked=True).astype("float64")

    valid = ~np.ma.getmaskarray(raw).any(axis=0)
    data = np.ma.filled(raw, np.nan)

    if layer.apply_calibration and layer.calibration is not None:
        data = layer.calibration.apply(data)

    if layer.kind == "rgb":
        rgb = np.dstack([_stretch(data[i]) for i in range(3)])
    elif layer.kind == "index":
        with np.errstate(invalid="ignore", divide="ignore"):
            if len(layer.bands) == 2:
                a, b = data[0], data[1]
                index = (a - b) / (a + b)
            else:
                # BSI: ((B11+B4) - (B8+B2)) / ((B11+B4) + (B8+B2))
                swir_red = data[0] + data[1]
                nir_blue = data[2] + data[3]
                index = (swir_red - nir_blue) / (swir_red + nir_blue)
        valid &= np.isfinite(index)
        rgb = _ramp(np.nan_to_num(index), layer.domain, layer.palette)
    else:  # scalar
        scalar = data[0]
        if layer.units == "°C":
            scalar = scalar - 273.15  # Kelvin -> Celsius, for display only
        valid &= np.isfinite(scalar)
        rgb = _ramp(np.nan_to_num(scalar), layer.domain, layer.palette)

    alpha = (valid * 255).astype("uint8")
    rgba = np.dstack([rgb, alpha])

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    Image.fromarray(rgba, mode="RGBA").save(tmp, format="PNG", optimize=True)
    os.replace(tmp, dest)
    return dest


def cache_path(cog_path: Path, layer_key: str) -> Path:
    """Where the rendered PNG lives: beside the COG, one per layer."""
    return cog_path.with_suffix(f".{layer_key}.png")


def cached_or_render(cog_path: Path, layer: Layer) -> Path:
    """Return a current PNG for this layer, rendering only if needed.

    Staleness is by mtime against the COG. Re-downloading a scene with
    --overwrite must invalidate every derived PNG, or the map keeps showing
    the old pixels with the new metadata beside them.
    """
    dest = cache_path(cog_path, layer.key)
    if dest.exists() and dest.stat().st_mtime >= cog_path.stat().st_mtime:
        return dest
    return render_png(cog_path, layer, dest)
# ─── RANGER V3 END: raster rendering ───
