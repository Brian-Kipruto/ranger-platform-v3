# F11 — Region-Aware Ingest

*Date: 2026-10-07*
*Branch: `feat/ingest-region` (from `main` @ `b20b0b3`, after `main` was fast-forwarded from F07's `6ca03c8` to the `chore/dev-scripts` tip)*
*Status: **complete.** A simulated Rabat fix lands in Postgres inside the Rabat box and moves its blip on the Dashboard, labelled SIM. The Kenya default is unchanged and swapped coordinates are still caught.*

---

## What this feature does

Before F11, every Rabat fix was skipped as `out_of_region`: `point_from_latlon`
defaults to the Kenya box, and `ros_ingest` had no way to choose another. The
finale would have written zero rows.

F11 adds **named regions** (`kenya`, `rabat`, plus `none` as a loud escape
hatch), a `--region` flag on `ros_ingest`, a Rabat site on the simulator with
hemisphere letters derived from the sign, a site passthrough in the start
scripts, and a one-time fly-to on the Dashboard so a blip 5,000 km from Nairobi
is on screen.

This is the first time the stack has carried a **north/west** fix. Every real
and simulated fix before it was south/east.

At the venue it is the same two commands with `live`:

```bash
scripts/dev_up.sh live rabat                                    # prints the next line
cd ranger_backend && python manage.py ros_ingest --source live --region rabat
```

| Checkpoint | Proven with | Status |
|---|---|---|
| 3a — region registry | 19 pytest cases, pure Python; 4 mutation checks | ✅ `b8394b4` |
| 3b — `ros_ingest --region` | 9 pytest cases through the real `handle()`; 5 mutation checks | ✅ `52f3e71` |
| 3b — Rabat sim | 9-case hemisphere test (sim → pynmea2, all four quadrants); 3 mutation checks; real pty smoke | ✅ `3f22eb9` |
| 3b — site passthrough + end to end | Rabat rows in Postgres inside the box; negative proof by provenance; Nairobi unchanged | ✅ `32d7f5b` |
| 3c — the blip in Rabat | Visual sign-off: flies once, no snap-back, STALE, Nairobi | ✅ `b2eb976` |

Decision: [ADR-0018](../decisions/0018-named-regions-and-ingest-region-flag.md).
Troubleshooting: [TS-032](../troubleshooting/032-concurrent-ros-ingest-double-writes.md).

---

## Sign-off evidence

### 3a — region registry (2026-10-07)

`core/test_regions.py`, 19 cases: the default region is still the identical
`KENYA_BBOX` object; `rabat` accepts the venue with N/W signs and rejects
Nairobi; swapped Rabat (−6.84, 34.02, in Tanzania) is rejected under both
`rabat` and `kenya`; `none` skips the box; unknown names (`""`, `"Rabat"`,
`"KENYA"`, `"morocco"`, `None`, `"kenya "`) raise; every box is well-formed;
the Kenya and Rabat boxes don't overlap; the venue sits ≥ 0.3° inside every
edge of the Rabat box.

| Mutation | Result |
|---|---|
| Rabat box widened to cover Tanzania | 3 fail, including the swap test |
| Rabat box typed lat-first | 3 fail, including the venue-margin test |
| Unknown name falls through to Kenya | all 6 unknown-name cases fail |
| Default region changed to `None` | 3 fail, including `test_default_region_is_still_kenya` |

### 3b — `ros_ingest --region` (2026-10-07)

`ros_bridge/test_ros_ingest_region.py` runs the real `handle()` via
`call_command`, with rosbridge and the inbox faked: Rabat saves N/W with
`· region=rabat` in the note and banner; Nairobi and swapped Rabat are
`out_of_region` under `rabat`; the default is `kenya`; three Rabat fixes under
the default save nothing (`Counter(out_of_region=3)`); `none` warns, saves and
says so; an unknown name raises before rosbridge is constructed; the CLI
rejects `--region=morocco`.

| Mutation | Result |
|---|---|
| `_ingest` ignores `--region` | 3 fail |
| Unknown name falls through to Kenya | 3 fail |
| Region not stamped in the note | 3 fail |
| No warning on `none` | 1 fails |
| Default flipped to `rabat` | 2 fail (both Kenya-default tests) |

### 3b — Rabat sim and hemispheres (2026-10-07)

`ros_bridge/test_nmea_hemisphere.py` loads `robot/tools/nmea_sim.py` from the
repo and parses its output with pynmea2 (checksum enforced) — the same parse
`gps_node.handle_gga` does. Paris (NE), Rabat (NW), Nairobi (SE) and Rio (SW)
round-trip to ±1e-6° with correct signs; the Rabat site parses N/W and passes
the `rabat` guard but fails the Kenya default; the sim's Rabat site equals
`core.geo.RABAT_VENUE`.

pynmea2 is `1.19.0` on both the PC (pinned in `requirements/development.txt`)
and the Orin.

Nairobi output is unchanged: 5,000 seeded runs of the old and new `gga()` gave
identical sentences apart from the time field.

| Mutation | Result |
|---|---|
| Hemisphere letters hard-coded `S`/`E` again | 5 fail |
| E/W inverted | 7 fail |
| Rabat site typed swapped | 3 fail |

### 3b — end to end (2026-10-07, DB verification: Brian)

Deployed `stack_up.sh` (`a1263d18…`) and `nmea_sim.py` (`0105669c…`); `sha256sum`
identical on PC and Orin.

`scripts/dev_up.sh sim rabat` → `starting fresh (running sim, want sim:rabat)`,
`ok: /fix publishing · mode=sim:rabat`, printed T2 line ending `--region rabat`.
Orin − PC = −0.30 s.

```
  id   | lat      | lon      | source    | provenance_note                                                | in_rabat
 26533 | 34.02002 | -6.83999 | simulated | ros_bridge /fix via rosbridge 192.168.55.1:9090 · region=rabat | t
 26532 | 34.01999 | -6.84000 | simulated | ros_bridge /fix via rosbridge 192.168.55.1:9090 · region=rabat | t
 …
```

**Negative proof.** `ros_ingest` with the default region against the Rabat sim:
`Stopped. {'out_of_region': 11}`, banner `region=kenya`. `max(id)` moved
26548 → 26559 during that run — the step-D `--region rabat` ingest was still
running in another terminal (TS-032). Proven by provenance instead:

| Query | Result |
|---|---|
| Rows 26549–26559 | all `34.02, −6.84`, `· region=rabat` (the other process) |
| `region=kenya` rows outside the Kenya box | **0** |
| `region=rabat` rows outside the Rabat box | **0** |
| `region=rabat` / `region=kenya` rows | 93 / 20 |

The 20 Kenya rows: 11 from the Nairobi run below (26606–26616) and 9 from an
earlier default run at 13:29 UTC against the Nairobi sim. Both inside Kenya.

**Nairobi unchanged.** `scripts/dev_up.sh sim` → `running sim:rabat, want
sim:nairobi`; default `ros_ingest` → rows at −1.2864, 36.8172,
`Stopped. {'saved': 11, 'broadcast': 11}`.

### 3c — the blip in Rabat (2026-10-07, visual sign-off: Brian)

| Check | Result |
|---|---|
| First live fix → map flies to Rabat; grey blip, `SIM`, header `· SIM`, readout `34.0200°, −6.8400°` | ✅ |
| Pan away (expanded, zoomed out) → no snap-back | ✅ |
| Ingest stopped → red, header `· DEMO` (F09 behaviour) | ✅ |
| Nairobi sim → blip in Nairobi, grey `SIM`, zoom 13 | ✅ |

`tsc -b && vite build` and `eslint` clean. The frontend has no test runner; the
visual sign-off is the test.

---

## Files

| File | Role |
|---|---|
| `ranger_backend/core/geo.py` | `RABAT_VENUE` (placeholder: city centre), `RABAT_BBOX`, `REGIONS`, `REGION_NONE`, `REGION_CHOICES`, `resolve_region()` — appended; existing code unchanged |
| `ranger_backend/core/test_regions.py` | 19 tests: registry, Kenya default, Rabat accept/reject, swap, venue margin |
| `ranger_backend/ros_bridge/management/commands/ros_ingest.py` | `--region {kenya,rabat,none}` (default `kenya`); resolved first in `handle()`; ` · region=<name>` on `provenance_note`; banner; WARNING on `none` |
| `ranger_backend/ros_bridge/test_ros_ingest.py` | fixture sets `c.region = KENYA_BBOX` |
| `ranger_backend/ros_bridge/test_ros_ingest_region.py` | 9 tests through the real `handle()` |
| `ranger_backend/ros_bridge/test_nmea_hemisphere.py` | 9 tests: four quadrants, Rabat N/W, Nairobi S/E, venue parity, guard, no-fix |
| `ranger_backend/requirements/development.txt` | `pynmea2==1.19.0` |
| `robot/tools/nmea_sim.py` | `[PATH] [--site {nairobi,rabat}]`; `SITES` (lat, lon, alt); hemisphere letters from the sign; prints its site at start |
| `robot/tools/stack_up.sh` | `--site` (sim only); `RANGER_MODE` marker `sim:<site>` / `live`; preflight rejects a pre-F11 `nmea_sim.py` |
| `scripts/dev_up.sh` | `[sim|live] [nairobi|rabat]`; restarts on a site change; prints the matching `ros_ingest` line |
| `ranger_frontend/src/pages/DashboardPage.tsx` | flies to the selected robot's first live position, once per robot per page load, zoom 13 |

## Running it

```bash
scripts/dev_up.sh sim rabat                                       # PC
cd ranger_backend && python manage.py runserver
cd ranger_backend && python manage.py ros_ingest --region rabat
cd ranger_frontend && npm run dev
```

`scripts/dev_up.sh` with no arguments is still `sim nairobi`, and the printed
ingest line is still plain `ros_ingest`.

After editing anything under `robot/`, deploy and compare:

```bash
scp robot/tools/stack_up.sh robot/tools/nmea_sim.py brian@192.168.55.1:~/ranger/
sha256sum robot/tools/stack_up.sh robot/tools/nmea_sim.py
ssh brian@192.168.55.1 'sha256sum ~/ranger/stack_up.sh ~/ranger/nmea_sim.py'
```

## Gotchas

**Boxes are `(min_lon, min_lat, max_lon, max_lat)`** — longitude first, the
opposite of `point_from_latlon`'s arguments. `test_venue_sits_inside_box_with_margin`
fails if one is typed lat-first.

**`RABAT_VENUE` exists twice:** in `core/geo.py` and as `SITES["rabat"]` in
`nmea_sim.py` (robot code can't import Django). `test_sim_rabat_site_matches_the_region_venue`
keeps them equal. Update both when the venue is confirmed, and move `RABAT_BBOX`
with it.

**`call_command(region=...)` bypasses argparse `choices`.** `handle()` resolves
the name itself, so an unknown region is a `CommandError` either way.

**Never probe a script by running it with `--help`.** The pre-F11 `nmea_sim.py`
treats `argv[1]` as its output path and writes NMEA to a file called `--help`
forever. `stack_up.sh`'s stale-copy check greps the file instead.

**`max(id)` is not a witness for "this run wrote nothing"** while another
ingest may be running. Check `pgrep -af ros_ingest`, and prove it by
`provenance_note` (TS-032).

**The map flies once per robot per page load.** The same robot jumping from
Rabat to Nairobi within one page load does not fly again; reload. In the Nairobi
sim the first fly is a ~600 m pan at the same zoom.

## Open items

- **AEOC venue coordinates.** `RABAT_VENUE` is Rabat city centre. When the venue
  is known: update `RABAT_VENUE`, `RABAT_BBOX` (±0.7°) and `SITES["rabat"]`;
  the tests enforce the rest.
- **N/W proven on the parser, not on a receiver.** The real NEO-6M has only ever
  fixed S/E. The first live fix in Morocco is the first real-hardware N/W fix:
  check the DB row's signs before anything else.
- **Field time** (TS-025, TS-029) — the remaining finale blocker. Next pass.
- **Nothing stops two `ros_ingest` processes** (TS-032). No lock.
- `run_simulation` has no `--region`; add it only if it becomes the Rabat demo fallback.
- Region is per process, not a `Robot`/`Mission` field.
- `ros_ingest.py` carries a pre-existing unused `import time` (ruff F401).
