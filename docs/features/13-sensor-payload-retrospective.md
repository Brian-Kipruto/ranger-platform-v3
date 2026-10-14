# F13 — Retrospective

*Date: 2026-10-14*
*Written at close, with the located LIVE row, the SDS011 and magnetometer calibration gated on location and hardware.*

---

## What worked

**Splitting Pass 5 at fork 0.** Sensors and drive share nothing but the Orin,
and driving on the ground was gated on Wi-Fi (4d) anyway. F13 closed cleanly
instead of stalling half-built behind a router purchase.

**Overriding the handoff's recommendation.** The note proposed "nullable, null =
inherit". Checked against ADR-0012, inheritance would have labelled a forgotten
simulated reading LIVE — the very over-claim the fork existed to prevent. NOT
NULL, weakest default, no inheritance; the DB refuses NULL.

**Contract tests across the robot/PC boundary.** The PC suite reads the robot's
`.msg` files, the manifest, `stack_up.sh`'s source line and `nmea_sim`'s
altitudes. Field-name drift, a dropped message, a wrong topic or a bad manifest
fails on the PC, not at `colcon build` or at the venue.

**Mutation checks kept finding real gaps.** Survivors pinned before handoff: a
stale reading kept in the cache, a yaw that rounds to 360.0, a signed read of
the BMP180's unsigned words (the datasheet example can't catch it), an
unmounted log heading, the uncalibrated-yaw path, the bridge topic name.

**Two-step isolation of the header UART.** Loopback showed corruption; an FTDI
on pin 8 alone proved TX clean. Twenty minutes to rule the port out instead of
a device-tree detour.

**Negative proofs, timed.** No-fix live mode: 30 s, zero rows. Dead Geiger feed:
silent within 3.1 s, not zero. Stale console: "—" within ~5 s, back in ~1 s.

**The honesty audit went past the brief.** The Dashboard's LIVE TELEMETRY had
shown invented values under a LIVE title since F07; Visualizations had no
provenance at all; SENSOR STREAMS said "REAL" over simulated data. All fixed,
because the rule is the rule wherever it's broken.

## What went wrong

**Unaccounted code in the sandbox.** Step 2 started from uncommitted work left
by an interrupted earlier run (Brian had stopped it mid-loop). It was audited
as foreign code before use, which found two real problems — but it should have
been flagged before reading it, not discovered by surprise.

**Files not attached, again.** 3a was built and described without the files —
the Pass 4 failure, repeated once. Caught by Brian.

**Commands that didn't run as written:** a literal `~/<repo>` placeholder; a
`cd` already done before the block; a `# <T2 command>` placeholder in place of a
command; `psql` from `docker exec -it` piped into `awk` (pager hang); Python
piped into `grep` (buffered, looked dead); `tail -6` cutting off the line that
mattered. Each cost a round trip. Every block now runs from an absolute path,
with real commands and unbuffered output.

**Untested robot-side assumptions.** The manifest's maintainer email was never
validated (no ROS in the sandbox); colcon refused it on the Orin. The IMU maths
assumed a flat board without asking how it was mounted (TS-035). Both now have
PC-side tests.

**A flaky test written in.** A module-level `time.time()` in a test file aged
past the 120 s skew guard on a long run. Found because the full suite was run
twice; reproduced deterministically before fixing.

**A banner that claimed more than it checked.** "ALL N POINTS AND THEIR
READINGS" was emitted when the server sent no reading counts. Caught by running
the logic on every case before handoff.

## Carry-forwards

- **Located LIVE row** when the robot can see sky: the first mixed-provenance
  row and the first per-cell SIM chip next to a LIVE position.
- **SDS011:** buy a CP2102 (check the chip, not CH340); `sds011_node`; add
  `/ranger/air_quality` to the live readings check.
- **Magnetometer calibration** with the board as mounted; N/E/S/W check; level
  trim for the ~10° lean.
- **F14:** Orbbec IMU telemetry; `uno_bridge` with `G,<counts>`; Uno firmware
  into the repo; genuine-Uno check; teleop through authenticated Channels.
- **Dose factor** from the replacement tube's datasheet.
- **4d before driving on the ground.** Still open from F12.
- Small: `n=1047` lacks a thousands separator next to `SIM 1,047`; pre-existing
  lint findings in `SatellitePage`, `DataExplorerPage` (`useReactTable`),
  `VisualizationsPage` (`set-state-in-effect`).
