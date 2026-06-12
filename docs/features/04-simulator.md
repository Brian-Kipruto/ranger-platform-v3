# Feature 04 — Simulator

> Status: Shipped 2026-06-12. Branch: `feat/simulator` (cut from
> `feat/core-models`). Commit: `0602737`.

## What it does

Adds a Django management command, `python manage.py run_simulation`, that
generates realistic sensor data and writes it into the Feature 03 models. It is
the bridge feature: Feature 03 built the tables empty, and Feature 05 (Data
Explorer) needs realistic rows to query — the simulator fills that gap. It is
V3's equivalent of V2's `run_simulation.py` (V2 docs §3.1.6, §4.1, §10.2.3),
rewritten against V3's models rather than ported.

Pure software. It writes rows to Postgres and nothing else — there is no Redis
broadcast, no WebSocket consumer, and no `ros_bridge` involvement, because none
of those are wired in V3 yet. When a live consumer exists (Phase 2), a broadcast
path can be added; until then there is nothing to broadcast to.

No model changes, so **no migrations**. The command only writes to existing
tables.

## Modes

The command has two modes, selected by the `--live` flag:

- **Backfill (default).** Generates `--count` historical `SensorLog` rows in one
  shot, with timestamps spaced `--interval-seconds` apart, the newest landing at
  ~`now()` and the rest walking backward. Then it exits. This is the mode Data
  Explorer needs — a body of historical rows to page, filter, and chart.
- **Live (`--live`).** Loops forever, writing one log every `--live-delay`
  seconds with a `now()` timestamp, until Ctrl-C (clean exit via
  `KeyboardInterrupt`, no traceback). Same write path as backfill; just
  continuous and real-time.

This is a deliberate upgrade over V2, whose simulator was live-loop-only
(broadcasting every 3 s to Redis). V3 adds the backfill mode V2 never had and
makes it the default, because the immediate consumer (Data Explorer) wants
history, not a live stream.

## Position: hybrid waypoint / random-walk

Each run targets one robot and chooses its movement model automatically:

- **Waypoint-driving** — if the target robot has an `IN_PROGRESS` mission with
  `PENDING` waypoints, the sim drives toward the next waypoint a fixed step per
  log (with light jitter so the path isn't ruler-straight), marks each waypoint
  `COMPLETED` on arrival, advances to the next, and attaches every log produced
  during the drive to that mission.
- **Random-walk** — otherwise (no active mission, or the route is exhausted
  mid-run) it nudges latitude/longitude by a small random amount each log, with
  `mission=None`.

The two compose: a backfill that completes a 4-waypoint route in ~31 logs then
spends the remaining logs as a random-walk tail. This mirrors V2's most advanced
simulator behaviour (§10.2.3, which drove `IN_PROGRESS` missions and marked
waypoints completed) while keeping V2's earlier pure random-walk (§3.1.6) as the
fallback — so the sim is useful whether or not a mission is set up.

## Readings driven by `installed_sensors`

For each `SensorLog`, the command writes **only** the reading models matching the
target robot's `installed_sensors`, matched on `SensorType.code`:

| code | reading model |
| --- | --- |
| `geiger` | `RadiationLog` |
| `pm` | `AirQualityLog` |
| `imu_baro` | `ImuBaroLog` |

A robot carrying only `geiger` + `pm` (the current seed) produces radiation and
air-quality readings and **no** IMU row. A robot with none of these recognised
codes gets a bare `SensorLog` with no readings and a one-time warning. This is a
V3 improvement over V2, which hardcoded which readings every log carried.

Because the reading models use `primary_key=True` on their OneToOne to
`SensorLog`, the parent log is created first, then each reading via
`RadiationLog.objects.create(sensor_log=log, ...)`. All of a log's rows are
written inside one `@transaction.atomic` so a log and its readings commit
together.

## Value generation

Values evolve as a smooth random walk between logs, not independent random draws,
so charts look like a real sensor track:

- **Radiation:** drifts around a 15–25 CPM baseline, with a ~3% chance per log of
  a transient spike (+20–60 CPM); clamped to 5–300 CPM. `dose_rate_usvh` is
  derived as `cpm * 0.0057`.
- **Air quality:** PM2.5 drifts in 2–150 µg/m³; PM10 is PM2.5 × 1.5–2.0.
- **IMU/baro** (only if the robot carries `imu_baro`): roll/pitch ±5°, yaw drifts
  and wraps 0–360°, pressure 1008–1018 hPa, altitude 1600–1700 m.

## Tenancy

The command never sets an `organization` anywhere — `SensorLog` has no such field
(ADR 0006). It already holds the target `Robot` object, so the active-mission
lookup is `robot.missions.filter(status=IN_PROGRESS)`, and tenancy is implicit:
a log's org is its robot's org. The verification step confirms the
`robot__organization=` filter and the related-reading access that Data Explorer's
`get_queryset` and serializer will use.

## Command interface

```
python manage.py run_simulation \
    --robot RANGER-PRIME-001    # robot_id_str; default: first robot, else seed one
    --count 200                 # backfill: number of logs (default 200)
    --interval-seconds 30       # backfill: seconds between log timestamps (default 30)
    --live                      # switch to continuous live loop
    --live-delay 3.0            # live: seconds between writes (default 3.0)
    --start-lat -1.2921         # random-walk origin (default: Nairobi)
    --start-lon 36.8219
    --clear                     # delete all SensorLogs for this robot first (prompts)
```

**Robot resolution.** With `--robot`, looks up that `robot_id_str` (hard error if
absent). Without it: uses `Robot.objects.first()`; if there are no robots at all,
seeds `North Field Bot` / `RANGER-PRIME-001` under org `byteanza` with `geiger` +
`pm` sensors (hard error if that org doesn't exist either).

**`--clear`.** Deletes all `SensorLog` rows for the target robot (readings go via
cascade), after a typed `yes` confirmation. Because `SensorLog` has no per-row
marker field (and adding one would mean a model change, which 04 avoids),
"clear" is scoped to the whole robot, not just sim-authored rows.

## Files

**New:**
- `core/management/__init__.py`
- `core/management/commands/__init__.py`
- `core/management/commands/run_simulation.py` — the whole feature

**Modified:** none. **Migrations:** none.

Placed in `core` (not a V2-style `api` app, which V3 doesn't have) because
`SensorLog` and the reading models live in `core`.

## Verification

Confirmed end-to-end before shipping, all via `manage.py shell -c`:

1. **Backfill + installed_sensors:** a 20-log backfill produced 20 `SensorLog`,
   20 `RadiationLog`, 20 `AirQualityLog`, and **0** `ImuBaroLog` (the seed robot
   has no `imu_baro`) — proving readings track `installed_sensors`.
2. **Waypoint-driving:** a 200-log backfill against an `IN_PROGRESS` mission with
   4 pending waypoints marked all four `COMPLETED` in order, attached 31 logs to
   the mission, then finished the remaining logs as a random-walk tail.
3. **Live mode:** wrote one log per `--live-delay`, timestamps correctly spaced,
   clean Ctrl-C exit.
4. **Data Explorer read pattern:** the exact org-scoped query Feature 05 will use
   returned correctly —

```bash
python manage.py shell -c "
from core.models import SensorLog
from accounts.models import Organization
org = Organization.objects.get(slug='byteanza')
qs = SensorLog.objects.filter(robot__organization=org).select_related('robot','mission')
print('org-scoped logs:', qs.count())
print('tenancy resolves through robot:', all(l.robot.organization == org for l in qs[:50]))
"
```

Output confirmed a nonzero org-scoped count, `tenancy resolves through robot:
True`, clean serializer-style flattening (radiation + PM present, IMU `None`),
and the expected mission-attached count. The `robot__organization=` filter and
`radiation_data` / `air_quality_data` related access are exactly what Data
Explorer depends on.

## Things that went wrong

Nothing in the simulator. During verification, reading counts briefly looked
mismatched (21 logs / 21 radiation / 20 air-quality) — this turned out to be the
Feature 03 hand-made verification row (`id 1`, CPM 42.5, radiation-only),
pre-existing in the DB, not anything the simulator produced. Confirmed by query,
then cleared with `--clear` to establish a clean baseline. No code bug, no
troubleshooting entry warranted.