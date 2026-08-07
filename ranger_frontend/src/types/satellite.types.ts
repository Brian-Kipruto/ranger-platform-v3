// ─── RANGER V3 START: satellite types ───
/**
 * Satellite EO types (F10.3 CP2).
 *
 * Mirrors satellite_integration/serializers.py EXACTLY. Two rules carried
 * across from that module's docstring, because a contract enforced on only
 * one side is not a contract:
 *
 * 1. There is no `cog_path` here, and there must never be. It is a
 *    filesystem path, not a URL; emitting it would let a client build
 *    /media/satellite/<org>/... directly and bypass org scoping entirely.
 *    Pixels come from the render endpoint, which re-checks tenancy per
 *    request (ADR-0012 §6, ADR-0013).
 *
 * 2. `scale` is REQUIRED on every image, not optional. SITE vs REGIONAL is
 *    what separates "Sentinel-2 resolves this 300 m site" from "one SMAP
 *    pixel covers the whole county". A type that lets you forget it is a
 *    type that invites rendering a regional covariate as a per-site
 *    measurement.
 */

/** [west, south, east, north] in EPSG:4326.
 *
 *  Not GeoJSON, deliberately: this is what MapLibre's ImageSource wants for
 *  a raster overlay, and every footprint we hold is an axis-aligned clip.
 *  /api/satellite/coverage/ serves real GeoJSON for the vector layer. */
export type BBox = [number, number, number, number]

/** SatelliteDataset.Scale. */
export type DatasetScale = "SITE" | "REGIONAL"

/** SatelliteQuery.Status. */
export type QueryStatus = "pending" | "running" | "complete" | "failed"

/**
 * DRF's PageNumberPagination envelope.
 *
 * /satellite/queries/ and /satellite/images/ ARE paginated (25 per page,
 * `limit` tunable to 1000). /satellite/datasets/ and /satellite/coverage/
 * are NOT — the catalog is ten rows and coverage is a single
 * FeatureCollection.
 *
 * `count` is the total across all pages, and it is the only honest source
 * for any figure that claims to describe the whole set. Deriving a KPI from
 * `results.length` would count one page and label it the total — the same
 * mistake the Data Explorer banner made against the capped map payload.
 */
export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// ─── catalog ────────────────────────────────────────────────────────

export interface SatelliteDataset {
  id: number
  code: string
  name: string
  provider: string
  provider_label: string
  gee_collection_id: string
  resolution_m: number
  temporal_resolution_days: number
  scale: DatasetScale
  scale_label: string
  bands: string[]
  archive_start: string | null
  archive_end: string | null
  /** False for radar and other products with no cloud property — do not
   *  offer a cloud slider for these. */
  has_cloud_filter: boolean
  description: string
  is_active: boolean
  /** True only once a real scene has been pulled and verified. Stronger than
   *  "the collection ID resolves", which is all check_gee proves. This is
   *  what drives the DATA PROVIDERS status in CP3 — never a hardcoded
   *  string. */
  is_verified: boolean
}

// ─── scenes ─────────────────────────────────────────────────────────

export interface SatelliteImage {
  id: number
  query: number
  dataset: number
  dataset_code: string
  dataset_name: string
  provider: string
  resolution_m: number
  /** See rule 2 above. Required. */
  scale: DatasetScale
  gee_asset_id: string
  acquisition_date: string
  cloud_cover_pct: number | null
  /** Null when the footprint geometry is absent. The render overlay cannot
   *  be positioned without it, so callers must handle null rather than
   *  assume. */
  bbox: BBox | null
  bands: string[]
  has_cog: boolean
  size_bytes: number | null
  downloaded_at: string | null
  /** A cached GEE tile URL is never authoritative. Lets a client tell "no
   *  imagery" apart from "the cached link expired". */
  tiles_stale: boolean
  properties: Record<string, unknown>
  created_at: string
}

// ─── retrievals ─────────────────────────────────────────────────────

export interface SatelliteQuery {
  id: number
  label: string
  dataset: number
  dataset_code: string
  dataset_name: string
  /** Null for an ad-hoc bbox with no mission behind it — the shape a
   *  satellite-only AOI needs, since Mission.robot is non-null. */
  mission: number | null
  mission_name: string | null
  aoi_bbox: BBox | null
  start_date: string
  end_date: string | null
  max_cloud_pct: number | null
  status: QueryStatus
  status_label: string
  /** What the run reported. */
  scene_count: number
  /** What actually survived. Diverges from scene_count when an image is
   *  deleted — the divergence is deliberately visible. */
  image_count: number
  error_message: string
  created_at: string
  completed_at: string | null
}

export interface SatelliteQueryDetail extends SatelliteQuery {
  images: SatelliteImage[]
}

// ─── coverage ───────────────────────────────────────────────────────

export interface CoverageFeature {
  type: "Feature"
  geometry: { type: "Polygon"; coordinates: number[][][] }
  properties: {
    id: number
    dataset_code: string
    acquisition_date: string
    scale: DatasetScale
    has_cog: boolean
  }
}

export interface CoverageCollection {
  type: "FeatureCollection"
  features: CoverageFeature[]
}

// ─── layers ─────────────────────────────────────────────────────────

export type SatelliteLayer = "truecolor" | "ndvi" | "thermal" | "bsi"

/**
 * What a rendered ramp actually means (F10.3 CP4.1).
 *
 * Index and scalar layers are percentile-stretched to the SCENE, because an
 * absolute -1..1 ramp rendered NDVI over arid Marsabit as a flat wash. That
 * makes colour relative to one image rather than an absolute physical value,
 * so the range MUST be shown. This block is what the legend renders; a
 * stretched ramp without it implies precision it does not have.
 */
export interface RampStats {
  layer: SatelliteLayer
  kind: "rgb" | "index" | "scalar"
  units: string
  palette: string
  stretch: "percentile" | "absolute"
  stretch_pct: [number, number]
  /** Ends of the colour ramp, in physical units. */
  display_min: number
  display_max: number
  /** Full observed range, before the percentile clip. */
  data_min: number | null
  data_max: number | null
  valid_px: number
}

/** Ramp stops, mirroring render._ramp so the legend gradient matches the
 *  pixels. If one side changes, so must the other. */
export const PALETTE_STOPS: Record<string, string[]> = {
  rdylgn: ["rgb(166,54,42)", "rgb(246,232,160)", "rgb(26,122,52)"],
  thermal: ["rgb(8,24,92)", "rgb(222,96,40)", "rgb(255,244,190)"],
  bare: ["rgb(26,62,34)", "rgb(196,172,120)", "rgb(250,248,240)"],
}

export function paletteGradient(palette: string): string {
  const stops = PALETTE_STOPS[palette] ?? PALETTE_STOPS.rdylgn
  return `linear-gradient(to right, ${stops.join(", ")})`
}

/**
 * Which layers each dataset can actually render.
 *
 * Mirrors render.LAYERS, which is keyed on the (dataset, layer) PAIR — there
 * is no dataset-agnostic "ndvi" on either side. The backend 404s an
 * unregistered pair rather than falling back; this table exists so the UI
 * never offers a toggle that would 404, because a greyed-out impossible
 * option is better than an error the user has to interpret.
 *
 * A dataset absent from this table renders no layers. That is correct: the
 * default is "we have no recipe for this product", not "try the S2 one".
 */
export const LAYERS_BY_DATASET: Record<string, SatelliteLayer[]> = {
  s2: ["truecolor", "ndvi", "bsi"],
  l9: ["truecolor", "ndvi", "thermal"],
}

/** Display metadata per layer. `caption` states what the number IS and what
 *  it is NOT — the same discipline as the provenance chip, one level up.
 *  Captions that vary by dataset are resolved by LAYER_CAPTION_OVERRIDES. */
export const LAYER_META: Record<
  SatelliteLayer,
  { label: string; short: string; caption: string }
> = {
  truecolor: {
    label: "True colour",
    short: "RGB",
    caption: "2–98% display stretch · NOT calibrated reflectance",
  },
  ndvi: {
    label: "NDVI",
    short: "NDVI",
    caption: "(NIR−Red)/(NIR+Red) · normalised difference vegetation index",
  },
  thermal: {
    label: "Surface temp",
    short: "TEMP",
    caption:
      "Landsat ST_B10 · scale + offset applied · land SURFACE temperature, " +
      "not air temperature",
  },
  bsi: {
    label: "Bare soil",
    short: "BSI",
    caption:
      "((SWIR+Red)−(NIR+Blue))/((SWIR+Red)+(NIR+Blue)) · surface brightness " +
      "and dryness proxy · NOT a salinity measurement",
  },
}

/**
 * Dataset-specific captions, where the honest wording differs by product.
 *
 * NDVI is the case that matters. Over Sentinel-2 the calibration is
 * multiplicative and cancels in the ratio, so the index is correct from raw
 * values. Over Landsat C02 L2 there is an additive offset which does NOT
 * cancel, so the backend applies calibration first. Same index, same name,
 * different provenance — and the caption says which.
 */
export const LAYER_CAPTION_OVERRIDES: Record<string, string> = {
  "s2:ndvi": "(B8−B4)/(B8+B4) · normalised ratio, scale-invariant",
  "l9:ndvi":
    "(SR_B5−SR_B4)/(SR_B5+SR_B4) · Collection 2 scale AND offset applied " +
    "before the ratio — the offset does not cancel",
  "s2:truecolor": "Sentinel-2 B4/B3/B2 · display stretch only",
  "l9:truecolor": "Landsat 9 SR_B4/B3/B2 · display stretch only",
  "s2:bsi":
    "((B11+B4)−(B8+B2))/((B11+B4)+(B8+B2)) · B11 resampled 20→10 m at " +
    "download · surface brightness and dryness proxy, NOT salinity",
}

export function layerCaption(
  datasetCode: string,
  layer: SatelliteLayer
): string {
  return (
    LAYER_CAPTION_OVERRIDES[`${datasetCode}:${layer}`] ??
    LAYER_META[layer].caption
  )
}

export function layersFor(datasetCode: string): SatelliteLayer[] {
  return LAYERS_BY_DATASET[datasetCode] ?? []
}
// ─── RANGER V3 END: satellite types ───