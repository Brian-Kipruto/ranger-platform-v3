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
import { useAuthStore } from "@/stores/authStore"
import { Panel } from "@/components/console/Panel"
import { MonoLabel } from "@/components/console/MonoLabel"
import { MetricTile } from "@/components/console/MetricTile"
import { SourceChip } from "@/components/console/SourceChip"
import { FieldMap, type FieldMapHandle } from "@/components/map/FieldMap"
import {
  getDataLogs,
  getMapData,
  getFilterOptions,
  exportCsv,
} from "@/api/dataLogs"
import {
  MEASURED_SOURCES,
  SOURCE_META,
  type DataSource,
  type DataLog,
  type DataLogFilters,
  type RobotOption,
  type MissionOption,
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
  // THIRD, deliberately: the eye reaches the provenance tier before it
  // reaches any instrument name, mission name or dose value. A source column
  // parked at the far right after fourteen others is a column nobody scrolls
  // to, which is the same as not having one.
  col.accessor("source", {
    header: "Source",
    cell: (c) => (
      <SourceChip source={c.getValue()} note={c.row.original.provenance_note} />
    ),
  }),
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

  // FieldMap owns the MapLibre instance now. The page keeps an imperative
  // handle (row-click flyTo + highlight) and a reactive copy of the track for
  // the summary tiles (refs don't trigger re-render).
  const fieldMap = useRef<FieldMapHandle | null>(null)
  const [trackFc, setTrackFc] = useState<import("@/types/dataLog.types").MapFeatureCollection | null>(null)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    let cancelled = false
    // ONE call, not two. Each of the old getRobotOptions/getMissionOptions
    // pulled the full unpaginated chart-data feed independently; at 12,081
    // Marsabit points (capped at MAX_CHART_POINTS=5000) that was 10,000 rows
    // over the wire to populate two dropdowns, before /map-data/ fetched
    // another 5,000. Invisible at 435 Nairobi points, not invisible on
    // conference wifi. The real fix is /api/robots/ + /api/missions/.
    getFilterOptions()
      .then(({ robots: r, missions: m }) => {
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
        // FieldMap consumes trackFc via props (setData + fitBounds happen
        // inside the component). The page keeps trackFc only for the summary.
        setTrackFc(fc)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [appliedFilters])

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
    fieldMap.current?.flyTo(row.longitude, row.latitude, 17)
    fieldMap.current?.setHighlight(row.longitude, row.latitude)
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

  /**
   * Provenance banner over the FULL filtered set (trackFc), not the current
   * page. Paging to row 26 must not change what the screen claims about the
   * data.
   *
   * Rules, in order:
   *   - every point one non-measured tier -> name that tier, cite the note
   *   - a mix including non-measured      -> say mixed, give the count
   *   - everything measured               -> no banner; the default is honest
   */
  const provenanceBanner = useMemo(() => {
    const prov = trackFc?.provenance
    if (!prov || prov.total === 0) return null

    const tiers = Object.keys(prov.by_source) as DataSource[]
    const nonMeasured = tiers.filter((t) => !MEASURED_SOURCES.includes(t))
    if (nonMeasured.length === 0) return null

    const nonMeasuredCount = nonMeasured.reduce(
      (sum, t) => sum + (prov.by_source[t] ?? 0),
      0
    )

    // The citation. One distinct note -> quote it. Several -> do NOT pick
    // one: a banner quoting Boji's n and mean over a set that is mostly
    // Dukana is a WRONG citation, and a wrong citation reads as
    // authoritative right up until someone opens Table 3.1. Name the shared
    // document instead and point at the per-row chips, which are correct.
    const note =
      prov.notes.length === 1
        ? prov.notes[0]
        : prov.notes.length > 1
          ? `${prov.notes.length}${prov.notes_truncated ? "+" : ""} distinct ` +
            `citations across this set — hover a SOURCE chip for the ` +
            `per-row provenance.`
          : ""

    if (tiers.length === 1) {
      const meta = SOURCE_META[tiers[0]] ?? SOURCE_META.simulated
      return {
        color: meta.color,
        headline:
          `ALL ${prov.total.toLocaleString()} POINTS IN THIS SET ARE ` +
          `${meta.label.toUpperCase()} — NOT MEASUREMENTS`,
        note,
      }
    }
    return {
      color: SOURCE_META.modelled.color,
      headline:
        `MIXED PROVENANCE — ${nonMeasuredCount.toLocaleString()} OF ` +
        `${prov.total.toLocaleString()} POINTS ARE NOT MEASUREMENTS`,
      note: note || "See the SOURCE column and the marker colours.",
    }
  }, [trackFc])

  /** Tiers actually present in the filtered track, for the map legend. */
  const presentSources = useMemo(() => {
    // From the uncapped summary when available: a tier present in the set but
    // absent from the 5,000 drawn points still belongs in the key.
    const seen = new Set<DataSource>(
      trackFc?.provenance
        ? (Object.keys(trackFc.provenance.by_source) as DataSource[])
        : (trackFc?.features ?? []).map((f) => f.properties.source)
    )
    // Fixed order (most to least authoritative), not Set insertion order,
    // so the legend does not reshuffle between fetches.
    return (["live", "reported", "modelled", "simulated"] as const).filter((s) =>
      seen.has(s)
    )
  }, [trackFc])

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
            {trackFc?.provenance?.truncated
              ? ` · MAP SHOWS ${trackFc.provenance.returned.toLocaleString()} OF ` +
                `${trackFc.provenance.total.toLocaleString()} · TABLE PAGINATED`
              : " · MAP SHOWS FULL TRACK · TABLE PAGINATED"}
          </span>
        )}
      </div>

      {/* ── provenance banner (full filtered set, not the current page) ── */}
      {!error && provenanceBanner ? (
        <div
          className="mb-3 px-3 py-2.5 rounded-md border"
          style={{
            borderColor: `${provenanceBanner.color}55`,
            background: `${provenanceBanner.color}12`,
          }}
        >
          <div
            className="font-mono text-[10px] tracking-[0.08em] leading-[1.5]"
            style={{ color: provenanceBanner.color }}
          >
            ⚠ {provenanceBanner.headline}
          </div>
          {provenanceBanner.note ? (
            <div className="mt-1.5 font-mono text-[9.5px] leading-[1.6] text-fg-dim">
              {provenanceBanner.note}
            </div>
          ) : null}
        </div>
      ) : null}

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

        {/* MAP PANEL — now the shared FieldMap (basemap toggle comes free) */}
        <div className="lg:w-1/2 min-w-0">
          <FieldMap
            ref={fieldMap}
            accent={accent}
            track={trackFc}
            fitToTrack
            headerTitle="FIELD MAP"
            headerRight={
              // Markers are coloured by provenance (F10.3 CP0), so the map
              // needs a key. Only the tiers actually present are shown —
              // a legend listing four tiers over a single-tier set implies
              // a variety the data does not have.
              <div className="flex items-center gap-2.5">
                {presentSources.map((src) => (
                  <span
                    key={src}
                    className="flex items-center gap-1 font-mono text-[8.5px] tracking-[0.06em]"
                    style={{ color: SOURCE_META[src].color }}
                    title={SOURCE_META[src].label}
                  >
                    <span
                      className="w-[6px] h-[6px] rounded-full"
                      style={{ background: SOURCE_META[src].color }}
                    />
                    {SOURCE_META[src].short}
                  </span>
                ))}
              </div>
            }
            height="68vh"
          />
          <p
            className="mt-2 font-mono text-[10px] text-fg-faint cursor-pointer hover:text-fg-dim transition-colors"
            onClick={() => fieldMap.current?.clearHighlight()}
          >
            CLICK A ROW TO FLY THERE · (CLEAR HIGHLIGHT)
          </p>
        </div>
      </div>
    </div>
  )
}
// ─── RANGER V3 END: data explorer page (CP4 — filters + table + map) ───