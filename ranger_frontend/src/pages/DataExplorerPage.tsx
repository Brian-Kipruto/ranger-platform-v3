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
import { Link } from "react-router-dom"
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
    <div className="min-h-screen p-6">
      <div className="max-w-[110rem] mx-auto">
        <header className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold">Data Explorer</h1>
            <p className="text-sm text-gray-500">
              {user?.organization?.name ?? "Organization"} sensor logs
            </p>
          </div>
          <Link to="/dashboard" className="text-sm underline text-gray-600 hover:text-gray-900">
            ← Dashboard
          </Link>
        </header>

        <div className="flex flex-wrap items-end gap-3 mb-4 p-4 border rounded-lg bg-gray-50 dark:bg-gray-900">
          <label className="flex flex-col text-xs gap-1">
            <span className="text-gray-600">Robot</span>
            <select
              value={robotId}
              onChange={(e) => setRobotId(e.target.value)}
              className="border rounded px-2 py-1.5 text-sm min-w-[12rem] bg-white dark:bg-gray-800"
            >
              <option value="">All robots</option>
              {robots.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} ({r.robot_id_str})
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col text-xs gap-1">
            <span className="text-gray-600">Mission</span>
            <select
              value={missionId}
              onChange={(e) => setMissionId(e.target.value)}
              className="border rounded px-2 py-1.5 text-sm min-w-[12rem] bg-white dark:bg-gray-800"
            >
              <option value="">All missions</option>
              {missions.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col text-xs gap-1">
            <span className="text-gray-600">From</span>
            <input
              type="date"
              value={dateStart}
              onChange={(e) => setDateStart(e.target.value)}
              className="border rounded px-2 py-1.5 text-sm bg-white dark:bg-gray-800"
            />
          </label>

          <label className="flex flex-col text-xs gap-1">
            <span className="text-gray-600">To</span>
            <input
              type="date"
              value={dateEnd}
              onChange={(e) => setDateEnd(e.target.value)}
              className="border rounded px-2 py-1.5 text-sm bg-white dark:bg-gray-800"
            />
          </label>

          <button
            onClick={handleFetch}
            disabled={loading}
            className="px-4 py-1.5 text-sm rounded text-white disabled:opacity-50"
            style={{ backgroundColor: accent }}
          >
            {loading ? "Loading…" : "Fetch Data"}
          </button>
          <button
            onClick={handleExport}
            disabled={exporting || totalCount === 0}
            className="px-4 py-1.5 text-sm rounded border disabled:opacity-50"
          >
            {exporting ? "Exporting…" : "Export CSV"}
          </button>
        </div>

        <div className="text-sm text-gray-600 mb-2">
          {error ? (
            <span className="text-red-600">{error}</span>
          ) : (
            <>
              {totalCount} record{totalCount === 1 ? "" : "s"}
              {isFiltered ? " (filtered)" : ""}
              {" · map shows the full filtered track; table is paginated"}
            </>
          )}
        </div>

        {/* Summary bar — stats over the full filtered set (from map-data) */}
        {!error && (radiationStat || pm25Stat) ? (
          <div className="flex flex-wrap gap-6 mb-3 p-3 border rounded-lg bg-gray-50 dark:bg-gray-900 text-sm">
            {radiationStat ? (
              <div>
                <span className="text-gray-500">Radiation (CPM): </span>
                <span>min {radiationStat.min.toFixed(1)}</span>
                {" · "}
                <span>max {radiationStat.max.toFixed(1)}</span>
                {" · "}
                <span>avg {radiationStat.avg.toFixed(1)}</span>
                <span className="text-gray-400"> (n={radiationStat.count})</span>
              </div>
            ) : null}
            {pm25Stat ? (
              <div>
                <span className="text-gray-500">PM2.5 (µg/m³): </span>
                <span>min {pm25Stat.min.toFixed(1)}</span>
                {" · "}
                <span>max {pm25Stat.max.toFixed(1)}</span>
                {" · "}
                <span>avg {pm25Stat.avg.toFixed(1)}</span>
                <span className="text-gray-400"> (n={pm25Stat.count})</span>
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="flex flex-col lg:flex-row gap-4">
          <div className="lg:w-1/2 flex flex-col min-w-0">
            <details className="mb-2 text-sm">
              <summary className="cursor-pointer text-gray-600 select-none">Columns</summary>
              <div className="flex flex-wrap gap-3 mt-2 p-3 border rounded bg-gray-50 dark:bg-gray-900">
                {allColumns.map((column) => (
                  <label key={column.id} className="flex items-center gap-1.5 text-xs">
                    <input
                      type="checkbox"
                      checked={column.getIsVisible()}
                      onChange={column.getToggleVisibilityHandler()}
                    />
                    {flexRender(column.columnDef.header, {} as never)}
                  </label>
                ))}
              </div>
            </details>

            <div className="border rounded-lg overflow-auto max-h-[70vh]">
              <table className="w-full text-sm">
                <thead className="bg-gray-100 dark:bg-gray-800 sticky top-0">
                  {table.getHeaderGroups().map((hg) => (
                    <tr key={hg.id}>
                      {hg.headers.map((header) => (
                        <th
                          key={header.id}
                          onClick={header.column.getToggleSortingHandler()}
                          className="px-3 py-2 text-left font-medium whitespace-nowrap cursor-pointer select-none hover:bg-gray-200 dark:hover:bg-gray-700"
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
                      <td colSpan={columns.length} className="px-3 py-8 text-center text-gray-400">
                        {loading ? "Loading…" : "No data. Adjust filters and Fetch Data."}
                      </td>
                    </tr>
                  ) : (
                    table.getRowModel().rows.map((row) => (
                      <tr
                        key={row.id}
                        onClick={() => handleRowClick(row.original)}
                        className="border-t cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50"
                      >
                        {row.getVisibleCells().map((cell) => (
                          <td key={cell.id} className="px-3 py-1.5 whitespace-nowrap">
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        ))}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex items-center gap-3 mt-3 text-sm">
              <button
                onClick={() => setPageIndex((i) => Math.max(0, i - 1))}
                disabled={pageIndex === 0 || loading}
                className="px-3 py-1 border rounded disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-gray-600">
                Page {pageIndex + 1} of {pageCount}
              </span>
              <button
                onClick={() => setPageIndex((i) => Math.min(pageCount - 1, i + 1))}
                disabled={pageIndex >= pageCount - 1 || loading}
                className="px-3 py-1 border rounded disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>

          <div className="lg:w-1/2 min-w-0">
            {MAP_STYLE ? (
              <div
                ref={mapContainer}
                className="w-full rounded-lg border"
                style={{ height: "70vh" }}
              />
            ) : (
              <div
                className="w-full rounded-lg border flex items-center justify-center text-center text-sm text-gray-500 p-6"
                style={{ height: "70vh" }}
              >
                Map unavailable: VITE_MAPTILER_KEY is not set in
                ranger_frontend/.env. Add it and restart the dev server.
              </div>
            )}
            <p
              className="mt-1 text-xs cursor-pointer text-gray-500 hover:text-gray-700"
              onClick={() => {
                highlightMarker.current?.remove()
                highlightMarker.current = null
              }}
            >
              Click a table row to fly here. (Clear highlight)
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
// ─── RANGER V3 END: data explorer page (CP4 — filters + table + map) ───