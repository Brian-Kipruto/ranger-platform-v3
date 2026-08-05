# F10.1 — Retrospective

*Date: 2026-08-03*

---

## What worked

**Contract-diffing was the right verification model for an invisible feature.**
F10.1 changes nothing a user can see, so "does it still work?" had no natural
test. Capturing `/api/map-data/`, `/api/data-logs/`, `/api/chart-data/`, and the
CSV export at `cp0`, then byte-diffing at each checkpoint, turned an unfalsifiable
claim into a pass/fail. Four comparisons ran across the feature; all clean. The
one at `cp3 → cp4` — spanning the irreversible column drop — is the one that
actually proved the property shim worked, and it took two seconds to run.

**Normalizing the captures before diffing.** Sorting features and rows by `id`
before saving anticipated `RemoveField`'s table rewrite reordering rows that
share a timestamp. Without it, `cp4` would have produced a diff full of shuffled
rows and no signal.

**The "properties over geometry" decision made the whole feature small.** The
grep that found *zero* ORM filters on `latitude`/`longitude` was maybe ten
minutes of work, and it collapsed the frontend blast radius to nothing —
`dataLog.types.ts`, `dataLogs.ts`, `DataExplorerPage.tsx`, and `FieldMap.tsx` all
went untouched through a storage-layer rewrite. `admin.py` too, once it turned
out `list_display` resolves model properties. The predicted 8-file CP4 shipped as
7, and the frontend diff was empty as designed.

**Expand → migrate → contract, one migration each.** Three separate migrations
per model meant the `0004` failure (wrong ENGINE) rolled back cleanly with
`showmigrations` still showing `[ ]` across the board — nothing half-applied,
nothing to hand-repair. Re-running after the fix applied all six in one go.

**Assertions inside the backfill.** Both `RunPython` steps verified geometry
against the source floats and against the Kenya bbox *before* committing. They
never fired — which is the point: an inverted backfill would have been caught
inside the transaction rather than discovered at F10.4 when correlations came
back empty.

**Per-row assertions on waypoints specifically.** Recognizing that no endpoint
serializes `Waypoint` — so the contract diff is structurally blind to it — was
the single most useful piece of analysis in the feature. Four rows, asserted
exhaustively, plus dedicated tests. An inverted waypoint doesn't raise; it makes
the simulator drive somewhere wrong, silently, for weeks.

---

## What hurt

**`manage.py check` passed while the database backend was wrong.** The CP2
handoff had two edits to `base.py`; only the first landed. `django.contrib.gis`
was in `INSTALLED_APPS`, so models validated, `makemigrations --check` reported
no changes, `CreateExtension` applied, and `PostGIS_Version()` answered — five
green signals with the ENGINE still on plain postgresql. The failure surfaced
only at the first geometry `AddField`, as an `AttributeError` deep in Django's
field internals. Cost maybe twenty minutes, but it's the second time this repo
has been bitten by a partially-applied multi-edit handoff (troubleshooting 015
was the first). Written up as 016.

**ROS 2 broke pytest before a single test ran.** `/opt/ros/humble` on
`PYTHONPATH` meant pytest auto-loaded ROS's Python 3.10 `launch_testing` plugin
into the 3.11 venv and died on `import yaml`. Nothing to do with RANGER code, and
invisible until the first-ever pytest invocation. `PYTHONPATH= pytest` fixes it
today; the underlying 3.10/3.11 split is a real F08 problem. Written up as 017.

**Bad `reverse()` names shipped past every static check.** The test module used
`reverse("data-logs")` and `reverse("export-data-logs")`; the actual names are
`data-log-list` and `data-log-export-csv`. `py_compile` passes, imports resolve,
and only running the tests catches it — a small reminder that "it compiles" was
never the bar (troubleshooting 013's lesson, in a different costume).

**File-transfer friction consumed real time.** Prefixed filenames
(`core__models.py`) prevented Downloads collisions but created a rename step that
went wrong twice — once leaving `core__geo.py` in place, once leaving migrations
named `core__0006_...`, which produced a `NodeNotFoundError` that looked like a
migration-graph bug and wasn't. Worth a better convention next time: hand over a
single directory tree to copy, rather than flat files needing individual renames.

**Two false starts on environment, not code.** `runserver` wasn't actually
running when the first baseline capture failed (the terminal held Vite), and the
demo password differed from `seed_demo`'s default with a `;` in it that bash ate.
Neither is interesting, but together they cost more wall-clock than the entire
schema migration did.

---

## Workflow notes

**The first version of `capture.sh` swallowed its own error.** It piped curl into
`jq` and printed a generic "login failed", hiding the HTTP status and body — the
information needed to distinguish "server down" from "wrong password" from "bad
URL". Diagnosing took three round-trips that a raw response dump would have
collapsed into one. v2 prints status, body, and the override syntax. **Tooling
written to verify a risky migration should be at least as loud as the migration
it verifies.**

**Two bugs came from the script resolving paths relative to `$0` after a `cd`.**
Resolving `SCRIPT_DIR` once, absolutely, at the top is the fix, and it's the kind
of thing worth doing by default in any script that changes directory.

**The public repo was a full feature behind at the start.** F07 lived on
`feat/dashboard-fieldmap`, unmerged, so the first clone showed F06. Fetching the
branch directly recovered it, but the merge-to-main step became CP0's first task
for a reason: an irreversible migration wants a clean, merged rollback target,
not a stack of two unmerged features.

**The spec was rewritten three times before any code.** Findings from reading the
repo (no `location` field to migrate, no `Mission.area_of_interest` at all, zero
ORM filters on the floats) each changed the plan materially. That reading was
maybe an hour and it prevented specifying a migration for a field that didn't
exist.

---

## Carry-forwards (for F10.2 and beyond)

- **Host GDAL is 3.4.1** (Ubuntu 22.04's) while the container ships PostGIS
  3.5.7. Fine for GeoDjango, but `rasterio` and `rio-cogeo` compile against the
  *host* GDAL, and some COG features want 3.6+. This is the first thing to settle
  in F10.2 — likely a PPA upgrade or a containerized backend.
- **Demo data is in the wrong place for the pitch.** All ~435 logs sit around
  Nairobi (36.82 E, −1.29 S); the satellite mockup features the **Magadi basin**,
  ~70 km southwest. F10.4's ground-truth correlation needs real `SensorLog`
  points inside the AOI actually being pitched. `run_simulation --seed` now makes
  that reproducible, and `--start-lat/--start-lon` already exist — but generating
  and committing to a demo AOI is a task in its own right, before F10.4.
- **`conftest.py`'s `sensor_log_at` factory is F10.4's test scaffolding.**
  Written deliberately as a factory rather than inline setup, because correlation
  tests need exactly "ground points at known positions inside a known footprint."
- **`4WD-001` still has almost no data** (5 logs, written through the new
  geometry path). Multi-robot correlation would benefit from a second populated
  source.
- **ROS/venv Python split becomes architectural at F08.** ROS 2 Humble is built
  for 3.10; the backend venv is 3.11. Today that's a pytest annoyance. When
  `ros_bridge` needs real `rclpy`, it's a design decision: separate bridge
  process over MQTT/WebSocket, matched interpreter, or containerized bridge.
- **ADR-0007 (no route guards) is untouched and still queued for F10.5**, where
  paid GEE queries make permission-scoped access load-bearing rather than
  cosmetic.
- **TimescaleDB deferred, not rejected.** Revisit when `SensorLog` reaches
  millions of rows or time-bucket queries get slow. Hypertable conversion doesn't
  change column types, so no satellite work will need redoing.
