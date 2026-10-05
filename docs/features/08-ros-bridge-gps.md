# F08 — ROS Bridge: GPS → SensorLog

*Date: 2026-09-28 · Signed off: 2026-10-03*
*Branch: `feat/ros-bridge-gps` (from `feat/postgis-foundation`)*
*Status: **complete.** Real GPS fixes landed in Postgres as `live` rows, verified by query.*

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
| Real sky — NEO-6M via FTDI USB, `--source live` | 22 `live` rows, verified by query | ✅ 2026-10-03 |

See [`ADR-0014`](../decisions/0014-robot-code-in-repo-gps-on-header-uart.md)
(amended 2026-10-03) and
[`ADR-0015`](../decisions/0015-ros-ingest-provenance-timestamps-threading.md).

---

## Sign-off evidence (2026-10-03)

Outdoors. NEO-6M on a `GY-GPS6MV2` /
`HW-248` carrier, through an FTDI FT232R cable into the Orin's USB.

Fix quality at sign-off: `qual=1`, **4–5 satellites, HDOP 3.0–3.3** — a marginal
fix. Cold start took roughly 15 minutes, most of it beside a wall where the
satellites in view were bunched (HDOP climbed past 45 with 4 satellites and the
receiver correctly refused to declare a fix). Moving to open sky fixed it.

```
$ python manage.py ros_ingest --source live
Connected. /fix -> SensorLog for RANGER-PRIME-001 (source=live). Ctrl-C to stop.
SensorLog #24643: -0.424254, 36.971360 [live] @ 14:06:05Z
...
SensorLog #24664: -0.424347, 36.971518 [live] @ 14:06:26Z
Stopped. {'no_fix': 8, 'saved': 22}
```

```
$ python manage.py shell -c "...filter(robot__robot_id_str='RANGER-PRIME-001', source='live')..."
live rows: 22
24664 2026-10-03 14:06:26.643255+00:00 -0.4243468333333333 36.971518 live
```

- `saved` equals the row count; every row `live`; coordinates match the raw NMEA
  and are not inverted.
- `no_fix: 8` — the fix dropped at the end of the run; skipped, nothing stored.
- Timestamps are the robot's stamps; zero `clock_skew` skips (after the clock was
  corrected — see TS-025).
- **Stationary jitter: ~21 m over 20 s** (18 m E–W, 11 m N–S) with the receiver
  not moving. That is the real accuracy of a 4–5 satellite, HDOP-3 fix, and it
  bounds any ground-truth claim made from fixes of this quality.
- Ctrl-C exits with `Stopped. {...}` and no traceback.

---

## Topology

```
ORIN (aarch64, headless, USB-tethered)                 PC (x86_64, Django, Postgres)
─────────────────────────────────────                  ──────────────────────────────
NEO-6M ──FTDI USB── /dev/serial/by-id/usb-FTDI_…       
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

---

## Files

| File | Runs on | Role |
|---|---|---|
| `robot/gps_node.py` | Orin | Reads NMEA, publishes `NavSatFix` on `/fix`. Params: `port` (default `/dev/ttyTHS1` — **pass the FTDI by-id path instead**, see ADR-0014), `baud` (9600), `frame_id` (`gps`) |
| `robot/tools/nmea_sim.py` | Orin | Synthetic GGA at 1 Hz: 3 no-fix sentences, then fixes near Nairobi CBD. Test tool |
| `robot/tools/gps_listen.py` | PC | 1a checkpoint probe: prints `/fix` over rosbridge. Throwaway |
| `ranger_backend/ros_bridge/management/commands/ros_ingest.py` | PC | Subscribes to `/fix`, writes `SensorLog` |
| `ranger_backend/requirements/base.txt` | — | `roslibpy==2.1.0` |

The Orin runs copies of the `robot/` files in `~/ranger/`, deployed with `scp`
(ADR-0014).

---

## Hardware (as signed off)

GPS → FTDI FT232R cable (colours per **this** cable's listing — not the genuine
FTDI code):

| GPS board | Cable wire |
|---|---|
| VCC | red (5 V) |
| GND | black |
| **TX** | **white** (cable RXD) |
| RX | leave unconnected — nothing is ever sent to the GPS |

The cable's **green is its TXD.** Never join it to a GPS TX.

Port: `/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_AZ6YQ8AI-if00-port0` — stable
across reboots and replugs, unlike `ttyUSB0`. `brltty` was installed on the Orin
and has been removed (TS-026).

The header UART (`/dev/ttyTHS1`, pins 8/10) passes loopback but has never
received NMEA from a live module; see TS-023.

---

## Running it

**Once per boot — clock first.** `ros_ingest` skips fixes more than 120 s from
server time.

```bash
# PC: give the Orin internet (resets on every PC reboot)
bash ~/jetson-internet.sh
# Orin: compare against a real reference, not just the sync flag
date -u          # vs the PC's date -u (in a PC terminal), or vs the GPS's GGA time
# If off, set it from the PC — in a PC terminal:
ssh -t brian@192.168.55.1 "sudo date -s @$(date +%s)"
```

**Watch for a fix before starting the node** (Orin):

```bash
P=/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_AZ6YQ8AI-if00-port0
stty -F $P 9600 raw -echo
grep --line-buffered -a '^\$GPGGA' $P | mawk -W interactive -F, '{print $2, "qual="$7, "sats="$8, "hdop="$9, $3 $4, $5 $6}'
```

`mawk -W interactive` matters: plain `awk` (mawk on Ubuntu) block-buffers piped
input and prints nothing for about a minute. Go on `qual=1`, 6+ sats, HDOP < ~2.5.
**Ctrl-C the watcher before starting the node** — two readers on one serial port
split the bytes and both get broken lines.

**Robot side (Orin, one session each):**

```bash
python3 ~/ranger/gps_node.py --ros-args -p port:=/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_AZ6YQ8AI-if00-port0
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

Simulated instead:

```bash
socat -d -d pty,raw,echo=0,link=/tmp/gps_sim pty,raw,echo=0,link=/tmp/gps_feed
python3 ~/ranger/gps_node.py --ros-args -p port:=/tmp/gps_sim
pkill -f nmea_sim.py; python3 ~/ranger/nmea_sim.py /tmp/gps_feed   # LAST
```

**Platform side (PC, `(.venv)`):**

```bash
cd ranger_backend
python manage.py ros_ingest                     # source=simulated (default)
python manage.py ros_ingest --source live       # ONLY with a real receiver under sky
```

**Verify in the database — never trust stdout:**

```bash
python manage.py shell -c "from core.models import SensorLog as S; q=S.objects.filter(robot__robot_id_str='RANGER-PRIME-001', source='live'); print('live rows:', q.count()); [print(r.pk, r.timestamp, r.latitude, r.longitude, r.source) for r in q[:3]]"
```

---

## Gotchas

**NaN arrives as `None`.** No-fix messages carry NaN; JSON has no NaN, so
rosbridge sends `null`. `ros_ingest` gates on `status.status < 0` first.

**`STATUS_FIX` is 0, not 1.** `NO_FIX=-1`, `FIX=0`, `SBAS_FIX=1`, `GBAS_FIX=2`.

**`latitude`/`longitude` are not fields** — read-only properties of `location`
since F10.1. Writes go through `point_from_latlon(lat=…, lon=…)`.

**The ORM cannot run in the roslibpy callback** (TS-027).

**`point_from_latlon` rejects anything outside Kenya** — every Rabat fix would be
`out_of_region`. See open items.

**Talker IDs differ by receiver.** The NEO-6M sends `$GPGGA`; the M8N sent
`$GNGGA`. The node accepts both.

**A wall halves the sky.** Satellites bunched on one side give HDOP in the tens
and no fix, however long you wait. Move, don't wait.

**`synchronized: no` ≠ wrong clock, and `date -u` twice in one shell compares
nothing.** Check the Orin against the PC (separate terminals) or the GPS's UTC.

---

## Skip accounting

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

- **Rabat: `--region`** on `ros_ingest`. Without it the finale writes zero rows.
- **Field time.** No NTP away from the PC; the Orin has no running RTC and was
  22 minutes slow on 2026-10-03. GPS UTC is the obvious field reference.
- **Header UART undiagnosed** (TS-023). Lead theory: wired to the wrong row.
  Five-minute loopback test at the exact positions used.
- **Second FTDI adapter** for the PM sensor — this one is now the GPS's.
- **Static `/etc/resolv.conf` must be verified across a reboot** (TS-025).
- Fix quality is not carried into the row: no HDOP, no satellite count, and
  `position_covariance` is published as unknown. Ground-truth claims need it.
- No robot-side buffering; foreground command, not a service (P5c);
  `mission=None`; manual `scp` deployment.
