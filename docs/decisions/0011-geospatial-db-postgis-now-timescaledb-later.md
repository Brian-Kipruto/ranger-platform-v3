# 0011 — Geospatial DB: PostGIS now, TimescaleDB later

*Date: 2026-08-03*
*Status: Accepted*

---

## Context

F10 reframes RANGER as **ground-truth infrastructure for Earth Observation** —
the layer that validates satellite EO products against real ground measurements.
The core operation of the whole epic (F10.4) is: given a `SensorLog` with a
position and a timestamp, find the satellite scene whose footprint *contains*
that point within ±N days, read the pixel value there, and store the delta.

That is a spatial join. Before F10.1, positions were stored as two indexed
`FloatField` columns (`latitude`, `longitude`) on `SensorLog` and `Waypoint`,
and `Mission` had no geometry at all. Point-in-polygon against a scene footprint
is not expressible against float columns without hand-rolling the maths, and it
cannot use a spatial index.

Two database extensions were candidates for this epic. Both are additive to the
Postgres already running in Docker.

## Problem

Which geospatial/time-series capability do we adopt, when, and in what
representation — given that changing the storage of `location` later means
re-migrating live tables a second time?

## Options considered

1. **PostGIS now, TimescaleDB now.** Rejected. TimescaleDB converts tables to
   hypertables, which is a second invasive migration of the same tables, with
   its own operational surface (chunk sizing, retention policies, backup
   implications). It is a *performance* optimization: invisible to the pitch,
   and the row counts (hundreds, not millions) do not need it.
2. **TimescaleDB first, PostGIS later.** Rejected. Adding PostGIS afterwards
   means re-migrating `SensorLog.location` a second time, on a table that is by
   then a hypertable.
3. **Neither — compute spatial joins in Python.** Rejected. Point-in-polygon
   over every scene footprint in application code, with no index, is both slower
   and more code than `ST_Within`, and it would have to be rewritten when the
   data grows.
4. **PostGIS now, TimescaleDB deferred.** Chosen.

## Decision

**Adopt PostGIS in F10.1. Defer TimescaleDB indefinitely** — it can be added
later *without* redoing any satellite work, because hypertable conversion does
not change column types.

Within that, four sub-decisions:

### Geometry as the sole source of truth

`SensorLog.location` and `Waypoint.location` are `PointField(srid=4326)`, NOT
NULL, GiST-indexed. The `latitude` / `longitude` **columns are dropped**; the
names survive as read-only model properties over `location`:

```python
@property
def latitude(self) -> float | None:
    return self.location.y if self.location else None
```

Considered and rejected: keeping both columns in sync via `save()`. That works
only while every write goes through `save()` — and F10.2's ingestion, plus the
F08/F09 ROS bridge, will want `bulk_create`. Two sources of truth that silently
diverge is the worst outcome available, because the correlation engine reads
geometry while the Data Explorer reads floats.

The property shim means the API response shape, the CSV export header, the
TypeScript types, and the Data Explorer frontend are **completely unchanged** by
this migration. Verified by byte-diffing `/api/data-logs/`, `/api/map-data/`,
`/api/chart-data/`, and the CSV export before and after.

This is only viable because nothing filtered on the floats — verified by grep
across the codebase at F10.1: no `filter(latitude__…)`, no `order_by`, no
`values()`. Properties cannot be used in ORM queries. Any future spatial query
should use `location` with PostGIS lookups anyway.

### `geometry(Point, 4326)`, not `geography`

WGS84 matches GeoJSON and MapLibre directly, so reads need no transform.
`ST_Within` / `ST_Intersects` against scene footprints — the F10.4 use case — is
a planar containment test where `geometry` is faster. True metric distance is
still available where needed via `.transform()` or a `geography` cast.

### 2D, not `PointZ`

Altitude already lives relationally on `ImuBaroLog.altitude_baro`. A Z dimension
would complicate GeoJSON output and every PostGIS predicate for a value we
already store.

### One sanctioned write path

`core/geo.py` exposes `point_from_latlon(*, lat, lon, region=KENYA_BBOX)`. It is
the **only** place lat/lon becomes a geometry.

PostGIS `Point(x, y)` takes **(longitude, latitude)** — the reverse of how humans
say it. Getting it backwards does not raise: an inverted Kenyan coordinate
(-1.29, 36.82) → (36.82, -1.29) is a perfectly valid position in the Indian
Ocean off Somalia. It renders on a map. It passes every type check. The helper's
arguments are keyword-only (so a positional call is impossible) and it validates
against a region bbox, which is the *only* check that catches inversion — both
transposed values are individually in valid global range.

`region=None` is the escape hatch for legitimately out-of-region data (satellite
AOIs elsewhere, imported datasets).

## Consequences

**Good**
- Spatial joins are now a one-line ORM query with index support: `SensorLog.objects.filter(location__within=footprint)`.
- `Mission.area_of_interest` (nullable `PolygonField`) exists, so F10.2's
  `SatelliteQuery` has something to scope against without another migration.
- Zero frontend changes; zero API contract change.
- The inversion trap is now guarded in one place and tested permanently.

**Costs / carry-forwards**
- Host machines need GDAL/GEOS/PROJ installed natively (Django runs outside
  Docker). New dev machines: `sudo apt install binutils libproj-dev gdal-bin libgdal-dev libgeos-dev`.
- The Postgres image is now `postgis/postgis:16-3.5-alpine`. Alpine chosen so
  the existing volume's libc is unchanged.
- `latitude` / `longitude` are no longer sortable in Django admin (properties
  can't be ordered by). Accepted — sorting on raw floats had no real use.
- Host GDAL is 3.4.1 (Ubuntu 22.04). **F10.2 carry-forward:** `rasterio` /
  `rio-cogeo` build against the host GDAL, and some COG features want 3.6+. This
  may force a GDAL upgrade or a containerized backend at F10.2.
- TimescaleDB remains deferred, not rejected. Revisit when `SensorLog` reaches
  millions of rows or time-bucket queries become slow.
