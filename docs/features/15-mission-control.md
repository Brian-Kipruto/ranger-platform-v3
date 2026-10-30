# F15 — Mission Control Tier 1

*Date: 2026-10-30 (6a → 6c built and proven 2026-10-29 → 30)*
*Branch: `feat/mission-control` (from `main` @ `59e49d5`), fast-forwarded to `main` @ `a6a9b53` before 6d (ADR-0032)*
*Status: **6a–6c closed; 6d (real robot) open.** An operator plans ordered waypoints on Mission Control, saves them, and starts the mission; the platform — never the robot, never the sim — completes each waypoint when a stored fix comes within `threshold_m` of the active one, in order, at the fix's own time; the console ticks it live over the dashboard socket. Proven on the real stack with the sim walking the route (ROS path), with the Orin off (`run_simulation` fallback), with a timed miss and recovery, and with another org seeing nothing. Open: 6d — teleop the 6WD through a real waypoint set under sky. See Open items.*

Pass 6 in the vault. The robot is **teleop-driven** throughout (fork 3): tier 1 never
asks it to move by itself. Waypoint following is Pass A1.

---

## What this feature does

**Plan (6a).** Click the map on `/mission` to add waypoints; reorder with ↑/↓, remove
with ✕; name the mission and set its reach (`threshold_m`, 1–50 m, default 5). SAVE
creates the mission; SAVE CHANGES fully replaces it while it is PENDING. The robot is
the console's paired robot (`VITE_VIDEO_ROBOT_ID`), addressed by `robot_id_str`.

**Start.** START (needs `missions.launch_mission`) moves a PENDING mission to
IN_PROGRESS and stamps `started_at`. A robot can have **one** running mission — the
database refuses a second (`one_in_progress_mission_per_robot`).

**Advance (6b).** Every *stored* fix for a robot is offered to
`missions.progress.advance` inside the row's own transaction (ADR-0028):

- the active waypoint is the running mission's first PENDING one by `order`;
- a fix within `threshold_m` of it (geodesic metres, PostGIS) completes it, with
  `completed_at` = the fix's timestamp; the last one completes the mission;
- at most one waypoint per fix, never out of order, no "closest approach" credit;
- the row is attached to that mission (`SensorLog.mission`), including the fix that
  completes it; a failed row write rolls the completion back with it;
- skipped fixes (no fix, skewed clock, out of region) are never offered.

Both writers use it: `ros_ingest` (live and `nmea_sim`) and `run_simulation` (the
PC-only fallback). Neither decides anything itself.

**Live (6c).** When `advance` completes something, the writer sends a
`mission.progress` event on the org's dashboard group after the row's own broadcast
(ADR-0030). The console re-reads the mission over HTTP and redraws: completed
waypoints green, the active one ringed, `N/M · ACTIVE WP k` → `M/M · COMPLETED`, with
the robot's live blip on the map. A 10 s re-read while a mission runs bounds how long
a lost event can hide a tick.

**Layout (fork 7).** Map | camera in equal halves on top, mission plan | drive below;
nothing unmounts (ADR-0031). The map's height follows the camera panel's.

**Sim along a path (fork 6, ADR-0029).** `manage.py mission_route` exports a mission
as GeoJSON; `nmea_sim --route` walks it on the Orin through the real GPS → ROS →
ingest path. `run_simulation` keeps the Orin-dead fallback, positions only.

### Forks settled

| # | Fork | Settled |
|---|---|---|
| 1 | Where completion is decided | the platform, in the ingest path — ADR-0028 |
| 2 | Threshold | per mission, `threshold_m` 1–50 m, default 5 |
| 3 | Dispatch | operator presses START; the robot is teleop-driven (autonomy is A1) |
| 4 | Planning UI | click the existing `FieldMap`; ↑/↓ list, no drag library |
| 5 | Actions at waypoints | out of scope |
| 6 | Sim along a path | `nmea_sim --route` + `mission_route`; `run_simulation` through `advance` — ADR-0029 |
| 7 | `/mission` layout | map \| camera, plan \| drive, all mounted — ADR-0031 |
| 6c | How progress reaches the browser | `mission.progress` event + HTTP re-read (B), not per-fix polling (A) — ADR-0030 |
| close | Merge before 6d? | yes: merge and document now, 6d as an open item (A) — ADR-0032 |

### API

All under `/api/`, `IsAuthenticated`, every queryset filtered by
`request.user.organization` (a user with no org sees nothing; another tenant's mission
is 404, never 403 — ADR-0007 pattern).

| Method | Path | Notes |
|---|---|---|
| GET | `/missions/` | org's missions, newest first, paginated (`?limit=`, ≤ 1000) |
| POST | `/missions/` | `{name, description, robot_id_str, threshold_m, waypoints: [{lat, lon}, …]}`; order = array index; org and creator from the request; one transaction |
| GET | `/missions/<id>/` | one mission with waypoints (`id, order, lat, lon, status, completed_at`) |
| PUT | `/missions/<id>/` | full replace; **409** unless PENDING (row-locked, re-checked) |
| POST | `/missions/<id>/start/` | **403** without `missions.launch_mission`; **409** if not PENDING or the robot already runs one |

Waypoints are named `{lat, lon}` objects (positional pairs are refused), 1–50 per
mission, and must all fall inside **one** known region (`kenya` or `rabat`). Swapped
coordinates fail that check for both venues: a swapped Nairobi point lands in the
Mediterranean, a swapped Rabat one in Tanzania. A foreign `robot_id_str` is "does not
exist", not "forbidden".

### Socket event (example)

```json
{"type": "mission.progress", "mission": 14, "robot": "RANGER-PRIME-001",
 "mission_status": "IN_PROGRESS",
 "waypoint": {"id": 57, "order": 0, "status": "COMPLETED", "completed_at": "2026-10-30T05:53:38.143Z"},
 "distance_m": 4.87}
```

Sent only on completion, on `dashboard.org.<id>`; the consumer forwards it as-is.
`LiveFeed` routes it to `missionLiveStore`; rows still go to `liveStore`.

---

## Sign-off evidence (DB checks and visual: Brian)

### 6a — plan + persist (2026-10-29)

Mission **#9 "6a test"**: three map clicks, waypoint 3 moved up, saved. DB: one row,
`threshold_m 5`, PENDING, org `byteanza`, creator `operator@byteanza.com`; waypoints
`0: -1.271620, 36.799286 · 1: -1.287950, 36.795171 · 2: -1.279972, 36.820981` —
exactly the panel's list. `client@magadi.com`: dropdown shows only `+ New mission`.
Sandbox browser run (13 checks): clicks → rows → markers → reorder → DB order →
PUT replace → locked when IN_PROGRESS; another org's list empty and detail 404.

### 6b — proximity advance (2026-10-29 → 30)

**Positive, ROS path.** Mission **#10 "6b sim"** (4 waypoints, legs ~300 m, 933 m),
started through the endpoint, `nmea_sim --route --speed 5` on the Orin:

| wp | completed_at (UTC) | distance at completion |
|---|---|---|
| 1 | 21:30:53.54 | — (scrolled out of the pane) |
| 2 | 21:31:55.64 | 4.9 m |
| 3 | 21:33:00.69 | 0.1 m |
| 4 | 21:33:58.79 | 4.7 m · MISSION COMPLETED |

Mission COMPLETED at wp4's time, 3 min 21.6 s after START; **199** rows attached.
4.9 and 4.7 m are the fix one 5 m step before the waypoint, plus jitter: the first fix
inside the radius wins.

**Negative, timed.** Mission **#12 "6b miss 2"** (a copy of #10): the sim walked the
route shifted east until its own closest-approach report showed wp1 ≥ 10 m. Before
recovery the mission stored **363** fixes along a **1,462 m** path, **16.1–450.4 m**
from wp1: nothing completed. Back on route at T0 = 07:36:48.94 EAT:

| wp | s after T0 |
|---|---|
| 1 | **6.1** (3 s no-fix warm-up + 3 s lead-in + ingest) |
| 2 | 67.2 |
| 3 | 131.3 |
| 4 | 191.4 · MISSION COMPLETED |

The first miss attempt (#11) was invalid — a 15 m east shift missed wp1 by only
4.6 m on that geometry — and was aborted (TS-047).

**Fallback, Orin off.** `ranger_down`, nothing ingesting; mission **#13
"6b fallback"** (a copy of #10) driven by `run_simulation --live --live-delay 1
--speed 15`: wp 1→4 at 05:09:08, 05:09:29, 05:09:51, 05:10:12 · MISSION COMPLETED;
**64** rows attached; distances 0.0 / 0.0 / 1.3 / 0.0 m.

**In-process.** `test_nmea_route.Test6bInProcess` runs walk → GGA → pynmea2 → region
guard → `advance` on every test run: complete, miss (wp3 passed at 0.24 m stays
PENDING behind a missed wp1), recover.

### 6c — live on the console (2026-10-30)

Mission **#14 "6c sim"** (4 waypoints, 435 m) started from the START button,
`nmea_sim --route --speed 5`: the blip walked the route, each waypoint turned green
as it arrived, the ring moved on, the bar reached `4/4 · COMPLETED`, and the panel
went read-only. Map and camera panels the same height. `client@magadi.com` on
`/mission`: no `6c sim`, no progress, no blip. Screenshots in the vault.

Sandbox browser run (real Django/Daphne socket, Redis, START clicked, `run_simulation
--live` driving): markers green **0.6–0.7 s** after the DB `completed_at`. With the
socket path removed only the 10 s re-read remained and the lag check failed
(2.57 s, wp1 never seen) — the ticks are the socket's.

### Tests

612 → **727** on the PC (+115): `missions/test_api.py` (32), `missions/test_advance.py`
(31), `ros_bridge/test_nmea_route.py` (32), `core/test_run_simulation.py` (14),
`ros_bridge/test_mission_live.py` (6). Mutation-checked, each turned red: the org
filter, the region check, the 409 lock, the robot scope, the threshold comparison,
next-in-order (vs nearest), the PENDING filter, the IN_PROGRESS filter, the START
permission, the forced fix at each waypoint, `load_route` coordinate order, the
`advance` call in `run_simulation`, its land-on-target clamp, its broadcast, the
consumer's `mission_progress` handler, emit-only-on-completion, and the console's
lock guard.

---

## Files

| File | Deployed as | Role |
|---|---|---|
| `ranger_backend/missions/models.py`, `migrations/0006_*`, `0007_*` | — | `threshold_m` (1–50, DB check), `started_at`/`completed_at`, `Waypoint.completed_at`; one running mission per robot |
| `ranger_backend/missions/serializers.py`, `views.py`, `urls.py`, `ranger_backend/urls.py` | — | planning API, START |
| `ranger_backend/missions/progress.py` | — | `advance()` — the one decider |
| `ranger_backend/missions/management/commands/grant_launch.py` | — | Mission Operators group (`missions.launch_mission`) |
| `ranger_backend/missions/management/commands/mission_route.py` | — | mission → GeoJSON for the sim |
| `ranger_backend/ros_bridge/management/commands/ros_ingest.py` | — | offers each stored fix to `advance`, attaches the row, emits progress |
| `ranger_backend/ros_bridge/broadcast.py`, `consumers.py` | — | `mission.progress` payload, send, consumer handler |
| `ranger_backend/core/management/commands/run_simulation.py` | — | fallback: positions in metres through `advance`; `--speed`, `--region`; live broadcast |
| `robot/tools/nmea_sim.py` | Orin `~/ranger/nmea_sim.py` | `--route`, `--speed`, `--offset-east-m`, `--jitter-m`, `--lead-in-m`; closest-approach report |
| `ranger_frontend/src/types/mission.types.ts`, `api/missions.ts` | — | shapes, API wrappers |
| `ranger_frontend/src/components/map/FieldMap.tsx` | — | `waypoints`, `onMapClick`, `fitToWaypointsKey`; route layer |
| `ranger_frontend/src/components/mission/useMissionPlan.ts`, `MissionPlanPanel.tsx` | — | planning state, START, live re-read, progress |
| `ranger_frontend/src/stores/missionLiveStore.ts`, `components/dashboard/LiveFeed.tsx` | — | `mission.progress` routing |
| `ranger_frontend/src/pages/MissionControlPage.tsx` | — | layout, own socket, blip, height match |

Tests: `missions/test_api.py`, `missions/test_advance.py`,
`ros_bridge/test_nmea_route.py`, `ros_bridge/test_mission_live.py`,
`core/test_run_simulation.py`.

---

## Install / deploy (record of what was done)

No system files changed on either machine.

```bash
# PC, repo root — deploy the sim; the two sha256 values must match
scp robot/tools/nmea_sim.py brian@192.168.0.50:/home/brian/ranger/nmea_sim.py
sha256sum robot/tools/nmea_sim.py && ssh brian@192.168.0.50 'sha256sum /home/brian/ranger/nmea_sim.py'
# 2026-10-29: cb04e33fd6a549c76ead37c10da5f4438640550f3fbc622f743241271c7aa12b on both

# PC — migrations 0006, 0007 (pre-check first: no robot may have two IN_PROGRESS missions)
python manage.py migrate missions

# PC — start rights
python manage.py grant_launch operator@byteanza.com
```

**Data change, 2026-10-29:** mission **#1 "Sim Test Mission"** (a leftover of the old
`run_simulation`, IN_PROGRESS on RANGER-PRIME-001) was set to ABORTED before 0007
applied. Left running, ingest would have attached every fix to it and START would
have returned 409 for any new mission on that robot (TS-048). Bench mission #11
(the invalid miss) was ABORTED the same way; #10, #12, #13, #14 are COMPLETED evidence.

---

## Running it

```bash
# bench (sim), as F14
scripts/ranger_up.sh sim nairobi auto --no-drive --no-video

# plan + START on /mission, then walk it with the sim
cd ranger_backend
python manage.py mission_route 14 --out /home/brian/route_6c.geojson
scp /home/brian/route_6c.geojson brian@192.168.0.50:/home/brian/ranger/route_6c.geojson
ssh brian@192.168.0.50 'tmux respawn-window -k -t ranger:nmea_sim "python3 -u /home/brian/ranger/nmea_sim.py /tmp/gps_feed --site nairobi --route /home/brian/ranger/route_6c.geojson --speed 5"'

# back to stationary afterwards
ssh brian@192.168.0.50 'tmux respawn-window -k -t ranger:nmea_sim "python3 /home/brian/ranger/nmea_sim.py /tmp/gps_feed --site nairobi"'

# Orin dead: the PC alone drives a running mission
python manage.py run_simulation --robot RANGER-PRIME-001 --live --live-delay 1 --speed 5 [--region rabat]
```

Before trusting a miss: read the sim's `closest approach` line. wp1 must be well
outside the threshold (TS-047).

---

## Gotchas

- **A move inside a `styledata` handler must be conditional.** `moveLayer` emits
  `styledata`; an unconditional move in `installLayers` loops forever and `load` never
  fires — every `FieldMap` freezes (TS-046). `ensureRouteOrder` moves only when wrong.
- **`--offset-east-m` is geometry-dependent** (TS-047). It shifts the walk east; a leg
  that runs east–west passes its own waypoints anyway. The miss holds because of the
  no-skip rule, so what matters is wp1's closest approach — which the sim prints.
- **A stale IN_PROGRESS mission swallows fixes** (TS-048). Check before migrating and
  before a bench run: `SELECT robot_id, count(*) FROM missions_mission WHERE
  status='IN_PROGRESS' GROUP BY robot_id;`
- **`FieldMap` draws blips only with `showOverlays`** (TS-049).
- **Fast sim, edge distances.** At 5 m/s a fix lands ~5 m before each waypoint; with
  jitter it may complete at 4.9 m or wait for the waypoint fix itself. Both are right.
- **Rows attach from START, not from the route.** Between START and the route walk,
  stationary-site fixes join the mission; that is the rule (every stored fix of a
  running mission belongs to it), not noise.
- **`pytest-django` wraps tests in `atomic()`.** The "advance refuses outside a
  transaction" test must be `transaction=True`, or it can't fail.
- **`authed_client` and `api_client` are the same object** in `conftest.py`; an
  "anonymous" check needs a fresh `APIClient()`.

---

## Open items

- **➡️ 6d — real robot run.** Teleop the 6WD outdoors through a real waypoint set;
  completion by real GPS. Needs: the **fuse** in the 3S lead, the **motor capacitors**
  (then `max_pwm` above 120), and the first located LIVE row under sky (F13). Record
  it here under Sign-off evidence when it happens.
- **Who may plan.** A client account (`client@magadi.com`) sees the planning UI for the
  console's robot; saving fails "robot does not exist", so nothing leaks. Decide
  whether planning needs a permission (like START) and hide the panel without it.
- **Perpendicular miss offset.** Replace `--offset-east-m` with an offset
  perpendicular to leg 1 so wp1 is missed by exactly the offset on any route (TS-047).
- **Suspected, unverified:** `FieldMap` moves the satellite raster under the track on
  every `styledata`, unconditionally — the TS-046 pattern. With a raster shown it may
  loop after `load` (CPU, not a freeze). Check on `/satellite` with the performance
  panel; guard it like `ensureRouteOrder` if so.
- **Live-status helpers duplicated.** `MissionControlPage` repeats the dashboard's
  5 s staleness and blip-status rule; move both into `lib/` when either changes.
- **Pre-existing:** `ros_ingest.py` imports `time` unused (ruff F401); 9 eslint
  problems (as F14).
