# 046 — Every map stuck loading: `moveLayer` inside the `styledata` handler

*Date: 2026-10-29 · caught in the sandbox before handoff*

---

## What we saw

With the 6a `FieldMap` change, a browser run on `/mission` clicked the map and got
rows in the list but **no waypoint markers**. Instrumented: `styledata` fired
continuously (165 times in a few seconds), `load` never fired, so `mapReady` stayed
false and every marker effect returned early. The same build on `/dashboard`: 75
`styledata`, no `load`. `main`'s `FieldMap` on the same page: 4 `styledata`, then
`load`.

## The cause

`installLayers` runs on every `styledata`. The new route layer was kept above any
raster with an **unconditional** `m.moveLayer(ROUTE_LAYER, TRACK_LAYER)` there.
`moveLayer` itself emits `styledata`, even when nothing moves, which re-entered
`installLayers`: an endless loop, and a style that never settles means `load` never
fires. Dashboard, Data Explorer and Satellite would all have frozen.

## The fix

`ensureRouteOrder(m)`: read `getLayersOrder()` and move the route only if it sits
above the track or below a raster. Re-proven: 4 `styledata` then `load`, as on `main`.

## Prevention

- Anything called from a `styledata` handler must be idempotent **and silent** when
  there is nothing to do: check, then act.
- Prove a map change on another page that uses `FieldMap`, not only the one you
  changed.
- The same unconditional pattern exists for the satellite raster (`moveLayer(RASTER,
  TRACK)` in `installLayers`); unverified, listed in F15's open items.
