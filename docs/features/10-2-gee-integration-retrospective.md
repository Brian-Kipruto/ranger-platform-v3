# F10.2 — Retrospective

*Date: 2026-08-06*

---

## What worked

**Typed exceptions at the Earth Engine boundary paid for themselves in CP0.**
Earth Engine reports configuration errors, auth failures, quota exhaustion, and
missing collections as the same `ee.EEException` with different prose. Writing
`_translate` once, and putting the two-IAM-roles explanation *inside*
`GEEAuthenticationError`'s message, meant the 403 during setup arrived already
diagnosed. Every later failure in the feature was legible for the same reason.

**`--dry-run` caught the most expensive bug in the feature before spending a
byte.** The blank `cloud_property` across the whole catalog (019) surfaced on
the first live search, in a mode that costs one `getInfo()` and writes nothing.
Had `fetch_scenes` been built without it, the first indication would have been a
downloaded scene under cloud, or worse, a demo built on one.

**Asserting the footprint intersection in PostGIS rather than trusting
`filterBounds`.** It has never fired against real data — which is the point.
It uses the same index-backed predicate F10.4's correlation join will use, so
the day it does fire it will fire here, at ingest, rather than three
checkpoints later as a correlation that returns nothing.

**Reading the footprint off the raster instead of taking GEE's.** Earth Engine
reports the whole scene's extent; the clip is a thousand times smaller. This was
a two-line decision that prevented the database from claiming coverage over
ground nobody downloaded — and it would have been nearly impossible to notice
downstream, because a too-large footprint produces *more* correlation matches,
not fewer.

**Atomic COG writes.** Translate to `<dest>.partial`, validate, then rename.
`cog_path` in a row is now a promise the file is complete and valid, which is
exactly the kind of invariant that is cheap to establish once and impossible to
retrofit after the first half-written file appears.

**Provenance defaulting to the weakest value.** `SensorLog.source` defaults to
`SIMULATED`. Every code path that forgets a label under-claims. This is one line
of model definition doing more work than any test in the feature.

**Splitting `cog.py` from `gee_client.py`.** `import rasterio` pulls a bundled
GDAL; `check_gee`, `seed_datasets`, and every test module import `gee_client`
and none of them need it. The split also made the entire raster pipeline
testable with a synthetic GeoTIFF and no credentials — 30-odd tests that run on
any laptop.

**Verifying against live GEE at CP5 rather than waiting for CP6.** Two datasets
retrieved end to end before a line of API code existed. The API was then built
against real rows with real band names and real footprints, not fixtures.

---

## What hurt

**Three separate instances of stale state that read as correct data.** This is
the theme of the feature, and it cost more than every genuine bug combined:

1. **Catalog rows blank since CP2.** `cloud_property` was added to the model and
   the spec but `seed_datasets` was never re-run. `--max-cloud 20` became a
   no-op, every scene reported `cloud n/a`, and nothing errored. (019)
2. **Two scenes retrieved before the band-labelling fix**, then silently reused
   by the "don't re-download" path, so they kept generic `band_1..band_7` names
   after the fix landed. Required `--overwrite` and a manual row cleanup.
3. **A test fixture creating a `Mission` without a robot**, which passed review
   and failed only against a real database.

None of these produced an error. Each produced plausible output that a slide
could have been built on.

**A warning that explained away the thing it was reporting.** The original
`--max-cloud ignored` message asserted a *cause* — "radar and reanalysis
products have no cloud concept" — which is true for `s1` and false for `s2`. It
was read past twice. A message that rationalises its own anomaly is worse than
no message: it converts "something is off" into "this is expected". Rewritten to
state the observation and name both possible causes.

**Warnings on the happy path.** Every scene emitted three GDAL warnings — an
`INTERLEAVE` mismatch between rio-cogeo's profile and GDAL's COG driver, and
two libtiff `PHOTOMETRIC` complaints about Earth Engine's own file. All benign,
all firing on every single retrieval. Fixed rather than tolerated, because noise
on a clean run is precisely how you learn to scroll past the warning that
matters. The photometric one is filtered by *message text* rather than by log
level, so genuine raster warnings still surface.

**`requirements/base.txt` was invalid and nobody knew.** A missing newline had
welded `Pillow==11.0.0` and `earthengine-api==1.7.38` into one unparseable
requirement. The venv worked only because earthengine-api had been installed by
hand. A fresh environment could not have been built from the repo — for an
unknown number of weeks.

**Two docstrings kept asserting a claim the pitch had already retracted.** The
Landsat drilling-era change-detection story was demoted on 2026-08-05 after
pulling the actual thumbnails, but `core/marsabit.py` and `seed_datasets.py`
still described it as the reason the archive matters. A claim that survives in a
docstring after being retracted in the narrative is a claim waiting to be picked
back up by whoever reads the code next.

**The frontend silently drops provenance.** CP2 added `source` and
`provenance_note` to the serializer, the CSV export, and the map payload, with
tests asserting each path. `DataExplorerPage.tsx` defines fourteen columns and
`source` is not among them; `dataLog.types.ts` does not have the field. So the
console currently displays 12,081 modelled points with instrument names, mission
names, and dose values, and nothing on screen distinguishes them from
measurements. The backend contract is intact and the guarantee is not — the
honesty system was defeated by the one door nobody guarded. **Found by looking
at the running app, not by any test.**

---

## Workflow notes

**Verification directions.** The repo built `check_gee` to verify the catalog
against the external world and never built the reverse — does the database match
the catalog spec? That asymmetry is what let 019 live for two checkpoints. Any
seeded reference table has the same exposure.

**"It compiles" and "the tests pass" were both insufficient, in different
ways.** The mission-fixture bug passed `py_compile` and `ruff` and failed on a
real database. The provenance-column gap passes *every* test in the repo,
because no test asserts what the frontend renders. Screenshot loops on the
running app remain the only check that catches the second class.

**Live verification early is worth its quota.** CP5's live run against Earth
Engine cost two scenes and surfaced the catalog drift, the band-naming gap, and
three warning classes. Deferring it to CP6 would have meant discovering all of
them while building the API on top.

**Full-file overwrites over spliced edits, when the exact current content is
known.** `gee_client.py` was delivered as a complete file with a `diff` proving
the first 307 lines were byte-identical, rather than as a find/replace. Given
troubleshooting 015 and 016 were both partially-applied multi-edit handoffs,
verifiable-whole beats surgical-and-hopeful.

---

## Carry-forwards

**Into F10.3 (immediately, before any satellite UI):**

- **Render `source` in the Data Explorer** — type, column, chip, and a banner
  when a filtered set is entirely modelled. This is a correctness fix, not a
  feature.
- **A demo account for the `knra` org in `seed_marsabit`.** The tenant owning
  every Marsabit point and both COGs has nobody who can log in. A user created
  by hand in admin does not survive a database rebuild.
- **The mockup's satellite screen is partly fiction.** It lists Planet SkySat
  and Maxar WorldView-3 as CONNECTED and labels the AOI "Magadi basin". The
  DATA PROVIDERS panel must be driven off `SatelliteDataset.is_verified` over
  the real catalog.
- **The CHANGE Δ toggle needs an honest form.** Two real Sentinel-2 dates in a
  swipe comparison is defensible; calling it change detection is not.

**Into F10.4:**

- Band names are now stamped from the catalog, so band selection can be by name.
- Values are raw. NDVI from raw DN is correct (the scale factor cancels);
  thermal needs the documented scale and offset applied.
- `conftest.py`'s `sensor_log_at` factory was written for exactly this —
  ground points at known positions inside a known footprint.

**Into F10.5:**

- **GEE noncommercial registration vs the business model.** Unresolved, and it
  gates data licensing entirely.
- **Lab results have no schema home** — 16 soil + 4 water rows.
- **`Mission.robot` is non-null**, so a satellite-only AOI cannot be represented
  without inventing a phantom robot. Chumvi is the strongest satellite argument
  in the pitch and currently has nowhere to live.
- **ADR-0007** (no route guards) — first real enforcement lands here.
- **ADR-0009** (demo login buttons) must be stripped before any public deploy.

**Technical debt worth an hour each:**

- A drift check in `check_gee` comparing database rows to the `DATASETS` spec.
- `core/views.py` has the same naive-datetime pattern the satellite views just
  fixed — same three-hour exposure, currently benign for the same reason.
- Duplicate demo users (`client` / `client@magadi.com`, and the same for
  community and operator) from `seed_demo` running under two conventions.
- Two queries can claim the same COG file; the second silently invalidates the
  first row's metadata.
