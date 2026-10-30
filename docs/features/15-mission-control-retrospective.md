# F15 — Retrospective

*Date: 2026-10-30*
*Written at merge (ADR-0032), with 6d — the real robot — still open.*

---

## What worked

**One decider, enforced twice.** Completion lives in `missions.progress.advance` and
nowhere else: `run_simulation`'s own rule was deleted, not kept "for the fallback",
and a test patches `advance` out to prove no other path completes anything. The
database backs it: one running mission per robot, a threshold check constraint.

**The sim through the real path.** `nmea_sim --route` exercised GGA, `gps_node`,
rosbridge and ingest — the 6d path with one source swapped — instead of a sim that
proves its own logic. The same walk also runs in-process on every test run (walk →
GGA → pynmea2 → region guard → `advance`).

**Proving the live path is the live path.** Markers ticked green 0.6–0.7 s after the
DB row; removing the socket route left only the 10 s re-read and the lag check failed.
Without that mutation, "it ticks" could have been the backstop all along.

**Asking the data when the output was missing.** The miss run's proof wasn't pasted;
one query over #12's stored fixes (363 fixes, 16.1–450.4 m from wp1, 1,462 m path)
proved the walk was real and the miss held.

**A pre-check before a constraint.** The one-running-mission migration was preceded
by a query that found mission #1 still IN_PROGRESS from the old simulator (TS-048) —
which would otherwise have swallowed every fix and blocked START.

**A real browser in the sandbox.** Playwright against real Django, PostGIS and Redis,
with only the basemap stubbed, caught two bugs before Brian saw them: the
`styledata` loop that froze every map (TS-046) and the missing blip (TS-049).

## What didn't

**A design made without reading its caller.** The 6a API took the robot's primary
key; the console only knows `robot_id_str` and has no robots endpoint. Found while
building the UI, fixed in its own commit (`28a9783`). Read the consumer before
fixing an API's shape.

**A claim about geometry made without checking it.** I said `--offset-east-m 15`
misses every waypoint; the tests showed an east–west leg runs straight over its own
waypoints. Corrected — and then the bench run still used 15 m on a leg where it
missed wp1 by only 4.6 m (TS-047). The "wp1 must be ≥ 6" condition was in my prose,
not in the command; the sim printed the answer and nothing stopped on it. I had
Brian's waypoints in a screenshot and could have computed it first.

**Redone steps with stale commands.** After the miss was redone as "6b miss 2", the
recovery command from the old message still said `'6b miss'` and measured an aborted
mission: `-25229.3 s`. When a step is redone, resend every command that names it.

**Prerequisites in prose, not in commands.** The fallback command assumed a mission
planned in the UI and died on `NoneType`; the 6c route step was skipped and the
mission sat at 0/4 ("is it supposed to take long?"). A command that depends on a
manual step should check it and say what's missing.

**Download names.** Two `urls.py` files were attached as `missions_urls.py` and
`root_urls.py`; placed under those names, the hash check failed. Attach under the
real name unless two files collide, and then give the `mv` in the same message.

**One hash check not pasted** before a commit (6b.1). The tests passing implied the
right files; the rule is still "no hash line, no commit".

## Carry-forwards

- **6d** — real robot, real GPS; fuse, capacitors, sky (feature doc → Open items).
- Who may plan (a permission like START's).
- A perpendicular miss offset in `nmea_sim`.
- Check the satellite raster's unconditional `moveLayer` (TS-046 pattern).
- Move the duplicated staleness/blip rule into `lib/`.
