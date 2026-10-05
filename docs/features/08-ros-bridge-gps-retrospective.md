# F08 — Retrospective

*Date: 2026-09-28*
*Written the same day, with real-sky sign-off still open.*

---

## What worked

**Splitting 1a and 1b with a checkpoint that reused the Pass 0 listener.** The
sensor and the database were never debugged in the same step. When `ros_ingest`
failed (TS-027), `/fix` was already proven, so there was exactly one place to
look.

**Keeping the pipeline moving when the hardware died.** A socat pty and forty
lines of `nmea_sim.py` stood in for the GPS. The node, rosbridge, the network
seam and the ingest were all proven against it, so the replacement module turns
the remaining work into wiring plus two flags rather than a feature. The sim
sends three no-fix sentences first on purpose — that is how NaN→`null` was
found before it could corrupt a real run.

**Bench isolation.** The GPS path had four unknowns: driver, UART, wiring,
module. Each was pinned separately — `lsusb -t` for the driver, a one-wire
loopback for the UART, the CH340 on the PC for the module — until only the
wires were left.

**`xxd` across three bauds instead of `cat` at one.** `cat` at 9600 showed
"nothing" for two different faults. Raw bytes at 38400 showed solid `0x00`,
which names a line held low and points straight at wiring.

**Verifying the model against the working branch.** The first check read
`core/models.py` on `main`, where `latitude`/`longitude` are columns. On
`feat/postgis-foundation` they are properties and the write path is `location`
via `point_from_latlon`. The spec's ingest code would have raised on its first
fix.

**Provenance decided before the first row.** The first rows `ros_ingest` ever
wrote were fake. The flag defaulting to `simulated` meant they were labelled
fake without anyone needing to remember.

**The catch-all in the callback.** It turned TS-027 from an idle-looking process
over an empty table into `Stopped. {'error': 9}` on the first run.

---

## What went wrong

**The plan assumed hardware that had never been tested on this machine.** "GPS
on a USB-serial adapter" was never tried on the Orin. The adapter needed a
driver the kernel doesn't ship (TS-022). A two-minute `lsusb -t` before writing
the plan would have routed straight to the header UART.

**Wiring instructions that were correct but easy to misread.** "Jumper pin 8 to
pin 10" was executed as "GPS TX/RX to pins 8 and 10", and "GPS TX → pin 10" was
read back as "GPS RX → pin 10" (TS-023). A table written from the GPS side
(*this GPS pin → that Orin pin*) was clearer than prose, and it came too late.

**A module destroyed by a hot-plugged, reversed supply** (TS-024). Rewiring with
the Orin powered was normalised by using the LED flash as a check. That was the
cost of the whole real-sky checkpoint.

**The project state in the handoff was stale.** It said the remote was at
Feature 07 and the next ADR was 0011. The working branch was at F10.3, with
ADRs to 0013 and troubleshooting to 020. Uncommitted work from three concerns
(F10 analysis, the camera detour, Mission Control) sat in the working tree.

**Cleaning that working tree turned up a regression.** The camera detour had
overwritten `App.tsx` with a copy that predated F10.3, silently unrouting the
Satellite screen. `tsc` passed, because an unrouted page isn't a type error.
Caught by reading the diff before committing, not by any check. Same class as
TS-015.

**A partial edit lost the `except KeyboardInterrupt:` in `ros_ingest`.**
Replacing the `while` block by hand took the `except` line with it, leaving a
stray `pass` before `finally`. The file parses and ingest works — rows land,
counts print — but Ctrl-C re-raises into a traceback. Found by reading the
pushed branch while writing these docs. Third paste/edit-boundary loss in the
project (TS-004, TS-015, this).

**The vault held a script the machine didn't.** `jetson-internet.sh` existed only
as text in Start Sequences (TS-025).

---

## Carry-forwards

- **Real-sky sign-off.** Replacement NEO-M8N: power off, wire from the GPS side
  by touch, `xxd` check on `/dev/ttyTHS1`, then node + `ros_ingest --source live`,
  rows verified in Postgres as `live`. F08 closes on that, not before.
- **`--region` on `ros_ingest` before Rabat.** The Kenya tripwire rejects every
  fix in Morocco. Zero rows at the finale otherwise.
- **Field time.** No NTP away from the PC; RTC reads 1970. RTC battery +
  `hwclock -w`, or GPS-disciplined time. Otherwise the skew guard blocks all
  ingest after an offline reboot.
- **CP2102 adapter** for the PM sensor (CH340 has no driver on the Orin).
- **Spare sensors** on the demo path — two M8Ns ordered.
- **TS-021 is owed** — the F10 `relative_cog_path` footprint bug (fixed in
  `52087db`) has no troubleshooting entry.
- **`analyze_covariance`** prints the `NOT significant` verdict for NDVI but not
  BSI.
- **`/mission` never visually signed off** before `feat/orbbec-console` was
  committed.
- 24 `simulated` rows from `nmea_sim` sit under `RANGER-PRIME-001`. Labelled,
  so harmless; filter by `provenance_note__startswith='ros_bridge'` to remove.
- Vault: Start Sequences should say the script must exist at
  `~/jetson-internet.sh`; Architecture Lockdown gets rows for ADR-0014/0015; the
  Pass 1 spec's `STATUS_FIX` value, ingest code and robot-creation snippet
  (`status='online'` vs `Robot.Status.ONLINE`) are wrong — link to this doc
  rather than fixing the spec in place.

---

## Sign-off addendum — 2026-10-03

F08 signed off: 22 `live` rows from a NEO-6M under open sky, verified by query.
The carry-forwards above are superseded by the list at the end of this section.

### What worked

**Splitting the hardware the same way again.** With the header failing, three
moves each changed one variable: GPS on header power with its TX read by the PC
(not powered), GPS on cable power read by the PC (alive), GPS on cable power read
by pin 10 (pin 10 deaf). Twenty minutes to two clean conclusions, with no
guessing and no powered rewiring.

**Taking the header out of the path instead of fixing it under deadline.** The
FTDI cable had a driver on the Orin, was already proven with this GPS, and
powered it from USB. The sign-off was the goal; the header became a logged
carry-forward rather than an afternoon.

**GPS UTC as the clock reference.** `timedatectl` said only "not synchronized".
The GPS's GGA time said the Orin was 22 minutes slow. That is also the field
answer to the open time problem.

**The receiver refusing a bad fix.** Beside a wall it held 4 satellites with
HDOP climbing past 45 and kept `qual=0`. A receiver that reported that position
would have put plausible garbage in the database.

### What went wrong

**The header failed twice and is still undiagnosed.** Both modules, two
sessions. The lead theory — wired to the odd (inner) row — explains every
observation and has not been tested. Angled photos could not settle it either
time.

**TS-025's fix was wrong twice.** `resolved.conf` was never read; `resolvconf`'s
`head` is never applied at boot. Both "worked" in-session, which is exactly why
they weren't questioned until the next reboot. A fix for a boot-time problem
isn't verified until it survives a boot.

**Wrong guidance on three small things, each costing a round trip:** the genuine
FTDI colour code (yellow = RX) for a cable whose RX is white; an `awk` pipeline
that mawk block-buffers into a minute of silence; and two `date -u` commands in
one block that got run in one shell, comparing the Orin with itself.

### Carry-forwards (current)

- **Rabat: `--region` on `ros_ingest`.** Zero rows in Morocco otherwise.
- **Field time.** Discipline the Orin from GPS UTC, or RTC battery + `hwclock -w`.
- **Header UART:** the exact-position loopback test (TS-023 addendum). If the
  row theory holds, move the GPS back to the header and supersede the
  ADR-0014 amendment.
- **Verify the static `/etc/resolv.conf` survives a reboot** (TS-025).
- **Second FTDI or CP2102 adapter** for the PM sensor.
- **Fix quality isn't stored.** HDOP and satellite count are dropped, and the
  node publishes `position_covariance` as unknown. This sign-off's fixes wandered
  ~21 m while stationary; a ground-truth claim needs that number on the row.
- `gps_node.py` defaults to `/dev/ttyTHS1`; the working port is passed by
  parameter.
- TS-021 still owed (F10 COG footprint bug); `analyze_covariance` BSI verdict;
  `/mission` visual sign-off on `feat/orbbec-console`.
- 24 `simulated` rows from 1b remain under `RANGER-PRIME-001` — labelled,
  harmless.
- Vault: Architecture Lockdown rows for ADR-0014 (with amendment) and ADR-0015;
  Start Sequences gets the static `resolv.conf`, the PC-side `date -s` fallback,
  and the fix-watch command.
