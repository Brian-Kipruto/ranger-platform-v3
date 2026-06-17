# Feature 05 Retrospective — Data Explorer

> Period: 2026-06-12 → 2026-06-15. Sessions: ~3 (05a backend; 05b page; 05c
> charts + docs). Branch: `feat/data-explorer`.

## What worked

**Typecheck-in-scratch before every handoff.** Both frontend bugs that would
have cost real debugging time were caught by compiling the files in a scratch
dir against the *real* libraries (TanStack, MapLibre, Recharts 3.8.1) before
they touched the repo. The `<Blob>`-vs-`unknown` error on the CSV export and a
couple of prop-shape issues surfaced as compile errors, not runtime mysteries.
The discipline from the backend (`py_compile` before handoff) ported cleanly to
the frontend (`tsc --noEmit` against installed lib types).

**Splitting 05 into 05a/05b/05c was the right call.** Each sub-feature ended in
a working, committed, verifiable state (`94221d8`, `0c9a441`, then 05c). The
backend was fully proven via the browsable API and test factory before a single
line of frontend existed, so when the table didn't render we knew it wasn't the
API. Three clean commits beat one multi-session monster with no checkpoint.

**The fourth endpoint (`map-data`) earned itself.** The handoff scoped three
endpoints with the map plotting the table's current page. Pushing back to add
`/api/map-data/` (which the V3 arch doc already named) meant the map shows the
full track decoupled from paging — and the payoff was visible the moment it
rendered: the random-walk blob and the mission waypoint-drive line, two distinct
simulator behaviours, legible on one map. The page-fed alternative would have
shown 25 scattered dots.

**Verifying the null-safety on real data, not in theory.** The whole serializer
was designed around the absent-IMU-reading landmine. Confirming `roll == None`
on an actual seed-robot row (05a CP1) before wiring any endpoint meant the thing
that crashed V2 was proven dead early, and it surfaced cleanly all the way up to
the 05c "no IMU data" empty state.

**Reading `accounts/views.py` before deciding permissions.** The handoff
flagged this as the gate for the perms decision, and it paid off: the existing
views use only `IsAuthenticated`, which settled ADR 0007 by precedent rather
than by inventing a one-off enforcement style.

## What was hard

**The map-data / load race (troubleshooting 011).** The most painful bug of the
feature, and a silent one — basemap fine, row-click fine, points just absent, no
error. Took reasoning from the contrast (marker works, layer doesn't) to isolate
it to the source-population path and the load-event race. The fix (stash +
re-apply on load + `mapReady` dep) is sound but it's the kind of async-timing
trap that's easy to ship because nothing throws.

**The robot-filter PK gap (troubleshooting 012), found mid-build.** Writing the
05b filter layer surfaced that the 05a serializer exposed the string robot ID
but the filter needed the integer PK — a gap created by deliberately not
building `/api/robots/`. Required amending committed 05a code (fine — same
branch, not pushed) and caught a second coupling: the CSV export's `fieldnames`
had to gain the new field too, or export 500s.

**Recharts 2.x vs 3.x.** Worth a pause to confirm the installed major (3.8.1)
before writing chart code, since 3.x shifted some API from the 2.x that V2 and
most tutorials use. Typechecking against the exact installed version avoided a
version-mismatch detour.

## What to do differently next time

**When a serializer is both a display and a filter contract, list the filter
keys it must expose up front.** The robot-filter gap was foreseeable: if an
endpoint filters by integer PK, the serializer feeding the filter UI has to
expose that PK. A one-line check during the 05a spec ("does the serializer
expose every field the filters key on?") would have caught it before 05b.

**Treat any map-source-from-async-fetch as a race by default.** Don't no-op when
the source is missing — stash and re-apply on `load`, and gate on a ready flag,
from the first version. 011 would not have happened if the load race had been
assumed rather than discovered.

**Pin the installed major version of a charting/UI lib before writing against
it.** Cheap check, avoids API-drift surprises.

## Numbers

- 3 sub-features, ~6 + 5 + 1 checkpoints across ~3 sessions
- 3 code commits (`94221d8` 05a, `0c9a441` 05b, `<05c>` 05c) + 1 docs commit
- 4 new backend files + 1 modified; 4 new frontend files + 2 modified
- 3 new deps (`@tanstack/react-table`, `maplibre-gl`, `recharts`)
- 0 migrations (read-only feature over existing models)
- 2 real bugs, both fixed and documented (011 map race, 012 robot-filter PK);
  both caught before any push. Several operator/editor red herrings, none
  doc-worthy.
- Verified against the 230 seed rows end to end: 4 endpoints, table, map,
  charts, CSV export, null-safe empties.

## Carry-forwards

- **Authorization is the next debt.** ADR 0007 ships 05 authenticated-only; the
  Feature 03 custom perms sit defined-but-unused. The first role that needs a
  data subset or an export denial (Community Viewer) should enforce across all
  read endpoints at once and set the V3 permission pattern.
- **`/api/robots/` and `/api/missions/` list endpoints don't exist.** 05b
  derives filter options from a chart-data pull and dedupes client-side. When
  those endpoints land, swapping `getRobotOptions`/`getMissionOptions` to hit
  them is localized — the dropdowns already consume `RobotOption[]` /
  `MissionOption[]`.
- **No WebSocket / live mode.** V2's Data Explorer had a live-updates toggle; V3
  has no consumer wired, so 05 is historical/filtered only. Revisit when a
  consumer exists.
- **MapTiler key** lives in `ranger_frontend/.env` as `VITE_MAPTILER_KEY`
  (gitignored). Restrict it to allowed HTTP origins before production.
- **Example chart thresholds are placeholders.** Real, sourced, configurable
  thresholds belong to the Alerts feature.