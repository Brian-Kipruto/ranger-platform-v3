# F10.3 — Satellite View Frontend

*Date: 2026-08-07*
*Epic: F10 (Satellite EO) — sub-feature 3 of 6*
*Branch: `feat/postgis-foundation`*

---

## What this feature does

F10.2 put satellite data on disk. F10.3 puts it on screen — and, in the same
pass, fixes the fact that the console had been showing 12,081 modelled points
as though they were measurements.

Both halves are the same requirement. A platform whose pitch is traceability
cannot render imagery beautifully while its ground data silently over-claims.
CP0 was therefore not a preamble to the feature; it was the feature's first
obligation.

**Shipped:**

- Provenance visible everywhere it exists: a `SOURCE` column third in the Data
  Explorer, marker colour on every map, a banner over the filtered set, and
  citations on hover
- An uncapped provenance summary on `/api/map-data/`, so a banner describes the
  set it claims to describe rather than the sample the map drew
- `GET /api/satellite/images/<id>/render/?layer=<key>` — PNG rendered from our
  own COGs, cached beside them, tenancy re-checked per request
- A per-`(dataset, layer)` registry with declared calibration — the thing that
  stops NDVI being computed wrongly over Landsat
- Percentile stretching to each scene, with a legend that reports the range
- The Satellite Integration screen: KPI tiles, DATA PROVIDERS, RETRIEVAL LOG
- An EO imagery panel with layer toggles, opacity, and the **ground sensor
  track drawn over the imagery**
- `seed_marsabit` creates a tenant login and refuses to double-seed
- 288 tests across the repo, up from 225

See [`ADR-0013`](../decisions/0013-raster-delivery-and-layer-semantics.md) for
why each choice was made.

---

## CP0 — the correctness debt

The backend had emitted `source` and `provenance_note` since F10.2 CP2, on the
serializer, the CSV export and the map payload, with tests asserting they
survive every path out. The frontend dropped all of it: `DataExplorerPage`
defined fourteen columns and `source` was not among them, and
`dataLog.types.ts` had no such field.

So the console showed 12,081 MODELLED points carrying real instrument names
(`KNRA-PGIS-2-1`), real mission names (`Dukana (Laga Balal) Well 2`) and real
dose values (`76.15 CPM`), with nothing on screen saying they were modelled.
Every viewer reads that as measurement, because everything on screen says
measurement.

Four things shipped in CP0, three of them found by reading the tree rather than
from the handoff:

**The provenance gap itself.** `DataSource` union and `SOURCE_META` mirroring
`SensorLog.Source`; a `SourceChip`; the column in third position, ahead of any
instrument name or value; markers coloured by a `match` expression with reduced
opacity on generated tiers so the distinction survives a projector and
greyscale.

**`FieldMap.installLayers` was captured at mount.** The init effect has `[]`
deps, so both the `load` and `styledata` handlers closed over the first
render's installer. Harmless while only `accent` varied; not harmless once
layer state does — and `styledata` fires on every basemap switch. Routed
through a ref, plus a paint-refresh tail, because the existing add-guards
prevent re-adding but never update a layer whose paint props changed.

**The Data Explorer fetched the full track three times on mount.** Two
independent `/chart-data/` pulls to fill two dropdowns, then `/map-data/`.
Capped at 5,000 each — free at 435 simulated Nairobi points, not free at
12,081.

**The `knra` org had no user.** The account had been made by hand in admin and
did not survive `--create-db`.

### CP0.5 — a summary must describe the set it claims to describe

The first banner counted `trackFc.features`. That array is capped at
`MAX_CHART_POINTS`, so the console announced **"ALL 5,000 POINTS IN THIS SET
ARE MODELLED"** directly above a record count of **12,081** — and quoted one
arbitrary feature's citation as though it covered all seven sites. Filtered to
Forole, it cited Boji.

`MapDataAPIView` now returns a `provenance` block computed on the *uncapped*
filtered queryset: `total`, `by_source`, distinct `notes`, `returned`,
`truncated`. With several distinct citations the banner names the shared
document and points at the per-row chips rather than picking one.

A wrong citation is worse than no citation. It reads as authoritative right up
until someone opens Table 3.1.

---

## CP1 — the render endpoint

`GET /api/satellite/images/<pk>/render/?layer=<key>` reads the COG we hold,
applies the layer recipe, and returns an RGBA PNG cached beside the COG.
Tenancy is re-checked per request through `_org_images`: `cog_path` stays
unserialized (ADR-0012 §6) so ids cannot be turned into pixels across tenants,
which holds only if the endpoint that *does* turn ids into pixels scopes its
own lookup.

### A layer is a `(dataset, layer)` pair

This is the correctness core of the feature, and it corrects the F10.2 handoff.

Sentinel-2 SR Harmonized calibrates purely multiplicatively, `ρ = 1e-4·DN`, so
in a normalised ratio the factor cancels exactly and NDVI is correct from raw
values. Landsat 9 Collection 2 Level 2 carries an **additive offset**,
`ρ = 2.75e-5·DN − 0.2`:

```
NDVI = (2.75e-5·(B5−B4)) / (2.75e-5·(B5+B4) − 0.4)
                                            ^^^^^ survives
```

An offset does not cancel. NDVI from raw Landsat DNs is not NDVI — it is a
number in the right range that renders as a completely convincing image over a
38×41 px scene, and nothing downstream can tell.

So `Calibration` carries scale and offset together and exposes
`cancels_in_a_ratio`; every `Layer` declares `apply_calibration`; and an
unregistered pair returns **404, never a fallback**. A fallback is precisely
how an S2 recipe gets computed over an L9 scene.

A registry-wide test asserts that any layer skipping calibration is either a
display stretch or has a calibration that provably cancels, so the bug cannot
return by omission when someone adds a layer.

| Dataset | Layer | Bands | Calibration |
|---|---|---|---|
| s2 | truecolor | B4, B3, B2 | display stretch only |
| s2 | ndvi | B8, B4 | none — scale cancels |
| s2 | bsi | B11, B4, B8, B2 | none — scale cancels |
| l9 | truecolor | SR_B4/B3/B2 | display stretch only |
| l9 | ndvi | SR_B5, SR_B4 | **applied — offset does not cancel** |
| l9 | thermal | ST_B10 | **applied — → Kelvin → °C** |

Bands resolve **by name** from the labels F10.2 stamps into the file, never by
position. A band-order change under positional indexing produces wrong colours
that read as a rendering preference rather than a bug.

---

## CP2/CP3 — the screen

Types mirroring the serializers, an API client, the `/satellite` nav entry and
route, and a screen driven entirely by the real catalog.

**MapLibre's `ImageSource` fetches its own URL, outside axios**, so the auth
interceptor never runs and `render/` would 401 with the map silently blank.
`transformRequest` would work until the token rotates — and silent refresh
rotates it, so the failure mode is a map that stops loading imagery
mid-session. `fetchLayerBlobUrl` pulls the PNG through axios as a Blob and
returns `{url, id, stats, revoke}`; the revoke is returned rather than implicit
because object URLs live until revoked.

**Three corrections against the mockup:**

- It lists Planet SkySat and Maxar WorldView-3 as CONNECTED. We have neither.
  Status derives from the catalog, never a hardcoded string.
- FUSION EVENTS is **RETRIEVAL LOG**. There is no correlation engine yet and
  naming one would be a claim.
- The nav subtitle is `// EO imagery · ground truth`, not change detection,
  which the Landsat coverage gap cannot support.

**`is_verified` means a scene landed**, not "the collection ID resolves" —
`check_gee` proves the latter and deliberately does not set the flag. So the
eight unpulled products read **CATALOGED**, not UNVERIFIED: they are products
we have not retrieved from, not products we doubt.

---

## CP4 — the EO imagery panel

The raster is an `ImageSource` pinned to its bbox corners. Our COGs are already
EPSG:4326 (F10.2 CP5), so corner-pinning is exact with no reprojection — most
of why the cheap delivery route is also the correct one at this scale.

Three details that matter more than they look:

- **`moveLayer(RASTER_LAYER, TRACK_LAYER)`** on every install. Sensor points
  always draw over imagery. Ground truth on top of satellite, literally.
- **`raster-resampling: "nearest"`.** The default smooths a 38×41 px scene into
  something that looks higher-resolution than it is. On a screen arguing about
  resolution, that is the wrong kind of pretty.
- **`fitToRaster`**, keyed on the raster id. Without it the map sat at its
  Nairobi default while the Forole scene loaded correctly 1,000 km away —
  which looks exactly like a rendering failure and is not one.

### CP4.1 — stretch to the scene, and say so

Absolute domains rendered every index as a flat wash. NDVI over arid Marsabit
spans about 0.11–0.17 of a −1…1 ramp, so every pixel landed in the same two
adjacent colours — on the layer whose entire pitch value is that NDVI explains
inter-site variance.

Percentile stretching (p2–p98, clamped to physical bounds first so one blown-up
pixel cannot drag the ramp) makes the structure visible. The trade is real:
colour becomes relative to **one scene**, not an absolute physical value. So
the range travels with the pixels — cached in a JSON sidecar beside the PNG,
returned in an `X-Ranger-Stats` header — and the legend reports it, ending with
*"colour is relative to this scene, not comparable across dates."*

True colour uses **one shared stretch across R/G/B**. Per-band stretching
normalises each to its own narrow range, which amplifies sensor noise into
colour casts and destroys the band balance: over arid terrain it turned tan
into saturated blue and orange blocks. The real band medians are B4 2480,
B3 1418, B2 856 — that 3:1 red-to-blue ratio is genuine, and a shared stretch
preserves it.

### CP4.2 — the two halves on one screen

The pitch thesis is that satellite EO explains ground radiological variability
and ground data validates satellite surface products. Until CP4.2 those halves
lived on separate screens.

The EO panel now draws the AOI's sensor track over the imagery: 1,819 gamma
dose-rate points over Forole, on top of the NDVI layer, coloured by provenance,
with the count, tier and Table 3.1 citation stated beneath. No map changes were
needed — CP4's layer ordering was built for this.

When a scene's query has no mission, there is no track, and the panel says
*"GROUND TRUTH — none for this AOI. Satellite coverage here stands alone."*
That is not an empty state; it is the argument a satellite-only site makes.

---

## What is not in this feature

**CP5 — Chumvi is deferred, blocked on coordinates.** The KNRA report describes
it as within the Chalbi Desert with salt-like surface formations, accessed from
Kargi, and records two soil samples — but gives no coordinates and no map
figure, and nothing public pins it inside a desert 110 km long. A bbox labelled
Chumvi that is not Chumvi is exactly the over-claim this feature exists to
prevent. The `bsi` layer it needs is built and registered.

Note also that those two samples were collected in the Chalbi area **after** the
access attempt failed. An AOI built from them marks the approach, not the salt
crust, and must be labelled that way.

**Change detection.** Landsat 5 has no coverage of the December 1985 drilling
window and the pad is not visible at 30 m. Demoted in F10.2 and not resurrected
here — including in the nav subtitle.

**The two-pass swipe.** The mockup's swipe works on a synthetic tile grid; on
MapLibre it needs two `ImageSources` and a clipped canvas, and with one scene
per site it would be a swipe between an image and itself. Deferred to F10.4
where change detection actually belongs.

---

## Verification

```bash
cd $R/ranger_backend && PYTHONPATH= pytest    # 288, gotcha 2
cd $R/ranger_frontend && npx tsc -b && npm run build
```

The screenshot loop caught four defects no test would have: the provenance gap
itself, the banner counting the capped sample, the flat index wash, and the
`12+ distinct citations` from a `.distinct()` chained onto an ordered queryset.
Gotcha 8 earned its place three times in one feature.
