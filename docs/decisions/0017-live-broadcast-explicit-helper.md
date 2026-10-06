# ADR-0017: Live fan-out — explicit broadcast helper; the database is the record, the socket is a view

- **Status:** Accepted
- **Date:** 2026-10-06
- **Feature:** F09 (Live on the Console)
- **Supersedes:** none
- **Related:** ADR-0012 (provenance tiers, weakest by default), ADR-0015 (ros_ingest), ADR-0016 (socket auth and groups)

## Context

A row saved by `ros_ingest` must reach every Dashboard socket in its org within
about a second, labelled with its provenance. Something has to call
`group_send`, and the console has to decide what a live position looks like.

## Decision 1 — An explicit `broadcast_sensorlog(log)`, not a `post_save` signal

`ros_ingest` calls it after `SensorLog.objects.create()`.

| Option | Verdict |
|---|---|
| `post_save` signal | **Rejected** — fires for admin edits, shell scripts and fixtures, so the console would show "live" movement nobody sent. Invisible at the call site. `bulk_create` skips it anyway. |
| Explicit helper | **Chosen** — greppable; a writer opts in. |

**Cost.** Every future live writer must call it. `run_simulation` live mode does
not yet; it should if it is ever the demo fallback.

## Decision 2 — The payload is built from the saved row

`{type, id, robot, ts, lat, lon, source}`, from `log.pk`, `log.timestamp`,
`log.latitude`/`log.longitude` (derived from `location`, ADR-0011) and
`log.source`. Never from the raw ROS message. The console shows exactly what the
database holds; the `id` lets a person check any frame against Postgres.

## Decision 3 — A failed broadcast is counted, never fatal

`broadcast_sensorlog` raises; `ros_ingest._broadcast` catches, counts
`broadcast_error`, and logs only on a state change (`broadcast DOWN …` once,
`broadcast recovered` once), so a dead Redis does not flood the terminal at 1 Hz.
Invariant at Ctrl-C: `saved == broadcast + broadcast_error`.

Verified 2026-10-06 with two Redis outages in one run: `saved 244 = broadcast 202
+ broadcast_error 42`, ids contiguous, no row lost.

**Consequence: no replay.** Rows saved while Redis is down are in Postgres but
never pushed. A reconnecting browser resumes at the next row; a freshly loaded
page shows DEMO coordinates until the first push. The socket is a view; history
belongs to the REST endpoints.

## Decision 4 — Provenance decides the blip, not the transport

Arriving over the live socket says nothing about whether a reading is real.

| Condition | Blip | Fleet signal |
|---|---|---|
| Fresh row, `source=live` | green, ping ring | `LIVE` |
| Fresh row, any other source | grey `#7a828f` (= `SOURCE_META.simulated`), no ping | `SIM` (the source's short label) |
| No push for 5 s | red (`offline`) | `STALE` |
| No live row ever | DEMO overlay, unchanged | DEMO value |

The map header tag is computed from what is on screen: `· LIVE` if any fresh
`live` position, `· SIM` if any fresh position, else `· DEMO`. It was
hard-coded `· LIVE` before F09.

**Rejected: `live` status plus a SIM label.** Colour and the ping ring are what
people read at a glance; a green pinging blip with small text saying SIM still
claims live.

## Consequences

- `--source live` on the NEO-6M turns the same blip green with no code change.
- Robots with no live data keep `FLEET_STATUS_DEMO`, which still marks
  `RANGER-PRIME-001` `live`, and the top-bar counts are DEMO. Both are open
  items in `features/09-live-console.md`.
