// ─── RANGER V3 START: satellite page ───
/**
 * Satellite Integration (F10.3 CP2).
 *
 * CP2 scope is PLUMBING: the route exists, the API client works end to end,
 * and every number on screen comes from the real catalog. CP3 builds the
 * mockup's layout on top — KPI tiles, DATA PROVIDERS, RETRIEVAL LOG. CP4
 * adds the EO imagery panel.
 *
 * It renders real data rather than a "coming soon" stub deliberately: a
 * placeholder proves the route resolves and nothing else, and the thing most
 * likely to be wrong here is the serializer-to-type contract, which only a
 * real fetch exercises.
 *
 * What this screen must never do, carried forward from the mockup review:
 *   - list Planet SkySat or Maxar WorldView-3 as CONNECTED. We have neither.
 *     Provider status derives from SatelliteDataset.is_verified over the real
 *     10-dataset catalog, never a hardcoded string.
 *   - claim a scene count we do not have. Two scenes are on disk.
 *   - render a REGIONAL product as a per-site measurement. `scale` rides on
 *     every image for exactly this reason.
 */
import { useEffect, useState } from "react"
import { Panel } from "@/components/console/Panel"
import { MonoLabel } from "@/components/console/MonoLabel"
import { MetricTile } from "@/components/console/MetricTile"
import { getDatasets, getImages, getQueries, type Page } from "@/api/satellite"
import { layersFor } from "@/types/satellite.types"
import type {
  SatelliteDataset,
  SatelliteImage,
  SatelliteQuery,
} from "@/types/satellite.types"

const EM_DASH = "—"

/** Empty Page, so the very first render has the right SHAPE — not a bare
 *  array that looks fine until something calls .filter on it. */
const EMPTY_PAGE = { items: [], count: 0, truncated: false }

/**
 * Provider status, derived from the catalog — never asserted.
 *
 * READ THE FLAG'S ACTUAL MEANING BEFORE CHANGING THIS.
 * `SatelliteDataset.is_verified` does NOT mean "the collection ID resolves".
 * check_gee proves that and deliberately does not set the flag; fetch_scenes
 * sets it when a real scene lands on disk; seed_datasets deliberately never
 * clobbers it. So is_verified means: WE HAVE ACTUALLY PULLED FROM THIS.
 *
 * Nothing in the schema records "check_gee passed", so this panel cannot
 * claim it. Hence CATALOGED rather than UNVERIFIED for the rest: they are
 * products we have not retrieved from, not products we doubt. "Unverified"
 * would understate eight collections whose IDs were checked live.
 */
function providerStatus(
  dataset: SatelliteDataset,
  sceneCount: number
): { label: string; color: string; title: string } {
  if (dataset.is_verified && sceneCount > 0) {
    return {
      label: "CONNECTED",
      color: "#4be08a",
      title: "A scene from this product is on disk now.",
    }
  }
  if (dataset.is_verified) {
    // A scene landed at some point but none is listed now — the row was
    // deleted, or a filter is hiding it. Worth distinguishing from never.
    return {
      label: "RETRIEVED",
      color: "#36c5f0",
      title: "A scene was retrieved from this product previously; none is listed now.",
    }
  }
  return {
    label: "CATALOGED",
    color: "#7a828f",
    title: "In the catalog; no scene retrieved from it yet.",
  }
}

function relativeTime(iso: string | null): string {
  if (!iso) return EM_DASH
  const then = new Date(iso).getTime()
  const mins = Math.round((Date.now() - then) / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

export default function SatellitePage() {
  const [datasets, setDatasets] = useState<SatelliteDataset[]>([])
  const [images, setImages] = useState<Page<SatelliteImage>>(EMPTY_PAGE)
  const [queries, setQueries] = useState<Page<SatelliteQuery>>(EMPTY_PAGE)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([getDatasets(), getImages(), getQueries()])
      .then(([d, i, q]) => {
        if (cancelled) return
        setDatasets(d)
        setImages(i)
        setQueries(q)
        setError(null)
      })
      .catch(() => {
        if (!cancelled) setError("Could not load satellite data.")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const imageList = images.items
  const queryList = queries.items

  const scenesOnDisk = imageList.filter((i) => i.has_cog).length
  const verified = datasets.filter((d) => d.is_verified).length
  const lastPass = imageList.length
    ? imageList
        .map((i) => i.acquisition_date)
        .sort()
        .slice(-1)[0]
    : null

  // The tiles count what we FETCHED. That is the whole set unless the server
  // paged us — and if it did, tiles labelled as totals would be describing
  // page one, the same failure the Data Explorer banner had against the
  // capped map payload. Say so rather than round down silently.
  const truncated = images.truncated || queries.truncated

  /**
   * Distinct AOIs with at least one scene — NOT distinct queries.
   *
   * Two products over one site is two queries and one site. Counting queries
   * showed "SITES COVERED 2" while only Forole had imagery, under a label
   * that reads as coverage. Identity is the AOI bbox (mission name as a
   * fallback), because a satellite-only AOI has no mission at all —
   * Mission.robot is non-null, so Chumvi will arrive as an ad-hoc bbox.
   */
  const sitesCovered = new Set(
    queryList
      .filter((q) => q.image_count > 0)
      .map((q) =>
        q.aoi_bbox
          ? q.aoi_bbox.map((v) => v.toFixed(4)).join(",")
          : (q.mission_name ?? `query-${q.id}`)
      )
  ).size

  const sceneCountByDataset = new Map<number, number>()
  for (const image of imageList) {
    if (!image.has_cog) continue
    sceneCountByDataset.set(
      image.dataset,
      (sceneCountByDataset.get(image.dataset) ?? 0) + 1
    )
  }

  return (
    <div className="p-[18px]">
      <div className="mb-3">
        <MonoLabel size="xs" tone="dim" tracking="0.12em">
          {loading
            ? "LOADING SATELLITE CATALOG…"
            : error
              ? error.toUpperCase()
              : `${datasets.length} DATASETS · ${scenesOnDisk} SCENE${
                  scenesOnDisk === 1 ? "" : "S"
                } ON DISK · ${queries.count} RETRIEVAL${
                  queries.count === 1 ? "" : "S"
                }`}
        </MonoLabel>
      </div>

      {truncated ? (
        <div
          className="mb-3 px-3 py-2 rounded-md border font-mono text-[10px] leading-[1.6]"
          style={{
            color: "#f5a623",
            borderColor: "#f5a62355",
            background: "#f5a62312",
          }}
        >
          ⚠ SHOWING {imageList.length} OF {images.count} SCENES AND{" "}
          {queryList.length} OF {queries.count} RETRIEVALS — THE TILES BELOW
          DESCRIBE THE FETCHED SUBSET, NOT THE FULL CATALOG.
        </div>
      ) : null}

      {/* ── KPI tiles. Every figure is a count of something real. ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
        <MetricTile
          label="SCENES ON DISK"
          value={scenesOnDisk}
          sub="COGs retrieved and verified"
        />
        <MetricTile
          label="DATASETS RETRIEVED"
          value={`${verified} / ${datasets.length}`}
          sub="a real scene has landed"
        />
        <MetricTile
          label="SITES COVERED"
          value={sitesCovered}
          sub="distinct AOIs with imagery"
        />
        <MetricTile
          label="LAST PASS"
          value={
            lastPass ? new Date(lastPass).toLocaleDateString() : EM_DASH
          }
          sub="most recent acquisition"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1.65fr_1fr] gap-3">
        {/* ── CP4 puts the EO imagery panel here. ── */}
        <Panel title="EO IMAGERY" right={<MonoLabel size="xs">CP4</MonoLabel>}>
          <div className="p-[14px] font-mono text-[11px] leading-[1.7] text-fg-dim">
            The raster overlay lands in CP4. The render endpoint and its layer
            registry are already live — each scene below lists the layers its
            dataset can actually render, which is what the toggle strip will
            offer.
            <div className="mt-3 space-y-2">
              {imageList.map((image) => (
                <div
                  key={image.id}
                  className="border border-border-strong rounded-md p-2.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-fg-soft">{image.dataset_name}</span>
                    <span className="text-[9px] tracking-[0.08em] px-1.5 py-0.5 rounded border border-border-strong">
                      {image.scale}
                    </span>
                  </div>
                  <div className="mt-1 text-[10px]">
                    {new Date(image.acquisition_date).toLocaleDateString()} ·{" "}
                    {image.resolution_m} m ·{" "}
                    {image.has_cog ? "COG on disk" : "no COG"}
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {layersFor(image.dataset_code).map((layer) => (
                      <span
                        key={layer}
                        className="font-mono text-[9px] tracking-[0.08em] px-1.5 py-0.5 rounded border border-border-strong text-fg-soft"
                      >
                        {layer.toUpperCase()}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
              {!loading && imageList.length === 0 ? (
                <div>No scenes retrieved yet. Run fetch_scenes.</div>
              ) : null}
            </div>
          </div>
        </Panel>

        <div className="flex flex-col gap-3">
          {/* ── DATA PROVIDERS — driven off the real catalog. ── */}
          <Panel
            title="DATA PROVIDERS"
            right={
              <MonoLabel size="xs">{`${verified}/${datasets.length}`}</MonoLabel>
            }
          >
            <div className="p-[14px] flex flex-col gap-2">
              {datasets.map((dataset) => {
                const status = providerStatus(
                  dataset,
                  sceneCountByDataset.get(dataset.id) ?? 0
                )
                return (
                  <div
                    key={dataset.id}
                    className="flex items-start justify-between gap-2 font-mono text-[10px] leading-[1.6]"
                  >
                    <div className="min-w-0">
                      <div className="text-fg-soft truncate">
                        {dataset.name}
                      </div>
                      <div className="text-fg-dim text-[9px]">
                        {dataset.provider_label} · {dataset.resolution_m} m ·{" "}
                        {dataset.temporal_resolution_days}d · {dataset.scale}
                      </div>
                    </div>
                    <span
                      className="flex items-center gap-1.5 flex-none text-[9px] tracking-[0.08em]"
                      style={{ color: status.color }}
                      title={status.title}
                    >
                      <span
                        className="w-[6px] h-[6px] rounded-full flex-none"
                        style={{ background: status.color }}
                      />
                      {status.label}
                    </span>
                  </div>
                )
              })}
            </div>
          </Panel>

          {/* ── RETRIEVAL LOG. The mockup calls this FUSION EVENTS; we have
                no correlation engine yet, and naming one would be a claim. ── */}
          <Panel title="RETRIEVAL LOG">
            <div className="p-[14px] flex flex-col gap-2 font-mono text-[10px] leading-[1.6]">
              {queryList.map((query) => (
                <div
                  key={query.id}
                  className="flex items-start justify-between gap-2"
                >
                  <div className="min-w-0">
                    <div className="text-fg-soft truncate">
                      {query.label || query.dataset_name}
                    </div>
                    <div className="text-fg-dim text-[9px]">
                      {query.status_label} · {query.image_count} scene
                      {query.image_count === 1 ? "" : "s"}
                      {query.mission_name ? ` · ${query.mission_name}` : ""}
                    </div>
                  </div>
                  <span className="text-fg-dim text-[9px] flex-none">
                    {relativeTime(query.completed_at ?? query.created_at)}
                  </span>
                </div>
              ))}
              {!loading && queryList.length === 0 ? (
                <div className="text-fg-dim">No retrievals yet.</div>
              ) : null}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  )
}
// ─── RANGER V3 END: satellite page ───