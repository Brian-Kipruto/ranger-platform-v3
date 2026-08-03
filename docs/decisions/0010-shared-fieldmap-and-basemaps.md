# 0010 — Shared FieldMap extraction + basemap strategy

*Date: 2026-06-25*
*Status: Accepted*

---

## Context

By the start of F07, the only working MapLibre setup lived inline inside
`DataExplorerPage.tsx` (built in F05, re-chromed in F06): map init, a `track`
GeoJSON source + circle layer, `fitBounds`, row-click `flyTo` + highlight marker,
the MapTiler key handling, and the "MAP UNAVAILABLE" fallback.

F07 needs a map on the Dashboard too — but a richer one: robot blips, a telemetry
readout overlay, expand-to-fullscreen, and a real SAT/VECTOR/TOPO basemap toggle
(the mockup's toggle was dead chrome). Two bad options loomed: copy-paste the DE
map into the Dashboard (two diverging copies of the same fiddly MapLibre code),
or bolt all the new features onto the DE page (a map component pretending not to
be one, used by one screen).

## Problem

How do we get one map implementation used by both screens, where each screen
gets only the chrome it needs, without duplicating the error-prone MapLibre
lifecycle code?

## Options considered

1. **Copy-paste DE's map into the Dashboard.** Rejected — two copies of the
   StrictMode-guarded init, the `styledata` handling, the key fallback. They
   would drift.
2. **Put all map logic on the Dashboard, have DE import from there.** Rejected —
   inverts the dependency awkwardly (DE predates the Dashboard map) and couples
   two pages.
3. **Extract a `<FieldMap>` component both pages consume.** A single component
   owning the MapLibre instance, with props/flags for the per-screen chrome.
   Chosen.

## Decision

Extract `src/components/map/FieldMap.tsx` + `src/components/map/basemaps.ts`.
Both Data Explorer and Dashboard render `<FieldMap>`.

Key design choices:

**Accent as a hex prop, never `var(--accent)`.** MapLibre paint properties are
set in JS and cannot read CSS custom properties. Each caller resolves
`user.organization.theme_color` (the same way DE always did) and passes the hex
string in. This keeps the org-driven multi-tenant accent working on the map
without leaking a CSS-var assumption into paint props.

**`installLayers()` as the single source/layer re-add point.** `map.setStyle()`
(used for basemap switching) wipes ALL sources and layers. So every data layer is
added in exactly one function, called both on the initial `load` and on every
`styledata` event. Without this, switching basemaps silently drops the track and
blips. This is the single most important mechanism in the component and the
thing most likely to break if someone adds a new layer and forgets to put it in
`installLayers`.

**Per-screen chrome via flags, not forks.** `showOverlays` (blips + readout) and
`expandable` (the EXPAND control) default off. The Data Explorer passes neither
and behaves exactly as it did before the extraction; the Dashboard opts into
both. The shared lifecycle code is identical for both.

**Basemaps in a key-aware registry.** `basemaps.ts` maps the three modes to
MapTiler style slugs (`streets-v2` / `satellite` / `outdoor-v2`) and returns
`null` when no key is configured (driving the fallback). One edit point if a
slug changes; all three modes share the single `VITE_MAPTILER_KEY`.

**Blips as real `maplibregl.Marker`s.** Rather than an SVG overlay re-projected
on every `move`, blips are Markers keyed by robot id, so they track pan/zoom for
free. The element is rebuilt on selection/status change.

## Consequences

- One map implementation, two consumers. The DE refactor removed 89 lines from
  `DataExplorerPage.tsx`.
- The DE map gained the basemap toggle for free.
- New per-screen map chrome is added via props on `<FieldMap>`, not by editing a
  page.
- **Gotcha to remember:** any new map data layer MUST be added inside
  `installLayers()`, or it will disappear the first time the user switches
  basemaps. This is non-obvious and is the most likely future regression.
- The blank-map bug during extraction (CP2) came from the component's container
  sizing, not its map logic — see Troubleshooting 014.