# Feature 04 Retrospective — Simulator

> Period: 2026-06-12. Sessions: 1. Branch: `feat/simulator`.

## What worked

**Branching off `feat/core-models` directly.** Feature 03 was pushed but not yet
merged to `main`, so cutting `feat/simulator` off `feat/core-models` (not bare
`main`) meant the models were present from the first commit. The
branch-cut import check (`shell -c` importing all core+missions models) confirmed
this before any code was written — no "models missing" surprise.

**`git status` before the branch cut, this time.** The 03 lesson held: checked
the working tree was clean *before* `git checkout -b`, so nothing stray rode
along. At commit time `git status` showed only `core/management/` untracked —
exactly the feature, nothing else.

**Writing the whole command at once, verified incrementally.** Rather than stub
then refill (which would have meant rewriting the same file three times), the
full `run_simulation.py` was written once and the checkpoints verified *behaviour*
(`--help`, then `--count 0` resolution-only, then real backfill, then waypoints,
then live, then E2E). This matched the "complete working code, not snippets"
preference and meant no code churn between checkpoints.

**Syntax-checking before handoff.** The file was `py_compile`'d in a scratch
environment before being handed over, so the first time it ran on the real DB it
was already known to parse. Every checkpoint then passed first try.

**The `--count 0` dry-run trick.** Running the full robot-resolution and
sensor-code detection path with zero writes was a cheap way to verify the
command found the right robot and read `installed_sensors` correctly before
committing any rows to the DB.

**Diagnosing the count mismatch instead of assuming a bug.** When reading counts
came back 21/21/20, the instinct was to check whether it was a write-path bug or
pre-existing data. A targeted query found the single radiation-only Feature 03
verification row (`id 1`, CPM 42.5) — pre-existing, not simulator-produced. Saved
a pointless debugging detour into the write path, which was correct all along.

## What was hard

**Nothing structural.** The models were a known quantity from 03, the V2
simulator was a reference for the random-walk and waypoint-driving shapes, and
the "no migrations, write-only" scope kept the blast radius tiny. The only real
design thinking was the hybrid movement model and the per-leg step sizing, and
both worked as intended on first run.

**Minor: waypoint spacing vs. step size is a bit coarse.** The verification
mission's waypoints were ~100 m apart and the drive step is ~13 m/log, so each
leg consumed ~8 logs and a 4-waypoint route finished in ~31 logs. Fine for
verification and not a defect, but for dense, realistic mission tracks the
waypoint spacing (not the simulator) is the thing to tune.

## What to do differently next time

**Establish a clean data baseline before verifying counts.** The 03 verification
row sitting in the DB made the first count check ambiguous for a round-trip.
Running `--clear` (or noting expected pre-existing rows) *before* the first
count-based assertion would have avoided the detour. For features that assert on
row counts, zero the relevant tables first.

**Nothing else.** The workflow (spec → GO → branch → checkpointed build →
verify → commit → docs) ran clean.

## Numbers

- 6 checkpoints across one session (branch/preflight, skeleton+resolution,
  random-walk backfill, waypoint-driving, live mode, E2E verification)
- 1 code commit: `feat:` (3 files — the command + two `__init__.py`)
- 0 migrations (no model changes — the defining constraint of the feature)
- 0 new dependencies (pure stdlib: `random`, `math`, `datetime`, `time`)
- 0 code bugs; 1 pre-existing-data red herring (the 03 verification row),
  diagnosed and cleared, not a simulator fault
- 230 sensor logs generated across all verification runs, serving as the initial
  dataset for Feature 05

## Carry-forwards for the next feature (05 — Data Explorer)

- **There is now data to explore.** ~230 `SensorLog` rows for
  `RANGER-PRIME-001` under ByteAnza, a mix of mission-attached (31) and
  random-walk (the rest), with radiation + air-quality readings and no IMU.
- **The read pattern is proven.** Data Explorer's `get_queryset` should filter
  `SensorLog.objects.filter(robot__organization=request.user.organization)`
  with `.select_related('robot','mission')` and
  `.prefetch_related('radiation_data','air_quality_data','imu_baro_data')`.
  The serializer flattens readings via `source='radiation_data.radiation_value'`
  etc. — and must handle the reading being **absent** (a log may have no
  air-quality row if the robot lacks that sensor; the simulator produces exactly
  this). V2's `DataLogSerializer` (V2 docs §3.1.7) is the reference shape.
- **Filters to support** (V2 parity, §3.1.4): `robot_id`, `mission_id`,
  `date_start`, `date_end`, with pagination for the table view and an
  unpaginated, point-capped variant for charts.
- **To regenerate / extend data:** `run_simulation --clear --count N` for a clean
  set, or plain `--count N` to add more. Set up an `IN_PROGRESS` mission with
  pending waypoints first if you want mission-attached logs.
- **Tenancy unchanged** (ADR 0006): all log queries go through
  `robot__organization`; there is no `organization` field on `SensorLog`.