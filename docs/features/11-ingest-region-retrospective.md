# F11 — Retrospective

*Date: 2026-10-07*
*Written the day of sign-off.*

---

## What worked

**Fork 0 checked against the repo, not the handoff.** `main` was a linear
ancestor of the stacked branches, so it was fast-forwarded from F07 to the
`chore/dev-scripts` tip and `feat/ingest-region` was cut from `main`. The same
check showed `feat/orbbec-console` rebases cleanly and can wait.

**All six forks settled in one exchange,** with one deliberate deviation from
the handoff: named simulator sites instead of `--origin LAT,LON`, for the same
reason the CLI takes region names and not boxes.

**The Kenya default was pinned by test before anything moved.** One test
asserts the default is the identical `KENYA_BBOX` object; flipping it in a
mutation fails three tests. Nothing that already worked could drift.

**Command tests ran the real `handle()`.** `call_command` with rosbridge and
the inbox faked exercised parsing, region resolution, the banner, the note, the
ingest loop and the `Stopped.` counters in one path, without an Orin. Every key
test was seen to fail under a mutation: twelve mutations across three files.

**The N/W path was proven on the PC, through the Orin's parser.** pynmea2 on the
PC pinned to the Orin's version (1.19.0); all four quadrants round-trip. This is
the only check of the sign path available before a receiver is in Morocco.

**Shell scripts were run before they were handed over.** A stub harness — real
tmux, socat and `nmea_sim`, fake rosbridge and `gps_node`, ssh/docker/ping
stubbed — ran `stack_up.sh` and `dev_up.sh` end to end. It caught a stale-copy
check that would have hung the Orin (below) before it was deployed.

**Provenance in the row made a contaminated check recoverable.** Stamping
`region=<name>` cost one line; it let the negative proof be redone from the
database after a second process polluted the count.

**The fly-to reused F07's `flyTo` handle.** One file changed, `FieldMap`
untouched.

## What went wrong

**`~/Downloads` was the wrong path, and the hash gate was skipped once.**
`cp ~/Downloads/<file>` failed in three handoffs; the files had already been put
in place some other way. Twice the hashes were then run by hand and matched. For
`3f22eb9` the `&&` chain stopped, no hashes printed, and the commit went in
anyway; the blobs on origin were checked afterwards and matched. Correct by
luck, not by process. Rule: no hash line, no commit. The download location is
still not known.

**The negative proof was contaminated by a still-running ingest.** `max(id)`
moved by 11 during a run that saved nothing; the step-D `--region rabat` process
was still writing. Re-proved by provenance (TS-032). Then 9 more `region=kenya`
rows needed archaeology: an earlier default run, 20 minutes before.

**A first-draft preflight would have hung the Orin.** The stale-copy check ran
`nmea_sim.py --help`; the pre-F11 copy treats `argv[1]` as its output path and
writes NMEA to a file named `--help` forever. Caught in the sandbox harness and
replaced by a `grep` of the file. A probe that executes the thing it is checking
inherits that thing's bugs.

**Sandbox services died between sessions.** A full test run reported 244 errors
from a stopped Postgres, which reads like a regression. Restart and re-run first.

## Carry-forwards

- **Field time** — the remaining finale blocker. Next pass.
- **AEOC venue coordinates** → `RABAT_VENUE`, `RABAT_BBOX`, `SITES["rabat"]`.
- **First live fix in Morocco:** check the row's signs before anything else.
- **Find where downloads land**, fix the handoff `cp` path once.
- **Per-robot ingest lock** (TS-032) before any unattended run.
- Still open from F09: DEMO overlay claims LIVE; snapshot on connect; ~480 ms
  lag; ADR-0005 #17–18; header UART; `git stash` decision.
- Vault: Architecture Lockdown row for ADR-0018; Start Sequences gets
  `dev_up.sh sim rabat` and the live-at-venue line.
