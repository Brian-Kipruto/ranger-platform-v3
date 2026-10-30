# ─── RANGER V3 START: 16-report-map ───
"""
Survey map figures for the compliance report (F16 fork 6). Offline, Pillow
only: no tiles, no network, no new dependency.

Two panels
----------
CONTEXT  The mission's own Sentinel-2/Landsat true-colour scene, rendered by
         the F10.3 path (render.cached_or_render) from the COG on disk, with
         the survey area outlined. Omitted, with the reason stated, when the
         mission has no scene with a readable COG.
DETAIL   The survey area itself on a plain background: graticule, scale bar,
         readings coloured by value. A site is ~110 m across, which is 11
         Sentinel-2 pixels: imagery under 2,000 points would say nothing and
         look like a render bug, so the detail panel has none.

Honesty rules
-------------
* A track line is drawn ONLY when no position is MODELLED. Modelled
  positions are placed inside the site to match published statistics; they
  have no sequence, and a line through them in time order is a scribble that
  looks like a route.
* Geometry is drawn in a local equirectangular projection scaled by
  cos(latitude), so a metre is the same length on both axes. At Marsabit
  (3.7 N) that changes almost nothing; at Rabat (34 N) skipping it would
  stretch every map 20% east-west.
* Captions and legends live in the report's HTML, not baked into pixels.
  This module returns pixels plus the facts the caption must state.
"""
from __future__ import annotations

import io
import logging
import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from core.models import SensorLog

log = logging.getLogger(__name__)

M_PER_DEG = 111_320.0          # metres per degree of latitude (and of
                               # longitude at the equator)
DETAIL_BOX = (1800, 1150)      # max pixel box for the detail panel
CONTEXT_BOX = (1100, 1100)     # max pixel box for the context panel
CONTEXT_K = 1.7                # overlay scale on the context panel, which
                               # prints at ~70 mm for ~1100 px
PAD_FRACTION = 0.12            # margin around the survey extent
MIN_SPAN_M = 40.0              # a single point still gets a readable frame

# Readings the detail panel can colour by, in preference order:
# (kind, row column, label, unit, decimals)
COLOUR_BY = [
    ("radiation", "dose_rate_usvh", "Dose rate", "µSv/h", 4),
    # CPM before PM: a radiation survey with an uncalibrated tube (dose rate
    # null by design) should still be mapped by radiation. Never MODELLED
    # CPM, which is back-calculated (stats rule 4).
    ("radiation", "cpm", "Count rate", "CPM", 1),
    ("air_quality", "pm25", "PM2.5", "µg/m³", 1),
]
NOT_COLOURED = {("cpm", SensorLog.Source.MODELLED.value)}

# The track is broken between consecutive fixes that imply an impossible
# move. A rover does not cross 500 m in a second; a line drawn across that
# jump is a route that never happened.
#
# 20 m/s (72 km/h): no ground rover gets near it, and a GPS teleport is
# hundreds of metres. 5 m/s was tried first and broke a simulated track 179
# times — nmea_sim's route walker covers 5-12 m per 1 Hz fix on some legs.
BREAK_SPEED_MS = 20.0
BREAK_GAP_S = 30.0

# Colour stretch percentiles. Survey dose data is right-skewed (Forole: mean
# 0.14, max 0.96 uSv/h): a P1-P99 stretch puts nearly every point in the
# bottom colour. P5-P95 spreads the bulk and saturates the high tail, which is
# where the story is. The legend states the clip; the stats table holds the
# true range.
CLIP_PCT = (5, 95)

# Perceptually ordered ramp (viridis stops). Low = dark blue, high = yellow.
RAMP = [(68, 1, 84), (59, 82, 139), (33, 145, 140), (94, 201, 98), (253, 231, 37)]

# Attribution the imagery licences require, by dataset code.
ATTRIBUTION = {
    "s2": "Contains modified Copernicus Sentinel data {year}",
    "l9": "Landsat imagery courtesy of the U.S. Geological Survey",
}

INK = (30, 30, 30)
GRID = (205, 205, 205)
OUTLINE = (255, 0, 200)        # survey-area outline on imagery: magenta
                               # reads on both tan desert and green


@dataclass
class Figure:
    png: bytes | None = None
    width: int = 0
    height: int = 0
    omitted: str | None = None         # reason, printed in place of the figure
    meta: dict = field(default_factory=dict)


# ── geometry ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Extent:
    west: float
    south: float
    east: float
    north: float

    @property
    def lat_mid(self) -> float:
        return (self.south + self.north) / 2

    @property
    def kx(self) -> float:
        """Metres per degree of longitude here."""
        return M_PER_DEG * math.cos(math.radians(self.lat_mid))

    @property
    def width_m(self) -> float:
        return (self.east - self.west) * self.kx

    @property
    def height_m(self) -> float:
        return (self.north - self.south) * M_PER_DEG

    def padded(self, fraction: float, min_span_m: float) -> "Extent":
        w = max(self.width_m, min_span_m)
        h = max(self.height_m, min_span_m)
        dx = (w * (1 + 2 * fraction)) / self.kx / 2
        dy = (h * (1 + 2 * fraction)) / M_PER_DEG / 2
        cx = (self.west + self.east) / 2
        cy = (self.south + self.north) / 2
        return Extent(cx - dx, cy - dy, cx + dx, cy + dy)

    def fit(self, box: tuple[int, int]) -> tuple[int, int]:
        """Largest pixel size inside `box` with equal metres per pixel on
        both axes."""
        bw, bh = box
        scale = min(bw / self.width_m, bh / self.height_m)
        return max(1, round(self.width_m * scale)), max(1, round(self.height_m * scale))

    def to_px(self, w: int, h: int, lon: float, lat: float) -> tuple[float, float]:
        x = (lon - self.west) / (self.east - self.west) * w
        y = (self.north - lat) / (self.north - self.south) * h
        return x, y


def bbox_of(lons, lats) -> Extent:
    return Extent(min(lons), min(lats), max(lons), max(lats))


def _nice(x: float) -> float:
    """1, 2 or 5 times a power of ten, <= x."""
    exp = math.floor(math.log10(x))
    for m in (5, 2, 1):
        if m * 10 ** exp <= x:
            return m * 10 ** exp
    return 10 ** exp


def _font(size: int):
    # Pillow >= 10.1 ships a scalable default font: no system font needed,
    # so the figure renders the same on any machine.
    return ImageFont.load_default(size=size)


def _scale_bar(draw, ext: Extent, w: int, h: int, *, k=1.0, on_image=False) -> float:
    """`k` scales every overlay size: the context panel is printed smaller
    per pixel than the detail panel, and fixed pixel sizes went unreadable."""
    m_per_px = ext.width_m / w
    length_m = _nice(ext.width_m * 0.25)
    length_px = length_m / m_per_px
    # Bottom-RIGHT, clear of the longitude labels below and the latitude
    # labels down the left edge.
    x0, y0 = w - length_px - 50 * k, h - 80 * k
    fill = (255, 255, 255) if on_image else INK
    if on_image:
        draw.rectangle([x0 - 12 * k, y0 - 44 * k, x0 + length_px + 12 * k, y0 + 22 * k],
                       fill=(0, 0, 0, 150))
    draw.rectangle([x0, y0, x0 + length_px, y0 + 8 * k], fill=fill)
    label = f"{length_m:g} m" if length_m < 1000 else f"{length_m / 1000:g} km"
    draw.text((x0, y0 - 36 * k), label, fill=fill, font=_font(round(26 * k)))
    return length_m


def _north_arrow(draw, w: int, *, k=1.0, on_image=False):
    fill = (255, 255, 255) if on_image else INK
    x, y = w - 60 * k, 30 * k
    if on_image:
        draw.rectangle([x - 30 * k, y - 10 * k, x + 30 * k, y + 92 * k], fill=(0, 0, 0, 150))
    draw.polygon([(x, y), (x - 16 * k, y + 42 * k), (x + 16 * k, y + 42 * k)], fill=fill)
    draw.text((x - 9 * k, y + 48 * k), "N", fill=fill, font=_font(round(28 * k)))


def _label(draw, xy, text, font):
    """Grey graticule label on a translucent white chip, so points under it
    don't swallow it."""
    box = draw.textbbox(xy, text, font=font)
    draw.rectangle([box[0] - 3, box[1] - 2, box[2] + 3, box[3] + 2], fill=(255, 255, 255, 200))
    draw.text(xy, text, fill=(100, 100, 100), font=font)


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _ramp_rgb(t: np.ndarray) -> np.ndarray:
    """t in [0, 1] -> uint8 RGB via linear interpolation between RAMP stops."""
    stops = np.array(RAMP, dtype=float)
    pos = np.clip(t, 0, 1) * (len(RAMP) - 1)
    i = np.minimum(pos.astype(int), len(RAMP) - 2)
    f = (pos - i)[:, None]
    return (stops[i] * (1 - f) + stops[i + 1] * f).round().astype("uint8")


def colour_bar_png(width=900, height=36) -> bytes:
    t = np.linspace(0, 1, width)
    row = _ramp_rgb(t)
    arr = np.repeat(row[None, :, :], height, axis=0)
    return _png(Image.fromarray(arr, mode="RGB"))


# ── detail panel ────────────────────────────────────────────────────

def detail_figure(points: list[dict], *, aoi=None, waypoints=()) -> Figure:
    """`points`: dicts with lon, lat, timestamp, source (position) and the
    COLOUR_BY columns plus their <kind>_source. Ordered by time."""
    if not points:
        return Figure(omitted="No positions on this mission.")

    lons = [p["lon"] for p in points]
    lats = [p["lat"] for p in points]
    if aoi is not None:
        w_, s_, e_, n_ = aoi.extent
        lons += [w_, e_]
        lats += [s_, n_]
    for wp in waypoints:
        lons.append(wp["lon"])
        lats.append(wp["lat"])
    ext = bbox_of(lons, lats).padded(PAD_FRACTION, MIN_SPAN_M)
    w, h = ext.fit(DETAIL_BOX)

    img = Image.new("RGB", (w, h), (252, 252, 250))
    draw = ImageDraw.Draw(img, "RGBA")

    # Graticule: ~5 lines per axis at a round step in degrees.
    step = _nice(max(ext.east - ext.west, ext.north - ext.south) / 5)
    font = _font(22)
    lon = math.ceil(ext.west / step) * step
    while lon < ext.east:
        x, _ = ext.to_px(w, h, lon, ext.south)
        draw.line([(x, 0), (x, h)], fill=GRID, width=1)
        text = f"{abs(lon):.4f}°{'E' if lon >= 0 else 'W'}"
        if x + 4 + draw.textlength(text, font=font) < w - 4:  # never clipped
            _label(draw, (x + 4, h - 28), text, font)
        lon += step
    lat = math.ceil(ext.south / step) * step
    while lat < ext.north:
        _, y = ext.to_px(w, h, ext.west, lat)
        draw.line([(0, y), (w, y)], fill=GRID, width=1)
        _label(draw, (6, y + 2), f"{abs(lat):.4f}°{'N' if lat >= 0 else 'S'}", font)
        lat += step

    if aoi is not None:
        ring = [ext.to_px(w, h, x, y) for x, y in aoi.exterior_ring.coords]
        draw.line(ring, fill=(120, 120, 120), width=3)

    position_tiers = {p["source"] for p in points}
    track = SensorLog.Source.MODELLED not in position_tiers and len(points) > 1
    segments = track_segments(points, ext) if track else []
    for seg in segments:
        if len(seg) > 1:
            draw.line([ext.to_px(w, h, p["lon"], p["lat"]) for p in seg],
                      fill=(90, 90, 90, 160), width=2)

    # Pick the quantity to colour by: the first with any value.
    colour = None
    for kind, col, label, unit, dec in COLOUR_BY:
        usable = [p for p in points if p.get(col) is not None
                  and (col, p.get(f"{kind}_source")) not in NOT_COLOURED]
        if usable:
            colour = (kind, col, label, unit, dec,
                      np.asarray([p[col] for p in usable], float), usable)
            break

    r = max(4, round(min(w, h) / 160))
    meta = {
        "track_drawn": track,
        "track_breaks": max(0, len(segments) - 1),
        "break_speed_ms": BREAK_SPEED_MS,
        "break_gap_s": BREAK_GAP_S,
        "position_sources": sorted(position_tiers, key=_rank),
        "n_points": len(points),
        "extent": [ext.west, ext.south, ext.east, ext.north],
        "m_per_px": ext.width_m / w,
    }
    if colour is None:
        for p in points:
            x, y = ext.to_px(w, h, p["lon"], p["lat"])
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(60, 60, 60, 200))
        meta["colour_by"] = None
    else:
        kind, col, label, unit, dec, vals, coloured = colour
        lo, hi = np.percentile(vals, CLIP_PCT, method="linear")
        if hi <= lo:
            lo, hi = float(vals.min()), float(vals.min()) + 1e-9
        coloured = list(coloured)
        # Highest values drawn last so anomalies are never buried.
        coloured.sort(key=lambda p: p[col])
        t = (np.array([p[col] for p in coloured]) - lo) / (hi - lo)
        rgbs = _ramp_rgb(t)
        for p, rgb in zip(coloured, rgbs):
            x, y = ext.to_px(w, h, p["lon"], p["lat"])
            draw.ellipse([x - r, y - r, x + r, y + r],
                         fill=(*map(int, rgb), 230), outline=(0, 0, 0, 90))
        tiers = sorted({p[f"{kind}_source"] for p in coloured}, key=_rank)
        meta["colour_by"] = {
            "label": label, "unit": unit, "decimals": dec,
            "domain": [float(lo), float(hi)],
            "data_min": float(vals.min()), "data_max": float(vals.max()),
            "n": int(vals.size), "sources": tiers,
        }

    for i, wp in enumerate(waypoints):
        x, y = ext.to_px(w, h, wp["lon"], wp["lat"])
        draw.rectangle([x - 9, y - 9, x + 9, y + 9], outline=INK, width=3)
        draw.text((x + 12, y - 14), str(i + 1), fill=INK, font=_font(24))

    _scale_bar(draw, ext, w, h)
    _north_arrow(draw, w)
    return Figure(png=_png(img), width=w, height=h, meta=meta)


def track_segments(points: list[dict], ext: Extent) -> list[list[dict]]:
    """Split a time-ordered track wherever consecutive fixes are more than
    BREAK_GAP_S apart or imply faster than BREAK_SPEED_MS."""
    segments = [[points[0]]]
    for a, b in zip(points, points[1:]):
        dt = (b["timestamp"] - a["timestamp"]).total_seconds()
        dx = (b["lon"] - a["lon"]) * ext.kx
        dy = (b["lat"] - a["lat"]) * M_PER_DEG
        dist = math.hypot(dx, dy)
        if dt > BREAK_GAP_S or dist > BREAK_SPEED_MS * max(dt, 1.0):
            segments.append([b])
        else:
            segments[-1].append(b)
    return segments


def _rank(tier: str) -> int:
    return [s.value for s in SensorLog.Source].index(tier)


# ── context panel ───────────────────────────────────────────────────

def pick_scene(mission):
    """The best true-colour scene linked to this mission, in its own org:
    finest resolution, then most recent. None if there is none."""
    from satellite_integration import render
    from satellite_integration.models import SatelliteImage

    qs = (
        SatelliteImage.objects
        .filter(query__mission=mission,
                query__organization_id=mission.organization_id)
        .exclude(cog_path="")
        .select_related("dataset")
        .order_by("dataset__resolution_m", "-acquisition_date", "id")
    )
    for image in qs:
        if (image.dataset.code, "truecolor") in render.LAYERS:
            return image
    return None


def context_figure(mission, survey: Extent) -> Figure:
    from satellite_integration import cog, render

    image = pick_scene(mission)
    if image is None:
        return Figure(omitted="No satellite scene is linked to this mission.")

    code = image.dataset.code
    try:
        layer = render.get_layer(code, "truecolor")
        path = cog.absolute_cog_path(image.cog_path)
        if not path.exists():
            raise FileNotFoundError(f"COG missing on disk: {image.cog_path}")
        png_path, stretch = render.cached_or_render(path, layer)
        bounds = cog.inspect_cog(path).bounds_4326
        src = Image.open(png_path).convert("RGBA")
    except Exception as exc:  # imagery must never sink the report
        log.warning("report context panel omitted for mission %s: %s", mission.pk, exc)
        return Figure(omitted=f"Satellite scene #{image.pk} could not be rendered: {exc}")

    ext = Extent(*bounds)
    w, h = ext.fit(CONTEXT_BOX)
    # NEAREST: one source pixel stays one visible block. Smoothing a 10 m
    # pixel into a gradient implies detail the sensor never had.
    scene = src.resize((w, h), Image.NEAREST)
    canvas = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    canvas.alpha_composite(scene)
    draw = ImageDraw.Draw(canvas, "RGBA")

    x0, y0 = ext.to_px(w, h, survey.west, survey.north)
    x1, y1 = ext.to_px(w, h, survey.east, survey.south)
    draw.rectangle([x0, y0, x1, y1], outline=OUTLINE, width=round(4 * CONTEXT_K))

    _scale_bar(draw, ext, w, h, k=CONTEXT_K, on_image=True)
    _north_arrow(draw, w, k=CONTEXT_K, on_image=True)

    acquired = image.acquisition_date
    return Figure(
        png=_png(canvas.convert("RGB")), width=w, height=h,
        meta={
            "image_id": image.pk,
            "dataset": code,
            "dataset_name": image.dataset.name,
            "resolution_m": image.dataset.resolution_m,
            "acquired": acquired.date().isoformat(),
            "layer_caption": layer.caption,
            "attribution": ATTRIBUTION.get(code, "").format(year=acquired.year),
            "bounds": list(bounds),
            "source_px": [src.width, src.height],
            "stretch": stretch,
        },
    )
# ─── RANGER V3 END: 16-report-map ───
