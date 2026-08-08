# ADR-0013: Raster delivery via rendered PNG, per-dataset layer semantics, and provenance in the UI

- **Status:** Accepted
- **Date:** 2026-08-07
- **Feature:** F10.3 (Satellite view frontend)
- **Supersedes:** none
- **Related:** ADR-0011 (geometry is the source of truth), ADR-0012 (satellite API surface; §6 on `cog_path`)

## Context

F10.2 left two real Sentinel-2 and Landsat-9 scenes on disk as COGs, band-labelled, in EPSG:4326, both over Forole. F10.3 has to put those pixels on a map in the browser, add layer toggles, and do it eleven days before the Africa EO Challenge pitch — whose entire thesis is traceability.

Three questions had to be settled before any of that: how pixels reach the browser, what a "layer" is, and whether the console tells the truth about where its numbers come from.

## Decision 1 — Render PNGs from our own COGs

`GET /api/satellite/images/<id>/render/?layer=<key>` reads the COG we hold, applies the layer's recipe, and returns an RGBA PNG cached beside the COG. The frontend pins it to its bbox corners with MapLibre's `ImageSource`.

**Rejected: GEE tile URLs.** They expire after a few days. A demo built on them works today, works tomorrow, and fails on the day that matters — silently, with no error anywhere. `SatelliteImage.tiles_are_stale()` exists because we already knew this. A cache is not a delivery mechanism.

**Rejected: a real XYZ tile server (rio-tiler / titiler).** Correct at scale, badly overbuilt here. The two scenes are 112×119 px and 38×41 px — a new service, a new dependency and a new failure mode to serve about fourteen thousand pixels, two weeks out.

Corner-pinning is exact rather than approximate because F10.2 CP5 already reprojects to EPSG:4326 on ingest. There is no reprojection step in the render path, which is most of why the cheap option is also the correct one at this scale.

**Consequences.** Renders are cached to `<cog>.<layer>.png` and invalidated by mtime against the COG, so `fetch_scenes --overwrite` cannot leave stale pixels beside fresh metadata. Writes are atomic (temp + `os.replace`), matching `cog.py`, because a half-written cache file is indistinguishable from a valid one on the next request. This does not scale to large scenes or deep zoom; when it stops being adequate, titiler is the answer and this ADR should be superseded rather than stretched.

## Decision 2 — A layer is a (dataset, layer) pair, and every layer declares its calibration

`render.LAYERS` is keyed on the pair. There is no dataset-agnostic `ndvi`.

This is not tidiness. Sentinel-2 SR Harmonized calibrates purely multiplicatively:

```
rho = 1e-4 * DN
NDVI = (1e-4*B8 − 1e-4*B4) / (1e-4*B8 + 1e-4*B4) = (B8−B4)/(B8+B4)
```

The factor cancels exactly, so NDVI is correct from raw DNs. Landsat 9 Collection 2 Level 2 carries an **additive offset**:

```
rho = 2.75e-5 * DN − 0.2
NDVI = (2.75e-5*(B5−B4)) / (2.75e-5*(B5+B4) − 0.4)
                                            ^^^^^ survives
```

An offset does not cancel. NDVI computed from raw Landsat DNs is not NDVI — it is a number in the right range that renders as a completely convincing image over a 38×41 px scene, and nothing downstream can distinguish it from the real thing.

So: `Calibration` carries `scale` and `offset` together and exposes `cancels_in_a_ratio`; every `Layer` declares `apply_calibration`; the renderer applies it before any band math; and an unregistered pair returns **404, never a fallback**. A fallback is precisely how an S2 recipe gets computed over an L9 scene.

A registry-wide test asserts that any layer setting `apply_calibration=False` either is a display stretch or has a calibration that provably cancels — so the next layer added cannot reintroduce this by omission.

**Consequences.** Adding a dataset means adding its layers explicitly; there is no inheritance and no default. That is the point. Bands are resolved by name from the labels F10.2 stamps into the file, never by position, because a band-order change under positional indexing produces wrong colours that read as a rendering preference.

## Decision 3 — Layer captions state what the number is not

Every layer carries a caption rendered under the panel:

- True colour → `display stretch only · NOT calibrated reflectance`
- NDVI (S2) → `normalised ratio, scale-invariant`
- NDVI (L9) → `Collection 2 scale AND offset applied before the ratio`
- Surface temp → `land SURFACE temperature, not air temperature`
- Bare soil → `surface brightness and dryness proxy · NOT a salinity measurement`

The last one matters most for the pitch. No optical index measures salinity. BSI separates bright, dry, unvegetated surfaces from everything else, and over the Chalbi that is the salt crust — a defensible claim. "Sentinel-2 salinity index" is not.

## Decision 4 — Provenance is a first-class UI requirement, and summaries are computed on the uncapped set

F10.2 emitted `source` and `provenance_note` on the serializer, the CSV export and the map payload. The frontend dropped all of it: fourteen columns, none of them provenance. The console showed 12,081 modelled points with real instrument names, real mission names and real dose values, and nothing on screen said they were modelled. Every viewer reads that as measurement, because everything on screen says measurement.

Provenance now reaches the screen as a coloured chip in the third column (ahead of any instrument name or value), as marker colour on the map, and as a banner over the filtered set.

The subtler half: **a summary must describe the set it claims to describe.** `MapDataAPIView` caps features at `MAX_CHART_POINTS`, so a banner derived from the features array announced "ALL 5,000 POINTS" directly above a record count of 12,081, and quoted one arbitrary feature's citation as though it covered all seven sites. The endpoint now returns a `provenance` block computed on the **uncapped** filtered queryset — `total`, `by_source`, distinct `notes`, `returned`, `truncated` — and the UI declines to cite when several citations apply, pointing at the per-row chips instead, which are correct.

A wrong citation is worse than no citation: it reads as authoritative right up until someone opens Table 3.1.

## Alternatives considered for Decision 1

| Option | Verdict |
|---|---|
| GEE tile URLs | Rejected — expire silently; a cache, not a delivery mechanism |
| titiler / rio-tiler XYZ | Rejected for now — correct at scale, overbuilt for 300 m sites two weeks out |
| Pre-baked PNGs at ingest | Rejected — couples layer choice to download time; adding a layer would mean re-fetching every scene |
| Render on request, cache on disk | **Chosen** |

## Open items carried forward

- Two queries can claim the same COG; the second silently invalidates the first row's metadata, and would also invalidate its render cache.
- The render path holds no lock, so two concurrent requests for an uncached layer both render. Harmless (atomic replace, identical output), wasteful.
- `SOURCE_META` (TypeScript) mirrors `SensorLog.Source` (Python) with no test binding them.
- No drift check between the database and the `DATASETS` spec.
