# 0012 — Satellite EO: GEE primary, COGs on disk, provenance tiers, tenancy asymmetry

*Date: 2026-08-06*
*Status: Accepted*

---

## Context

F10.2 makes RANGER actually hold satellite data. F10.1 gave us geometry; this
feature gives us scenes — retrieved from a real provider, clipped to real areas
of interest, stored on disk, and queryable by the spatial predicates F10.4's
correlation engine will use.

The area of interest is seven sites from a KNRA radiological and geochemical
survey of former Amoco oil-exploration sites in Marsabit County (fieldwork
1–5 July 2024, report April 2026). The sites are **100–300 m across**, which
drives more of this ADR than anything else: it decides which products can
resolve a site at all, how much of a scene is worth downloading, and whether a
given dataset is a measurement or a covariate.

It also sits under a pitch. The Africa Earth Observation Challenge positions
RANGER as ground-truth infrastructure validating satellite EO products over
African landscapes. That framing is only defensible if every claim the platform
makes is traceable to something real, which is why half the decisions below are
about provenance rather than plumbing.

## Problem

Six coupled questions, each of which is expensive to reverse:

1. Which satellite data provider, given a noncommercial registration and a
   commercial business model on the roadmap?
2. How does data of differing authority — measured, published, modelled,
   simulated — coexist in one table without the weakest silently borrowing the
   credibility of the strongest?
3. How do three new models divide along tenant lines?
4. How do scenes get from the provider onto disk?
5. In what projection, and with what pixel values?
6. What does the API expose, and what must it never expose?

---

## Decision 1 — Google Earth Engine as the primary provider

**Chosen.** GEE's catalog covers everything the epic needs (Sentinel-1/2/5P,
Landsat 5/8/9, SMAP, MODIS, CHIRPS, ERA5) behind one credential, with
server-side filtering so a search costs one round trip rather than a catalog
crawl.

Alternatives considered: **Sentinel Hub** (excellent, but Copernicus-only —
no SMAP, no MODIS, no CHIRPS, so we would need a second provider anyway);
**STAC via pystac-client** (provider-agnostic and the right long-term answer,
but discovery only — it finds assets, it does not compute, so NDVI and band
math would move to our machine); **direct Copernicus Data Space** (same
Copernicus-only limitation, more plumbing).

### The unresolved consequence

The Cloud project `ranger-eo` is registered **noncommercial** and runs on the
Community Tier. Licensing GEE-derived products under an LLC — which is exactly
what F10.5's data-licensing model proposes — is commercial use. This is not a
problem today and is a real one before any revenue. The likely resolutions are
a commercial GEE licence, or moving the production path to Sentinel Hub or
Copernicus Data Space while keeping GEE for research. **Deferred to F10.5, and
deliberately recorded here rather than in a comment nobody reads.**

## Decision 2 — Four provenance tiers, defaulting to the weakest

`SensorLog.source` carries one of `live` / `reported` / `modelled` /
`simulated`, with `provenance_note` for the citation.

The raw per-point KNRA survey logs are **not available to this project** — only
the published report. Every Marsabit point is therefore *generated* to match the
report's per-site statistics (n, mean, SD, min, max, skew) and labelled
`MODELLED`. The distribution is faithful; the individual points are fiction.

**The default is `SIMULATED`, the least authoritative value.** This is the whole
design in one line: a row written by code that forgot to set `source`
under-claims rather than silently asserting a measurement that was never made.
Considered and rejected: defaulting to `LIVE` (matching the common case of real
telemetry), which inverts the failure mode so that forgetting a label
manufactures credibility.

Labels ride in the serializer, the CSV export, and the map-data properties.
Tests in `core/test_seed_marsabit.py` and `core/test_provenance.py` assert they
survive every path out of the backend.

**Known gap at time of writing:** the Data Explorer *frontend* does not render
`source` — the field is in the payload and absent from the table's column set.
The backend guarantee is intact; the presentation is not. Closing this is the
first checkpoint of F10.3, ahead of any satellite UI.

## Decision 3 — Three models, three different tenancy answers

Deliberate asymmetry, each half following an existing precedent:

| Model | Tenancy | Precedent |
|---|---|---|
| `SatelliteDataset` | **None.** Global reference data | `SensorType` |
| `SatelliteQuery` | `organization` FK **directly** | `Mission` |
| `SatelliteImage` | **Through** `query__organization` | `SensorLog` through `Robot` (ADR-0006) |

Sentinel-2 is Sentinel-2 for every tenant; a per-org catalog would imply each
tenant has a private view of the sky. A query, by contrast, is *initiated* by an
org and spends real EECU quota, so the org that spent it owns the record — and
unlike a `SensorLog`, there is no robot to inherit from. An image inherits from
its query for the same reason a sensor log inherits from its robot: it is always
reached through its parent, and a second FK is a second thing to keep in sync.

## Decision 4 — `getDownloadURL` to a COG on disk

**Chosen:** synchronous `ee.Image.getDownloadURL(format="GEO_TIFF")`, clipped
to the AOI, converted to a Cloud-Optimized GeoTIFF with rio-cogeo, stored under
`MEDIA_ROOT/satellite/<org>/<dataset>/<asset-id>.tif`.

**Clipping is not optional.** A full Sentinel-2 tile is ~1 GB; a Forole site
buffered by 500 m at 10 m is ~400 kB. An unclipped request would spend Community
Tier quota on roughly a million times more pixels than anyone looks at.

Rejected: **`Export.image.toDrive` / `toCloudStorage`** — asynchronous, needs a
Drive or GCS destination and a polling loop, for payloads three orders of
magnitude under the synchronous endpoint's 32 MB ceiling. Rejected: **caching
GEE tile URLs as the display path** — Google expires them after days, which
means a demo built on them fails silently, later, with no error. `tile_url` and
`tiles_expire_at` exist on the model as a *cache*, and `tiles_are_stale()`
exists so nothing can treat them as a source of truth. `gee_asset_id` is the
durable identifier; everything regenerates from it.

Two supporting rules, both enforced in `satellite_integration/cog.py`:

- **Writes are atomic.** Translation goes to `<dest>.partial` and is renamed
  onto the final path only after `cog_validate` passes. A crash, a kill, or a
  full disk therefore never leaves a half-written raster at a path a row points
  at. `cog_path` is a promise the file is complete.
- **Downloads are checked for TIFF magic bytes.** Earth Engine returns errors
  with HTTP 200 — an HTML quota page would otherwise reach rio-cogeo as an
  opaque GDAL failure.

## Decision 5 — EPSG:4326, raw pixel values, footprint from the file

**Projection: EPSG:4326.** Native UTM (32637 here) preserves square pixels and
is the better analysis grid in principle. But 4326 means the raster,
`SensorLog.location`, `SatelliteQuery.geometry`, MapLibre, and any future
deck.gl layer share one CRS — no reprojection anywhere in the stack, including
F10.3 and F10.4. At 3°N the anisotropy over a 1.5 km box is negligible. **The
cost, recorded so it is not rediscovered:** zonal *area* statistics over
geographic pixels need care, and a future analysis over a large region may want
a UTM export path.

**Values are raw.** Sentinel-2 SR is scaled ×10000; Landsat C2 L2 carries its
own scale and offset. Retrieval is not the place to bury a correction, and a
scale factor applied silently at ingest is indistinguishable from one applied
twice. The COG records `RANGER_VALUES=raw` in its own GeoTIFF metadata, so the
warning travels with the file rather than living in a docstring. Note that NDVI
from raw DN is *correct*, not approximate — the scale factor cancels in a
normalised ratio. Thermal does need the documented scale and offset applied.

**Band names are stamped from the catalog.** GEE returns selected bands in the
order requested but does not name them, so a raw download arrives as
`band_1..band_n`. Left that way, `SatelliteDataset.bands` ordering becomes an
undocumented contract that F10.4 would index into blind. Names are written only
when the count matches exactly — a mislabelled band is worse than an unlabelled
one, because it is wrong in a way that reads as authoritative.

**The footprint is read off the raster, and the intersection is asserted in
PostGIS.** Earth Engine reports the whole scene's extent; what lands on disk is
a clip a thousand times smaller. Storing the API's footprint would claim
coverage over ground nobody downloaded. After each scene is persisted,
`fetch_scenes` runs a `geometry__intersects` query against the stored AOI — the
same index-backed predicate F10.4's correlation join will use — and fails the
query rather than trusting `filterBounds`.

## Decision 6 — What the API exposes, and what it must not

`cog_path` is **never serialized**. It is a filesystem path relative to
`MEDIA_ROOT`, and a path is not a URL. `settings.DEBUG` already serves
`MEDIA_URL` statically with no authentication and no org check, so emitting the
path would make every org-scoped queryset in `satellite_integration/views.py`
bypassable by string concatenation. Clients get `has_cog`; F10.3 adds a render
endpoint that re-checks tenancy per request.

`dataset.scale` (`SITE` vs `REGIONAL`) rides on **every** image payload and
every coverage feature. It is what separates "Sentinel-2 resolves this 300 m
site" from "one SMAP pixel covers the whole county", and the provenance
discipline governing `SensorLog.source` is worth nothing if it stops at the API
boundary. A frontend should have to ignore a field to get this wrong.

A malformed `bbox` filter returns **nothing**, not everything — deliberately
unlike the date filters, which ignore unparseable input. A dropped date filter
shows extra rows and you notice. A dropped *spatial* filter renders imagery from
somewhere the user never asked about, on a map, looking authoritative.

Another tenant's object **404s rather than 403s**; a 403 confirms the id exists.

---

## Consequences

**Good.** Scenes are ours: on our disk, in our projection, with provenance in
the file itself. Nothing in the display path can expire. The spatial predicates
F10.4 needs are proven working against real data, not assumed. Two datasets are
verified end to end (`s2`, `l9`) with a mechanism — `is_verified` — that means
"a real scene was retrieved", not merely "the collection ID resolves".

**Costs and open items.**

- **GEE noncommercial vs the F10.5 business model.** Unresolved; see Decision 1.
- **KNRA data authorization.** The report PDF is deliberately not committed.
  Institutional co-branding for the pitch beats self-asserted use.
- **Lab results have no schema home.** 16 soil and 4 water rows (Bq/kg, ppm,
  mg/L) do not fit `RadiationLog` or `AirQualityLog`. Deferred to F10.5.
- **`Mission.robot` is non-null**, so a satellite-only AOI has nowhere to live.
  This matters: the strongest satellite argument in the pitch is Chumvi, *where
  the field team could not physically go*. Representing it today would require
  inventing a phantom robot — the same category of dishonesty the provenance
  tiers exist to prevent.
- **Two queries can claim the same COG.** The unique constraint is
  `(query, gee_asset_id)`, so re-running with `--overwrite` rewrites a file an
  earlier row still describes, silently invalidating that row's `bands` and
  `size_bytes`. Acceptable with one operator; not acceptable with many.
- **Nothing verifies the database against the catalog spec.** `check_gee`
  validates the catalog against the external world; the reverse direction has no
  check, which is how `cloud_property` sat blank for two checkpoints (see
  troubleshooting 019).
- **The Landsat change-detection story is demoted.** Landsat 5 has no coverage
  of Laga Balal between 1985-04-15 and 1986-01-12, and the wells were drilled
  22 December 1985 — inside the gap. The bracketing pair does not resolve the
  well pad at 30 m. The archive is a landscape baseline, not a "watch the pad
  appear" slide.

## Related

- [`ADR-0006`](0006-sensorlog-tenancy-through-robot.md) — the tenancy-through-parent precedent
- [`ADR-0007`](0007-data-explorer-authenticated-only.md) — still open; the satellite API is authenticated-only for the same reason
- [`ADR-0011`](0011-geospatial-db-postgis-now-timescaledb-later.md) — geometry as sole source of truth
- [`troubleshooting/018`](../troubleshooting/018-gee-service-account-missing-iam-roles.md)
- [`troubleshooting/019`](../troubleshooting/019-stale-catalog-blank-cloud-property.md)
