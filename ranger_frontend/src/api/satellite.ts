// ─── RANGER V3 START: satellite api ───
/**
 * Satellite EO API client (F10.3 CP2).
 *
 * Same pattern as api/dataLogs.ts: thin wrappers over the shared `api` axios
 * instance, which attaches the JWT and handles silent refresh.
 *
 * THE RENDER ENDPOINT IS DIFFERENT, and it is worth understanding why.
 *
 * MapLibre's ImageSource takes a URL and fetches it ITSELF, with its own
 * request, which never passes through the axios interceptor. So handing
 * MapLibre `/api/satellite/images/12/render/?layer=ndvi` produces an
 * unauthenticated request and a 401 — the map just shows nothing, with no
 * error surfaced anywhere.
 *
 * Two ways out:
 *
 *   (a) MapLibre's `transformRequest`, injecting the Authorization header
 *       for same-origin /api/ URLs. Clean, but the token it captures goes
 *       stale on rotation, and the silent-refresh flow rotates it. The
 *       failure is a map that stops loading imagery mid-session.
 *
 *   (b) Fetch the PNG through axios as a Blob, hand MapLibre an object URL.
 *       Immune to rotation, because every fetch goes through the interceptor
 *       that already knows how to refresh. Costs an explicit revoke.
 *
 * We take (b). The images are around 100 KB; correctness under token
 * rotation is worth more than saving a copy. `fetchLayerBlobUrl` returns the
 * object URL AND its revoke function so the caller cannot forget — see the
 * lifecycle note on RenderedLayer.
 */
import { api } from "./client"
import type {
  CoverageCollection,
  Paginated,
  SatelliteDataset,
  SatelliteImage,
  SatelliteLayer,
  SatelliteQuery,
  SatelliteQueryDetail,
  RampStats,
} from "../types/satellite.types"

/**
 * Default page size for the two PAGINATED endpoints.
 *
 * DRF caps `limit` at 1000. We ask for it: the satellite surface is small
 * (two scenes today, tens after CP5) and a screen that summarises the whole
 * catalog should not be summarising page one of it.
 *
 * `count` still comes back from the server, so `truncated` below is real
 * rather than assumed — if the set ever outgrows 1000, the UI says so
 * instead of quietly under-reporting.
 */
const PAGE_LIMIT = 1000

/** A fetched page, plus what it does and does not cover. */
export interface Page<T> {
  items: T[]
  /** Total across all pages — the only honest figure for a KPI. */
  count: number
  /** items.length < count: this page is not the whole set. */
  truncated: boolean
}

function toPage<T>(payload: Paginated<T>): Page<T> {
  const items = payload.results ?? []
  const count = payload.count ?? items.length
  return { items, count, truncated: items.length < count }
}

// ─── catalog ────────────────────────────────────────────────────────

export interface DatasetFilters {
  verified?: boolean
  scale?: "SITE" | "REGIONAL"
  include_inactive?: boolean
}

/** UNPAGINATED — ten rows; the backend sets pagination_class = None. */
export async function getDatasets(
  filters: DatasetFilters = {}
): Promise<SatelliteDataset[]> {
  const params: Record<string, string> = {}
  if (filters.verified !== undefined) params.verified = String(filters.verified)
  if (filters.scale) params.scale = filters.scale
  if (filters.include_inactive) params.include_inactive = "true"

  const { data } = await api.get<SatelliteDataset[]>("/satellite/datasets/", {
    params,
  })
  return data
}

export async function getDataset(id: number): Promise<SatelliteDataset> {
  const { data } = await api.get<SatelliteDataset>(
    `/satellite/datasets/${id}/`
  )
  return data
}

// ─── retrievals ─────────────────────────────────────────────────────

export interface QueryFilters {
  dataset?: number
  status?: string
}

/** PAGINATED endpoint — returns a Page, not a bare array. */
export async function getQueries(
  filters: QueryFilters = {}
): Promise<Page<SatelliteQuery>> {
  const params: Record<string, string> = { limit: String(PAGE_LIMIT) }
  if (filters.dataset) params.dataset = String(filters.dataset)
  if (filters.status) params.status = filters.status

  const { data } = await api.get<Paginated<SatelliteQuery>>(
    "/satellite/queries/",
    { params }
  )
  return toPage(data)
}

/** Detail includes nested images — one call, not two. */
export async function getQuery(id: number): Promise<SatelliteQueryDetail> {
  const { data } = await api.get<SatelliteQueryDetail>(
    `/satellite/queries/${id}/`
  )
  return data
}

// ─── scenes ─────────────────────────────────────────────────────────

export interface ImageFilters {
  dataset?: number
  query?: number
  date_start?: string
  date_end?: string
  /** "west,south,east,north" */
  bbox?: string
}

/** PAGINATED endpoint — returns a Page, not a bare array. */
export async function getImages(
  filters: ImageFilters = {}
): Promise<Page<SatelliteImage>> {
  const params: Record<string, string> = { limit: String(PAGE_LIMIT) }
  if (filters.dataset) params.dataset = String(filters.dataset)
  if (filters.query) params.query = String(filters.query)
  if (filters.date_start) params.date_start = filters.date_start
  if (filters.date_end) params.date_end = filters.date_end
  if (filters.bbox) params.bbox = filters.bbox

  const { data } = await api.get<Paginated<SatelliteImage>>(
    "/satellite/images/",
    { params }
  )
  return toPage(data)
}

export async function getImage(id: number): Promise<SatelliteImage> {
  const { data } = await api.get<SatelliteImage>(`/satellite/images/${id}/`)
  return data
}

export async function getCoverage(): Promise<CoverageCollection> {
  const { data } = await api.get<CoverageCollection>("/satellite/coverage/")
  return data
}

// ─── rendered layers ────────────────────────────────────────────────

export interface RenderedLayer {
  /** Object URL to hand MapLibre's ImageSource. */
  url: string
  /** Identity for cache-busting an ImageSource update. */
  id: string
  /** The ramp's meaning, for the legend. Null if the header was missing —
   *  which in a split deployment means Access-Control-Expose-Headers was not
   *  set, so the UI must degrade to "no legend" rather than to a legend of
   *  wrong numbers. */
  stats: RampStats | null
  /**
   * MUST be called when the layer changes or the component unmounts.
   * Object URLs are held by the document until revoked; a map that switches
   * layers a few dozen times over a session leaks every PNG it ever drew.
   */
  revoke: () => void
}

/**
 * Fetch one rendered layer as an object URL.
 *
 * Errors are deliberately NOT swallowed. The endpoint distinguishes 404
 * (unregistered dataset/layer pair — the backend refuses to fall back to
 * another product's recipe) from 409 (row exists, pixels do not: no COG, or
 * the scene lacks a band this layer needs). Both are things the UI should
 * say out loud rather than render as an empty map.
 */
export async function fetchLayerBlobUrl(
  imageId: number,
  layer: SatelliteLayer
): Promise<RenderedLayer> {
  const response = await api.get<Blob>(
    `/satellite/images/${imageId}/render/`,
    {
      params: { layer },
      responseType: "blob",
      // Force revalidation on OUR request rather than trusting whatever the
      // browser stored earlier.
      //
      // This endpoint once answered with `max-age=3600`. Entries cached under
      // that rule stay fresh for an hour, so the browser serves them without
      // contacting the server at all — and a JS-initiated XHR is NOT covered
      // by Ctrl+Shift+R, which only forces revalidation for the document and
      // the subresources the reload itself fetches. The result was a render
      // pipeline that could be rewritten, redeployed and have its cache files
      // deleted on disk while the screen kept showing the old pixels, with no
      // request reaching Django to explain it.
      //
      // The server now sends `no-cache` + ETag, so this is belt-and-braces —
      // but it is the belt that makes the client independent of whatever a
      // given browser happens to be holding.
      headers: { "Cache-Control": "no-cache" },
    }
  )
  const url = URL.createObjectURL(response.data)

  // The body is a PNG, so the ramp's range rides in a header. A parse
  // failure yields null and no legend — never a partial one, because a
  // legend showing the wrong range is worse than none.
  let stats: RampStats | null = null
  const raw = response.headers?.["x-ranger-stats"]
  if (typeof raw === "string") {
    try {
      stats = JSON.parse(raw) as RampStats
    } catch {
      stats = null
    }
  }

  return {
    url,
    id: `${imageId}:${layer}`,
    stats,
    revoke: () => URL.revokeObjectURL(url),
  }
}

/**
 * The raw endpoint path, for logging and error messages ONLY.
 *
 * Deliberately not called `renderUrl` and deliberately not handed to
 * MapLibre: fetching this directly bypasses the auth interceptor and 401s.
 * Use fetchLayerBlobUrl.
 */
export function renderEndpointPath(
  imageId: number,
  layer: SatelliteLayer
): string {
  return `/api/satellite/images/${imageId}/render/?layer=${layer}`
}
// ─── RANGER V3 END: satellite api ───