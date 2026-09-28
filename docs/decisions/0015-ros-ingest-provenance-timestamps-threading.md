# ADR-0015: ROS ingest — provenance flag, robot timestamps, counted skips, main-thread writes

- **Status:** Accepted
- **Date:** 2026-09-28
- **Feature:** F08 (ROS bridge: GPS → SensorLog)
- **Supersedes:** none
- **Related:** ADR-0011 (one write path via `point_from_latlon`), ADR-0012 (four provenance tiers, weakest by default), ADR-0014 (robot code layout)

## Context

`ros_ingest` is the first writer of `SensorLog.Source.LIVE` — the model comment
has said "the ROS bridge does, in F08" since F10.2. It is also the first
long-running process that writes to the database from a network callback.

F08 was built and verified entirely against a simulated GPS, because the real
module was destroyed mid-feature. That made the provenance question concrete
on day one: the first rows this command ever wrote were fake.

## Decision 1 — `--source` is a CLI flag, defaulting to `simulated`

```bash
python manage.py ros_ingest                  # simulated
python manage.py ros_ingest --source live    # deliberate
```

Only `simulated` and `live` are accepted; a ROS feed cannot be `reported` or
`modelled`. `provenance_note` is stamped automatically
(`ros_bridge /fix via rosbridge 192.168.55.1:9090`).

This is ADR-0012's rule applied to a new writer: **a forgotten label
under-claims.** Running against `nmea_sim` without thinking produces honest
rows. Producing `live` rows requires typing `live`.

**Rejected: derive `source` from the robot's `frame_id`** (`gps` vs `gps_sim`).
More automatic, and wrong in the dangerous direction: it trusts a string the
robot sends, and a node launched with the default frame over a simulator would
write `live`. The default must sit where the claim is made, not where the data
is produced.

**Consequences.** An operator can still type `--source live` over a simulator.
The flag makes over-claiming deliberate, not impossible.

## Decision 2 — `timestamp` is the robot's header stamp, guarded by a skew check

`SensorLog.timestamp` comes from `NavSatFix.header.stamp`, not server receive
time. A fix whose stamp differs from server time by more than `--max-skew`
(default 120 s) is skipped and counted as `clock_skew`, loudly.

Measurement time is the fact being recorded; receive time folds in bridge
latency and queueing. But the Orin's clock was found **four months wrong**
during F08 (TS-025). Trusting the stamp unguarded would have back-dated every
row to May, silently, and they would have sorted, filtered and charted as
valid data.

**Rejected: server receive time.** Always plausible, which is the problem — it
hides a broken robot clock rather than surfacing it.

**Consequences.** A robot with an unsynced clock writes nothing, and says why.
That is correct but it is a field risk: away from the PC's NAT there is no NTP,
and the Orin RTC reads 1970. Field operation needs a set RTC or GPS-disciplined
time (open item).

## Decision 3 — Gate on fix status; every skip is counted

Order: `status < 0` → `no_fix`; lat/lon `None`/NaN → `no_coords`; skew →
`clock_skew`; `point_from_latlon` `ValueError` → `out_of_region`. Every message
ends in exactly one counter, printed on exit.

Status comes first because the values are unreliable exactly when there is no
fix: the node publishes NaN, and rosbridge serialises NaN as JSON `null`. A
value-based NaN check (`lon != lon`) never sees a NaN.

Writes go only through `core.geo.point_from_latlon` (ADR-0011), so the Kenya
inversion tripwire applies to live data too.

## Decision 4 — The callback enqueues; the main thread writes

roslibpy invokes subscriber callbacks on its Twisted reactor thread, which has
an event loop running. Django raises `SynchronousOnlyOperation` for ORM calls
on such a thread (TS-027). `on_fix` only does `inbox.put_nowait(m)`; the
command's main thread — plain synchronous code — drains a bounded queue
(1,000) and does all ORM work, calling `close_old_connections()` before each
write so a dropped Postgres connection recovers in a long run.

| Option | Verdict |
|---|---|
| `DJANGO_ALLOW_ASYNC_UNSAFE=true` | Rejected — disables the guard rather than satisfying it |
| `sync_to_async` from the callback | Rejected — needs an awaitable context the Twisted callback is not |
| Queue → main thread | **Chosen** — the ORM only ever runs where Django expects it; backpressure is visible as `dropped` |

The callback also catches everything. An exception on the reactor thread does
not stop the process; it stops the rows while the main loop keeps "running".
The first run of F08 hit exactly this and showed `Stopped. {'error': 9}`
instead of a silent nothing.

## Open items carried forward

- **`--region` for Rabat.** `point_from_latlon` defaults to the Kenya box; every
  fix at the Rabat finale would be `out_of_region`. Add a `--region` flag (named
  box or `none`) before the demo.
- **Field time.** RTC or GPS-disciplined clock, or Decision 2 blocks all field
  ingest after an offline reboot.
- No robot-side buffering: fixes published while `ros_ingest` is down are lost.
- Foreground command, not a supervised service (P5c).
- Rows carry `mission=None`.
