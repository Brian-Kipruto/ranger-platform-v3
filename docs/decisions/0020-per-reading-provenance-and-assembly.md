# ADR-0020: Each reading carries its own provenance; readings attach to fresh fixes

- **Status:** Accepted
- **Date:** 2026-10-14
- **Feature:** F13 (Sensor Payload)
- **Amends:** ADR-0012 — `SensorLog.source` now labels the **position**, not the whole row
- **Related:** ADR-0012 (provenance tiers, weakest default), ADR-0014 (robot code in the repo), ADR-0015 (robot stamps, skew guard, thread model), ADR-0017 (live broadcast), ADR-0021 (Geiger seam)

## Context

Pass 5 puts a real GPS fix, a real IMU and a **simulated** Geiger (the GM tube is
dead) on one `SensorLog` row. The reading tables had no provenance; the row's
`source` was the only label. A live row would call its simulated radiation LIVE,
or, labelled weakest-wins, call its real position SIM and make the blip lie the
other way. The Pass 5 note also left the assembly rule — how readings attach
to a fix — unresolved (vault *Sensor to Topic to Model Map*).

## Decision 1 — A `source` per reading, NOT NULL, default `simulated`, never inherited

`RadiationLog`, `AirQualityLog`, `ImuBaroLog` share an abstract
`ReadingProvenance`: `source` with the same four tiers, NOT NULL, default
`simulated`. Migration 0009 adds it and backfills each existing reading from its
row in one transaction, so all existing data reads exactly as before.

| Option | Verdict |
|---|---|
| Nullable, null = inherit the row's (the handoff's recommendation) | **Rejected** — an unlabelled simulated reading on a live row inherits LIVE: the exact over-claim. Breaks ADR-0012's weakest default |
| Mark the whole row by the weakest of its parts | **Rejected** — every real position reads SIM until the tube is replaced; the blip says SIM on a live robot |
| Separate rows for simulated readings | **Rejected** — doubles rows at one position; the blip flips between SIM and LIVE |

The column is NOT NULL so "inherit" cannot come back as a NULL in disguise
(tested at the DB level).

## Decision 2 — The robot claims; the operator's `--source` is a ceiling

Every reading message carries the publishing node's claim (`live` |
`simulated`). Ingest stores `weakest(claim, --source)`; a missing or unknown
claim is `simulated`.

- The node knows the truth: the sim radiation node can't emit `live`, and
  swapping in the real count source swaps the label with it (ADR-0021).
- The ceiling keeps sim mode honest wholesale: `dev_up.sh sim` stores
  everything `simulated`, including a real IMU on a sim position — a real value
  at a fake place is not ground truth.

## Decision 3 — Assembly: GPS-triggered, fresh in robot time, consume-once, one transaction

`ros_ingest` subscribes to the reading topics and keeps the latest of each. On
each **accepted** `/fix` (after the region and skew guards) it attaches every
reading whose header stamp is within that topic's window of the fix stamp:
radiation 2 s, air quality 2 s, IMU 1 s.

- **Robot time**, not PC receive time: both stamps come from the Orin's clock,
  which F12 syncs; rosbridge jitter doesn't enter.
- **Consume-once:** a reading attaches to at most one row, then is cleared. At
  1 Hz with a 2 s window the same PM sample would otherwise land on two rows and
  double-count in any spatial analysis.
- **Stale readings are dropped**, counted (`<kind>_stale`), never carried
  forward. Readings with no fix write nothing — there are no positionless rows.
- **One inbox:** callbacks only enqueue `(topic, msg)` (ADR-0015's thread
  model); the main thread updates the cache and processes fixes in order. The
  row and its readings are written in one `transaction.atomic`; the broadcast
  follows the commit and carries the readings (ADR-0017).

## Decision 4 — `ranger_msgs`: one message per table, each with a stamp and a claim

`Radiation` (`cpm`, `dose_rate_usvh`), `AirQuality` (`pm25`, `pm10`), `ImuBaro`
(`roll`, `pitch`, `yaw`, `pressure_hpa`, `altitude_m`), each with
`std_msgs/Header` and `string source` plus `SOURCE_LIVE`/`SOURCE_SIMULATED`
constants; topics `/ranger/radiation`, `/ranger/air_quality`, `/ranger/imu_baro`.
`yaw` is a compass heading: degrees clockwise from **magnetic** north, [0, 360);
NaN when unknown.

- Supersedes the vault's split IMU contract (`/imu/data`, `/imu/mag`,
  `/ranger/barometer`), which had no 1:1 mapping onto `ImuBaroLog`.
- An interface-only colcon package on the Orin (`~/ranger/ws`); nodes stay plain
  `rclpy` scripts (ADR-0014). rosbridge must source the overlay.
- A PC test parses the `.msg` files and the manifest (with catkin_pkg) and fails
  if they and `readings.py` disagree in either direction.

| Option | Verdict |
|---|---|
| `std_msgs/Float32` per value | **Rejected** — no stamp (Decision 3), no claim (Decision 2) |
| `diagnostic_msgs/DiagnosticArray` (no build) | **Rejected** — stringly typed contract; kept as the fallback if colcon on the Orin were a problem (it wasn't) |

## Consequences

- Anything that shows a reading value must show **that reading's** source, never
  the row's. Done in F13 for the live console, Data Explorer (chip on a cell
  whose source differs from its position's), CSV (`radiation_source`,
  `air_quality_source`, `imu_source`), map summary (`provenance.readings`),
  Visualizations and SENSOR STREAMS. A new screen must do the same.
- The CSV header changed (three columns); the pinned header test was updated
  deliberately.
- The provenance banner counts positions **and** each reading kind: live
  positions with simulated radiation are flagged, where before F13 they
  produced no banner.
- Changing a `.msg` means a rebuild on the Orin and a stack restart.
