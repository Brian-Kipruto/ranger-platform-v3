# ADR-0021: The Geiger seam — count sources, counts not CPM, no data is not zero

- **Status:** Accepted (sim source in use; real source built and bench-proven, waiting on a tube and F14's `uno_bridge`)
- **Date:** 2026-10-14
- **Feature:** F13 (Sensor Payload)
- **Changes:** the planned Uno → Orin line `G,<cpm>` (vault *Arduino Uno - Motor and Geiger Node*) becomes `G,<counts>`
- **Related:** ADR-0020 (per-reading provenance, robot claims), ADR-0014

## Context

The GM tube is dead. The demo still needs radiation, and the Pass 5 note's rule
is that the seam is the deliverable: getting a replacement tube working must be
a one-line source swap, not a rewrite. The Uno counts the tube and also drives
the motors over the same serial link (F14).

## Decision 1 — `radiation_node` takes counts from a pluggable count source

A count source has `claim` and `counts(dt_s)`. `COUNT_SOURCES` maps the node's
`count_source` parameter to a class:

- `sim` — `SimCounts`: Poisson counts at background + an operator hot spot
  (`ros2 param set /radiation_node hotspot_cpm 400.0`). Claims `simulated`.
- `uno` — `UnoCounts`: sums `std_msgs/UInt32` reports from `/ranger/geiger_counts`
  between ticks. Claims `live`.

The claim lives on the source, so the swap — `count_source:=sim` →
`count_source:=uno` in `stack_up.sh` — flips the label with it (ADR-0020
Decision 2). The node, topic, message, ingest path and DB are unchanged.
Proven on the Orin with hand-published counts: `cpm: 120.0`, `source: live`.

## Decision 2 — The Uno sends counts; CPM is computed once, on the Orin

The Uno sends `G,<counts>` — counts since its previous `G` line, about once a
second. `radiation_node` windows counts into CPM (`CpmWindow`, rolling 60 s;
scaled while filling, never reported low), identically for sim and real.

- One windowing implementation, tested once, for both sources.
- The window length is a parameter on the Orin, not firmware.
- A hot spot ramps in over the window, like a real counter's display (measured
  6.8 CPM/s against 400/60 = 6.67).

## Decision 3 — The Uno's serial port has one owner; counts arrive by topic

F14's `uno_bridge` owns the port (it also sends `M,<left>,<right>` motor
commands) and republishes each `G` line on `/ranger/geiger_counts`. The count
source subscribes; it never opens the port. The topic name is pinned by a test
as the bridge contract.

## Decision 4 — No data is not zero

`UnoCounts.counts()` returns **None** when no report arrived for `geiger_stale_s`
(3 s) or ever. `radiation_node` then publishes **nothing**, clears its window,
and logs once; when counts return it logs once and starts a fresh window.

A dead tube or bridge must never read as a clean area labelled LIVE. Publishing
nothing means ingest attaches no radiation to those rows — absent, which the
screens show as "—". Measured: silent 3.0–3.1 s after the last count.

## Decision 5 — No dose rate until the tube is known

`dose_rate_usvh` is NaN (stored null) unless `usvh_per_cpm` is set. The factor
is tube-specific, and the repo already holds two conflicting ones (0.0057 µSv/h
per CPM in `run_simulation`, 1/334 in `marsabit`). A dose from an unknown tube is
false precision.

## Consequences

- Radiation stays SIM on every screen until the tube and `uno_bridge` exist —
  correctly.
- F14 must implement `G,<counts>` in the Uno firmware and `uno_bridge`, and bring
  the firmware into the repo before changing it.
- Running the `uno` source with hand-faked counts while ingest runs would store
  fake counts as LIVE. Bench tests of the swap are done with ingest stopped.
