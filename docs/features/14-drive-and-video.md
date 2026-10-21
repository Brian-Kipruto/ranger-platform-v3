# F14 — Drive and Video

*Date: 2026-10-20 (5a closed 2026-10-19; 5b, 5e and 4d built and proven 2026-10-19 → 20)*
*Branch: `feat/drive-video` (from `main` @ `f450c24`)*
*Status: **closed with current draw carried to Pass 8.** The 6WD drives from the console through an authenticated path with four independent stop layers under an RC consent switch; the Orbbec Gemini 2 streams from the Orin to a see-and-drive Mission Control screen that refuses to show a frozen frame as live; the whole bench starts and stops with one click; and the robot drives untethered over Wi-Fi behind a console-PC-only firewall, with the same stop margins as on the cable. Open: current draw (meter + USB 3 cable), the motor-noise capacitors, venue network and battery (Pass 8). See Open items.*

Pass 5 in the vault was split at fork 0: F13 = sensor payload, **F14 = drive and
video** (5a, 5b, 5e). Checkpoint **4d** (Pass 4, untethered on Wi-Fi) was on ice
and blocked driving on the ground; it was done here, on this branch, and is
recorded in this document. F12's open item points here.

---

## What this feature does

- **RC arbitration in the Uno (ADR-0022).** The Uno owns the motors. The FS-X6B
  receiver's PPM stream on D3 is filtered (spike check, edge spacing, channel
  count and range, two-frame agreement) because PPM has no checksum. RC link
  lost → stop within 100 ms. Switch A (CH6) selects RC or NET; in NET the Orin's
  `M,<l>,<r>` lines drive, with a 250 ms watchdog.
- **An authenticated teleop path (ADR-0023).** Browser → `TeleopConsumer`
  (`/ws/teleop/<robot>/`, ADR-0016 token auth, `core.drive_robot`, a Redis
  one-driver lease) → channel layer → `teleop_relay` (PC) → rosbridge →
  `/ranger/cmd_vel` → `uno_bridge` (Orin) → Uno. Never browser → rosbridge.
  Four stop layers: browser deadman, relay staleness, bridge staleness, Uno
  watchdog — under the RC link and the switch.
- **Video (ADR-0024).** `web_video_server` on the Orin serves MJPEG straight to the
  browser, bound to one address. Mission Control is the see-and-drive screen:
  camera large, `DrivePanel` beside it, both for the one robot the feed belongs
  to (`VITE_VIDEO_ROBOT_ID`). A single-probe watchdog marks a frozen feed
  **STALE** in about 3 s; removed `<img>` elements close their connection.
- **One-command, one-click bench (ADR-0027).** `stack_up.sh` starts and checks
  drive and video with the sensors; `scripts/ranger_up.sh` runs `dev_up.sh` and the
  four PC services in tmux and opens Mission Control; `ranger_down.sh` stops
  everything cleanly. Dock icons run both.
- **Untethered on Wi-Fi (4d; ADR-0025).** The Orin joins the house Wi-Fi at boot
  with a static address; the PC has a reservation; time comes from the PC over
  Wi-Fi; one `usb|wifi` argument moves every address with it.
- **A console-PC-only firewall (ADR-0026).** rosbridge and the feed are
  unauthenticated, so the Orin accepts `:9090` and `:8080` only from the PC.
  `stack_up.sh` refuses to start unless the rules themselves are in place.

| Checkpoint | Proven with | Status |
|---|---|---|
| 5a — Uno firmware into the repo | unmodified import | ✅ `2fdc2dc` |
| 5a — PPM RC + NET arbitration, 250 ms watchdog | 17 host test functions (`test_drive_logic.cpp`); bench | ✅ `d76d5bf` `f22e9f7` |
| 5a — PPM integrity | two-frame agreement added after a corrupted in-range frame; counters in `S` | ✅ `a116ab6` |
| 5a — `uno_bridge` + udev rule | 18 protocol tests; stale stop 252–298 ms over ~40 stops | ✅ `7e6e928` |
| 5a — `teleop_relay` | 13 tests; 51 queued commands dropped on restart | ✅ `8ebba6a` |
| 5a — `TeleopConsumer`, lease, `grant_drive` | 38 tests incl. the Redis lease backend; 13/13 mutants | ✅ `faa85c0` |
| 5a — Dashboard DRIVE panel | on wheels (blocks): drive, deadman, 4409, disarm, `kill -9` relay | ✅ `b2dc92a` |
| 5b — Orbbec on the Orin → console | 30 fps over USB 2; Mission Control visual sign-off | ✅ `a066bd1` `c4613d1` |
| 5b — frozen-feed watchdog | live, timed: STALE 2.95 s after the last frame; LIVE 0.12–0.9 s; mutation | ✅ `c4613d1` |
| 5b — stream leak + probe memory | one stream per tab after reconnects; +6 MB vs +268 MB per 30 s outage | ✅ `c4613d1` |
| 5e — compute baseline | tegrastats P0/P1/P2 | ✅ (measurement) |
| 5e — stack starts drive + video | 17 harness scenarios; 30 s fresh, 3 s idempotent, negative timed | ✅ `7e03fac` |
| 5e — one-click bench | 7 real-tmux scenarios; 8.1 s up, 7.4 s down, dock icons | ✅ `66c2217` |
| 5e — magnetometer under motor current | raw heading/field per phase, scripted | ✅ (measurement) |
| 5e — current draw | — | ➡️ Pass 8 (needs a meter, USB 3 cable) |
| 4d — Wi-Fi link, clock over Wi-Fi | untethered cold start 49 s; reboot → Wi-Fi in 109–112 s | ✅ `676241e` |
| 4d — firewall | netns test; phone as intruder; reboot check | ✅ `91a1663` `6df3d7b` |
| 4d — first untethered drive | 0 jitter stops over a 10 s hold; relay kill → stop 314 ms; ingest lag 40 ms | ✅ |

Decisions: [ADR-0022](../decisions/0022-rc-arbitration-in-the-uno-over-ppm.md),
[ADR-0023](../decisions/0023-teleop-path-auth-and-stop-layers.md),
[ADR-0024](../decisions/0024-direct-mjpeg-video-and-frozen-feed-watchdog.md),
[ADR-0025](../decisions/0025-wifi-link-and-link-following-config.md),
[ADR-0026](../decisions/0026-console-pc-only-firewall-on-the-orin.md),
[ADR-0027](../decisions/0027-one-click-bench-not-a-console-button.md).
Troubleshooting: [TS-036](../troubleshooting/036-rc-dropouts-under-motor-load.md),
[TS-037](../troubleshooting/037-orin-empty-resolv-conf.md),
[TS-038](../troubleshooting/038-orbbec-gemini2-launch-missing-comma.md),
[TS-039](../troubleshooting/039-mjpeg-leaked-streams-peg-web-video-server.md),
[TS-040](../troubleshooting/040-snapshot-probes-queue-memory-burst.md),
[TS-041](../troubleshooting/041-firewall-rules-wiped-at-boot.md),
[TS-042](../troubleshooting/042-firewall-test-from-pc-masqueraded.md),
[TS-043](../troubleshooting/043-wifi-power-saving-latency.md).

---

## Sign-off evidence (hardware runs: Brian)

### 5a — drive

**Chain:** browser DRIVE panel → `/ws/teleop/<robot>/` → Redis channel
`teleop.robot.<pk>` → `teleop_relay` → rosbridge → `/ranger/cmd_vel` →
`uno_bridge` → `M,<l>,<r>` → Uno → BTS7960.

| Stop layer | Measured |
|---|---|
| Browser deadman (release, Space, blur, hidden tab) | stops on every trigger |
| Relay drops commands > 300 ms old, zero on exit | 51 queued commands all dropped on restart |
| `uno_bridge` `M,0,0` when `cmd_vel` > 250 ms stale | 252–298 ms across ~40 stops |
| Uno watchdog | `m_age=251` |
| RC link lost | `rc_age=100` |

On wheels (blocks), browser: forward, reverse, spin both ways, slider 36–96 PWM;
window switch → stop; second tab → 4409; disarm → zero, robot freed. **C7:**
relay `kill -9` mid-drive with W held → wheels stopped (observed; the same path
timed 252–298 ms elsewhere). RC arbitration: SwA up → RC drives, `M` ignored; TX
off → `X`, `M` ignored; `pkill -9 uno_bridge` mid-drive → Uno stopped on its own.

Auth: 38 tests (incl. the Redis lease backend), 13/13 mutants.
`operator@byteanza.com` is a superuser, so the Drivers-group path is proven by
tests only (open item).

### 5b — video

| Check | Result |
|---|---|
| Camera | Gemini 2 (`2bc5:0670`), firmware 1.4.92, SDK/wrapper 2.8.6, **USB 2.0** via a hub; colour 640×480 @ 30 MJPG |
| Topic rate | 29.6–30.0 Hz |
| `web_video_server` bind | `192.168.55.1:8080` only (later the link's address) |
| Stream to the PC | 149 frames / 5 s |
| Mission Control | LIVE, 4:3, DRIVE beside it, stacks below `lg`; drive + stop from the screen |

**Watchdog, live, against the camera's own `ros2 topic hz` log:**

| Event | Result |
|---|---|
| Camera dies → STALE | 2.9 s (first design); **2.95 s after the last frame** (single-probe design) |
| `web_video_server` killed → STALE | 2.3 s |
| Frames back → LIVE | 0.12–0.9 s |
| Mutation `STALE_AFTER` disabled | LIVE shown over a dead camera for 38 s+, no STALE |

**Leaks found and fixed:** a reconnect left the old MJPEG connection streaming
(two streams from one tab, TS-039) → one stream after camera reconnect,
`web_video_server` reconnect and a page round trip; zero after leaving the page.
Abort-and-reprobe left hanging `/snapshot` requests queued on the server: +268 MB
RSS after a 30 s outage → single outstanding probe: **+6 MB** (TS-040). Sandbox
harness for the hook: 2 probes per 30 s hang (old design 24), mutants killed.

**JPEG quality** (one viewer, 30 fps, all qualities):

| q | kB/frame | MB/s | `web_video_server` CPU |
|---|---|---|---|
| 95 | 57 | 1.7 | 42% |
| 70 | 25 | 0.76 | 40% |
| 50 | 14 | 0.44 | 37% |

Quality moves bandwidth, not CPU. Stream q70, probe q50.

### 5e — together

**Compute** (tegrastats, USB 2, colour only):

| Phase | RAM | CPU avg (6 cores) | Busiest core | `VDD_IN` | tj |
|---|---|---|---|---|---|
| P0 stack + `uno_bridge` | 621 MB | 4.0% | 19% | 3.15 W | 45.3 °C |
| P1 + camera, no subscriber | 701 MB | 5.2% | 22% | 3.20 W | 45.7 °C |
| P2 + `web_video_server` + 1 viewer | 766 MB | 24.2% | 45% | 3.53 W | 46.2 °C |

The Orbbec driver is lazy: no subscriber, almost no cost. One viewer: about 0.7 of
a core, +65 MB, +0.38 W. `VDD_IN` is the module only, not the robot.

**Stack:** fresh 30.2 s; already running 3.1 s; camera unplugged → `FAIL: no
Orbbec camera on USB (2bc5)` at preflight; replug → recovered in 28.9 s. Drive
through the stack: stops on release.

**Launcher:** `ranger_up.sh` 8.1 s with the Orin stack up; `ranger_down.sh`
7.4 s; dock icons both work.

**Magnetometer under motor current** (on blocks, `max_pwm` 120, raw, robot still;
`imu_node` by hand on a remapped topic; phases scripted with local `cmd_vel`):

| Phase | Heading shift | Heading sd | Field change |
|---|---|---|---|
| W60 | 0.0° | 0.5° | 0.2% |
| W120 | −1.5° | 2.9° | 4.6% |
| SPIN120 | +0.3° | 2.1° | 4.6% |
| OFF between | ±0.0° | 0.3–0.5° | 0.4–0.5% |
| final OFF | −0.3° | 0.5° | 3.0% |

At this cap the mean shift is small; the noise triples at full power. Unloaded
motors on blocks draw less than on the ground, so this is a lower bound.

### 4d — untethered

| Check | Result |
|---|---|
| Orin Wi-Fi | `wlP1p1s0`, joins "Brian" at `192.168.0.50`, power saving off |
| Latency, before → after PC power saving off | Orin→PC 68/122 → **8.2/40 ms** avg/max; PC→Orin 15/59 → **6.8/60 ms** |
| Reboot → ssh over Wi-Fi | 109–112 s, DNS and power saving intact |
| Clock | `synced to 192.168.0.102`, orin − pc +0.00…+0.01 s |
| `dev_up … wifi`, tether out, cold | 49.3 s, all `ok:` |
| Link switch wifi → usb | `starting fresh (…@192.168.0.50 → …@192.168.55.1)`, 37.8 s |
| `ranger_up … wifi`, cold after reboot | 58.2 s, Mission Control LIVE, no `.env` edit |
| Firewall, phone as intruder | `:8080`, `:9090` refused; stopped → feed loads; restored → open stream freezes |
| Firewall after reboot | `RULES_IN_PLACE`; netfilter-persistent 25.19 s → ranger-firewall 25.64 s → NetworkManager 44.75 s |
| First untethered drive | W/A/D/Space all stop |
| 10 s continuous hold | **0 jitter stops**; release stop 258–264 ms |
| Relay `kill -9` mid-drive | stopped on its own; stale **294 ms**, **314 ms** after the kill |
| Recovery | `ranger_up … wifi` 10.3 s |
| Ingest over Wi-Fi | 120 rows / 2 min; `created_at − timestamp` 40 ms avg (27–65) |

---

## Files

| File | Deployed as | Role |
|---|---|---|
| `robot/firmware/uno_motor_geiger/uno_motor_geiger.ino`, `drive_logic.h` | Uno (Arduino IDE, from the PC) | PPM RC, NET arbitration, watchdog, `S`/`G` lines |
| `robot/firmware/uno_motor_geiger/test/test_drive_logic.cpp` | — | host tests for `drive_logic.h` (`g++`) |
| `robot/firmware/ppm_probe/ppm_probe.ino` | Uno (bench only) | PPM probe for the FS-X6B |
| `robot/uno_protocol.py`, `robot/uno_bridge.py` | Orin `~/ranger/` | `cmd_vel` → `M`, stale stop, `S` → `/ranger/uno_status`, `G` → `/ranger/geiger_counts` |
| `robot/config/99-ranger-uno.rules` | Orin `/etc/udev/rules.d/` | ModemManager off the Uno |
| `ranger_backend/ros_bridge/teleop.py`, `teleop_consumer.py`, `drive_lock.py`, `routing.py` | — | drive socket, auth, close codes, Redis lease |
| `ranger_backend/ros_bridge/management/commands/teleop_relay.py`, `grant_drive.py` | — | channel layer → rosbridge; Drivers group |
| `ranger_backend/core/models.py`, `migrations/0010_robot_drive_permission.py` | — | `core.drive_robot` |
| `ranger_frontend/src/lib/teleop.ts`, `components/dashboard/DrivePanel.tsx`, `pages/DashboardPage.tsx` | — | DRIVE panel, deadman |
| `ranger_frontend/src/lib/video.ts` | — | video config, robot pairing, single-probe watchdog |
| `ranger_frontend/src/components/camera/CameraPanel.tsx`, `pages/MissionControlPage.tsx`, `App.tsx` | — | feed, STALE overlay, `MjpegStream`, see-and-drive layout |
| `robot/tools/stack_up.sh` | Orin `~/ranger/stack_up.sh` | drive, camera, video windows; firewall, hardware and frame checks |
| `scripts/dev_up.sh` | — | flags, link-following addresses, video and `.env` checks |
| `scripts/ranger_up.sh`, `scripts/ranger_down.sh`, `scripts/desktop/*.desktop` | dock icons (see Install) | one-click bench |
| `robot/config/ranger-firewall.sh`, `ranger-firewall.service`, `sudoers-ranger-firewall` | Orin (see Install) | console-PC-only firewall, rule check |
| `config/pc/chrony-ranger.conf`, `robot/config/timesyncd-ranger.conf` | PC / Orin (F12 paths) | time over Wi-Fi |

---

## Install / deploy (record of what was done)

Everything outside the repo or outside `~/ranger/` on the Orin. Compare
`sha256sum` on both machines after every deploy.

**Orin (brian@jetson-orin)**
- `/etc/udev/rules.d/99-ranger-uno.rules` ← `robot/config/99-ranger-uno.rules`
  (`ENV{ID_MM_DEVICE_IGNORE}="1"` for `2341:0043`).
- `ros-humble-web-video-server` 3.1.0 (apt).
- OrbbecSDK_ROS2 in `~/ros2_ws` at `9b69bbfa` (`v2-main`), built before F14, with
  `/etc/udev/rules.d/99-obsensor-libusb.rules` from that build. **Local patch:**
  `orbbec_camera/launch/gemini2.launch.py` line 47, a missing comma (TS-038),
  in `src/` and copied to `install/`; sha256 `a61077c5…` for both.
  `stack_up.sh` refuses to start if the launch file stops parsing.
- NetworkManager profile `ranger-house`
  (`/etc/NetworkManager/system-connections/ranger-house.nmconnection`): SSID
  Brian, static `192.168.0.50/24`, gateway and DNS `192.168.0.1`, IPv6 off,
  `802-11-wireless.powersave 2`, autoconnect, priority 10. Created with the PSK
  read silently (`read -rs`), never typed into a command.
- `/etc/NetworkManager/conf.d/90-ranger-dns.conf`: `dns=default`,
  `rc-manager=file` (TS-037).
- `/etc/systemd/timesyncd.conf.d/ranger.conf` ← `robot/config/timesyncd-ranger.conf`
  (`NTP=192.168.0.102 192.168.55.100`).
- `/usr/local/sbin/ranger-firewall` (0755) ← `robot/config/ranger-firewall.sh`;
  `/etc/systemd/system/ranger-firewall.service` (enabled) ←
  `robot/config/ranger-firewall.service`; `/etc/sudoers.d/ranger-firewall` (0440,
  `visudo -c`) ← `robot/config/sudoers-ranger-firewall`.
- `~/ranger/`: `uno_protocol.py`, `uno_bridge.py`, `stack_up.sh`.

**PC (brian@Kipruto)**
- `/etc/chrony/conf.d/ranger.conf` ← `config/pc/chrony-ranger.conf`
  (`allow 192.168.0.50` added).
- NetworkManager "Brian": `802-11-wireless.powersave 2` (TS-043).
- `~/.ssh/known_hosts`: ed25519 entry for `192.168.0.50`, added only after its
  fingerprint matched the one presented over the tether.
- `~/.local/share/applications/ranger-up.desktop`, `ranger-down.desktop`,
  generated from `scripts/desktop/` with `@REPO@` substituted; pinned to the dock.
- `ranger_frontend/.env` (gitignored): `VITE_VIDEO_SERVER_URL`,
  `VITE_VIDEO_ROBOT_ID` for a hand-started Vite.

**Router (Tenda, `192.168.0.1`)**
- Advanced → Static IP: `192.168.0.102` ↔ the PC's `wlo1` MAC (remark `ranger-pc`).
- AP Isolation: Disabled.

**Uno:** flash from the PC's Arduino IDE with `uno_bridge` stopped; pick the port
labelled "Arduino Uno" (`/dev/ttyACM0` on the PC is the Orin tether).

```bash
# deploy (PC, repo root); compare sha256sum on both machines
scp robot/uno_protocol.py robot/uno_bridge.py robot/tools/stack_up.sh brian@192.168.0.50:~/ranger/
```

---

## Running it

```bash
# one command (or the RANGER Up icon, which runs usb)
scripts/ranger_up.sh sim nairobi wifi      # [sim|live] [nairobi|rabat] [usb|wifi]
scripts/ranger_down.sh                     # or the RANGER Down icon
# logs
tmux attach -t ranger-pc                                  # PC: runserver, ingest, relay, vite
ssh -t brian@192.168.0.50 tmux attach -t ranger           # Orin: stack incl. drive, camera, video
```

Expected from `ranger_up`: `ok: drive · uno_bridge talking to the Uno`,
`ok: video · frames at http://<orin>:8080 (bound to <orin> only)`,
`ok: console video URL for this link`, `ok: windows running: runserver ingest relay vite`,
Mission Control opens LIVE. To drive: wheels on blocks until ground runs are
cleared, TX on, SwA in NET, ARM, hold W/A/S/D.

`dev_up.sh` alone still works and prints the four PC terminals. `--no-drive` and
`--no-video` start the stack without those parts.

---

## Gotchas

**The tether is the Orin's only USB-C port.** Devices go in the four USB-A ports.
The Gemini's C-to-C cable through a USB 2 hub works for colour only; USB 3 needs a
C-to-A cable rated 5 Gbps.

**`dev_up.sh live` needs the GPS FTDI cable.** A failed `live` start tears down a
running sim stack; use `sim` for drive and video work.

**Vite reads `.env` only at startup.** A stale `VITE_VIDEO_SERVER_URL` shows
`retrying http://localhost:8080`. `ranger_up` passes the link's URL to Vite and
avoids this; a hand-started Vite needs `.env` right and a restart.

**`web_video_server` encodes per client.** Every open stream (an old raw
`/stream` tab included) costs about a third to half a core. Count clients with
`ss -tn state established '( sport = :8080 )'`.

**The Orbbec driver publishes nothing without a subscriber.** A topic that exists
proves little; `stack_up` proves frames with one long `/snapshot`.

**A dead camera's MJPEG `<img>` keeps its last frame and never errors.** That is
what the watchdog exists for. Don't remove it.

**`ros2 topic hz` without `--window`** averages over gaps; a restarted camera looks
slow for a while.

**React StrictMode mounts twice in dev.** Anything that aborts a resource on
unmount must own a fresh one per effect run (`MjpegStream`).

**The Gemini 2 IMU publishes `/camera/gyro_accel/sample`** whatever
`enable_accel`/`enable_gyro` say. Display-only (fork 6).

**Arming produces one `cmd_vel stale` line** in `uno_bridge`'s log; a release
produces another. Count "+2 per arm-hold-release" when checking for jitter stops.

**`ssh` "Host key verification failed" on a new Orin address** is expected. Compare
fingerprints over the tether, then add the key.

**`ranger_down` finds the Orin on the tether or Wi-Fi**, whichever answers.

**`jetson-internet.sh` re-prompts for sudo after a tether replug** (its NAT check).
Harmless; see Open items.

**`grep -q` after a pipe under `pipefail`** can fail on a match (SIGPIPE to the
writer). The stack scripts use `grep … >/dev/null`.

---

## Open items

- **➡️ Pass 8 — current draw.** A meter on the battery lead; idle, sensing,
  sensing + video, driving; rerun P2 with the USB 3 C-to-A cable and depth on.
- **➡️ Pass 8 — the venue.** Router or hotspot (WPA2-AES only; the house router is
  WPA1/WPA2 mixed); its addresses in `ranger-firewall.sh` `ALLOW`, `chrony` `allow`,
  timesyncd `NTP=`, `dev_up.sh` `ORIN_WIFI_HOST`; a second NetworkManager profile;
  the Orin on the rover battery; PC offline; `dev_up.sh live <site> wifi` with
  `clock_skew: 0` (needs sky); confirm the DNS drop-in holds there.
- **🔧 Motor-noise capacitors.** 100 nF across each motor; rerun the drive
  pattern and compare `ppm_glitches` (TS-036). Until then `max_pwm` stays 120.
  Then rerun the magnetometer test at the higher cap, and on the ground.
- **Ground driving.** Allowed now that 4d is done; start slow, in a clear space,
  with the RC kill in hand.
- **Drivers-group live check** with a non-superuser account (`grant_drive <user>`).
- **`jetson-internet.sh`** adds `-o wlo1 MASQUERADE` again on every run and covers
  all traffic (TS-042). Scope it to `-s 192.168.55.0/24` and make it idempotent,
  or retire it now that the Orin has internet over Wi-Fi.
- **Authenticated or proxied video** if anyone but the console PC must see it
  (ADR-0024).
- **A read-only stack-status panel** in the console (ADR-0027).
- **A `wifi` (and later `live`) dock launcher**; the icons start `usb`.
- **Magnetometer calibration** (F13) is still open; heading stays null.
- **Pre-existing:** 9 eslint problems (`client.ts`, `SatellitePage`,
  `VisualizationsPage`, `DataExplorerPage`); auth bootstrap logs 401s on an expired
  stored token.
- Carried from F13: first located LIVE row (sky), SDS011 (CP2102). From F12: 4c.
