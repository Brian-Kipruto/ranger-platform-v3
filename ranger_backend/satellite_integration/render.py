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

import json
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
    #: PHYSICAL bounds for index/scalar layers, after calibration. Used to
    #: clamp, and as the fallback domain when a scene has too few valid
    #: pixels to derive percentiles from.
    domain: tuple[float, float] = (-1.0, 1.0)
    #: "percentile" stretches the ramp to what this SCENE actually contains;
    #: "absolute" pins it to `domain`.
    #:
    #: Percentile is the default because absolute was unreadable: NDVI over
    #: arid Marsabit occupies roughly 0.1-0.25 of a -1..1 ramp, so every
    #: pixel landed in the same two adjacent colours and the layer rendered
    #: as a flat wash — on a screen whose argument is that NDVI explains
    #: inter-site variance.
    #:
    #: The trade is real: a stretched ramp's colours mean something RELATIVE
    #: to one scene, not an absolute physical value, so the render MUST
    #: report the range it used and the UI MUST show it. An unlabelled
    #: stretched ramp implies absolute values it does not have. That is why
    #: render_png returns stats rather than just pixels.
    stretch: str = "percentile"
    #: Percentile clip, low and high.
    stretch_pct: tuple[float, float] = (2.0, 98.0)
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


def _percentiles(array, lo_pct, hi_pct):
    """(lo, hi) over finite values, or None if there are none."""
    import numpy as np

    valid = array[np.isfinite(array)]
    if valid.size == 0:
        return None
    lo, hi = (float(v) for v in np.percentile(valid, [lo_pct, hi_pct]))
    if hi <= lo:
        hi = lo + 1e-6
    return lo, hi


def _to_uint8(array, lo, hi):
    import numpy as np

    scaled = (array - lo) / (hi - lo if hi > lo else 1.0)
    return (np.clip(scaled, 0.0, 1.0) * 255).astype("uint8")


def _rgb_shared_stretch(data, lo_pct, hi_pct):
    """Stretch R, G and B against ONE shared range.

    Per-band independent stretching is the obvious implementation and it is
    wrong for low-contrast scenes: each band gets normalised to its own
    narrow range, which amplifies sensor noise into colour casts and destroys
    the relative band balance. Over arid Marsabit that turned a tan landscape
    into saturated blue and orange blocks — a true-colour layer that looks
    nothing like the ground beneath it costs more credibility than it buys.

    One range across all three preserves the balance between bands, which is
    what makes the result read as true colour.
    """
    import numpy as np

    stacked = np.concatenate([band[np.isfinite(band)].ravel() for band in data])
    if stacked.size == 0:
        return np.zeros(data[0].shape + (3,), dtype="uint8"), (0.0, 1.0)
    lo, hi = (float(v) for v in np.percentile(stacked, [lo_pct, hi_pct]))
    if hi <= lo:
        hi = lo + 1e-6
    return np.dstack([_to_uint8(data[i], lo, hi) for i in range(3)]), (lo, hi)


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


def render_png(cog_path: Path, layer: Layer, dest: Path) -> dict:
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

    lo_pct, hi_pct = layer.stretch_pct

    if layer.kind == "rgb":
        rgb, (display_lo, display_hi) = _rgb_shared_stretch(data, lo_pct, hi_pct)
        field = None
    else:
        if layer.kind == "index":
            with np.errstate(invalid="ignore", divide="ignore"):
                if len(layer.bands) == 2:
                    a, b = data[0], data[1]
                    field = (a - b) / (a + b)
                else:
                    # BSI: ((B11+B4) - (B8+B2)) / ((B11+B4) + (B8+B2))
                    swir_red = data[0] + data[1]
                    nir_blue = data[2] + data[3]
                    field = (swir_red - nir_blue) / (swir_red + nir_blue)
        else:  # scalar
            field = data[0]
            if layer.units == "°C":
                field = field - 273.15  # Kelvin -> Celsius, display only

        # Clamp to the layer's PHYSICAL bounds first. A division blowing up
        # near zero can produce values outside the index's definition, and a
        # single such pixel would drag the percentiles with it.
        field = np.clip(field, layer.domain[0], layer.domain[1])
        valid &= np.isfinite(field)

        if layer.stretch == "percentile":
            bounds = _percentiles(np.where(valid, field, np.nan), lo_pct, hi_pct)
            # Too few valid pixels to derive a range from — fall back to the
            # absolute domain rather than inventing one from noise.
            display_lo, display_hi = bounds if bounds else layer.domain
        else:
            display_lo, display_hi = layer.domain

        rgb = _ramp(
            np.nan_to_num(field), (display_lo, display_hi), layer.palette
        )

    alpha = (valid * 255).astype("uint8")
    rgba = np.dstack([rgb, alpha])

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    Image.fromarray(rgba, mode="RGBA").save(tmp, format="PNG", optimize=True)
    os.replace(tmp, dest)

    stats = _stats(
        layer, field, valid, display_lo, display_hi
    )
    _write_stats(dest, stats)
    return stats


def _stats(layer, field, valid, display_lo, display_hi) -> dict:
    """What the ramp actually means, for the legend.

    This travels with every render because a percentile-stretched ramp is
    only defensible if the range it used is on screen. Without these numbers
    the colours imply absolute values they do not carry.
    """
    import numpy as np

    valid_count = int(valid.sum())
    if field is not None and valid_count:
        observed = field[valid]
        data_min = float(np.nanmin(observed))
        data_max = float(np.nanmax(observed))
    else:
        data_min = data_max = None

    return {
        "layer": layer.key,
        "kind": layer.kind,
        "units": layer.units,
        "palette": layer.palette,
        "stretch": layer.stretch,
        "stretch_pct": list(layer.stretch_pct),
        "display_min": round(display_lo, 6),
        "display_max": round(display_hi, 6),
        "data_min": round(data_min, 6) if data_min is not None else None,
        "data_max": round(data_max, 6) if data_max is not None else None,
        "valid_px": valid_count,
    }


def _stats_path(png: Path) -> Path:
    return png.with_suffix(png.suffix + ".json")


def _write_stats(png: Path, stats: dict) -> None:
    path = _stats_path(png)
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(json.dumps(stats), encoding="utf-8")
    os.replace(tmp, path)


def cache_path(cog_path: Path, layer_key: str) -> Path:
    """Where the rendered PNG lives: beside the COG, one per layer."""
    return cog_path.with_suffix(f".{layer_key}.png")


def cached_or_render(cog_path: Path, layer: Layer) -> tuple[Path, dict]:
    """Return a current PNG for this layer AND its stats, rendering if needed.

    Staleness is by mtime against the COG. Re-downloading a scene with
    --overwrite must invalidate every derived PNG, or the map keeps showing
    the old pixels with the new metadata beside them.

    Stats are cached in a sidecar next to the PNG. Without that, a cache hit
    could serve pixels but not the range they were stretched to — and the
    legend would go blank on exactly the second view onwards. A missing or
    unreadable sidecar forces a re-render rather than serving unlabelled
    pixels.
    """
    dest = cache_path(cog_path, layer.key)
    stats_file = _stats_path(dest)
    fresh = dest.exists() and dest.stat().st_mtime >= cog_path.stat().st_mtime
    if fresh and stats_file.exists():
        try:
            return dest, json.loads(stats_file.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass  # corrupt sidecar — re-render rather than serve unlabelled
    return dest, render_png(cog_path, layer, dest)
# ─── RANGER V3 END: raster rendering ───