# ADR-0029: Sim along a path — `nmea_sim --route`; `run_simulation` as positions only

- **Status:** Accepted
- **Date:** 2026-10-29
- **Feature:** F15 (checkpoint 6b, fork 6)
- **Related:** ADR-0028 (one decider), F11 (`nmea_sim --site`)

## Context

6b needs a fix that actually passes through the planned waypoints. `nmea_sim` was a
stationary jittered fix; `run_simulation` could drive a mission but decided completion
itself, teleported onto waypoint 1, wrote straight to the DB (no broadcast), and was
Kenya-only.

## Decision

- **`nmea_sim --route FILE`** walks a mission on the Orin, so the proof runs GGA →
  socat → `gps_node` → `/fix` → rosbridge → `ros_ingest` → `advance` — the 6d path
  with only the GGA source swapped.
  - `--speed` m/s (≤ 20), one fix per second; **a fix exactly on every waypoint**, so
    speed can never step over a threshold circle.
  - `--lead-in-m 15`: start before waypoint 1, outside any radius.
  - `--offset-east-m`: the miss proof; `--jitter-m` in metres.
  - Refuses a route > 5 km from `--site` (also catches a swapped file).
  - Prints each waypoint's **closest approach** before walking (TS-047).
- **`manage.py mission_route <id> --out`** writes the route as GeoJSON — `[lon, lat]`
  by the spec, so no typed coordinate pair exists to swap.
- **`run_simulation` stays the Orin-dead fallback, positions only:** drives toward the
  DB's active waypoint in metres, lands exactly on it when within a step, offers every
  row to `advance`, broadcasts in live mode, takes `--region`. Its own completion
  logic is deleted.

## Rejected

- **Drive `run_simulation` from the mission for 6b:** it would have proven its own
  rule, not the platform's, and bypassed ingest entirely.
- **Feed `run_simulation` through `ros_ingest._ingest`:** `_ingest` rejects rows older
  than 120 s (backfill) and takes readings from a ROS topic cache; faking both buys
  little once both writers share `advance`.

## Consequences

The sim tooling is test-only and deployed by `scp` + `sha256sum`. `--offset-east-m`
misses only where the geometry allows; a perpendicular offset is an open item.
