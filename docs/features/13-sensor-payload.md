# F13 — Sensor Payload

*Date: 2026-10-14 (built and proven 2026-10-13 → 14)*
*Branch: `feat/sensor-payload` (from `main` @ `8142a95`)*
*Status: **closed with three items gated on hardware or location.** Every reading on a row carries its own provenance; readings attach to a GPS fix only when fresh; the 10-DOF board's roll, pitch and pressure reach the stack live; radiation is simulated behind a seam where a real tube is one parameter; the console, Data Explorer, CSV and Visualizations label each reading by its own source. Open: the first located LIVE row (needs sky), the SDS011 (needs a CP2102 adapter), magnetometer calibration. See Open items.*

Pass 5 in the vault was split at fork 0: **F13 = sensor payload** (5-pre, 5c, 5d),
**F14 = drive and video** (5a, 5b, 5e). Nothing in F14 is built here.

---

## What this feature does

Before F13 a row had one label, `SensorLog.source`, and `ros_ingest` wrote
positions only. Pass 5 puts a simulated Geiger, a real IMU and (later) a real
SDS011 on the same row as a real GPS fix. One label can't describe that: a
live row would either call its simulated radiation LIVE or call its real
position SIM.

- **Per-reading provenance (ADR-0020 Decision 1).** `RadiationLog`,
  `AirQualityLog` and `ImuBaroLog` each have their own `source`, NOT NULL,
  default `simulated`. The row's `source` now labels the **position** only.
  No inheritance: an unlabelled reading under-claims.
- **The robot claims, the operator caps (Decision 2).** Each reading message
  carries the node's own claim; ingest stores the weaker of that claim and
  `--source`. The sim radiation node cannot emit `live`; `dev_up.sh sim` forces
  everything to `simulated`.
- **Assembly (Decision 3).** `ros_ingest` subscribes to three reading topics,
  keeps the latest of each, and on each accepted `/fix` attaches every reading
  within its freshness window (robot time), **consume-once**. Stale readings
  are dropped; no fix → no row. One transaction per row.
- **`ranger_msgs` (Decision 4).** One message per DB table, each with a header
  stamp and a `source` claim: `/ranger/radiation`, `/ranger/air_quality`,
  `/ranger/imu_baro`. A PC test reads the `.msg` files and fails if they and
  `readings.py` drift.
- **The Geiger seam (ADR-0021).** `radiation_node` asks a count source for
  counts, windows them into CPM, publishes the source's claim. `sim` (Poisson,
  operator hot spot) today; `uno` (real tube via `/ranger/geiger_counts`, LIVE)
  ready. A stale feed publishes **nothing**, never zero.
- **Real IMU.** `imu_node` reads the MPU6050, QMC5883L and BMP180 on I²C bus 7,
  rotated into the robot frame by `imu_mount.json`. Heading is published as
  NaN (stored null) until the magnetometer is calibrated.
- **Honest screens.** The live console, Data Explorer, CSV export, map summary,
  Visualizations and SENSOR STREAMS show each reading's own source. The
  Dashboard's invented LIVE TELEMETRY values (F07 demo) are gone.

| Checkpoint | Proven with | Status |
|---|---|---|
| 5-pre 1 — per-reading `source`, backfill | migration on the real DB: 12,511 + 430 readings relabelled, 0 mismatches; 4 mutations | ✅ `824a90c` |
| 5-pre 2 — assembly in `ros_ingest` | 25 tests, 10 mutations (one survivor pinned); T0 flake found and fixed | ✅ `da38a59` |
| 5-pre 3a — `ranger_msgs` | colcon build on the Orin; contract test, 9 mutations incl. manifest | ✅ `be4f5da` |
| 5-pre 3b — Geiger seam, sim parity, `stack_up` | 62 rows with all three readings, SIM; hot-spot ramp 6.8 CPM/s (model 6.67); 6-case harness | ✅ `983d58d` |
| 5c — IMU node + mount | bench + tip test on the robot; 67 tests, 20 mutations | ✅ `3e136b7` |
| 5c — IMU in live mode | live stack readings check; 30 s no-fix negative, 0 rows | ✅ `385d3de` |
| 5c — SDS011 | header UART ruled out (TS-034) | 🧊 needs a CP2102 |
| 5c — positive located LIVE row | — | 🧊 needs sky |
| 5c — Orbbec IMU as telemetry | — | ➡️ moved to F14 (needs the Orbbec on the Orin) |
| 5d-1 — real-tube count source | bench swap on the Orin: `cpm 120.0 · source live`; stale → silent in ~3 s | ✅ `dbcb28e` |
| 5d-2 — live console readings | visual sign-off; stale/recovery | ✅ `8d87889` |
| 5d-3a — API, CSV, map summary | 6 tests, 6 mutations incl. tenancy | ✅ `4a40828` |
| 5d-3b — Explorer, Visualizations, Streams | visual sign-off; banner logic run | ✅ `2df3b08` |

Decisions: [ADR-0020](../decisions/0020-per-reading-provenance-and-assembly.md),
[ADR-0021](../decisions/0021-geiger-seam.md).
Troubleshooting: [TS-034](../troubleshooting/034-orin-header-uart-rx-zeroes-bytes.md),
[TS-035](../troubleshooting/035-imu-reads-tilted-wrong-mount-assumption.md).

---

## Sign-off evidence (2026-10-13 → 14; hardware runs: Brian)

### 5-pre — the data path

**Migration 0009 on the real DB:** `RadiationLog: 12511`, `AirQualityLog: 430`,
`ImuBaroLog: 0` readings labelled from their row; a join of every reading
against its row: **0 mismatches** on all three tables.

**Assembly** (sandbox, PostGIS): fresh readings attach, stale don't, no fix → no
row, consume-once, window edges, weakest-of claim and ceiling, atomic row.
Mutation survivor *stale reading kept in the cache* was pinned before handoff.
The test file's module-level `T0 = time.time()` aged past the 120 s skew guard
in a full run (19 spurious failures at 141 s); now reset per test.

**`ranger_msgs` on the Orin:** `colcon build` 16 s; `ros2 interface show`
matches the contract; `SOURCE_LIVE`/`SOURCE_SIMULATED` = `'live'`/`'simulated'`.
First build failed on the manifest (see Gotchas); the PC test now parses
`package.xml` with `catkin_pkg` exactly as colcon does.

**End to end (sim stack):** 62 rows saved and broadcast; `imu_baro_attached 62`,
`air_quality_attached 61`, `radiation_attached 61` (row 1 was the first fix,
before the other nodes published); 0 stale. CPM 33–37 around 30 background,
pressure 829 hPa (Nairobi), yaw advancing ~3.4°/s as simulated. Every source
`simulated`, dose null.

**Hot spot:** `hotspot_cpm 400.0` → CPM 27 → 244 over 32 s, **6.8 CPM/s**
against the 60 s window's 400/60 = 6.67.

**`stack_up.sh`** — fresh start prints both checks:
```
ok: /fix publishing · mode=sim:nairobi · rosbridge :9090 · tmux attach -t ranger
ok: readings publishing · /ranger/radiation:Radiation /ranger/air_quality:AirQuality /ranger/imu_baro:ImuBaro
```
Stub harness (fake tmux/ros2/timedatectl, real listener on :9090), 6 cases:
overlay missing → refused before any session; all topics → ok; one topic
silent → FAIL, session kept, marker `failed`; live → radiation (+IMU) only;
`sensor_sim.py` missing in sim → refused. `shellcheck` clean.

### 5c — real sensors

**Header UART (SDS011's planned port):** dead for receiving — see TS-034. GPS
stays on the FTDI. Rows identified by function (FTDI GND on pin 6 worked).

**10-DOF board on I²C bus 7** (`c250000`, header pins 3/5, VCC pin 1 3.3 V):
`0x68` MPU6050 (`WHO_AM_I` 0x68), `0x77` BMP180 (chip id 0x55), `0x0d`
QMC5883L once the MPU6050's I²C bypass is on (`INT_PIN_CFG` 0x02; resets on
power-cycle — `imu_node` sets it every start).

**Bench, before the mount fix:** roll −166°, pitch +80° at rest — correct
readings of a board mounted vertically under a flat-mount assumption (TS-035).

**After `imu_mount.json` (`forward -z`, `up -x`) on the robot:**

| Position | Read |
|---|---|
| On blocks | roll +2.4, pitch −9.5 (the bracket's ~10° lean) |
| Rear lifted (nose down) | pitch → +20 |
| Left lifted (right down) | roll → +24 … +38 |
| Right lifted | roll → −25 |
| Front lifted (nose up) | pitch → −26 |

All four signs as REP-103. `heading_raw` held 183–192° through tilts up to 38°
(187° at rest): tilt compensation works and the magnetometer's axes match the
MPU6050's. `/ranger/imu_baro` at 9.9–10.0 Hz, `yaw: .nan`, `source: live`;
831.6 hPa ±0.05, 1635 m (no weather correction). BMP180 maths reproduces the
datasheet example (15.0 °C, 69,964 Pa). The clockwise-turn check is deferred to
calibration.

**Live mode on the tether (no sky):** `ok: readings publishing ·
/ranger/radiation:Radiation /ranger/imu_baro:ImuBaro`. Ingest `--source live`
for exactly 30 s: `Connected` in 9 ms, then `Stopped. {'no_fix': 30}` — real
IMU and radiation publishing throughout, **zero rows, zero readings attached**.

### 5d — the seam and the screens

**Real-tube swap on the Orin**, counts faked with `ros2 topic pub` (ingest NOT
running — fake counts through `uno` would be stored LIVE):

| Proof | Result |
|---|---|
| `count_source:=uno`, no counts | `no geiger data: publishing nothing…`; `echo --once` → exit 124 |
| `hotspot_cpm` on `uno` | `Setting parameter failed: hotspot_cpm only exists with count_source:=sim` |
| 2 counts/s | `cpm: 120.0`, `dose_rate_usvh: .nan`, **`source: live`** |
| feed stops | `no geiger data` 3.0–3.1 s after the last count (stale 3 s + ≤1 tick) |

**Live console:** each tile its own SIM chip; invented 14.2/29/842/24.6 gone;
TEMP → HEADING; stale → all "—" (checked by Brian); ingest restart → values
back within ~1 s.

**API/CSV/map** (real DB): newest sim rows `simulated` on all four labels; a
Marsabit row `modelled` position and radiation, `None` where no reading.

**Data Explorer** (3,070 rows): `MIXED PROVENANCE — NOT MEASUREMENTS: POINTS
3,036/3,070 · RADIATION 888/888 · PM 888/888 · IMU 461/461`; column header
**Position**; cards `n=888 · SIM 888`. **Visualizations:** `(n=1047 · SIM
1,047)` on every stat line. **SENSOR STREAMS:** `FROM DB` + SIM chips.

The banner logic run directly: LIVE positions + SIM radiation →
`MIXED PROVENANCE — NOT MEASUREMENTS: RADIATION 10/10` (before F13: no banner).

**Final suite:** 505 passed on the PC (2 GEE integration tests included);
frontend `tsc -b` clean, build clean, `eslint` clean on every changed file.

---

## Files

| File | Deployed as | Role |
|---|---|---|
| `ranger_backend/core/migrations/0009_reading_source.py` | — | reading `source` + backfill from the row, one transaction |
| `ranger_backend/ros_bridge/readings.py` | — | topic specs, freshness windows, `ReadingCache`, weakest-of |
| `ranger_backend/ros_bridge/management/commands/ros_ingest.py` | — | subscribes to readings; attaches in the row's transaction |
| `ranger_backend/ros_bridge/broadcast.py` | — | live payload gains `readings`, each with its own source |
| `ranger_backend/core/serializers.py`, `core/views.py` | — | `*_source` fields; CSV columns; map props; `provenance.readings` |
| `robot/ranger_msgs/` | Orin `~/ranger/ws/src/ranger_msgs` (colcon) | `Radiation`, `AirQuality`, `ImuBaro` |
| `robot/sensor_sources.py` | Orin `~/ranger/` | Geiger seam (`SimCounts`, `UnoCounts`, `CpmWindow`, `RadiationTicker`), sim PM/IMU models |
| `robot/radiation_node.py` | Orin `~/ranger/` | `/ranger/radiation`, 1 Hz |
| `robot/sensor_sim.py` | Orin `~/ranger/` | sim `/ranger/air_quality` 1 Hz, `/ranger/imu_baro` 10 Hz (sim mode only) |
| `robot/imu_math.py`, `robot/imu_node.py` | Orin `~/ranger/` | 10-DOF board → `/ranger/imu_baro`, 10 Hz (live mode) |
| `robot/config/imu_mount.json` | Orin `~/ranger/config/imu_mount.json` | which sensor axes point forward/up |
| `robot/tools/stack_up.sh` | Orin `~/ranger/stack_up.sh` | sources the overlay; starts and checks the reading nodes |
| `ranger_frontend/src/lib/readingProvenance.ts` | — | banner over positions + readings; breakdowns |
| `ranger_frontend/src/components/dashboard/liveTelemetrySpecs.ts` | — | live tiles from the feed; "—" rules |
| `ranger_frontend/src/stores/liveStore.ts` | — | parses `readings`; 60-sample history |

Nothing is installed outside `~/ranger/` on the Orin. PC dev requirement:
`catkin_pkg==1.1.1` (manifest test).

## Install / deploy (record of what was done)

**Orin, once (brian@jetson-orin):** `~/ranger/ws` is a colcon workspace holding
only `ranger_msgs` (the Orbbec workspace is separate).
```bash
mkdir -p ~/ranger/ws/src ~/ranger/config
# from the PC: scp -r robot/ranger_msgs brian@192.168.55.1:~/ranger/ws/src/
cd ~/ranger/ws && source /opt/ros/humble/setup.bash
colcon build --packages-select ranger_msgs        # ~16 s
```
Rebuild after any `.msg` change, then restart the stack (rosbridge loads the
types at start).

**Deploy (PC, repo root):**
```bash
scp robot/{sensor_sources,radiation_node,sensor_sim,imu_math,imu_node}.py robot/tools/stack_up.sh brian@192.168.55.1:~/ranger/
scp robot/config/imu_mount.json brian@192.168.55.1:~/ranger/config/
# compare sha256sum on both machines
```

## Running it

Unchanged: `scripts/dev_up.sh [sim|live] [nairobi|rabat] [usb|wifi]`, then the
three PC terminals it prints. `stack_up.sh` now also starts `radiation_node`
(both modes, `count_source:=sim`) and `sensor_sim` (sim) or `imu_node` (live),
and fails unless every expected reading topic publishes.

```bash
# Orin: what's on the wire
ros2 topic echo --once /ranger/radiation ranger_msgs/msg/Radiation
ros2 topic hz /ranger/imu_baro
# demo hot spot (sim source only; the value must be a float)
ros2 param set /radiation_node hotspot_cpm 400.0     # ramps over ~60 s
ros2 param set /radiation_node hotspot_cpm 0.0
```

The real tube, when it works: F14's `uno_bridge` publishes `G,<counts>` lines on
`/ranger/geiger_counts` (`std_msgs/UInt32`); change `count_source:=sim` to
`count_source:=uno` in `stack_up.sh`. Nothing else (ADR-0021).

## Gotchas

**A real reading on a sim row is stored `simulated`.** The ceiling is the
operator's `--source`: in sim mode a real IMU reading is capped, by design — a
real value at a fake position isn't ground truth. The IMU's located LIVE row
needs live mode and a GPS fix.

**Readings with no fix write nothing.** Indoors in live mode every fix is
`no_fix`; the IMU publishes and nothing lands. Correct, not broken.

**`ros2 topic pub` loses its first messages** before discovery, and
`radiation_node`'s stale timer counts from the **last count received**, not
from when the publisher process exits.

**`colcon` refused `maintainer@localhost`.** catkin_pkg wants a dotted domain.
The PC contract test now parses the manifest with catkin_pkg first.

**The I²C bypass resets on power-cycle.** Without it the QMC5883L is invisible
(hidden behind the MPU6050). `imu_node` sets it each start.

**The 10-DOF board is mounted vertically.** Remount → edit `imu_mount.json`,
redo the tip test (TS-035).

**Heading is null until calibration**, by design. `heading_raw` in the node's
1 Hz log line is uncalibrated and log-only.

**Roll and pitch come from the accelerometer alone** — fine at rest; while
driving, acceleration leaks in. A gyro filter is later work.

**Commands that fooled us:** `psql` piped from `docker exec -it` opens a pager
and hangs (use `-i` and `-P pager=off`); Python piped into `grep` buffers its
output (use `python -u`); `tail -6` cut off the `ok:` lines.

**GitHub over port 22 is blocked on this network.** `~/.ssh/config` on the PC
routes `github.com` to `ssh.github.com:443`.

## Open items

- **🧊 First located LIVE row** — live mode with sky (window or outdoors):
  `SensorLog` `live`, `imu_baro` `live`, `radiation` `simulated` on the same row;
  the first per-cell SIM chip in the Data Explorer next to a LIVE position.
- **🧊 SDS011** — buy a **CP2102** USB-UART (not CH340, TS-022); then an
  `sds011_node` (frame parser syncing on `AA C0`, checksum), live mode only,
  `/ranger/air_quality` added to the live readings check.
- **🧊 Magnetometer calibration** — a capture tool (min/max per axis over 2–3
  slow turns, board as mounted, motors idle) writing `~/ranger/config/mag_cal.json`;
  then the N/E/S/W check (±10°) and a level trim for the ~10° bracket lean.
- **➡️ F14:** Orbbec IMU as telemetry; `uno_bridge` (owns the Uno's serial port:
  motors + `G,<counts>`); check the Uno is genuine (`2341:`) not CH340 (`1a86:`);
  teleop through an authenticated Channels consumer, not raw rosbridge.
- **Dose factor unknown** — `usvh_per_cpm` stays NaN until the replacement tube's
  datasheet sets it. The repo holds two conflicting factors (0.0057 in
  `run_simulation`, 1/334 in `marsabit`).
- **Header UART** — root cause unconfirmed (TS-034); likely also TS-023's.
- Carried: 4d (Wi-Fi, required for driving on the ground), 4c, AEOC venue
  coordinates, per-robot ingest lock (TS-032).
