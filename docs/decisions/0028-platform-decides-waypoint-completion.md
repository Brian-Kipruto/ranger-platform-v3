# ADR-0028: The platform decides waypoint completion, in the ingest path

- **Status:** Accepted
- **Date:** 2026-10-29
- **Feature:** F15 (checkpoint 6b, fork 1)
- **Related:** ADR-0029 (sim along a path), ADR-0030 (live progress)

## Context

A mission's waypoints must turn COMPLETED as the robot reaches them. The robot is
teleop-driven (fork 3), the demo may run on the sim, and the old `run_simulation`
already decided completion itself — a degree threshold of ~16 m, snapping onto each
waypoint, no `completed_at` — so two deciders would have existed the moment ingest
learned the rule.

## Decision — one function, `missions.progress.advance`, called by every writer

- **Where:** inside the transaction that stores the fix. `ros_ingest` and
  `run_simulation` both call it; nothing else changes waypoint status.
- **Rule:** the active waypoint is the running mission's first PENDING one by
  `order`. A stored fix within the mission's `threshold_m` (PostGIS geodesic metres)
  completes it at the **fix's** timestamp; the last one completes the mission.
- **Order:** at most one waypoint per fix, never out of order, no credit for a near
  miss. Passing near waypoint 3 while 2 is PENDING does nothing.
- **Attachment:** the row joins the mission it was measured for
  (`SensorLog.mission`), including the completing fix; Pass 7's report reads it.
- **Atomicity:** the mission row is locked; a failed row write rolls the completion
  back. `advance` refuses to run outside `atomic()`.
- **One running mission per robot,** enforced by a partial unique constraint, so
  "the robot's active mission" is never ambiguous. START returns 409 otherwise.
- Skipped fixes (no fix, skew, out of region) are never offered: an unstored fix
  completes nothing.

## Rejected

- **The robot decides** (an on-board node publishing "arrived"): a second notion of
  position and time, robot code the platform can't test, and nothing for the sim.
- **Closest approach over a window:** credits paths that never reached the waypoint;
  the operator sees green where the robot wasn't.
- **Keep `run_simulation`'s own logic for the fallback:** the spec's "advance in two
  places" trap; the demo would prove a different rule from the live run.

## Consequences

Proven on the real stack (6b): in order, a timed miss and a 6.1 s recovery, and the
Orin-dead fallback through the same function. Tier-1 completion is purely positional;
actions at waypoints (fork 5) would hook here later.
