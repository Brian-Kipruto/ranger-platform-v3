# F08 — ROS Bridge: GPS → SensorLog

*Date: 2026-09-28*
*Branch: `feat/ros-bridge-gps` (from `feat/postgis-foundation`)*
*Status: **sim-verified end to end. Real-sky sign-off pending a replacement NEO-M8N.***

---

## What this feature does

Pass 0 proved the pipe: a string crossed from ROS on the robot to Python on the
PC over rosbridge. F08 proves the pipe carries **real data into the database**:
a GPS fix on the Orin becomes a `SensorLog` row in Postgres, tenanted to
`RANGER-PRIME-001`, with honest provenance.

This is the first code in the `ros_bridge` app and the first code in the repo
that runs on the robot. Every later sensor follows the same template: a node
publishes a standard message, `ros_ingest` turns it into a `SensorLog`, and a
reading table hangs off that log.

| Stage | Proven with | Status |
|---|---|---|
| 1a — NMEA → `/fix` on the Orin → rosbridge → PC | `nmea_sim` over a socat pty | ✅ `4811dbb` |
| 1b — `/fix` → `SensorLog` in Postgres | 24 `simulated` rows, verified by query | ✅ `74553b7` |
| Real sky — NEO-M8N on `/dev/ttyTHS1`, `--source live` | — | ⏳ module destroyed; replacement ordered |

**F08 is not signed off until real coordinates land as `live` rows.**

See [`ADR-0014`](../decisions/0014-robot-code-in-repo-gps-on-header-uart.md) and
[`ADR-0015`](../decisions/0015-ros-ingest-provenance-timestamps-threading.md).

---

## Topology

```
ORIN (aarch64, headless, USB-tethered)                 PC (x86_64, Django, Postgres)
─────────────────────────────────────                  ──────────────────────────────
NEO-M8N ──UART── /dev/ttyTHS1                          
   (or nmea_sim ── socat pty ── /tmp/gps_sim)          
            │                                          
      robot/gps_node.py                                
            │ sensor_msgs/NavSatFix on /fix            
      rosbridge_server :9090  ──── USB network ────►  ros_ingest (roslibpy)
                                  192.168.55.1          │ queue → main thread
                                                        ▼
                                                  core.geo.point_from_latlon
                                                        ▼
                                                  SensorLog (Postgres/PostGIS)
```

The ingest command runs on the PC because that is where Django runs. The 1a
checkpoint probe (`gps_listen.py`) deliberately ran there too, so 1a proved the
exact network path 1b depends on.

---

## Files

| File | Runs on | Role |
|---|---|---|
| `robot/gps_node.py` | Orin | Reads NMEA, publishes `NavSatFix` on `/fix`. Params: `port` (default `/dev/ttyTHS1`), `baud` (9600), `frame_id` (`gps`) |
| `robot/tools/nmea_sim.py` | Orin | Writes synthetic GGA at 1 Hz: 3 no-fix sentences, then fixes near Nairobi CBD. Test tool |
| `robot/tools/gps_listen.py` | PC | 1a checkpoint probe: prints `/fix` over rosbridge. Throwaway |
| `ranger_backend/ros_bridge/management/commands/ros_ingest.py` | PC | Subscribes to `/fix`, writes `SensorLog` |
| `ranger_backend/requirements/base.txt` | — | `roslibpy==2.1.0` |

The Orin runs copies of the `robot/` files in `~/ranger/`. Deployment is manual
for now (`scp`); see ADR-0014.

---

## Running it

**Orin — once per boot:**

```bash
# PC first, if the Orin needs internet (apt, pip, NTP): restore NAT
bash ~/jetson-internet.sh
# Orin: confirm the clock is real — ros_ingest rejects skewed stamps
timedatectl | grep synchronized          # expect: yes
```

**Orin — the robot side (one SSH session each):**

```bash
# Real GPS
python3 ~/ranger/gps_node.py --ros-args -p port:=/dev/ttyTHS1
# ...or simulated:
socat -d -d pty,raw,echo=0,link=/tmp/gps_sim pty,raw,echo=0,link=/tmp/gps_feed
python3 ~/ranger/gps_node.py --ros-args -p port:=/tmp/gps_sim
python3 ~/ranger/nmea_sim.py /tmp/gps_feed        # start LAST to see the no-fix path

ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

**PC — the platform side (`(.venv)` active):**

```bash
cd ranger_backend
python manage.py ros_ingest                     # source=simulated (default)
python manage.py ros_ingest --source live       # ONLY with a real receiver under sky
```

Expected:

```
Connected. /fix -> SensorLog for RANGER-PRIME-001 (source=simulated). Ctrl-C to stop.
SensorLog #24640: -1.286405, 36.817183 [simulated] @ 13:32:48Z
...
Stopped. {'saved': <n>, 'no_fix': <n>, ...}
```

**Verify in the database — never trust stdout:**

```bash
python manage.py shell -c "from core.models import SensorLog as S; q=S.objects.filter(robot__robot_id_str='RANGER-PRIME-001', provenance_note__startswith='ros_bridge'); print('rows:', q.count()); [print(r.pk, r.timestamp, r.latitude, r.longitude, r.source) for r in q[:3]]"
```

```
rows: 24
24642 2026-09-28 13:32:50.781670+00:00 -1.2864166666666668 36.817225 simulated
24641 2026-09-28 13:32:49.781673+00:00 -1.2863933333333333 36.81717666666667 simulated
24640 2026-09-28 13:32:48.781653+00:00 -1.286405 36.81718333333333 simulated
```

Row count must equal `saved`; coordinates must be ~`-1.2864, 36.8172` (not
inverted); every row `simulated`.

---

## Switching to the real GPS

No code change. Two flags:

1. Orin: `-p port:=/dev/ttyTHS1` on the node.
2. PC: `--source live` on `ros_ingest`.

Wiring (Orin **powered off**, pins counted by touch — see TS-023 and TS-024):

| NEO-M8N board | Orin 40-pin |
|---|---|
| VCC | pin 2 (5V) |
| GND | pin 6 |
| **TX** | **pin 10** (UART RXD) |
| **RX** | **pin 8** (UART TXD) |

Sanity check before any ROS: `stty -F /dev/ttyTHS1 9600 raw -echo -crtscts; timeout 5 cat /dev/ttyTHS1`
must show `$GN…` sentences. Indoors they carry empty lat/long — expected.

---

## Gotchas

**NaN arrives as `None`.** The node publishes NaN lat/long without a fix. JSON has
no NaN, so rosbridge sends `null` and roslibpy yields `None`. The original spec's
guard (`lon != lon`) would never have fired. `ros_ingest` gates on
`status.status < 0` first, then treats `None` or NaN as a skip.

**`STATUS_FIX` is 0, not 1.** `NavSatStatus`: `NO_FIX=-1`, `FIX=0`, `SBAS_FIX=1`,
`GBAS_FIX=2`. The Pass 1 vault spec had this wrong in its expected output.

**`latitude`/`longitude` are not fields.** Since F10.1 they are read-only
properties derived from `location`. The Pass 1 vault spec's
`SensorLog.objects.create(latitude=…, longitude=…)` would raise. All writes go
through `point_from_latlon(lat=…, lon=…)`.

**The ORM cannot run in the roslibpy callback** (TS-027). The callback only
enqueues; the main thread writes.

**`point_from_latlon` rejects anything outside Kenya.** Its default region is the
inversion tripwire. Fixes outside it are skipped as `out_of_region`. This
**will reject every fix in Rabat** — see open items.

**The M8N talks `$GN`, not `$GP`.** Multi-constellation talker IDs. The node
accepts both `$GPGGA` and `$GNGGA`.

**Stray sims interleave.** A second `nmea_sim` on the same pty produces two fix
streams per second. `pkill -f nmea_sim.py` before starting one.

---

## Skip accounting

Nothing is dropped silently. Every message ends in exactly one counter, printed
on exit:

| Counter | Meaning |
|---|---|
| `saved` | Row written |
| `no_fix` | `NavSatStatus < 0` |
| `no_coords` | lat/lon `None` or NaN |
| `clock_skew` | Robot stamp differs from server time by > `--max-skew` (120 s) |
| `out_of_region` | `point_from_latlon` region tripwire |
| `dropped` | Inbox full (1,000) — the main thread fell behind |
| `error` | Anything else, printed as it happens |

---

## Open items

- **Real-sky sign-off** — replacement NEO-M8N on `/dev/ttyTHS1`, `--source live`,
  rows verified in Postgres. The header-UART wiring has never carried a live
  module end to end (TS-023/024).
- **Rabat: add `--region`** to `ros_ingest` (a Morocco bbox, or `none`). Without
  it the finale demo writes zero rows.
- **Field clock.** Away from the PC's NAT there is no NTP, and the Orin's RTC
  reads 1970. After a field reboot the clock resumes from its last saved value
  and every fix fails the skew guard. Needs a set RTC or GPS-disciplined time.
- Readings are lost while `ros_ingest` is not running; no robot-side buffer.
- `ros_ingest` is a foreground command, not a supervised service (P5c).
- Rows carry `mission=None`.
- Robot deployment is manual `scp` (ADR-0014).
