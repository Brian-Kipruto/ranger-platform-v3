// ─── RANGER V3 START: visualizations page ───
/**
 * Visualizations — four time-series charts over the org's sensor logs,
 * fed by /api/chart-data/ (unpaginated, ascending, point-capped — verified
 * in 05a). Recharts 3.x.
 *
 * Charts: Radiation, Air Quality (PM2.5 + PM10), IMU Orientation (roll +
 * pitch), Barometer (pressure + altitude, dual Y-axis). The IMU and
 * Barometer charts are EMPTY for the seed robot (no imu_baro sensor) — they
 * render a "no data for this sensor" state rather than a blank axis. When a
 * robot with those sensors logs data, they populate automatically.
 *
 * Reference lines on Radiation and Air Quality are ILLUSTRATIVE EXAMPLES,
 * clearly labelled — not regulatory thresholds. Real, sourced, configurable
 * thresholds belong to the future Alerts feature.
 *
 * 18-polish: retrofitted to the Field Console (it predated F06): Panels on the
 * console surfaces, mono labels, the Data Explorer's filter bar, dark-themed
 * Recharts, no page <h1> or back link (the TopBar and NavRail own those).
 * The point count now says when the 5,000-point chart cap is hiding rows.
 */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import { Panel } from "@/components/console/Panel" // 18-polish
import { MonoLabel } from "@/components/console/MonoLabel" // 18-polish
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from "recharts"
import { useAuthStore } from "@/stores/authStore"
import { getChartData, getDataLogs, getFilterOptions } from "@/api/dataLogs"
import type { DataLog, DataSource, RobotOption } from "@/types/dataLog.types"
import { sourceBreakdown } from "@/lib/readingProvenance" // 13

// Illustrative example thresholds — NOT regulatory limits. See file header.
const EXAMPLE_RADIATION_THRESHOLD = 100 // CPM
const EXAMPLE_PM25_THRESHOLD = 35 // µg/m³

interface ChartRow extends DataLog {
  timestamp_ms: number
}

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

// 18-polish: date ticks for multi-day spans (see xAxis in the page).
const fmtDateTick = (ms: number): string => {
  const d = new Date(ms)
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString([], { day: "2-digit", month: "short" })
}
const fmtTick = (ms: number): string => {
  const d = new Date(ms)
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}
const fmtTooltipLabel = (ms: number): string => {
  const d = new Date(ms)
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString()
}

// ─── RANGER V3 START: 18-polish ───
// Recharts draws SVG presentation attributes, which do not resolve CSS
// variables — so the console tokens are repeated here as hex (index.css).
const T = {
  grid: "#262c36", // --color-border-strong
  tick: "#7a828f", // --color-fg-dim
  panel: "#111419", // --color-surface-panel
  fg: "#cdd2da", // --color-fg-soft
  alert: "#ff5d5d", // --color-alert
  second: "#f5a623", // --color-warn: the second series on a chart
}
const TICK = { fontSize: 10, fill: T.tick, fontFamily: "IBM Plex Mono, monospace" }
const TOOLTIP_PROPS = {
  contentStyle: { background: T.panel, border: `1px solid ${T.grid}`, borderRadius: 6, fontSize: 11 },
  labelStyle: { color: T.fg },
  itemStyle: { color: T.fg },
}
const LEGEND_PROPS = { wrapperStyle: { fontSize: 10, color: T.tick } }

function StatLine({ label, stat, unit, mix }: { label: string; stat: Stat | null; unit: string; mix?: string }) {
  if (!stat) return null
  // 13-reading-source: `mix` = the readings' own sources ("SIM 774 · MOD 10").
  // These charts had no provenance at all; an avg over modelled and simulated
  // values must at least say what it averages.
  return (
    <div className="font-mono text-[10px] text-fg-dim">
      {label}: min {stat.min.toFixed(1)} · max {stat.max.toFixed(1)} · avg {stat.avg.toFixed(1)} {unit}{" "}
      <span className="text-fg-faint">(n={stat.count}{mix ? ` · ${mix}` : ""})</span>
    </div>
  )
}

function EmptyChart({ message }: { message: string }) {
  return (
    <div
      className="w-full flex items-center justify-center text-center font-mono text-[10px] text-fg-faint border border-dashed border-border-strong rounded-md px-4"
      style={{ height: 260 }}
    >
      {message}
    </div>
  )
}

/** One chart panel: title, note, stat lines, then the chart or its empty state. */
function ChartPanel({ title, note, stats, children }: {
  title: string
  note: string
  stats: ReactNode
  children: ReactNode
}) {
  return (
    <Panel title={title}>
      <div className="p-[13px] flex flex-col gap-2">
        <p className="font-mono text-[10px] text-fg-faint leading-[1.6]">{note}</p>
        <div className="flex flex-col gap-0.5 min-h-[14px]">{stats}</div>
        {children}
      </div>
    </Panel>
  )
}
// ─── RANGER V3 END: 18-polish ───

const X_AXIS_PROPS = {
  dataKey: "timestamp_ms",
  type: "number" as const,
  scale: "time" as const,
  domain: ["dataMin", "dataMax"] as [string, string],
  tickFormatter: fmtTick,
  tick: TICK, // 18-polish
  stroke: T.grid, // 18-polish
}

export default function VisualizationsPage() {
  const user = useAuthStore((s) => s.user)
  const accent = user?.organization?.theme_color ?? "#0ea5e9"

  const [robotId, setRobotId] = useState<string>("")
  const [dateStart, setDateStart] = useState<string>("")
  const [dateEnd, setDateEnd] = useState<string>("")
  const [robots, setRobots] = useState<RobotOption[]>([])
  const [data, setData] = useState<ChartRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasFetched, setHasFetched] = useState(false)
  // 18-polish: the true row count for the same filters, so a capped chart
  // pull can say what it is not showing.
  const [total, setTotal] = useState<number | null>(null)
  const [optionsFailed, setOptionsFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    getFilterOptions() // 18-polish: one pull, not the deprecated wrapper
      .then(({ robots: r }) => {
        if (!cancelled) setRobots(r)
      })
      .catch(() => {
        if (!cancelled) setOptionsFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const filters = {
        robot_id: robotId || undefined,
        date_start: dateStart || undefined,
        date_end: dateEnd || undefined,
      }
      const [rows, page] = await Promise.all([getChartData(filters), getDataLogs(filters, 1, 1)])
      setTotal(page.count)
      const mapped: ChartRow[] = rows
        .map((r) => ({ ...r, timestamp_ms: new Date(r.timestamp).getTime() }))
        .filter((r) => !Number.isNaN(r.timestamp_ms))
      setData(mapped)
      setHasFetched(true)
    } catch {
      setError("Failed to load chart data. Check that you're logged in and the backend is running.")
      setData([])
      setTotal(null)
    } finally {
      setLoading(false)
    }
  }, [robotId, dateStart, dateEnd])

  // Fetch once on mount (default: all robots, no date filter).
  useEffect(() => {
    fetchData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ─── per-series stats ───
  const stats = useMemo(
    () => ({
      radiation: computeStat(data.map((d) => d.radiation_value)),
      pm25: computeStat(data.map((d) => d.pm25)),
      pm10: computeStat(data.map((d) => d.pm10)),
      roll: computeStat(data.map((d) => d.roll)),
      pitch: computeStat(data.map((d) => d.pitch)),
      pressure: computeStat(data.map((d) => d.pressure_baro)),
      altitude: computeStat(data.map((d) => d.altitude_baro)),
    }),
    [data]
  )

  // ─── RANGER V3 START: 13-reading-source ───
  const mix = useMemo(() => {
    const of = (pick: (d: DataLog) => number | null, src: (d: DataLog) => DataSource | null) =>
      sourceBreakdown(data.filter((d) => pick(d) !== null).map(src))
    return {
      radiation: of((d) => d.radiation_value, (d) => d.radiation_source),
      pm25: of((d) => d.pm25, (d) => d.air_quality_source),
      pm10: of((d) => d.pm10, (d) => d.air_quality_source),
      roll: of((d) => d.roll, (d) => d.imu_source),
      pitch: of((d) => d.pitch, (d) => d.imu_source),
      pressure: of((d) => d.pressure_baro, (d) => d.imu_source),
      altitude: of((d) => d.altitude_baro, (d) => d.imu_source),
    }
  }, [data])
  // ─── RANGER V3 END: 13-reading-source ───

  const hasRadiation = stats.radiation !== null
  const hasAir = stats.pm25 !== null || stats.pm10 !== null
  const hasImu = stats.roll !== null || stats.pitch !== null
  const hasBaro = stats.pressure !== null || stats.altitude !== null

  // ─── RANGER V3 START: 18-polish ───
  const capped = total !== null && total > data.length
  const margin = { top: 8, right: 24, bottom: 4, left: -8 }
  // A clock-only tick repeats across days and reads as time running
  // backwards (11:37 then 11:21). Past ~1.5 days of span, label by date.
  const spanMs = data.length > 1 ? data[data.length - 1].timestamp_ms - data[0].timestamp_ms : 0
  const xAxis = { ...X_AXIS_PROPS, tickFormatter: spanMs > 36 * 3600 * 1000 ? fmtDateTick : fmtTick }

  return (
    <div className="p-[18px]">
      {/* filter bar — same controls as the Data Explorer */}
      <Panel noHeader className="mb-3">
        <div className="flex flex-wrap items-end gap-3 p-[14px]">
          <label className="flex flex-col gap-1">
            <MonoLabel size="xs" tone="dim" tracking="0.12em">Robot</MonoLabel>
            <select
              value={robotId}
              onChange={(e) => setRobotId(e.target.value)}
              className="bg-surface-input border border-border-strong rounded-md px-2.5 py-1.5 text-[12px] text-fg-soft outline-none focus:border-[var(--accent)] transition-colors min-w-[12rem]"
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
            onClick={fetchData}
            disabled={loading}
            className="font-mono text-[10px] tracking-[0.1em] text-white px-4 py-2 rounded-md disabled:opacity-50 transition-opacity"
            style={{ background: "var(--accent)" }}
          >
            {loading ? "LOADING…" : "↻ FETCH DATA"}
          </button>
        </div>
      </Panel>

      {/* status line — says when the chart cap hides rows */}
      <div className="mb-3 font-mono text-[10px] tracking-[0.06em]">
        {error ? (
          <span className="text-alert">{error}</span>
        ) : (
          <span className="text-fg-dim">
            {loading && !hasFetched
              ? "LOADING…"
              : capped
                ? `CHARTING MOST RECENT ${data.length.toLocaleString()} OF ${(total ?? 0).toLocaleString()} POINTS · NARROW THE DATES TO SEE EARLIER DATA`
                : `${data.length.toLocaleString()} POINT${data.length === 1 ? "" : "S"}`}
            {hasFetched && !loading && data.length === 0 ? " · ADJUST FILTERS AND FETCH" : ""}
            {optionsFailed ? " · ROBOT LIST FAILED TO LOAD" : ""}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-[14px]">
        <ChartPanel
          title="RADIATION"
          note="Counts per minute (CPM) over time. The dashed line is an example threshold, not a regulatory limit."
          stats={<StatLine label="Radiation" stat={stats.radiation} unit="CPM" mix={mix.radiation} />}
        >
          {hasRadiation ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={data} margin={margin}>
                <CartesianGrid stroke={T.grid} strokeDasharray="3 3" />
                <XAxis {...xAxis} />
                <YAxis tick={TICK} stroke={T.grid} />
                <Tooltip {...TOOLTIP_PROPS} labelFormatter={(l) => fmtTooltipLabel(l as number)} />
                <Legend {...LEGEND_PROPS} />
                <ReferenceLine
                  y={EXAMPLE_RADIATION_THRESHOLD}
                  stroke={T.alert}
                  strokeDasharray="6 4"
                  label={{ value: "example threshold", fontSize: 10, fill: T.alert, position: "insideTopRight" }}
                />
                <Line type="monotone" dataKey="radiation_value" name="Radiation (CPM)" stroke={accent} dot={false} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart message="NO RADIATION DATA FOR THIS SELECTION" />
          )}
        </ChartPanel>

        <ChartPanel
          title="AIR QUALITY"
          note="Particulate matter (µg/m³) over time. The dashed line is an example PM2.5 threshold, not a regulatory limit."
          stats={
            <>
              <StatLine label="PM2.5" stat={stats.pm25} unit="µg/m³" mix={mix.pm25} />
              <StatLine label="PM10" stat={stats.pm10} unit="µg/m³" mix={mix.pm10} />
            </>
          }
        >
          {hasAir ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={data} margin={margin}>
                <CartesianGrid stroke={T.grid} strokeDasharray="3 3" />
                <XAxis {...xAxis} />
                <YAxis tick={TICK} stroke={T.grid} />
                <Tooltip {...TOOLTIP_PROPS} labelFormatter={(l) => fmtTooltipLabel(l as number)} />
                <Legend {...LEGEND_PROPS} />
                <ReferenceLine
                  y={EXAMPLE_PM25_THRESHOLD}
                  stroke={T.alert}
                  strokeDasharray="6 4"
                  label={{ value: "example PM2.5 threshold", fontSize: 10, fill: T.alert, position: "insideTopRight" }}
                />
                <Line type="monotone" dataKey="pm25" name="PM2.5" stroke={accent} dot={false} connectNulls={false} />
                <Line type="monotone" dataKey="pm10" name="PM10" stroke={T.second} dot={false} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart message="NO AIR-QUALITY DATA FOR THIS SELECTION" />
          )}
        </ChartPanel>

        <ChartPanel
          title="IMU ORIENTATION"
          note="Roll and pitch (degrees) over time."
          stats={
            <>
              <StatLine label="Roll" stat={stats.roll} unit="°" mix={mix.roll} />
              <StatLine label="Pitch" stat={stats.pitch} unit="°" mix={mix.pitch} />
            </>
          }
        >
          {hasImu ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={data} margin={margin}>
                <CartesianGrid stroke={T.grid} strokeDasharray="3 3" />
                <XAxis {...xAxis} />
                <YAxis tick={TICK} stroke={T.grid} />
                <Tooltip {...TOOLTIP_PROPS} labelFormatter={(l) => fmtTooltipLabel(l as number)} />
                <Legend {...LEGEND_PROPS} />
                <Line type="monotone" dataKey="roll" name="Roll (°)" stroke={accent} dot={false} connectNulls={false} />
                <Line type="monotone" dataKey="pitch" name="Pitch (°)" stroke={T.second} dot={false} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            // 18-polish: was "this robot has no IMU/barometer sensor installed" —
            // a claim about hardware the data cannot make. Only absence is known.
            <EmptyChart message="NO IMU READINGS FOR THIS SELECTION" />
          )}
        </ChartPanel>

        <ChartPanel
          title="BAROMETER"
          note="Pressure (hPa) and altitude (m) over time, on separate axes."
          stats={
            <>
              <StatLine label="Pressure" stat={stats.pressure} unit="hPa" mix={mix.pressure} />
              <StatLine label="Altitude" stat={stats.altitude} unit="m" mix={mix.altitude} />
            </>
          }
        >
          {hasBaro ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={data} margin={margin}>
                <CartesianGrid stroke={T.grid} strokeDasharray="3 3" />
                <XAxis {...xAxis} />
                <YAxis yAxisId="left" tick={TICK} stroke={T.grid} />
                <YAxis yAxisId="right" orientation="right" tick={TICK} stroke={T.grid} />
                <Tooltip {...TOOLTIP_PROPS} labelFormatter={(l) => fmtTooltipLabel(l as number)} />
                <Legend {...LEGEND_PROPS} />
                <Line yAxisId="left" type="monotone" dataKey="pressure_baro" name="Pressure (hPa)" stroke={accent} dot={false} connectNulls={false} />
                <Line yAxisId="right" type="monotone" dataKey="altitude_baro" name="Altitude (m)" stroke={T.second} dot={false} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart message="NO BAROMETER READINGS FOR THIS SELECTION" />
          )}
        </ChartPanel>
      </div>
    </div>
  )
  // ─── RANGER V3 END: 18-polish ───
}
// ─── RANGER V3 END: visualizations page ───