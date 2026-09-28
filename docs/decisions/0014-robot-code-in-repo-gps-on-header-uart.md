# ADR-0014: Robot-side code lives in `robot/` in the platform repo; GPS on the Orin header UART

- **Status:** Accepted
- **Date:** 2026-09-28
- **Feature:** F08 (ROS bridge: GPS → SensorLog)
- **Supersedes:** none
- **Related:** ADR-0011 (geometry is the source of truth), ADR-0015 (ROS ingest)

## Context

F08 is the first code that runs on the robot rather than the platform. The Orin
(Jetson Orin Nano, JetPack 6.2.2, ROS 2 Humble) is headless and USB-tethered to
the development PC. Before this feature it held no project code at all; the
Pass 0 work lived in the Obsidian vault and on the PC.

Two questions had to be settled: where robot code is versioned, and how the
GPS physically reaches the Orin now that the Arduino Mega that used to front
the sensors is dead.

## Decision 1 — Robot code lives in `robot/` at the repo root, as plain `rclpy` scripts

```
ranger-platform-v3/
├── ranger_backend/
├── ranger_frontend/
└── robot/
    ├── gps_node.py
    └── tools/
        ├── nmea_sim.py
        └── gps_listen.py
```

`robot/` sits beside `ranger_backend/` and `ranger_frontend/`. Nodes are single
`rclpy` scripts run with `python3`, configured by ROS parameters (`--ros-args -p
port:=…`), not constants.

**Rejected: a separate robot repo.** The seam is the product. A change to the
`/fix` message contract and the ingest that consumes it should land in one
commit, reviewed together. Two repos means two histories that can disagree
about what the robot publishes.

**Rejected: a colcon/ament package now.** Correct eventually, overbuilt for one
node. A package adds `package.xml`, `setup.py`, a workspace, and a build step
between editing a file and running it, while the node is still changing hourly.

**Rejected: code only on the Orin.** Pass 0 did this. Nothing on the Orin is
backed up, reviewed, or diffable, and the Orin is exactly the machine most
likely to be reflashed.

**Consequences.** Deployment is manual: the Orin runs copies in `~/ranger/`,
moved with `scp`. The repo is the source of truth; the Orin copy can drift and
nothing detects it. The Orin runs system `python3` + ROS Humble, not the
project `.venv` (Python 3.11 vs ROS's 3.10 — see TS-017). When `robot/` holds
more than a few nodes, or deployment becomes supervised (P5c), this becomes a
colcon package and this ADR should be superseded, not stretched.

## Decision 2 — The GPS connects to the 40-pin header UART, not a USB-serial adapter

NEO-M8N TX → pin 10, RX → pin 8, on `/dev/ttyTHS1` (UARTA, MMIO `0x3100000`).

The CH340 adapter the plan assumed has **no driver in the JetPack 6.2.2 kernel**
(`5.15.185-tegra` ships `ftdi_sio` and `cp210x`, not `ch341`; TS-022). The
device enumerates and binds nothing.

| Option | Verdict |
|---|---|
| Build `ch341.ko` out of tree | Rejected — a kernel-module detour that breaks on every JetPack update, for the least important part of the path |
| CP2102 / FTDI adapter | Viable — drivers present. Not on hand; bought for the PM sensor |
| Header UART | **Chosen** — no driver, no USB enumeration, a fixed device name, 3.3 V logic matching the M8N |

**Consequences.** `/dev/ttyTHS1` is fixed hardware, so no udev rule is needed for
the GPS — the "ttyUSB0 is not guaranteed after reboot" problem does not apply.
The UART is proven by loopback; the full header path with a live module was
**not** proven before the module was destroyed (TS-023, TS-024), so the
real-sky checkpoint must re-verify wiring first. Any future sensor behind a
CH340 hits the same wall; CP2102 is the standing choice for USB-serial on the
Orin.
