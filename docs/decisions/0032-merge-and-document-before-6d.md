# ADR-0032: Merge F15 and write its docs before 6d

- **Status:** Accepted
- **Date:** 2026-10-30
- **Feature:** F15 (close)
- **Related:** F14's "Open items" pattern

## Context

6a–6c are proven on the bench and ready to merge. 6d — teleop the real 6WD through
waypoints, completed by real GPS — needs the fuse wired, the motor capacitors and a
fix under open sky, none of which has a date. The convention is a `docs:` commit at
feature close.

## Decision — A

Fast-forward `feat/mission-control` into `main` now (full suite green on the PC,
727), and write the feature doc, ADRs, troubleshooting and retrospective now, with
**6d recorded as an open item**. When 6d runs, its evidence is appended to
`features/15-mission-control.md` in its own `docs:` commit.

## Rejected — B: hold the merge and the docs until 6d

Matches "docs at close" literally, but the branch would drift from `main` for an
unknown time, and the details that make the docs useful (fork 6, the offset mistake,
the `styledata` loop) would be written from memory later.

## Consequences

`main` carries proven tier-1 mission control. F15 stays formally open until 6d is
recorded; nothing in 6d is expected to change code, only to prove it on hardware.
