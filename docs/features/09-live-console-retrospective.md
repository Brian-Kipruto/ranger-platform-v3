# F09 — Retrospective

*Date: 2026-10-06*
*Written the day of sign-off.*

---

## What worked

**Forks settled before code, each with a recommendation.** Four forks, all
decided in one exchange. The one overridden — query-string token → subprotocol —
cost about ten lines and removed a logged credential.

**Checking the working branch first.** `feat/ros-bridge-gps`, not `main`. That
check also found what the handoff missed: `ros_bridge` absent from `testpaths`
(the tenancy test would never have run), and the demo data already rendering
`RANGER-PRIME-001` as green LIVE.

**Tests against the real stack, then a mutation check.** The tenancy test runs
the real `application` (origin validator, router, consumer) and the real
`broadcast_sensorlog` on a saved row. Collapsing all orgs into one group made it
fail; deleting the broadcast call or the `try/except` failed the ingest tests.
A test that has been seen to fail is evidence.

**Three checkpoints, one layer each.** The socket was proven from a hand-written
browser console client before any React existed, so 2c's blank page had one
place to look.

**The database is the record.** Two Redis outages mid-run: 244 rows saved, 42
unbroadcast, none lost, ingest never paused.

**Measuring the lag found a clock bug.** The latency budget made a constant
12 s offset impossible to ignore. A bracketed ssh measurement (±0.14 s) settled
it in one command.

**Hashes as the acceptance test for file handoff.** After three rounds of
hand-edit damage, whole-file replacement verified by `git hash-object` (backend)
and `cp` from downloads (frontend) ended it. No eyeballing a diff for a
16-space indent.

## What went wrong

**The clock fallback was wrong, twice over.** TS-025's documented command sets
the Orin behind by however long the sudo password takes. The first instruction
to apply it also didn't say which machine; run on the Orin, `$(date +%s)` reads
the broken clock it is meant to fix. TS-029.

**The build was verified, not the dev server.** `react-use-websocket` is CJS-only;
the build interops its default export, Vite dev does not. Blank page on first
load. TS-030.

**Hand edits damaged files three passes running.** A deleted import left as a
blank line; markers indented 16 spaces; a needed blank line removed; a final
newline dropped by an editor setting toggled for another file. Each was found by
`diff --stat` not matching. The stat mismatch was also committed past once and
amended.

**Two unrelated working-tree changes at branch time** — a stray `+++` line in
`03-core-models-retrospective.md` (restored) and a change to
`satellite_integration/models.py` (stashed, unexamined).

**Session-start setup took longer than any checkpoint.** Rosbridge down, clock
three days behind, publishers stalled after the clock step. Each was a separate
round trip.

## Carry-forwards

- **Rabat: `--region` on `ros_ingest`**, and **field time** — both block the finale.
- **DEMO overlay still claims LIVE** for `RANGER-PRIME-001` and in the top bar.
- **Snapshot on connect** (latest position per robot) so a fresh page isn't DEMO
  until the next fix.
- **ADR-0005 #17–18** before any deploy.
- **~480 ms pipeline lag** — stamp each hop.
- **`git stash list`** — the `satellite_integration/models.py` change needs a
  decision.
- **NTP didn't sync with the NAT up** — check `ping google.com` (TS-025).
- **A start script** for the Orin stack and the PC services: the 2b/2c sessions
  lost more time to setup than to code.
- Vault: Architecture Lockdown rows for ADR-0016/0017; Start Sequences gets the
  corrected clock command and the offset measurement.
