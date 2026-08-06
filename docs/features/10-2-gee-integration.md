# F10.2 — GEE Integration & Satellite Data Retrieval

*Date: 2026-08-06*
*Epic: F10 (Satellite EO) — sub-feature 2 of 6*
*Branch: `feat/postgis-foundation`*

---

## What this feature does

Connects RANGER to Google Earth Engine and turns that connection into files:
real Sentinel-2 and Landsat scenes, clipped to real areas of interest in
Marsabit County, stored on disk as validated Cloud-Optimized GeoTIFFs, with
footprints PostGIS confirms intersect the ground they claim to cover — and a
read-only API over all of it.

Where F10.1 was deliberately invisible, this one is the opposite: at the end of
it the platform *holds* satellite data rather than describing a plan to.

**Shipped:**

- `satellite_integration` app with `SatelliteDataset` / `SatelliteQuery` / `SatelliteImage`
- A 10-dataset catalog, every collection ID verified against the live API
- `SensorLog.source` + `provenance_note` — four provenance tiers, defaulting to the weakest
- 12,081 MODELLED Marsabit points across 7 KNRA survey sites, seeded from published statistics
- `gee_client.py` — lazy init, typed exceptions, one `getInfo()` per search, clipped downloads
- `cog.py` — atomic COG translation, validation, band labelling, storage layout
- `fetch_scenes` — the retrieval command, with `--dry-run` and PostGIS-asserted footprints
- Seven read-only, org-scoped API endpoints including a GeoJSON coverage layer
- 138 tests in this app; 225 across the repo

See [`ADR-0012`](../decisions/0012-satellite-eo-gee-cog-pipeline.md) for why
each choice was made.

---

## The AOI: Marsabit County

Seven sites from a KNRA radiological and geochemical survey of former Amoco
oil-exploration and suspected dumping sites (fieldwork 1–5 July 2024, report
April 2026). Bounds are read from the report's figure axes and live in
`core/marsabit.py`.

| Site | Mean dose rate (nSv/h) | Why it matters |
|---|---|---|
| Kargi (Sirius well) | 55 ± 31 | Soil Pb 436, Zn 314 ppm |
| Boji | 46 ± 30 | Worst geochemistry: Pb 616, Cu 454, Zn 794 ppm; water Fe 32 mg/L |
| Gamura | 79 ± 37 | Prospector camp + borehole |
| Dukana (Laga Balal) W1/W2 | 73 / 82 ± 36 | Wells drilled 22 Dec 1985 |
| Balesa (Kalacha) | 87 ± 50 | **Control site** |
| Forole | 140 ± 78, max >1000 | The anomaly. Zr 2185 ppm; report recommends follow-up |

The sites are **100–300 m across**. Sentinel-2 (10 m) and Landsat (30 m)
resolve them; SMAP (11 km), CHIRPS (5.5 km), ERA5 (11 km) and MODIS (1 km) are
regional covariates only. The `scale` field on `SatelliteDataset` encodes this
and a test enforces it.

## Provenance — the thing that must not break

The raw per-point survey logs are **not available** to this project; only the
published report is. Every Marsabit point is generated to match the published
per-site statistics (n, mean, SD, min, max, skew) and labelled `MODELLED`, with
a citation in `provenance_note`.

`SensorLog.source` defaults to `SIMULATED` — deliberately the *least*
authoritative value, so a forgotten label under-claims rather than over-claims.

**Modelled data is never relabelled as reported or live to make a demo look
better.** That single failure would make the platform's central claim false.

---

## Files

**New — backend**

| Path | Purpose |
|---|---|
| `ranger_backend/satellite_integration/models.py` | Dataset / Query / Image, with the tenancy asymmetry |
| `ranger_backend/satellite_integration/gee_client.py` | Earth Engine wrapper: init, search, clipped download |
| `ranger_backend/satellite_integration/cog.py` | Raster I/O, COG translation, storage layout |
| `ranger_backend/satellite_integration/serializers.py` | Read-only API shapes |
| `ranger_backend/satellite_integration/views.py` | Seven org-scoped read endpoints |
| `ranger_backend/satellite_integration/urls.py` | Routes under `/api/satellite/` |
| `ranger_backend/satellite_integration/management/commands/seed_datasets.py` | The catalog |
| `ranger_backend/satellite_integration/management/commands/check_gee.py` | Credential + collection-ID check |
| `ranger_backend/satellite_integration/management/commands/fetch_scenes.py` | Retrieval |
| `ranger_backend/core/marsabit.py` | KNRA survey reference data |
| `ranger_backend/core/management/commands/seed_marsabit.py` | Modelled point generation |
| `ranger_backend/satellite_integration/conftest.py` | Synthetic raster factory |

**Modified**

| Path | Change |
|---|---|
| `ranger_backend/core/models.py` | `SensorLog.source` + `provenance_note` |
| `ranger_backend/core/serializers.py` | Provenance in every row (changed the CSV header) |
| `ranger_backend/core/views.py` | Provenance in map-data properties |
| `ranger_backend/ranger_backend/settings/base.py` | `GEE_*` settings |
| `ranger_backend/ranger_backend/urls.py` | `/api/satellite/` include |
| `ranger_backend/requirements/base.txt` | earthengine-api, rasterio, rio-cogeo, requests |
| `ranger_backend/pytest.ini` | `satellite_integration` in `testpaths` |

**Tests:** `test_gee_client.py`, `test_seed_datasets.py`, `test_cog.py`,
`test_fetch_scenes.py`, `test_api.py`, `core/test_provenance.py`,
`core/test_seed_marsabit.py`.

---

## Checkpoints

| CP | What shipped |
|---|---|
| CP0 | GEE access: Cloud project `ranger-eo`, service account, IAM roles, key outside the repo |
| CP1 | `satellite_integration` app + three models |
| CP2 | `SensorLog` provenance + the 10-dataset catalog |
| CP3 | `seed_marsabit` — 12,081 modelled points |
| CP4 | `gee_client` — lazy init, typed exceptions, one `getInfo()` per search |
| CP5 | `fetch_scenes` — clipped COG retrieval, PostGIS-asserted footprints |
| CP6 | Read-only org-scoped API + docs |

---

## Commands

```bash
# Verify credentials and every catalog collection ID
python manage.py check_gee

# (Re)seed the catalog — idempotent, never resets is_verified
python manage.py seed_datasets

# Seed the modelled Marsabit ground data
python manage.py seed_marsabit --scale 1.0

# See what a retrieval would fetch. One getInfo(), nothing written.
python manage.py fetch_scenes --site forole --dataset s2 \
    --start 2026-01-01 --max-cloud 20 --dry-run

# Retrieve for real
python manage.py fetch_scenes --site forole --dataset s2 \
    --start 2026-01-01 --max-cloud 20 --limit 1 --org knra
```

Site codes: `kargi`, `boji`, `gamura`, `dukana-w1`, `dukana-w2`, `balesa`,
`forole`. Dataset codes: `s2`, `s1`, `s5p_no2`, `smap`, `modis_lst`, `l5`,
`l8`, `l9`, `chirps`, `era5_land`.

## API

All endpoints are `IsAuthenticated`. Datasets are global; everything else is
org-scoped, images through `query__organization`.

```
GET /api/satellite/datasets/       ?verified= &scale= &include_inactive=
GET /api/satellite/datasets/<id>/
GET /api/satellite/queries/        ?dataset= &status=
GET /api/satellite/queries/<id>/   includes nested images
GET /api/satellite/images/         ?dataset= &query= &date_start= &date_end= &bbox=
GET /api/satellite/images/<id>/
GET /api/satellite/coverage/       GeoJSON FeatureCollection of footprints
```

`cog_path` is never serialized — see ADR-0012, Decision 6.

---

## Verified against live Earth Engine

| Dataset | Scene | Result |
|---|---|---|
| `s2` | `COPERNICUS/S2_SR_HARMONIZED/20260805T073609_..._T37NCE` | 112×119 px, 7 bands, 124 kB |
| `l9` | `LANDSAT/LC09/C02/T1_L2/LC09_168058_20260706` | 38×41 px, 7 bands, 27 kB |

Both over Forole, both under org `knra`, both with band names from the catalog,
both with footprints PostGIS confirms intersect the queried AOI.

---

## Gotchas

1. **`django.contrib.gis` in `INSTALLED_APPS` without the PostGIS `ENGINE`
   passes every check.** Fails at the first geometry `AddField`. (016)
2. **ROS 2 breaks pytest.** Always `PYTHONPATH= pytest`. (017)
3. **A GEE service account needs TWO IAM roles.** A valid key with missing
   roles 403s identically to a bad key. (018)
4. **A stale catalog row is indistinguishable from a product characteristic.**
   Blank `cloud_property` silently disables cloud filtering. (019)
5. **`pytest.ini` `testpaths` must list every app** — an uncollected test file
   is indistinguishable from a passing one.
6. **`importlib.reload` mints new exception classes**; use `module_from_spec`.
7. **GEE emits Landsat footprints as `LinearRing`**, which is not valid GeoJSON.
8. **Anything touching `ee.Geometry` must run after `ee.Initialize()`** —
   module-level geometry constants fail at import.
9. **Earth Engine returns errors with HTTP 200.** Check TIFF magic bytes.
10. **GEE does not name bands.** Stamp them from the catalog at ingest.
11. **`getDownloadURL` caps around 32 MB** with an opaque error; estimate first.
12. **Naive datetimes against an aware field** are correct only because Django
    guesses `TIME_ZONE` for you. Say what you mean.

## Known gaps at close

- The Data Explorer frontend does not render `source`. The backend guarantee is
  intact; the presentation is not. **First checkpoint of F10.3.**
- The `knra` org has no user account — `seed_marsabit` creates the org, robots,
  and missions but nobody who can log in.
- `Mission.robot` is non-null, so a satellite-only AOI (Chumvi) has no home.
- Two queries can claim the same COG file.
- Nothing verifies the database against the catalog spec.
- GEE noncommercial registration vs the F10.5 business model. Unresolved.
