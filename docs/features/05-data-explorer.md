# Feature 05 — Data Explorer

> Status: Shipped 2026-06-15. Branch: `feat/data-explorer` (cut from
> Commits: `94221d8` (05a backend), `0c9a441` (05b page),
> `38f724f` (05c charts), plus the docs commit that adds this file.

## What it does

The first real read surface over the core models filled by Feature 04. Three
parts on one branch:

- **05a — Backend.** Four authenticated, org-scoped read endpoints over
  `core.SensorLog`, plus a null-safe serializer that flattens a log and its
  decoupled reading models into one flat JSON object.
- **05b — Data Explorer page** (`/data`). Filterable, sortable, paginated
  TanStack table beside a MapLibre map showing the full filtered track, with
  row→fly-to interaction, a summary bar, and CSV export.
- **05c — Visualizations page** (`/visualizations`). Four Recharts time-series
  charts (radiation, air quality, IMU, barometer) with example threshold
  reference lines and per-series stats.

No model changes, so **no migrations**. Authenticated-only (see ADR 0007).

## Endpoints (05a)

| Method | URL | Returns |
| --- | --- | --- |
| GET | `/api/data-logs/` | Paginated, org-scoped, filterable log list (newest first). The table feed. |
| GET | `/api/data-logs/export/` | Same filters, no pagination, chronological, streamed as a CSV attachment. |
| GET | `/api/chart-data/` | Same filters, no pagination, **oldest first**, point-capped (`MAX_CHART_POINTS = 5000`). For charts. |
| GET | `/api/map-data/` | GeoJSON `FeatureCollection`, point-capped, thin per-point properties. For the map. |

All inherit `IsAuthenticated` from the DRF default and scope through
`robot__organization=request.user.organization` (ADR 0006 — no `organization`
field on `SensorLog`). Filters (V2 §3.1.4 parity): `robot_id`, `mission_id`,
`date_start`, `date_end`. Dates inclusive; `date_end` extends to end-of-day. A
shared `_apply_filters` helper applies them identically across all four views,
with int-guards on `robot_id`/`mission_id` so a malformed value returns an
empty set rather than a 500.

### The null-safety landmine

A `SensorLog` may have **no** reading of a given type: the simulator writes only
the reading models matching a robot's `installed_sensors`, and the seed robot
(`geiger` + `pm`, no `imu_baro`) produces ~230 logs with radiation and air
quality but **no** IMU/barometer row. V2's serializer used
`source='radiation_data.radiation_value'`, which **raises** when the related
object is missing. `DataLogSerializer` instead routes every reading field
through a `SerializerMethodField` guarded with `getattr(obj, '<related>', None)`,
so an absent reading nulls its whole group cleanly. This was verified against a
real seed-robot row (`roll` came back `None`, not an exception) before any
endpoint was wired.

### Serializer shape

Flat — all reading fields top-level and nullable — so TanStack Table accessor
keys and Recharts `dataKey`s map directly with no client-side flatten step.
Includes both `robot_id` (integer PK, used by the robot filter) and
`robot_id_str` (human ID). The CSV export reuses the same serializer so cells
and JSON rows agree exactly.

### Pagination

`StandardResultsSetPagination` (page_size 25, max 1000, `limit` query param) on
the list endpoint only. Export, chart-data, and map-data are deliberately
unpaginated; chart-data and map-data carry the `MAX_CHART_POINTS` cap.

## Data Explorer page (05b)

Two-column layout: TanStack Table v8 on the left (server-side pagination via
`manualPagination`, client-side sort of the current page, column-visibility
toggles), MapLibre map on the right. Filter panel (robot/mission dropdowns +
date range) with an explicit Fetch button. Summary bar shows min/max/avg for
radiation and PM2.5 over the **full filtered set**.

**The map is decoupled from the table.** It's fed by `/api/map-data/`, which
returns the whole filtered track regardless of which table page is shown —
paging the table never changes the map. This is the entire reason the fourth
endpoint exists (the handoff scoped three; `map-data` was carried over from the
V3 arch doc §5.1). Clicking a table row flies the map to that point and drops a
highlight marker. GeoJSON coordinates are `[lng, lat]` (verified in 05a).

**CSV export** fetches `/api/data-logs/export/` as a blob through the shared
`api` axios instance, so the JWT access token rides through the interceptor and
the download works in production where there is no session cookie. This diverges
deliberately from V2's session-cookie `window.open` approach.

The MapTiler vector style requires `VITE_MAPTILER_KEY` in
`ranger_frontend/.env` (gitignored). If absent, the map area shows a clear
"key not set" message instead of failing silently. `maplibre-gl.css` is
imported in the page (omitting it renders controls/markers broken — the V2 bug).

## Visualizations page (05c)

Four `ResponsiveContainer` + `LineChart` charts fed by `/api/chart-data/`
(ascending, so the time axis runs oldest→newest). Timestamps are converted ISO
→ epoch ms client-side for a proper time scale. Robot + date-range filters; no
pagination (V2 §3.3.7 parity).

- **Radiation** (CPM) — single line, example threshold reference line.
- **Air Quality** — PM2.5 + PM10, example PM2.5 threshold.
- **IMU Orientation** — roll + pitch. Empty for the seed robot.
- **Barometer** — pressure + altitude on dual Y-axes. Empty for the seed robot.

The IMU and barometer charts detect an all-null series and render a "no data for
this sensor" empty state rather than a blank axis — the null-safety from the
serializer surfacing cleanly in the UI. They populate automatically when a robot
with `imu_baro` logs data.

**Reference lines are illustrative examples, clearly labelled — not regulatory
thresholds.** Real, sourced, configurable thresholds are deferred to the future
Alerts feature; presenting unsourced numbers as compliance limits on an
environmental platform would be misleading.

## Files

**Backend (`ranger_backend/`), new:** `core/serializers.py`,
`core/pagination.py`, `core/views.py`, `core/urls.py`.
**Backend, modified:** `ranger_backend/urls.py` (include `core.urls`).

**Frontend (`ranger_frontend/src/`), new:** `types/dataLog.types.ts`,
`api/dataLogs.ts`, `pages/DataExplorerPage.tsx`, `pages/VisualizationsPage.tsx`.
**Frontend, modified:** `App.tsx` (two routes), `pages/DashboardPage.tsx` (nav
links).
**Deps added:** `@tanstack/react-table`, `maplibre-gl`, `recharts`.

## Verification

05a verified end-to-end against the 230 seed rows via the browsable API and the
DRF test factory: paginated list with IMU fields null and the `limit` param
working; malformed `robot_id` returning an empty 200 (not a 500); CSV export
with the correct header and null cells; chart-data unpaginated, ascending,
counted 230; map-data a `FeatureCollection` with `[lng, lat]` order confirmed;
401 when unauthenticated; org-scoping holding (cross-tenant test skipped — only
ByteAnza exists in the DB). 05b/05c verified in the browser: table loads via the
JWT path, map shows the full track and decouples from paging, row-click flies +
marks, summary bar and per-chart stats compute, CSV blob downloads, and the
IMU/barometer empty states render as designed.

## Things that went wrong

Two real ones, both with troubleshooting entries:

- **Map-data race** (`011`): the GeoJSON fetch could resolve before MapLibre's
  `load` event, silently dropping the track (points never appeared while
  row-click still worked). Fixed by stashing the latest track and re-applying it
  on `load`, with the effect also keyed on a `mapReady` flag.
- **Robot-filter PK gap** (`012`): the serializer exposed only `robot_id_str`
  but the list endpoint filters by integer `robot_id`, so the robot dropdown had
  no value to send. Found while building the consumer; fixed by adding `robot_id`
  (integer PK) to the serializer — which then required adding it to the CSV
  `fieldnames` too, or the export 500s.

Smaller, no entry warranted: a stale editor TS-server cache reported a
"cannot find module" for a file that existed and built clean (`tsc -b` passed) —
resolved by restarting the TS server. And two operator-side paste slips (a `<id>`
placeholder kept literally; an `/admin/` vs `/api/` URL typo), same bar as 04's
red herring.

## Related docs

- `features/03-core-models.md`, `features/04-simulator.md`
- `decisions/0006-sensorlog-tenancy-through-robot.md`
- `decisions/0007-data-explorer-authenticated-only.md`
- `troubleshooting/011-mapdata-load-race.md`,
  `troubleshooting/012-robot-filter-pk-gap.md`