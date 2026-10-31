# ADR-0034: Offline survey map — Pillow, two panels, honest tracks

- **Status:** Accepted
- **Date:** 2026-10-30
- **Feature:** F16 (Pass 7 fork 6)
- **Related:** ADR-0013 (raster delivery), ADR-0035

## Context

The PDF must render with no network. The console map (MapLibre + MapTiler tiles) is
browser-only. A Marsabit site is ~110 m across: 11 Sentinel-2 pixels. Marsabit
positions are MODELLED: placed uniformly inside the site bbox, with synthetic 1 s
timestamps.

## Decision

Two figures, drawn with Pillow (already a dependency):

- **Detail** — the survey area on a plain background: graticule, scale bar, north
  arrow, AOI outline, planned waypoints; readings coloured by dose rate, else CPM
  (never MODELLED CPM), else PM2.5, on a P5–P95 ramp, highest drawn last.
- **Context** — the mission's own true-colour scene (finest resolution, then most
  recent, same org) via `render.cached_or_render` from the COG on disk, upscaled
  NEAREST (a 10 m pixel stays a 10 m block), survey area outlined in magenta.
  Omitted with the reason stated when no readable scene exists; imagery never fails
  a report.
- **Local equirectangular projection scaled by cos(latitude)**: a metre is the same
  length on both axes (matters at Rabat, 34 N).
- **Track rules:** no track at all if any position is MODELLED (their order is not a
  route); otherwise break between consecutive fixes more than 30 s apart or implying
  more than 20 m/s. The caption states the number of breaks.

## Rejected

- **Imagery under the detail panel** — 11 pixels under 2,000 points reads as a render bug.
- **matplotlib** — a new dependency for a scatter plot.
- **Cached MapTiler tiles** — licensing and a cache to keep warm, for no gain.
- **5 m/s break threshold** — broke a simulated track 179 times; `nmea_sim`'s route
  walker covers 5–12 m per 1 Hz fix (TS-053).

## Consequences

Bench missions (Nairobi, Rabat) have no satellite context: stated, not hidden. Every
fact the caption prints is stored in `Report.summary["map"]`.
