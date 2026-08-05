# F10.1 — PostGIS Foundation

*Date: 2026-08-03*
*Epic: F10 (Satellite EO) — sub-feature 1 of 6*
*Branch: `feat/postgis-foundation`*

---

## What this feature does

Migrates RANGER's position storage from float column pairs to PostGIS geometry,
so that the satellite epic's core operation — matching a ground measurement to
the satellite pixel above it — is a spatial join with index support rather than
hand-rolled maths.

It is deliberately **invisible**: every screen behaves identically afterward,
every API payload is byte-identical, and no frontend file changed. The value is
entirely in what it makes possible (F10.2 onward).

**Shipped:**

- PostGIS 3.5 on the Docker Postgres; GDAL/GEOS/PROJ on the host
- GeoDjango wired (`django.contrib.gis` + PostGIS backend engine)
- `SensorLog.location`, `Waypoint.location` — `PointField(4326)`, NOT NULL, GiST-indexed
- `Mission.area_of_interest` — new nullable `PolygonField(4326)` for F10.2
- `core/geo.py` — the single sanctioned lat/lon → geometry conversion
- `latitude` / `longitude` float columns dropped, returning as derived properties
- First pytest configuration in the repo + 21 core / 8 missions tests

See [`ADR-0011`](../decisions/0011-geospatial-db-postgis-now-timescaledb-later.md)
for why each of those choices was made.

---

## Files

**New**

| Path | Purpose |
|---|---|
| `ranger_backend/core/geo.py` | `point_from_latlon`, `polygon_from_bbox`, `KENYA_BBOX` |
| `ranger_backend/core/migrations/0003_enable_postgis.py` | `CreateExtension("postgis")` |
| `ranger_backend/core/migrations/0004_sensorlog_location.py` | add nullable geometry |
| `ranger_backend/core/migrations/0005_backfill_sensorlog_location.py` | populate + assert |
| `ranger_backend/core/migrations/0006_sensorlog_location_required.py` | NOT NULL |
| `ranger_backend/core/migrations/0007_drop_sensorlog_floats.py` | drop lat/lon (irreversible) |
| `ranger_backend/missions/migrations/0002_waypoint_location_mission_aoi.py` | geometry + AOI |
| `ranger_backend/missions/migrations/0003_backfill_waypoint_location.py` | populate + assert |
| `ranger_backend/missions/migrations/0004_waypoint_location_required.py` | NOT NULL |
| `ranger_backend/missions/migrations/0005_drop_waypoint_floats.py` | drop lat/lon (irreversible) |
| `ranger_backend/pytest.ini` | pytest + pytest-django config |
| `ranger_backend/conftest.py` | shared fixtures incl. `sensor_log_at` factory |

**Modified**

| Path | Change |
|---|---|
| `docker-compose.yml` | `postgres:16-alpine` → `postgis/postgis:16-3.5-alpine` |
| `ranger_backend/ranger_backend/settings/base.py` | `django.contrib.gis` app + PostGIS `ENGINE` |
| `ranger_backend/core/models.py` | `location` field; lat/lon as properties |
| `ranger_backend/missions/models.py` | `location`, `area_of_interest`; lat/lon as properties |
| `ranger_backend/core/serializers.py` | lat/lon → `ReadOnlyField` (Meta.fields unchanged) |
| `ranger_backend/core/views.py` | map-data reads `location.x/.y` |
| `ranger_backend/core/management/commands/run_simulation.py` | writes via `point_from_latlon`; new `--seed` |
| `ranger_backend/core/tests.py`, `missions/tests.py` | stubs → real suites |

**Deliberately unchanged:** `core/admin.py` (`list_display` resolves model
properties as-is), and **every file under `ranger_frontend/`**.

---

## The migration pattern: expand → migrate → contract

Three migrations per model, never one. A single migration mixing
`AddField(null=False)` with a data backfill cannot succeed on a populated table.

```
0004  AddField(location, null=True)          ← expand
0005  RunPython(backfill + assert)           ← migrate
0006  RunPython(guard) + AlterField(NOT NULL)← contract
0007  RemoveField(latitude, longitude)       ← cutover (irreversible)
```

0005 is genuinely reversible: its `reverse` writes the floats back out of the
geometry, so `migrate core 0004` restores the pre-backfill state. 0007 is not —
after it, the float data exists only in a `pg_dump`.

The backfill migrations **do not import `core.geo`**. Migrations are frozen
history; importing application code means a future refactor of `geo.py`
retroactively changes what an applied migration did. The `Point(lon, lat)`
construction is inlined with its own assertions.

---

## Verification method

Because this feature must change nothing user-visible, verification was
contract-diffing rather than feature-testing. Three scripts (kept outside the
repo, in `~/ranger-baselines/`):

- `capture.sh <label>` — authenticates, saves `/api/map-data/`,
  `/api/data-logs/?page=1`, `/api/chart-data/`, and the CSV export, plus a DB
  shape snapshot. Payloads are normalized (sorted by `id`) because `RemoveField`
  rewrites the table and can reorder rows sharing a timestamp.
- `compare.sh <before> <after>` — diffs two captures.
- `verify_cp3.py` — checks what the API diff *cannot* see: waypoint geometry,
  spatial index presence, AOI column, and spatial query behaviour.

Captured at four points (`cp0`, `cp2`, `cp3`, `cp4`), every comparison clean.

**The waypoint gap is worth internalizing:** no endpoint serializes `Waypoint`,
so the contract diff is blind to it. An inverted waypoint doesn't raise — it
makes the simulator steer toward a target in the wrong place, discovered weeks
later. Hence per-row assertions in the backfill and dedicated tests in
`missions/tests.py`.

---

## Gotchas encountered

1. **`django.contrib.gis` in `INSTALLED_APPS` without the PostGIS `ENGINE`
   passes every check.** `manage.py check` was clean, `CreateExtension` applied
   fine, and the failure only surfaced at the first geometry `AddField` with
   `AttributeError: 'DatabaseOperations' object has no attribute 'geo_db_type'`.
   See [`troubleshooting/016`](../troubleshooting/016-geodjango-app-without-postgis-engine.md).

2. **ROS 2 on `PYTHONPATH` breaks pytest entirely.** Sourcing
   `/opt/ros/humble/setup.bash` puts ROS's Python 3.10 site-packages on the path;
   pytest auto-loads ROS's `launch_testing` plugin into the 3.11 venv and dies
   before collecting anything. See
   [`troubleshooting/017`](../troubleshooting/017-ros-pythonpath-breaks-pytest.md).

3. **`reverse("data-logs")` doesn't exist** — the URL names are `data-log-list`
   and `data-log-export-csv`. Compile checks don't catch bad `reverse()` names;
   only running the tests does.

4. **Alpine vs Debian PostGIS image.** The existing volume was initialized by
   `postgres:16-alpine` (musl). Switching to the Debian PostGIS image would
   change the libc under an existing data directory — same PG major, so it
   starts, but locale/collation differences can subtly affect text index
   ordering. The alpine PostGIS tag avoids the question entirely.

---

## Carry-forwards to F10.2+

- **Host GDAL is 3.4.1** (Ubuntu 22.04) while the container ships PostGIS 3.5.7.
  Fine for GeoDjango, but `rasterio` / `rio-cogeo` build against the *host* GDAL
  and some COG features want 3.6+. Resolve at F10.2.
- **`--seed` exists on `run_simulation`, but demo data is still in Nairobi**
  (36.82 E, −1.29 S), not the Magadi basin AOI in the satellite mockup. F10.4
  correlation needs real ground points inside the featured AOI. Positioning
  reproducible seed data there is a prerequisite task, not part of F10.1.
- **`conftest.py`'s `sensor_log_at` factory is written for reuse** — F10.4's
  correlation tests need exactly "ground points at known positions inside a known
  footprint."
- **ROS/venv Python version split (3.10 vs 3.11)** becomes a real architectural
  question at F08/F09, when the ROS bridge needs `rclpy` rather than being a stub.
- **TimescaleDB still deferred.** Revisit at millions of rows.
