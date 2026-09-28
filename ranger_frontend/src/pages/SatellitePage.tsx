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
import { useCallback, useEffect, useRef, useState } from "react"
import { Panel } from "@/components/console/Panel"
import { MonoLabel } from "@/components/console/MonoLabel"
import { MetricTile } from "@/components/console/MetricTile"
import { FieldMap, type FieldMapRaster } from "@/components/map/FieldMap"
import { getMapData } from "@/api/dataLogs"
import {
  MEASURED_SOURCES,
  SOURCE_META,
  type DataSource,
  type MapFeatureCollection,
} from "@/types/dataLog.types"
import type { BasemapMode } from "@/components/map/basemaps"
import { useAuthStore } from "@/stores/authStore"
import {
  fetchLayerBlobUrl,
  getDatasets,
  getImages,
  getQueries,
  type Page,
} from "@/api/satellite"
import {
  LAYER_META,
  layerCaption,
  layersFor,
  paletteGradient,
} from "@/types/satellite.types"
import type {
  SatelliteDataset,
  SatelliteImage,
  SatelliteLayer,
  SatelliteQuery,
  RampStats,
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

  const [activeImageId, setActiveImageId] = useState<number | null>(null)
  const [activeLayer, setActiveLayer] = useState<SatelliteLayer>("truecolor")
  const [opacity, setOpacity] = useState(0.85)
  const [raster, setRaster] = useState<FieldMapRaster | null>(null)
  const [rasterError, setRasterError] = useState<string | null>(null)
  const [rampStats, setRampStats] = useState<RampStats | null>(null)

  /**
   * Ground sensor track over the same AOI (F10.3 CP4.2).
   *
   * The pitch thesis is that satellite EO explains ground radiological
   * variability and ground data validates satellite surface products. Until
   * now those two halves lived on separate screens, which asks a viewer to
   * hold them together in their head. Here they share one viewport: gamma
   * readings drawn OVER the index they are supposed to correlate with.
   *
   * CP4 already forces the raster beneath TRACK_LAYER, so this needs no map
   * changes at all — the ordering was built for exactly this.
   */
  const [track, setTrack] = useState<MapFeatureCollection | null>(null)
  const [trackLoading, setTrackLoading] = useState(false)
  const [rasterLoading, setRasterLoading] = useState(false)
  // Controlled, with a handler — passing `basemap` without one would freeze
  // the SAT/VECTOR/TOPO control. Defaults to "sat": an EO overlay against a
  // vector basemap looks like a graphic; against imagery it looks like the
  // measurement it is.
  const [basemap, setBasemap] = useState<BasemapMode>("sat")

  const user = useAuthStore((s) => s.user)
  const accent = user?.organization?.theme_color ?? "#0ea5e9"

  /**
   * The object URL currently held by MapLibre.
   *
   * Object URLs live until revoked. Toggling four layers over two scenes a
   * few dozen times in a demo leaks every PNG ever drawn, and the leak is
   * invisible — nothing errors, memory just climbs. Revoke the PREVIOUS one
   * only after the new raster is installed, never before: revoking a URL
   * MapLibre is still reading blanks the map.
   */
  const heldRevoke = useRef<(() => void) | null>(null)

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

  const activeImage =
    images.items.find((i) => i.id === activeImageId) ?? null

  // Default to the first scene that actually has pixels.
  useEffect(() => {
    if (activeImageId !== null) return
    const first = images.items.find((i) => i.has_cog)
    if (first) setActiveImageId(first.id)
  }, [images, activeImageId])

  // Keep the layer valid for the selected dataset. Switching from an l9
  // scene on THERMAL to an s2 scene must not leave THERMAL selected — the
  // backend would 404 that pair, correctly, and the user would see an error
  // for a choice they did not make.
  useEffect(() => {
    if (!activeImage) return
    const available = layersFor(activeImage.dataset_code)
    if (available.length && !available.includes(activeLayer)) {
      setActiveLayer(available[0])
    }
  }, [activeImage, activeLayer])

  useEffect(() => {
    if (!activeImage || !activeImage.has_cog || !activeImage.bbox) {
      setRaster(null)
      return
    }
    let cancelled = false
    setRasterLoading(true)
    setRasterError(null)

    fetchLayerBlobUrl(activeImage.id, activeLayer)
      .then((rendered) => {
        if (cancelled) {
          rendered.revoke()
          return
        }
        const previous = heldRevoke.current
        heldRevoke.current = rendered.revoke
        setRampStats(rendered.stats)
        setRaster({
          id: rendered.id,
          url: rendered.url,
          bbox: activeImage.bbox as [number, number, number, number],
          opacity,
        })
        // Only now is the old URL safe to release.
        previous?.()
      })
      .catch((err) => {
        if (cancelled) return
        const status = err?.response?.status
        setRaster(null)
        setRampStats(null)
        setRasterError(
          status === 409
            ? "This scene cannot render that layer — it lacks a band the layer needs."
            : status === 404
              ? "This product has no recipe for that layer."
              : "Could not load the rendered layer."
        )
      })
      .finally(() => {
        if (!cancelled) setRasterLoading(false)
      })

    return () => {
      cancelled = true
    }
    // `opacity` deliberately absent: it is applied below without a refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeImage, activeLayer])

  // ── ground track for the active scene's AOI ──
  useEffect(() => {
    if (!activeImage) {
      setTrack(null)
      return
    }
    // The scene belongs to a query; the query may belong to a mission. A
    // satellite-only AOI has NO mission (Mission.robot is non-null, so an
    // unreachable site arrives as an ad-hoc bbox) — and in that case the
    // absence of a track is the point, not a gap. Chumvi will land here.
    const query = queries.items.find((q) => q.id === activeImage.query)
    if (!query?.mission) {
      setTrack(null)
      return
    }

    let cancelled = false
    setTrackLoading(true)
    getMapData({ mission_id: query.mission })
      .then((fc) => {
        if (!cancelled) setTrack(fc)
      })
      .catch(() => {
        if (!cancelled) setTrack(null)
      })
      .finally(() => {
        if (!cancelled) setTrackLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [activeImage, queries])

  // Opacity is a paint change, not a new image. Refetching for it would
  // re-request a PNG we already hold.
  useEffect(() => {
    setRaster((r) => (r ? { ...r, opacity } : r))
  }, [opacity])

  // Release the last URL on unmount.
  useEffect(() => {
    return () => {
      heldRevoke.current?.()
      heldRevoke.current = null
    }
  }, [])

  const selectImage = useCallback((id: number) => setActiveImageId(id), [])

  /** What the track actually contains, for the line under the map. */
  const trackSummary = (() => {
    const feats = track?.features ?? []
    if (feats.length === 0) return null
    const tiers = new Set<DataSource>(feats.map((f) => f.properties.source))
    const ordered = (["live", "reported", "modelled", "simulated"] as const)
      .filter((t) => tiers.has(t))
    const anyGenerated = ordered.some((t) => !MEASURED_SOURCES.includes(t))
    return {
      count: feats.length,
      tiers: ordered,
      anyGenerated,
      note: feats[0].properties.provenance_note,
    }
  })()

  const imageList = images.items
  const queryList = queries.items

  /** "Forole Hills foothills" -> "FOROLE". Declared before the grouping
   *  below, which calls it while counting label collisions. */
  const shortSite = (label: string) =>
    label.split(/[\s(]/)[0].toUpperCase().slice(0, 10)

  /**
   * Scenes grouped by SITE, not by product (F10.3 CP5).
   *
   * The picker used to label every button with its dataset code, which was
   * fine at two scenes over one AOI and useless at seven: `S2 S2 S2 S2 S2 S2
   * L9` names the sensor and hides the only thing the user is choosing
   * between. With one scene per KNRA survey site the axis that matters is
   * WHERE; the product is a secondary choice within it.
   *
   * Site identity is the AOI bbox — the same key SITES COVERED uses, so the
   * two cannot disagree — because a satellite-only AOI has no mission at all
   * (Mission.robot is non-null).
   */
  const sceneOptions = imageList
    .filter((i) => i.has_cog)
    .map((image) => {
      const q = queries.items.find((x) => x.id === image.query)
      return {
        image,
        siteKey: q?.aoi_bbox
          ? q.aoi_bbox.map((v) => v.toFixed(4)).join(",")
          : (q?.mission_name ?? `query-${image.query}`),
        siteLabel: q?.mission_name ?? q?.label ?? "Unnamed AOI",
      }
    })

  /** One entry per site, alphabetical so the strip does not reshuffle. */
  const rawSites = Array.from(
    sceneOptions
      .reduce((acc, opt) => {
        if (!acc.has(opt.siteKey)) {
          acc.set(opt.siteKey, {
            key: opt.siteKey,
            label: opt.siteLabel,
            scenes: [] as SatelliteImage[],
          })
        }
        acc.get(opt.siteKey)!.scenes.push(opt.image)
        return acc
      }, new Map<string, { key: string; label: string; scenes: SatelliteImage[] }>())
      .values()
  ).sort((a, b) => a.label.localeCompare(b.label))

  /**
   * Button labels, disambiguated.
   *
   * `shortSite` takes the first word, which is right for six of the seven
   * sites and wrong for the two Dukana wells: "Dukana (Laga Balal) Well 1"
   * and "Well 2" both shorten to DUKANA, giving two identical buttons that
   * select different AOIs. Where a short label collides, append the trailing
   * number from the full name.
   */
  const shortCounts = new Map<string, number>()
  for (const site of rawSites) {
    const key = shortSite(site.label)
    shortCounts.set(key, (shortCounts.get(key) ?? 0) + 1)
  }
  const sites = rawSites.map((site) => {
    const base = shortSite(site.label)
    if ((shortCounts.get(base) ?? 0) <= 1) return { ...site, short: base }
    const trailing = site.label.match(/(\d+)\s*$/)?.[1]
    return {
      ...site,
      short: trailing
        ? `${base} ${trailing}`
        : `${base} ${site.label.split(/\s+/).slice(-1)[0].toUpperCase()}`,
    }
  })

  const activeSiteKey =
    sceneOptions.find((o) => o.image.id === activeImageId)?.siteKey ?? null
  const activeSite = sites.find((x) => x.key === activeSiteKey) ?? null

  /**
   * Switching site keeps the current PRODUCT where that site has it.
   *
   * Comparing Forole against Boji is the whole point of seven sites; silently
   * dropping from L9 back to S2 mid-comparison would change two variables at
   * once, which is how a covariate argument stops being one.
   */
  const selectSite = useCallback(
    (key: string) => {
      const site = rawSites.find((x) => x.key === key)
      if (!site || site.scenes.length === 0) return
      const sameProduct = site.scenes.find(
        (sc) => sc.dataset_code === activeImage?.dataset_code
      )
      setActiveImageId((sameProduct ?? site.scenes[0]).id)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sceneOptions.length, activeImage, imageList.length]
  )


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
        <Panel
          title="EO IMAGERY"
          right={
            <MonoLabel size="xs" tone={rasterError ? "alert" : "dim"}>
              {rasterLoading
                ? "RENDERING…"
                : rasterError
                  ? "RENDER FAILED"
                  : activeImage
                    ? `${activeSite ? activeSite.short + " · " : ""}${activeImage.dataset_code.toUpperCase()} · ${activeImage.resolution_m} M`
                    : "NO SCENE"}
            </MonoLabel>
          }
          bodyClassName="p-0"
        >
          <div className="p-[14px] pb-0 flex flex-wrap items-center gap-2">
            {/* Site picker — the axis that actually matters. */}
            {sites.map((site) => (
              <button
                key={site.key}
                onClick={() => selectSite(site.key)}
                className="font-mono text-[9px] tracking-[0.08em] px-2 py-1 rounded border transition-colors"
                style={{
                  color: site.key === activeSiteKey ? accent : undefined,
                  borderColor:
                    site.key === activeSiteKey ? `${accent}88` : undefined,
                  background:
                    site.key === activeSiteKey ? `${accent}18` : undefined,
                }}
                title={`${site.label} · ${site.scenes.length} scene${
                  site.scenes.length === 1 ? "" : "s"
                }`}
              >
                {site.short}
              </button>
            ))}

            {/* Product picker, only where the site HAS more than one. A lone
                button offering no alternative is chrome, not a control. */}
            {activeSite && activeSite.scenes.length > 1 ? (
              <>
                <span className="w-px h-4 bg-border-strong mx-1" />
                {activeSite.scenes.map((scene) => (
                  <button
                    key={scene.id}
                    onClick={() => selectImage(scene.id)}
                    className="font-mono text-[9px] tracking-[0.08em] px-2 py-1 rounded border transition-colors"
                    style={{
                      color: scene.id === activeImageId ? accent : undefined,
                      borderColor:
                        scene.id === activeImageId ? `${accent}88` : undefined,
                      background:
                        scene.id === activeImageId ? `${accent}18` : undefined,
                    }}
                    title={`${scene.dataset_name} · ${new Date(
                      scene.acquisition_date
                    ).toLocaleDateString()} · ${scene.resolution_m} m`}
                  >
                    {scene.dataset_code.toUpperCase()}
                  </button>
                ))}
              </>
            ) : null}

            <span className="w-px h-4 bg-border-strong mx-1" />

            {/* Layer toggles — ONLY layers this dataset can render.
                Offering a toggle the backend would 404 makes the user
                interpret an error for a choice they did not make. */}
            {activeImage
              ? layersFor(activeImage.dataset_code).map((layer) => (
                  <button
                    key={layer}
                    onClick={() => setActiveLayer(layer)}
                    className="font-mono text-[9px] tracking-[0.08em] px-2 py-1 rounded border transition-colors"
                    style={{
                      color: layer === activeLayer ? accent : undefined,
                      borderColor:
                        layer === activeLayer ? `${accent}88` : undefined,
                      background:
                        layer === activeLayer ? `${accent}18` : undefined,
                    }}
                  >
                    {LAYER_META[layer].short}
                  </button>
                ))
              : null}

            <label className="ml-auto flex items-center gap-2 font-mono text-[9px] tracking-[0.08em] text-fg-dim">
              OPACITY
              <input
                type="range"
                min={0.2}
                max={1}
                step={0.05}
                value={opacity}
                onChange={(e) => setOpacity(Number(e.target.value))}
                className="w-24 accent-[var(--accent)]"
              />
            </label>
          </div>

          <div className="p-[14px]">
            <FieldMap
              accent={accent}
              raster={raster}
              fitToRaster
              track={track}
              // fitToRaster owns the viewport. Both fitters would fight, and
              // the raster footprint is the tighter, more relevant frame —
              // the track can extend well beyond one scene's clip.
              fitToTrack={false}
              showOverlays={false}
              expandable
              height={420}
              basemap={basemap}
              onBasemapChange={setBasemap}
            />

            {/* The caption is the point. It states what the number IS and
                what it is NOT, and it varies BY DATASET — NDVI over S2 is
                correct from raw values because the calibration cancels;
                over L9 the offset does not cancel and the backend applies
                calibration first. Same index, same name, different
                provenance, and the viewer is told which. */}
            <div className="mt-2.5 font-mono text-[9.5px] leading-[1.7] text-fg-dim">
              {activeImage ? (
                <>
                  <span className="text-fg-soft">
                    {LAYER_META[activeLayer].label.toUpperCase()}
                  </span>
                  {" — "}
                  {layerCaption(activeImage.dataset_code, activeLayer)}
                  <div className="mt-1">
                    {activeImage.dataset_name} ·{" "}
                    {new Date(
                      activeImage.acquisition_date
                    ).toLocaleDateString()}{" "}
                    · {activeImage.resolution_m} m · {activeImage.scale}
                    {activeImage.cloud_cover_pct !== null
                      ? ` · ${activeImage.cloud_cover_pct.toFixed(1)}% cloud`
                      : ""}
                  </div>
                </>
              ) : (
                "No scene selected. Run fetch_scenes to retrieve imagery."
              )}
            </div>

            {/* ── ground truth over the same AOI ──
                The two halves of the argument, in one line: what the ground
                measured, at what provenance tier, over the scene it is being
                correlated with. Silence here is meaningful too — a satellite
                -only AOI has no track, and saying so is the Chumvi case. */}
            <div className="mt-1.5 font-mono text-[9.5px] leading-[1.7]">
              {trackLoading ? (
                <span className="text-fg-dim">Loading ground track…</span>
              ) : trackSummary ? (
                <span className="text-fg-dim">
                  <span className="text-fg-soft">GROUND TRUTH</span>
                  {" — "}
                  {trackSummary.count.toLocaleString()} gamma dose-rate points
                  over this AOI{" "}
                  {trackSummary.tiers.map((t) => (
                    <span
                      key={t}
                      className="ml-1 px-1 py-0.5 rounded border text-[8.5px] tracking-[0.08em]"
                      style={{
                        color: SOURCE_META[t].color,
                        borderColor: `${SOURCE_META[t].color}55`,
                        background: `${SOURCE_META[t].color}15`,
                      }}
                    >
                      {SOURCE_META[t].short}
                    </span>
                  ))}
                  {trackSummary.anyGenerated ? (
                    <div className="mt-1">
                      ⚠ These points are NOT measurements.
                      {trackSummary.note ? ` ${trackSummary.note}` : ""}
                    </div>
                  ) : null}
                </span>
              ) : (
                <span className="text-fg-dim">
                  GROUND TRUTH — none for this AOI. Satellite coverage here
                  stands alone.
                </span>
              )}
            </div>

            {/* ── ramp legend ──
                Only shown for stretched index/scalar layers, and it always
                carries the RANGE. A percentile-stretched ramp's colours are
                relative to this scene; without these numbers the image
                implies absolute physical values it does not have, which is
                the whole reason the stats travel with the pixels. */}
            {rampStats && rampStats.kind !== "rgb" ? (
              <div className="mt-2.5">
                <div
                  className="h-[8px] rounded-sm border border-border-strong"
                  style={{ background: paletteGradient(rampStats.palette) }}
                />
                <div className="mt-1 flex items-center justify-between font-mono text-[9px] tracking-[0.06em] text-fg-dim">
                  <span>
                    {rampStats.display_min.toFixed(2)}
                    {rampStats.units}
                  </span>
                  <span className="text-center">
                    {rampStats.stretch === "percentile"
                      ? `STRETCHED TO THIS SCENE · p${rampStats.stretch_pct[0]}–p${rampStats.stretch_pct[1]}`
                      : "ABSOLUTE SCALE"}
                  </span>
                  <span>
                    {rampStats.display_max.toFixed(2)}
                    {rampStats.units}
                  </span>
                </div>
                {rampStats.data_min !== null && rampStats.data_max !== null ? (
                  <div className="mt-0.5 font-mono text-[9px] leading-[1.6] text-fg-dim">
                    Full observed range {rampStats.data_min.toFixed(3)} to{" "}
                    {rampStats.data_max.toFixed(3)}
                    {rampStats.units} over{" "}
                    {rampStats.valid_px.toLocaleString()} valid pixels · colour
                    is relative to this scene, not comparable across dates
                  </div>
                ) : null}
              </div>
            ) : null}

            {rasterError ? (
              <div
                className="mt-2 px-3 py-2 rounded-md border font-mono text-[10px] leading-[1.6]"
                style={{
                  color: "#f5a623",
                  borderColor: "#f5a62355",
                  background: "#f5a62312",
                }}
              >
                ⚠ {rasterError}
              </div>
            ) : null}
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