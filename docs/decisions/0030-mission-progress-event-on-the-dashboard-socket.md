# ADR-0030: Live progress — a `mission.progress` event, then an HTTP re-read

- **Status:** Accepted
- **Date:** 2026-10-30
- **Feature:** F15 (checkpoint 6c)
- **Related:** ADR-0016 (socket auth), ADR-0028

## Context

The dashboard socket already carries every saved row to its org's group. It does not
say that waypoint 2 just completed; the console needs that within a second, and
another org must never see it.

## Decision — B: an event on completion

- `ros_bridge.broadcast.broadcast_mission_progress(adv)` sends `mission.progress`
  (mission, robot, mission status, the waypoint, distance) to
  `dashboard.org.<mission org>`, **only when `advance` completed something**, after
  that row's own broadcast. Both writers send it; a failure is counted and never
  blocks the row or the completion (ingest's existing policy).
- `DashboardConsumer.mission_progress` forwards it unchanged; tenancy is the group's.
- The console treats it as "mission N moved" and **re-reads the mission over HTTP** —
  what it draws is the database, never a patched copy of a message.
- While a mission runs, a 10 s re-read bounds how long a lost event can hide a tick.

## Rejected — A: re-fetch on every live row

No backend change, but ~1 request per second per console for as long as a mission
runs, and a tick that lags one fetch behind.

## Consequences

Measured in a browser: markers green 0.6–0.7 s after the DB `completed_at`; with the
socket path removed, only the 10 s re-read remained and the check failed (2.57 s).
Mission Control mounts its own `LiveFeed` (the dashboard's unmounts with it).
