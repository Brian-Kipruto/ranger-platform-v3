# ADR-0018: Named regions, a `--region` flag on `ros_ingest`, and named simulator sites

- **Status:** Accepted
- **Date:** 2026-10-07
- **Feature:** F11 (Region-Aware Ingest)
- **Supersedes:** none
- **Related:** ADR-0011 (one write path via `point_from_latlon`; the region box as an inversion tripwire), ADR-0012 (weakest-by-default provenance), ADR-0015 (`ros_ingest`: flags, counted skips — Decision 3 `out_of_region`)

## Context

`point_from_latlon` checks every coordinate against a box. ADR-0011 made that
box an **inversion tripwire, not a business rule**: a Kenyan point with lat and
lon swapped is still a valid coordinate (in the Indian Ocean) and only the box
catches it. The box defaulted to Kenya, and `ros_ingest` passed nothing, so
every fix at the Rabat finale would have been `out_of_region`.

The fix has to let Rabat in without weakening the tripwire, without moving the
Kenya default that three other writers rely on, and without a migration this
close to the finale.

## Decision 1 — Regions are named in a registry, never typed as a bbox

```python
REGIONS = {"kenya": KENYA_BBOX, "rabat": RABAT_BBOX}   # core/geo.py
resolve_region("rabat") -> RABAT_BBOX; resolve_region("none") -> None; anything else -> ValueError
```

| Option | Verdict |
|---|---|
| `--bbox MIN_LON,MIN_LAT,MAX_LON,MAX_LAT` | **Rejected** — a hand-typed box can be argument-order wrong, which disables the tripwire it configures, silently. |
| Named registry | **Chosen** — one place to read, one place to test. A lat-first box fails `test_venue_sits_inside_box_with_margin`. |

An unknown name raises. It never falls through to Kenya.

## Decision 2 — The Rabat box is city-region scale, ±0.7° around the venue

`RABAT_BBOX = (-7.54, 33.32, -6.14, 34.72)`, centred on `RABAT_VENUE`
(34.02, −6.84), covering Rabat–Salé–Témara–Kénitra.

- **Tighter is a sharper tripwire.** Swapped Rabat is (−6.84, 34.02), in
  Tanzania; a test asserts it is rejected under `rabat`, and widening the box to
  cover Tanzania fails it.
- **Not a national box.** It avoids encoding a national border the platform has
  no business drawing.
- **The venue is a placeholder** (city centre) until the AEOC venue is
  confirmed. A test requires the venue to sit ≥ 0.3° inside every edge, so
  moving one without the other fails.
- Kenya and Rabat boxes must not overlap (tested): a point valid in both would
  make the choice meaningless.

## Decision 3 — `--region` is a CLI flag on `ros_ingest`, default `kenya`, stamped in provenance

```bash
python manage.py ros_ingest --region rabat
# Connected. /fix -> SensorLog for RANGER-PRIME-001 (source=simulated, region=rabat).
# provenance_note: ros_bridge /fix via rosbridge 192.168.55.1:9090 · region=rabat
```

| Option | Verdict |
|---|---|
| Field on `Robot` or `Mission` | **Rejected for now** — a migration near the finale for robots that don't yet move between regions. Revisit if they do. |
| CLI flag | **Chosen** — same shape as `--source` (ADR-0015); current operations unchanged. |

The region is resolved first in `handle()`, before the DB lookup and before
rosbridge, so a bad name never connects. Each row records which guard it passed,
which is what made the F11 negative proof checkable after the fact (TS-032).

Only `ros_ingest` takes the flag. `run_simulation` and `seed_marsabit` keep the
Kenya default; `seed_marsabit` is Kenya-only by design.

## Decision 4 — `none` is allowed, never the default, and loud

`--region none` prints `WARNING: --region none — the inversion tripwire is OFF`
at start and stamps `region=none` on every row. It exists for one case: the
venue turns out to sit outside the box on the day.

## Decision 5 — The simulator takes a named site, with hemispheres from the sign

`nmea_sim.py [PATH] --site {nairobi,rabat}`, not `--origin LAT,LON` as the pass
handoff proposed: a typed origin is as invertible as the bug the tripwire exists
for. Hemisphere letters are derived from the sign; they were hard-coded `S`/`E`.

Robot code cannot import Django, so `SITES["rabat"]` duplicates `RABAT_VENUE`;
`test_sim_rabat_site_matches_the_region_venue` keeps them equal. The PC test
parses the sim's output with the same pynmea2 version the Orin runs (1.19.0),
which is the only proof of the N/W sign path short of a receiver in Morocco.

The start scripts pass the site through: `scripts/dev_up.sh sim rabat` →
`stack_up.sh sim --fresh --site rabat`; the tmux marker becomes `sim:<site>` so a
running sim at the wrong site is restarted, not kept. `dev_up.sh` prints the
`ros_ingest` line with the matching `--region`.

## Decision 6 — The Dashboard flies to a robot's first live position, once

`FieldMap` opens on Nairobi; a Rabat blip is ~5,000 km off-screen. The Dashboard
calls the existing `FieldMap` `flyTo` handle when the selected robot's first live
position arrives, at the map's opening zoom (13), once per robot per page load.

**Rejected: follow the robot on every fix** — the user can't pan away.
**Rejected: fly only when off-screen** — needs a viewport query on the handle;
more code for a ~600 m pan saved in the Nairobi case.

## Consequences

- At the venue: `scripts/dev_up.sh live rabat`, then the printed
  `ros_ingest --source live --region rabat`.
- Forgetting `--region rabat` in Rabat saves nothing and counts every fix as
  `out_of_region` — under-claims, never mis-stores.
- Adding a region is one registry entry plus its venue-margin and swap tests.
- Two copies of the Rabat venue (Django, robot) must move together.
