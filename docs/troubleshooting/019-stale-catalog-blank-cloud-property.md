# 019 — `--max-cloud` silently did nothing: catalog rows blank since the field was added

*Date: 2026-08-06*

---

## What we saw

F10.2 CP5, the first live dry run against Earth Engine:

```bash
python manage.py fetch_scenes --site forole --dataset s2 \
    --start 2026-01-01 --max-cloud 20 --dry-run
```

```
--max-cloud ignored: s2 has no cloud property (radar and reanalysis products
have no cloud concept). ...
  COPERNICUS/S2_SR_HARMONIZED/20260805T073609_..._T37NCE @ 2026-08-05 (cloud n/a)
  COPERNICUS/S2_SR_HARMONIZED/20260802T075451_..._T37NCE @ 2026-08-02 (cloud n/a)
  COPERNICUS/S2_SR_HARMONIZED/20260731T073611_..._T37NCE @ 2026-07-31 (cloud n/a)
```

Sentinel-2 unambiguously *has* a cloud property — `CLOUDY_PIXEL_PERCENTAGE`,
and it is right there in `seed_datasets.py`. Every scene reported `cloud n/a`,
and a 20% ceiling excluded nothing.

Confirmed across the whole catalog:

```bash
python manage.py shell -c 'from satellite_integration.models import SatelliteDataset as D; print("\n".join(f"{d.code:<10} {d.cloud_property or chr(45)}" for d in D.objects.order_by("code")))'
```

```
chirps     -
era5_land  -
l5         -          ← should be CLOUD_COVER
l8         -          ← should be CLOUD_COVER
l9         -          ← should be CLOUD_COVER
modis_lst  -
s1         -
s2         -          ← should be CLOUDY_PIXEL_PERCENTAGE
s5p_no2    -
smap       -
```

## What caused it

`cloud_property` was added to the model and to the `DATASETS` spec in CP2, but
`seed_datasets` was never re-run afterwards. The catalog rows predated the
field, so they carried its `blank=True, default=""`.

The write path was never broken — re-running repaired all ten in one pass
(`0 created, 10 updated`), which is what proves it was drift rather than a bug.

Why it stayed invisible for two checkpoints:

1. **A blank `cloud_property` is meaningful, not missing.** Radar and reanalysis
   products genuinely have no scene-level cloud percentage. `search_scenes`
   deliberately skips the filter when the property is absent, because filtering
   on a property a collection does not have returns an *empty collection* rather
   than an error — which reads as "no scenes over this AOI".
2. **`check_gee` cannot see this.** It verifies the catalog against the external
   world — do these collection IDs resolve? Nothing verifies the database
   against the catalog *spec*, so a correct spec sat beside empty columns.
3. **No test asserted it.** `test_seed_datasets.py` covered creation and
   idempotency, not field values.

## The part that was our fault

`fetch_scenes` warned correctly — and then **explained the anomaly away**:

> `--max-cloud ignored: s2 has no cloud property (radar and reanalysis products
> have no cloud concept).`

True for `s1`, `chirps`, `era5_land`. Completely wrong for `s2`. A message that
rationalises the thing it is reporting converts "something is off" into "this is
expected", and it was read past twice before anyone stopped.

## How we fixed it

```bash
python manage.py seed_datasets
```

Then three things so it cannot recur silently:

1. **The warning no longer asserts a cause.** It now says the catalog row has no
   `cloud_property`, notes that this is correct for radar and reanalysis, and
   states explicitly that for an *optical* product it means the row is stale and
   `seed_datasets` should be re-run.
2. **`TestCloudProperty` in `test_seed_datasets.py`** — asserts the four optical
   products carry their property, the six others are deliberately blank, and a
   blanked row is repaired by re-seeding.
3. **Recorded as a carry-forward:** a drift check inside `check_gee` comparing
   every database row against the `DATASETS` spec. Roughly fifteen lines, and it
   would have caught this in a second.

## How to prevent it

**Re-run `seed_datasets` after any change to the catalog spec or the model.** It
is idempotent, it does not reset `is_verified`, and it takes under a second.

More generally: this repo has two verification directions and only ever built
one. `check_gee` asks *does the external world match our catalog?* Nothing asked
*does our database match our catalog?* Any seeded reference table has the same
exposure — `SensorType` and the demo Groups included.

And when a warning fires on a path you expected to be clean, read it as a
question rather than a statement. This one was legible enough to disbelieve only
because the product it named was obviously wrong for the claim it made.
