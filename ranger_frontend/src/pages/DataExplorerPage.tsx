// ─── RANGER V3 START: data explorer page (CP4 — filters + table + map) ───
/**
 * Data Explorer — filterable table + MapLibre map over the org's sensor logs.
 *
 * CP3 added filters + table. CP4 adds the map: it's fed by /api/map-data/
 * (the full filtered track as GeoJSON), DECOUPLED from table pagination — the
 * table shows 25 rows at a time, the map shows every filtered point. Clicking
 * a table row flies the map to that point and drops a highlight marker.
 * CP5 adds the summary bar + CSV export.
 *
 * MapLibre-in-React notes (the error-prone bits):
 *  - The map instance lives in a ref, never state — it isn't React-reactive.
 *  - Init runs once; React 19 StrictMode double-invokes effects in dev, so
 *    the init effect is guarded (map.current check) and cleaned up on unmount.
 *  - The container needs an explicit height or MapLibre renders 0px tall.
 *  - maplibre-gl.css MUST be imported or controls/markers render broken
 *    (this exact bug bit V2).
 *  - GeoJSON coordinates are [lng, lat] — verified backend-side in 05a.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
  type VisibilityState,
} from "@tanstack/react-table"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { useAuthStore } from "@/stores/authStore"
import { Panel } from "@/components/console/Panel"
import { MonoLabel } from "@/components/console/MonoLabel"
import { MetricTile } from "@/components/console/MetricTile"
import {
  getDataLogs,
  getMapData,
  getRobotOptions,
  getMissionOptions,
  exportCsv,
} from "@/api/dataLogs"
import type {
  DataLog,
  DataLogFilters,
  RobotOption,
  MissionOption,
} from "@/types/dataLog.types"

const EM_DASH = "—"
const fmtNum = (v: number | null, dp = 2): string =>
  v === null || v === undefined ? EM_DASH : v.toFixed(dp)
const fmtCoord = (v: number | null): string =>
  v === null || v === undefined ? EM_DASH : v.toFixed(5)
const fmtTime = (iso: string): string => {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

// ─── summary stats over the full filtered track ───
interface Stat {
  min: number
  max: number
  avg: number
  count: number
}
function computeStat(values: (number | null)[]): Stat | null {
  const nums = values.filter(
    (v): v is number => v !== null && v !== undefined && !Number.isNaN(v)
  )
  if (nums.length === 0) return null
  const sum = nums.reduce((a, b) => a + b, 0)
  return { min: Math.min(...nums), max: Math.max(...nums), avg: sum / nums.length, count: nums.length }
}

const col = createColumnHelper<DataLog>()
const columns = [
  col.accessor("timestamp", { header: "Timestamp", cell: (c) => fmtTime(c.getValue()) }),
  col.accessor("robot_id_str", { header: "Robot" }),
  col.accessor("mission_name", { header: "Mission", cell: (c) => c.getValue() ?? EM_DASH }),
  col.accessor("latitude", { header: "Lat", cell: (c) => fmtCoord(c.getValue()) }),
  col.accessor("longitude", { header: "Lon", cell: (c) => fmtCoord(c.getValue()) }),
  col.accessor("radiation_value", { header: "Radiation (CPM)", cell: (c) => fmtNum(c.getValue()) }),
  col.accessor("dose_rate_usvh", { header: "Dose (µSv/h)", cell: (c) => fmtNum(c.getValue(), 4) }),
  col.accessor("pm25", { header: "PM2.5", cell: (c) => fmtNum(c.getValue()) }),
  col.accessor("pm10", { header: "PM10", cell: (c) => fmtNum(c.getValue()) }),
  col.accessor("roll", { header: "Roll", cell: (c) => fmtNum(c.getValue()) }),
  col.accessor("pitch", { header: "Pitch", cell: (c) => fmtNum(c.getValue()) }),
  col.accessor("yaw", { header: "Yaw", cell: (c) => fmtNum(c.getValue()) }),
  col.accessor("pressure_baro", { header: "Pressure (hPa)", cell: (c) => fmtNum(c.getValue()) }),
  col.accessor("altitude_baro", { header: "Altitude (m)", cell: (c) => fmtNum(c.getValue()) }),
]

const PAGE_SIZE = 25
const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY as string | undefined
const MAP_STYLE = MAPTILER_KEY
  ? `https://api.maptiler.com/maps/streets-v2/style.json?key=${MAPTILER_KEY}`
  : null
const NAIROBI: [number, number] = [36.8219, -1.2921]

export default function DataExplorerPage() {
  const user = useAuthStore((s) => s.user)
  const accent = user?.organization?.theme_color ?? "#0ea5e9"

  const [robotId, setRobotId] = useState<string>("")
  const [missionId, setMissionId] = useState<string>("")
  const [dateStart, setDateStart] = useState<string>("")
  const [dateEnd, setDateEnd] = useState<string>("")
  const [appliedFilters, setAppliedFilters] = useState<DataLogFilters>({})

  const [robots, setRobots] = useState<RobotOption[]>([])
  const [missions, setMissions] = useState<MissionOption[]>([])

  const [rows, setRows] = useState<DataLog[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [pageIndex, setPageIndex] = useState(0)
  const [sorting, setSorting] = useState<SortingState>([])
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const pageCount = Math.max(1, Math.ceil(totalCount / PAGE_SIZE))

  const mapContainer = useRef<HTMLDivElement | null>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const highlightMarker = useRef<maplibregl.Marker | null>(null)
  const [mapReady, setMapReady] = useState(false)
  const pendingTrack = useRef<import("@/types/dataLog.types").MapFeatureCollection | null>(null)
  // Reactive copy of the track for the summary bar (refs don't trigger re-render).
  const [trackFc, setTrackFc] = useState<import("@/types/dataLog.types").MapFeatureCollection | null>(null)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([getRobotOptions(), getMissionOptions()])
      .then(([r, m]) => {
        if (!cancelled) {
          setRobots(r)
          setMissions(m)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!mapContainer.current || map.current || !MAP_STYLE) return

    const m = new maplibregl.Map({
      container: mapContainer.current,
      style: MAP_STYLE,
      center: NAIROBI,
      zoom: 13,
    })
    m.addControl(new maplibregl.NavigationControl(), "top-right")
    m.addControl(new maplibregl.ScaleControl(), "bottom-left")

    m.on("load", () => {
      m.addSource("track", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      })
      m.addLayer({
        id: "track-points",
        type: "circle",
        source: "track",
        paint: {
          "circle-radius": 4,
          "circle-color": accent,
          "circle-stroke-width": 1,
          "circle-stroke-color": "#ffffff",
          "circle-opacity": 0.8,
        },
      })
      setMapReady(true)
      // If a track fetch landed before the map finished loading, apply it now.
      if (pendingTrack.current) {
        const src = m.getSource("track") as maplibregl.GeoJSONSource | undefined
        if (src) src.setData(pendingTrack.current)
      }
    })

    map.current = m
    return () => {
      m.remove()
      map.current = null
      setMapReady(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const fetchPage = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getDataLogs(appliedFilters, pageIndex + 1, PAGE_SIZE)
      setRows(data.results)
      setTotalCount(data.count)
    } catch {
      setError("Failed to load data. Check that you're logged in and the backend is running.")
      setRows([])
      setTotalCount(0)
    } finally {
      setLoading(false)
    }
  }, [appliedFilters, pageIndex])

  useEffect(() => {
    fetchPage()
  }, [fetchPage])

  useEffect(() => {
    let cancelled = false
    getMapData(appliedFilters)
      .then((fc) => {
        if (cancelled) return
        // Stash the latest track so the load handler can apply it if the
        // map wasn't ready when this fetch resolved.
        pendingTrack.current = fc
        setTrackFc(fc) // reactive copy for the summary bar
        const src = map.current?.getSource("track") as
          | maplibregl.GeoJSONSource
          | undefined
        if (src) {
          src.setData(fc)
          if (fc.features.length > 0) {
            const b = new maplibregl.LngLatBounds()
            for (const f of fc.features) {
              b.extend(f.geometry.coordinates)
            }
            map.current?.fitBounds(b, { padding: 40, maxZoom: 16, duration: 600 })
          }
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
    // mapReady in deps: when the map finishes loading AFTER this effect first
    // ran, this re-runs and applies the data to the now-existing source.
  }, [appliedFilters, mapReady])

  const handleFetch = () => {
    setPageIndex(0)
    setAppliedFilters({
      robot_id: robotId || undefined,
      mission_id: missionId || undefined,
      date_start: dateStart || undefined,
      date_end: dateEnd || undefined,
    })
  }

  const handleRowClick = useCallback((row: DataLog) => {
    if (!map.current) return
    const lngLat: [number, number] = [row.longitude, row.latitude]
    map.current.flyTo({ center: lngLat, zoom: 17, duration: 800 })
    if (highlightMarker.current) {
      highlightMarker.current.setLngLat(lngLat)
    } else {
      highlightMarker.current = new maplibregl.Marker({ color: "#facc15" })
        .setLngLat(lngLat)
        .addTo(map.current)
    }
  }, [])

  const handleExport = async () => {
    setExporting(true)
    try {
      await exportCsv(appliedFilters)
    } catch {
      setError("Export failed. Check that you're logged in and the backend is running.")
    } finally {
      setExporting(false)
    }
  }

  const radiationStat = useMemo(
    () => computeStat((trackFc?.features ?? []).map((f) => f.properties.radiation_value)),
    [trackFc]
  )
  const pm25Stat = useMemo(
    () => computeStat((trackFc?.features ?? []).map((f) => f.properties.pm25)),
    [trackFc]
  )

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting, columnVisibility },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualPagination: true,
    pageCount,
  })

  const allColumns = useMemo(() => table.getAllLeafColumns(), [table])
  const isFiltered = !!(
    appliedFilters.robot_id ||
    appliedFilters.mission_id ||
    appliedFilters.date_start ||
    appliedFilters.date_end
  )

  return (
    <div className="p-[18px]">
      {/* ── filter bar: robot/mission/date selects + fetch + export ── */}
      <Panel noHeader className="mb-3">
        <div className="flex flex-wrap items-end gap-3 p-[14px]">
          <label className="flex flex-col gap-1">
            <MonoLabel size="xs" tone="dim" tracking="0.12em">Robot</MonoLabel>
            <select
              value={robotId}
              onChange={(e) => setRobotId(e.target.value)}
              className="bg-surface-input border border-border-strong rounded-md px-2.5 py-1.5 text-[12px] text-fg-soft min-w-[12rem] outline-none focus:border-[var(--accent)] transition-colors"
            >
              <option value="">All robots</option>
              {robots.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} ({r.robot_id_str})
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <MonoLabel size="xs" tone="dim" tracking="0.12em">Mission</MonoLabel>
            <select
              value={missionId}
              onChange={(e) => setMissionId(e.target.value)}
              className="bg-surface-input border border-border-strong rounded-md px-2.5 py-1.5 text-[12px] text-fg-soft min-w-[12rem] outline-none focus:border-[var(--accent)] transition-colors"
            >
              <option value="">All missions</option>
              {missions.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <MonoLabel size="xs" tone="dim" tracking="0.12em">From</MonoLabel>
            <input
              type="date"
              value={dateStart}
              onChange={(e) => setDateStart(e.target.value)}
              className="bg-surface-input border border-border-strong rounded-md px-2.5 py-1.5 text-[12px] text-fg-soft outline-none focus:border-[var(--accent)] transition-colors [color-scheme:dark]"
            />
          </label>

          <label className="flex flex-col gap-1">
            <MonoLabel size="xs" tone="dim" tracking="0.12em">To</MonoLabel>
            <input
              type="date"
              value={dateEnd}
              onChange={(e) => setDateEnd(e.target.value)}
              className="bg-surface-input border border-border-strong rounded-md px-2.5 py-1.5 text-[12px] text-fg-soft outline-none focus:border-[var(--accent)] transition-colors [color-scheme:dark]"
            />
          </label>

          <button
            onClick={handleFetch}
            disabled={loading}
            className="font-mono text-[10px] tracking-[0.1em] text-white px-4 py-2 rounded-md disabled:opacity-50 transition-opacity"
            style={{ background: "var(--accent)" }}
          >
            {loading ? "LOADING…" : "↻ FETCH DATA"}
          </button>
          <button
            onClick={handleExport}
            disabled={exporting || totalCount === 0}
            className="font-mono text-[10px] tracking-[0.1em] font-semibold text-[#0a0d12] bg-ok px-4 py-2 rounded-md disabled:opacity-40 transition-opacity"
          >
            {exporting ? "EXPORTING…" : "↓ EXPORT CSV"}
          </button>
        </div>
      </Panel>

      {/* ── status line ── */}
      <div className="mb-3 font-mono text-[10px] tracking-[0.06em]">
        {error ? (
          <span className="text-alert">{error}</span>
        ) : (
          <span className="text-fg-dim">
            {totalCount} RECORD{totalCount === 1 ? "" : "S"}
            {isFiltered ? " · FILTERED" : ""}
            {" · MAP SHOWS FULL TRACK · TABLE PAGINATED"}
          </span>
        )}
      </div>

      {/* ── summary metric tiles (full filtered set) ── */}
      {!error && (radiationStat || pm25Stat) ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
          {radiationStat ? (
            <MetricTile
              label="RADIATION"
              value={radiationStat.avg.toFixed(1)}
              unit="CPM avg"
              sub={`min ${radiationStat.min.toFixed(1)} · max ${radiationStat.max.toFixed(1)} · n=${radiationStat.count}`}
            />
          ) : null}
          {pm25Stat ? (
            <MetricTile
              label="PM2.5"
              value={pm25Stat.avg.toFixed(1)}
              unit="µg/m³ avg"
              bar="var(--color-warn)"
              sub={`min ${pm25Stat.min.toFixed(1)} · max ${pm25Stat.max.toFixed(1)} · n=${pm25Stat.count}`}
            />
          ) : null}
        </div>
      ) : null}

      {/* ── table + map ── */}
      <div className="flex flex-col lg:flex-row gap-3">
        {/* TABLE PANEL */}
        <div className="lg:w-1/2 flex flex-col min-w-0">
          <Panel
            title="SENSOR LOGS"
            right={
              <details className="relative">
                <summary className="cursor-pointer list-none font-mono text-[9px] tracking-[0.1em] text-fg-dim hover:text-fg-soft select-none">
                  COLUMNS ▾
                </summary>
                <div className="absolute right-0 z-10 mt-2 w-[260px] flex flex-wrap gap-2.5 p-3 bg-surface-panel border border-border-strong rounded-lg shadow-xl">
                  {allColumns.map((column) => (
                    <label key={column.id} className="flex items-center gap-1.5 font-mono text-[10px] text-fg-muted">
                      <input
                        type="checkbox"
                        checked={column.getIsVisible()}
                        onChange={column.getToggleVisibilityHandler()}
                        className="accent-[var(--accent)]"
                      />
                      {flexRender(column.columnDef.header, {} as never)}
                    </label>
                  ))}
                </div>
              </details>
            }
            bodyClassName="overflow-auto max-h-[68vh]"
          >
            <table className="w-full">
              <thead className="bg-surface-3 sticky top-0 z-[1]">
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {hg.headers.map((header) => (
                      <th
                        key={header.id}
                        onClick={header.column.getToggleSortingHandler()}
                        className="px-3 py-2.5 text-left font-mono text-[9px] tracking-[0.1em] uppercase text-fg-dim whitespace-nowrap cursor-pointer select-none hover:text-fg-soft border-b border-border"
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {{ asc: " ▲", desc: " ▼" }[header.column.getIsSorted() as string] ?? ""}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.length === 0 ? (
                  <tr>
                    <td colSpan={columns.length} className="px-3 py-10 text-center font-mono text-[11px] text-fg-faint">
                      {loading ? "LOADING…" : "NO DATA · ADJUST FILTERS AND FETCH"}
                    </td>
                  </tr>
                ) : (
                  table.getRowModel().rows.map((row) => (
                    <tr
                      key={row.id}
                      onClick={() => handleRowClick(row.original)}
                      className="cursor-pointer border-b border-border-soft hover:bg-surface-3 transition-colors"
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="px-3 py-2 font-mono text-[11px] text-fg-soft whitespace-nowrap">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </Panel>

          {/* pagination */}
          <div className="flex items-center gap-3 mt-3">
            <button
              onClick={() => setPageIndex((i) => Math.max(0, i - 1))}
              disabled={pageIndex === 0 || loading}
              className="font-mono text-[10px] tracking-[0.08em] text-fg-muted bg-surface-3 border border-border-strong px-3 py-1.5 rounded-md disabled:opacity-40 hover:border-border-strong-2 transition-colors"
            >
              ← PREV
            </button>
            <MonoLabel size="sm" tone="dim" tracking="0.08em">
              PAGE {pageIndex + 1} / {pageCount}
            </MonoLabel>
            <button
              onClick={() => setPageIndex((i) => Math.min(pageCount - 1, i + 1))}
              disabled={pageIndex >= pageCount - 1 || loading}
              className="font-mono text-[10px] tracking-[0.08em] text-fg-muted bg-surface-3 border border-border-strong px-3 py-1.5 rounded-md disabled:opacity-40 hover:border-border-strong-2 transition-colors"
            >
              NEXT →
            </button>
          </div>
        </div>

        {/* MAP PANEL */}
        <div className="lg:w-1/2 min-w-0">
          <Panel
            title="FIELD MAP"
            right={<MonoLabel size="xs" tone="accent">FILTERED TRACK</MonoLabel>}
            bodyClassName="relative"
          >
            {MAP_STYLE ? (
              <div ref={mapContainer} className="w-full" style={{ height: "68vh" }} />
            ) : (
              <div
                className="w-full flex items-center justify-center text-center font-mono text-[11px] text-fg-dim p-6"
                style={{ height: "68vh" }}
              >
                MAP UNAVAILABLE · VITE_MAPTILER_KEY NOT SET IN ranger_frontend/.env ·
                ADD IT AND RESTART THE DEV SERVER
              </div>
            )}
          </Panel>
          <p
            className="mt-2 font-mono text-[10px] text-fg-faint cursor-pointer hover:text-fg-dim transition-colors"
            onClick={() => {
              highlightMarker.current?.remove()
              highlightMarker.current = null
            }}
          >
            CLICK A ROW TO FLY THERE · (CLEAR HIGHLIGHT)
          </p>
        </div>
      </div>
    </div>
  )
}
// ─── RANGER V3 END: data explorer page (CP4 — filters + table + map) ───