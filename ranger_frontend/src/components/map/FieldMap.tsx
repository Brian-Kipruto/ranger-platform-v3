// ─── RANGER V3 START: FieldMap component ───
/**
 * FieldMap — the shared MapLibre map used by both the Data Explorer and the
 * Dashboard. Extracted from DataExplorerPage's inline map (F05/F06) so the two
 * screens share one battle-tested setup, then upgraded with the three F07
 * capabilities the DE map never had:
 *
 *   1. THREE BASEMAPS (vector / sat / topo) via map.setStyle(). Because setStyle
 *      wipes all sources & layers, every data layer is (re)added in ONE place —
 *      installLayers() — called on the initial `load` AND on every `styledata`.
 *   2. EXPAND → fullscreen. A CSS-class fullscreen on the same container (no
 *      re-init), with map.resize() after the size change so tiles don't clip.
 *   3. OVERLAYS — robot blips (real MapLibre Markers, so they track pan/zoom for
 *      free) + a bottom-left telemetry readout, layered over the canvas.
 *
 * MapLibre-in-React invariants (carried verbatim from the DE map — the
 * error-prone bits that bit V2 and F05):
 *   - The map instance lives in a ref, never state (it isn't React-reactive).
 *   - Init runs once, guarded by a map.current check; React 19 StrictMode
 *     double-invokes effects in dev, hence the guard + unmount cleanup.
 *   - The container needs an explicit height or MapLibre renders 0px tall.
 *   - maplibre-gl.css MUST be imported (broken controls/markers otherwise).
 *   - GeoJSON coordinates are [lng, lat] (verified backend-side in F05).
 *   - PAINT PROPS CAN'T READ CSS VARS: the accent is a hex string PROP, never
 *     var(--accent). Callers resolve org.theme_color and pass it in.
 *
 * CP1 scope: map + track + basemaps + fallback. The overlay/expand props below
 * are part of the final contract (so the CP2 Data Explorer refactor compiles
 * against the finished shape), but their rendering is fully wired in CP3.
 */
import { useCallback, useEffect, useImperativeHandle, useRef, useState, forwardRef } from "react"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { cn } from "@/lib/utils"
import { MonoLabel } from "@/components/console/MonoLabel"
import type { MapFeatureCollection } from "@/types/dataLog.types"
import {
  type BasemapMode,
  styleUrl,
  MAP_KEY_PRESENT,
  DEFAULT_BASEMAP,
  BASEMAP_ORDER,
  BASEMAP_LABEL,
} from "./basemaps"

const NAIROBI: [number, number] = [36.8219, -1.2921]

/** A robot marker overlaid on the map (dashboard). Rendered in CP3. */
export interface FieldMapBlip {
  id: string
  lng: number
  lat: number
  status: "live" | "mqtt" | "offline" | "idle"
}

/** Bottom-left telemetry readout content (dashboard). Rendered in CP3. */
export interface FieldMapReadout {
  id: string
  call?: string
  coords?: string
  headingDeg?: number
  speedMs?: number
}

/** Imperative handle so callers (Data Explorer) can flyTo a clicked row. */
export interface FieldMapHandle {
  flyTo: (lng: number, lat: number, zoom?: number) => void
  setHighlight: (lng: number, lat: number) => void
  clearHighlight: () => void
  resize: () => void
}

export interface FieldMapRaster {
  /** Identity of the CURRENT image+layer, e.g. "12:ndvi". Changing it swaps
   *  the pixels via updateImage rather than remove/re-add — no flicker. */
  id: string
  /** Object URL from fetchLayerBlobUrl. NOT the raw endpoint path: MapLibre
   *  fetches this itself, outside axios, so an /api/ URL would go
   *  unauthenticated and 401 with the map silently blank. */
  url: string
  /** [west, south, east, north], EPSG:4326. Our COGs are already 4326
   *  (F10.2 CP5), so corner-pinning is exact — no reprojection. */
  bbox: [number, number, number, number]
  opacity?: number
}

export interface FieldMapProps {
  /** Resolved accent hex (org theme_color). NEVER var(--accent) — see header. */
  accent: string
  /** Historical track points as GeoJSON. Both screens feed this. */
  track?: MapFeatureCollection | null
  /** Fit the map to the track whenever the track changes. DE wants this. */
  fitToTrack?: boolean
  /** Robot blips overlaid on the map (dashboard). CP3. */
  blips?: FieldMapBlip[]
  selectedBlipId?: string | null
  onSelectBlip?: (id: string) => void
  /** Telemetry readout box, bottom-left (dashboard). CP3. */
  readout?: FieldMapReadout | null
  /** Show overlay chrome (blips + readout). DE passes false; dashboard true. */
  showOverlays?: boolean
  /** Controlled basemap. Omit for internal state. */
  basemap?: BasemapMode
  onBasemapChange?: (m: BasemapMode) => void
  /** Show the EXPAND → control + enable fullscreen. CP3. */
  expandable?: boolean
  /** Header chrome. Falsy hides the header row entirely. */
  headerTitle?: string
  headerSub?: string
  /** Extra header-right slot (e.g. DE's FILTERED TRACK label). */
  headerRight?: React.ReactNode
  /**
   * Georeferenced raster overlay, pinned to its bbox corners (F10.3 CP4).
   * Null removes it. Always drawn BENEATH the track layer — ground truth
   * renders over satellite imagery, never under it.
   */
  raster?: FieldMapRaster | null
  /**
   * Fit the viewport to the raster's bbox when its `id` changes (F10.3 CP4).
   *
   * Needed because the map's default center is Nairobi and a scene may be
   * anywhere — Forole is ~1,000 km north, so without this the overlay loads
   * correctly and is simply not on screen, which looks exactly like a
   * rendering failure and is not one.
   *
   * Keyed on `id`, not on the object, so an opacity change does not yank the
   * viewport back while the user is panning.
   */
  fitToRaster?: boolean
  /** Map viewport height (the container needs an explicit height). */
  height?: string | number
  className?: string
}

const TRACK_SOURCE = "track"
const TRACK_LAYER = "track-points"
const RASTER_SOURCE = "eo-raster"
const RASTER_LAYER = "eo-raster-layer"

/** ImageSource wants four corners CLOCKWISE FROM TOP-LEFT, not a bbox.
 *  Getting this order wrong mirrors or rotates the image over the map,
 *  which reads as a georeferencing bug in the data rather than in this
 *  five-line function. */
function cornersFromBbox(
  bbox: [number, number, number, number]
): [[number, number], [number, number], [number, number], [number, number]] {
  const [w, s, e, n] = bbox
  return [
    [w, n],
    [e, n],
    [e, s],
    [w, s],
  ]
}

// Blip status → semantic color (hex literals matching index.css tokens;
// JS-created marker DOM can't read CSS vars). live=ok, mqtt=warn, offline=alert,
// idle=info.
/**
 * Track-point colour BY PROVENANCE (F10.3 CP0).
 *
 * A modelled point and a measured point must not be the same colour on a map
 * that IS the argument. Falls through to the org accent for any tier not
 * listed, so a future SensorLog.Source value still renders.
 *
 * Defined once, at module scope, because it is consumed in two places that
 * must not drift: addLayer (first install) and setPaintProperty (refresh
 * after the accent or the style changes).
 *
 * Hex literals mirror SOURCE_META in dataLog.types.ts — paint props cannot
 * read CSS vars, see the header invariants.
 */
function trackColorExpression(accent: string) {
  return [
    "match",
    ["get", "source"],
    "live", "#4be08a",
    "reported", "#36c5f0",
    "modelled", "#f5a623",
    "simulated", "#7a828f",
    accent,
  ] as unknown as maplibregl.ExpressionSpecification
}

/**
 * Generated tiers render slightly transparent with a thinner ring, so the
 * measured/generated distinction survives a projector, a greyscale print,
 * and colour-blind viewers — three conditions a pitch room can supply all
 * at once, and none of which colour alone survives.
 */
function trackOpacityExpression() {
  return [
    "match",
    ["get", "source"],
    "live", 0.9,
    "reported", 0.9,
    0.6,
  ] as unknown as maplibregl.ExpressionSpecification
}

function trackStrokeWidthExpression() {
  return [
    "match",
    ["get", "source"],
    "live", 1.4,
    "reported", 1.4,
    0.6,
  ] as unknown as maplibregl.ExpressionSpecification
}

const BLIP_COLOR: Record<FieldMapBlip["status"], string> = {
  live: "#4be08a",
  mqtt: "#f5a623",
  offline: "#ff5d5d",
  idle: "#36c5f0",
}

/**
 * Build the DOM element for a blip marker. A colored dot, a small label above,
 * an optional ping ring (live only), and a selected emphasis ring. Returned
 * element is handed to maplibregl.Marker so it tracks pan/zoom automatically.
 */
function buildBlipEl(blip: FieldMapBlip, selected: boolean): HTMLDivElement {
  const color = BLIP_COLOR[blip.status]
  const wrap = document.createElement("div")
  wrap.style.cssText = "position:relative;width:0;height:0;cursor:pointer;"

  // ping ring (live only)
  if (blip.status === "live") {
    const ping = document.createElement("span")
    ping.style.cssText =
      `position:absolute;left:50%;top:50%;width:14px;height:14px;transform:translate(-50%,-50%);` +
      `border-radius:50%;background:${color};opacity:.55;animation:rngPing 2.4s ease-out infinite;`
    wrap.appendChild(ping)
  }

  // sweep ring on the selected blip
  if (selected) {
    const sweep = document.createElement("span")
    sweep.style.cssText =
      `position:absolute;left:50%;top:50%;width:46px;height:46px;transform:translate(-50%,-50%);` +
      `border-radius:50%;overflow:hidden;pointer-events:none;` +
      `background:conic-gradient(from 0deg, ${color}55, transparent 42%);animation:rngSweep 3.6s linear infinite;`
    wrap.appendChild(sweep)
  }

  // the dot
  const dot = document.createElement("span")
  const size = selected ? 13 : 10
  dot.style.cssText =
    `position:absolute;left:50%;top:50%;width:${size}px;height:${size}px;transform:translate(-50%,-50%);` +
    `border-radius:50%;background:${color};` +
    `border:2px solid ${selected ? "#fff" : "#0a0d12"};` +
    `box-shadow:${selected ? `0 0 0 4px ${color}44, 0 0 14px ${color}` : `0 0 8px ${color}aa`};`
  wrap.appendChild(dot)

  // label above the dot
  const label = document.createElement("div")
  label.textContent = blip.id
  label.style.cssText =
    `position:absolute;left:50%;top:-9px;transform:translate(-50%,-100%);` +
    `font-family:'IBM Plex Mono',monospace;font-size:8.5px;letter-spacing:0.06em;` +
    `color:${selected ? "#e9ebef" : "#7a828f"};white-space:nowrap;` +
    `background:rgba(8,9,11,0.7);padding:1px 4px;border-radius:3px;`
  wrap.appendChild(label)

  return wrap
}


export const FieldMap = forwardRef<FieldMapHandle, FieldMapProps>(function FieldMap(
  {
    accent,
    track,
    fitToTrack = false,
    blips,
    selectedBlipId,
    onSelectBlip,
    readout,
    showOverlays = false,
    basemap,
    onBasemapChange,
    expandable = false,
    headerTitle,
    headerSub,
    headerRight,
    raster = null,
    fitToRaster = false,
    height = "68vh",
    className,
  },
  ref
) {
  const mapContainer = useRef<HTMLDivElement | null>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const highlightMarker = useRef<maplibregl.Marker | null>(null)
  // Blip markers keyed by robot id, so we can diff/update/remove on change.
  const blipMarkers = useRef<Map<string, maplibregl.Marker>>(new Map())
  const [mapReady, setMapReady] = useState(false)
  // Fullscreen expand (CP3). map.resize() is called after the size change.
  const [expanded, setExpanded] = useState(false)

  // Basemap can be controlled (prop) or uncontrolled (internal state).
  const [internalBasemap, setInternalBasemap] = useState<BasemapMode>(basemap ?? DEFAULT_BASEMAP)
  const activeBasemap = basemap ?? internalBasemap

  // Keep the latest track in a ref so the load/styledata handlers can apply it
  // even if a fetch resolved before the map (or new style) was ready.
  const pendingTrack = useRef<MapFeatureCollection | null>(track ?? null)
  // Same reason as pendingTrack: a blob may resolve before the map (or a new
  // style) is ready, and styledata re-installs from whatever is current.
  const pendingRaster = useRef<FieldMapRaster | null>(raster)
  /** Last raster id the viewport was fitted to, so a repeat fit is skipped. */
  const fittedRasterId = useRef<string | null>(null)

  /**
   * installLayers — the SINGLE place every source/layer is (re)added. Called on
   * the initial `load` and on every `styledata` (after setStyle wipes them).
   * Idempotent: guards against re-adding an existing source/layer.
   */
  const installLayers = useCallback(
    (m: maplibregl.Map) => {
      // ── raster FIRST, so it exists to insert the track above ──
      const r = pendingRaster.current
      if (r) {
        if (!m.getSource(RASTER_SOURCE)) {
          m.addSource(RASTER_SOURCE, {
            type: "image",
            url: r.url,
            coordinates: cornersFromBbox(r.bbox),
          })
        }
        if (!m.getLayer(RASTER_LAYER)) {
          m.addLayer({
            id: RASTER_LAYER,
            type: "raster",
            source: RASTER_SOURCE,
            paint: {
              "raster-opacity": r.opacity ?? 1,
              // Nearest, not the default linear: these scenes are 38x41 and
              // 112x119 px. Smoothing them invents detail the sensor never
              // resolved, which on a screen arguing about resolution is the
              // wrong kind of pretty.
              "raster-resampling": "nearest",
              "raster-fade-duration": 0,
            },
          })
        }
      }

      if (!m.getSource(TRACK_SOURCE)) {
        m.addSource(TRACK_SOURCE, {
          type: "geojson",
          data: pendingTrack.current ?? { type: "FeatureCollection", features: [] },
        })
      }
      if (!m.getLayer(TRACK_LAYER)) {
        m.addLayer({
          id: TRACK_LAYER,
          type: "circle",
          source: TRACK_SOURCE,
          paint: {
            "circle-radius": 4,
            // F10.3 CP0: colour by provenance, not by tenant accent.
            "circle-color": trackColorExpression(accent),
            "circle-stroke-width": trackStrokeWidthExpression(),
            "circle-stroke-color": "#ffffff",
            "circle-opacity": trackOpacityExpression(),
          },
        })
      }

      // Sensor points ALWAYS draw over imagery. If the raster were added
      // after the track (a styledata re-install with a newly-set raster, say)
      // it would cover every ground measurement on the screen whose whole
      // argument is that ground measurements validate the imagery.
      if (m.getLayer(RASTER_LAYER) && m.getLayer(TRACK_LAYER)) {
        m.moveLayer(RASTER_LAYER, TRACK_LAYER)
      }

      // The guards above prevent re-ADDING a layer that already exists. They
      // do NOT update one whose paint props changed since it was added —
      // which happens on every accent change, and from CP4 on every raster
      // layer switch. Refresh explicitly rather than relying on idempotence
      // to mean "correct".
      if (m.getLayer(TRACK_LAYER)) {
        m.setPaintProperty(TRACK_LAYER, "circle-color", trackColorExpression(accent))
      }
      if (m.getLayer(RASTER_LAYER) && r) {
        m.setPaintProperty(RASTER_LAYER, "raster-opacity", r.opacity ?? 1)
      }
    },
    [accent]
  )

  // The init effect below has [] deps — it MUST run exactly once — so every
  // value it closes over is frozen at mount. `installLayers` is not frozen:
  // it reads `accent` today, and from F10.3 CP4 it will read the active
  // raster layer, image id and opacity, all of which change constantly.
  //
  // `styledata` fires on EVERY basemap switch. Without this ref, switching
  // the basemap re-installs the layers as they were at first render, so a
  // user who changes layers and then changes basemap silently gets their
  // original layer back. Nothing in the type system or the test suite
  // catches that; it is a screenshot-loop bug (gotcha 8).
  const installLayersRef = useRef(installLayers)
  useEffect(() => {
    installLayersRef.current = installLayers
  }, [installLayers])

  // ── init once (StrictMode-safe), cleanup on unmount ──
  useEffect(() => {
    if (!mapContainer.current || map.current || !MAP_KEY_PRESENT) return
    const initialStyle = styleUrl(activeBasemap)
    if (!initialStyle) return

    const m = new maplibregl.Map({
      container: mapContainer.current,
      style: initialStyle,
      center: NAIROBI,
      zoom: 13,
    })
    m.addControl(new maplibregl.NavigationControl(), "top-right")
    m.addControl(new maplibregl.ScaleControl(), "bottom-left")

    m.on("load", () => {
      installLayersRef.current(m)
      setMapReady(true)
    })

    // After every setStyle, the style reloads and wipes sources/layers.
    // styledata fires once the new style is ready — re-add our layers here.
    m.on("styledata", () => {
      installLayersRef.current(m)
    })

    map.current = m
    return () => {
      m.remove()
      map.current = null
      highlightMarker.current = null
      setMapReady(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── push track updates into the source (and optionally fit) ──
  useEffect(() => {
    pendingTrack.current = track ?? null
    const m = map.current
    if (!m || !mapReady) return
    const src = m.getSource(TRACK_SOURCE) as maplibregl.GeoJSONSource | undefined
    if (!src) return
    src.setData(track ?? { type: "FeatureCollection", features: [] })
    if (fitToTrack && track && track.features.length > 0) {
      const b = new maplibregl.LngLatBounds()
      for (const f of track.features) b.extend(f.geometry.coordinates)
      m.fitBounds(b, { padding: 40, maxZoom: 16, duration: 600 })
    }
  }, [track, fitToTrack, mapReady])

  // ── raster changes: swap pixels, move, or remove ──
  useEffect(() => {
    pendingRaster.current = raster
    const m = map.current
    if (!m || !mapReady) return

    const source = m.getSource(RASTER_SOURCE) as
      | maplibregl.ImageSource
      | undefined

    if (!raster) {
      // Layer before source — MapLibre throws if a source still has a layer.
      if (m.getLayer(RASTER_LAYER)) m.removeLayer(RASTER_LAYER)
      if (m.getSource(RASTER_SOURCE)) m.removeSource(RASTER_SOURCE)
      fittedRasterId.current = null
      return
    }

    if (!source) {
      // Nothing installed yet — installLayers reads pendingRaster and does it.
      installLayersRef.current(m)
      return
    }

    // updateImage rather than remove/re-add: no flicker between layer
    // toggles, and the layer keeps its position under the track.
    source.updateImage({
      url: raster.url,
      coordinates: cornersFromBbox(raster.bbox),
    })
    if (m.getLayer(RASTER_LAYER)) {
      m.setPaintProperty(RASTER_LAYER, "raster-opacity", raster.opacity ?? 1)
      if (m.getLayer(TRACK_LAYER)) m.moveLayer(RASTER_LAYER, TRACK_LAYER)
    }
  }, [raster, mapReady])

  // ── fit the viewport to the raster, once per image+layer ──
  useEffect(() => {
    const m = map.current
    if (!m || !mapReady || !fitToRaster || !raster) return
    if (fittedRasterId.current === raster.id) return
    fittedRasterId.current = raster.id
    const [w, s2, e, n] = raster.bbox
    m.fitBounds(
      [
        [w, s2],
        [e, n],
      ],
      // Generous padding: a 300 m site fitted edge-to-edge gives no
      // surrounding context, and the context is what makes the footprint
      // legible as a clip rather than as the whole world.
      { padding: 60, maxZoom: 17, duration: 700 }
    )
  }, [raster, fitToRaster, mapReady])

  // ── accent change: repaint the existing layer ──
  // installLayers only runs on load/styledata, neither of which fires when
  // the accent prop changes (a tenant switch). Without this, the fallback
  // colour in the match expression goes stale until the next style reload.
  useEffect(() => {
    const m = map.current
    if (!m || !mapReady || !m.getLayer(TRACK_LAYER)) return
    m.setPaintProperty(TRACK_LAYER, "circle-color", trackColorExpression(accent))
  }, [accent, mapReady])

  // ── basemap switch: setStyle; layers re-added by the styledata handler ──
  useEffect(() => {
    const m = map.current
    if (!m || !mapReady) return
    const url = styleUrl(activeBasemap)
    if (url) m.setStyle(url)
  }, [activeBasemap, mapReady])

  // ── blip markers: diff `blips` against the registry; add/update/remove ──
  // Markers are real maplibregl.Markers, so they track pan/zoom for free (no
  // manual map.project on every move). Rebuilding the element on change keeps
  // selected-emphasis / status-color in sync.
  useEffect(() => {
    const m = map.current
    if (!m || !mapReady || !showOverlays) return
    const registry = blipMarkers.current
    const next = new Map((blips ?? []).map((b) => [b.id, b]))

    // remove markers whose blip is gone
    for (const [id, marker] of registry) {
      if (!next.has(id)) {
        marker.remove()
        registry.delete(id)
      }
    }

    // add or update
    for (const blip of next.values()) {
      const selected = blip.id === selectedBlipId
      const el = buildBlipEl(blip, selected)
      el.addEventListener("click", (e) => {
        e.stopPropagation()
        onSelectBlip?.(blip.id)
      })
      const existing = registry.get(blip.id)
      if (existing) {
        // replace element (selection/status may have changed) + move
        existing.remove()
      }
      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([blip.lng, blip.lat])
        .addTo(m)
      registry.set(blip.id, marker)
    }
  }, [blips, selectedBlipId, showOverlays, onSelectBlip, mapReady])

  // ── clean up all blip markers on unmount ──
  useEffect(() => {
    const registry = blipMarkers.current
    return () => {
      for (const marker of registry.values()) marker.remove()
      registry.clear()
    }
  }, [])

  // ── expand: container size changes, so MapLibre needs a resize ──
  useEffect(() => {
    const m = map.current
    if (!m) return
    // wait a frame for the fullscreen CSS to apply, then resize the canvas
    const id = requestAnimationFrame(() => m.resize())
    return () => cancelAnimationFrame(id)
  }, [expanded])

  // ── imperative handle for the Data Explorer's row-click flyTo + highlight ──
  useImperativeHandle(
    ref,
    (): FieldMapHandle => ({
      flyTo: (lng, lat, zoom = 17) => {
        map.current?.flyTo({ center: [lng, lat], zoom, duration: 800 })
      },
      setHighlight: (lng, lat) => {
        if (!map.current) return
        if (highlightMarker.current) {
          highlightMarker.current.setLngLat([lng, lat])
        } else {
          highlightMarker.current = new maplibregl.Marker({ color: "#facc15" })
            .setLngLat([lng, lat])
            .addTo(map.current)
        }
      },
      clearHighlight: () => {
        highlightMarker.current?.remove()
        highlightMarker.current = null
      },
      resize: () => map.current?.resize(),
    }),
    []
  )

  const handleBasemap = (m: BasemapMode) => {
    if (onBasemapChange) onBasemapChange(m)
    else setInternalBasemap(m)
  }

  const hasHeader = !!(headerTitle || headerRight || expandable)

  // ── no-key fallback (unchanged behaviour from F05/F06) ──
  if (!MAP_KEY_PRESENT) {
    return (
      <div
        className={cn(
          "bg-surface-4 border border-border rounded-[10px] overflow-hidden",
          className
        )}
      >
        <div
          className="w-full flex items-center justify-center text-center font-mono text-[11px] text-fg-dim p-6"
          style={{ height }}
        >
          MAP UNAVAILABLE · VITE_MAPTILER_KEY NOT SET IN ranger_frontend/.env ·
          ADD IT AND RESTART THE DEV SERVER
        </div>
      </div>
    )
  }

  return (
    <div
      className={cn(
        "bg-surface-4 border border-border overflow-hidden",
        expanded ? "fixed inset-0 z-50 rounded-none" : "rounded-[10px]",
        className
      )}
    >
      {hasHeader ? (
        <div className="flex items-center justify-between px-[13px] py-[11px] border-b border-border">
          <div className="flex items-center gap-[9px] min-w-0">
            {headerTitle ? (
              <MonoLabel size="md" tone="soft" tracking="0.13em">
                {headerTitle}
              </MonoLabel>
            ) : null}
            {headerSub ? (
              <MonoLabel size="xs" tone="faint" tracking="0.04em" className="normal-case">
                {headerSub}
              </MonoLabel>
            ) : null}
          </div>
          <div className="flex items-center gap-[7px]">
            {/* basemap toggle — three real modes */}
            {BASEMAP_ORDER.map((mode) => {
              const on = mode === activeBasemap
              return (
                <button
                  key={mode}
                  type="button"
                  onClick={() => handleBasemap(mode)}
                  className="cursor-pointer font-mono text-[9px] rounded px-2 py-[3px] border transition-colors"
                  style={
                    on
                      ? {
                          color: "var(--accent)",
                          borderColor: "color-mix(in srgb, var(--accent) 40%, transparent)",
                        }
                      : { color: "var(--color-fg-dim)", borderColor: "var(--color-border-strong-2)" }
                  }
                >
                  {BASEMAP_LABEL[mode]}
                </button>
              )
            })}
            {expandable ? (
              <button
                type="button"
                onClick={() => setExpanded((e) => !e)}
                className="cursor-pointer font-mono text-[9px] rounded px-2 py-[3px] border border-border-strong-2 text-fg-muted hover:text-fg-soft hover:border-[#39414f] transition-colors"
              >
                {expanded ? "COLLAPSE ✕" : "EXPAND →"}
              </button>
            ) : null}
            {headerRight}
          </div>
        </div>
      ) : null}

      {/* map viewport — explicit height so MapLibre never renders 0px tall.
          When expanded, fill the screen below the 54px header row. Blip
          markers attach to the map itself (auto-tracking); the readout is an
          absolutely-positioned overlay box. */}
      <div
        className="relative"
        style={{ height: expanded ? "calc(100vh - 54px)" : height }}
      >
        <div ref={mapContainer} className="absolute inset-0 w-full h-full" />
        {showOverlays && readout ? (
          <div className="absolute left-[13px] bottom-[13px] z-[1] font-mono text-[10px] leading-[1.7] text-fg-dim bg-[rgba(8,9,11,0.6)] px-[11px] py-2 border border-border rounded-md backdrop-blur-sm pointer-events-none">
            <div className="text-fg-soft">
              {readout.id}
              {readout.call ? ` · ${readout.call}` : ""}
            </div>
            {readout.coords ? <div>{readout.coords}</div> : null}
            {readout.headingDeg !== undefined || readout.speedMs !== undefined ? (
              <div>
                {readout.headingDeg !== undefined ? `HDG ${readout.headingDeg}°` : ""}
                {readout.headingDeg !== undefined && readout.speedMs !== undefined ? " · " : ""}
                {readout.speedMs !== undefined ? `${readout.speedMs} m/s` : ""}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  )
})
// ─── RANGER V3 END: FieldMap component ───