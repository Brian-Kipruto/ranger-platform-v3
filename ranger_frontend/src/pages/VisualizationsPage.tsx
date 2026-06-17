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
 */
import { useCallback, useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
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
import { getChartData, getRobotOptions } from "@/api/dataLogs"
import type { DataLog, RobotOption } from "@/types/dataLog.types"

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

function StatLine({ label, stat, unit }: { label: string; stat: Stat | null; unit: string }) {
  if (!stat) return null
  return (
    <span className="text-xs text-gray-500 mr-4">
      {label}: min {stat.min.toFixed(1)} · max {stat.max.toFixed(1)} · avg{" "}
      {stat.avg.toFixed(1)} {unit} <span className="text-gray-400">(n={stat.count})</span>
    </span>
  )
}

function EmptyChart({ message }: { message: string }) {
  return (
    <div
      className="w-full flex items-center justify-center text-sm text-gray-400 border border-dashed rounded"
      style={{ height: 280 }}
    >
      {message}
    </div>
  )
}

const X_AXIS_PROPS = {
  dataKey: "timestamp_ms",
  type: "number" as const,
  scale: "time" as const,
  domain: ["dataMin", "dataMax"] as [string, string],
  tickFormatter: fmtTick,
  tick: { fontSize: 11 },
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

  useEffect(() => {
    let cancelled = false
    getRobotOptions()
      .then((r) => {
        if (!cancelled) setRobots(r)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const rows = await getChartData({
        robot_id: robotId || undefined,
        date_start: dateStart || undefined,
        date_end: dateEnd || undefined,
      })
      const mapped: ChartRow[] = rows
        .map((r) => ({ ...r, timestamp_ms: new Date(r.timestamp).getTime() }))
        .filter((r) => !Number.isNaN(r.timestamp_ms))
      setData(mapped)
      setHasFetched(true)
    } catch {
      setError("Failed to load chart data. Check that you're logged in and the backend is running.")
      setData([])
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

  const hasRadiation = stats.radiation !== null
  const hasAir = stats.pm25 !== null || stats.pm10 !== null
  const hasImu = stats.roll !== null || stats.pitch !== null
  const hasBaro = stats.pressure !== null || stats.altitude !== null

  return (
    <div className="min-h-screen p-6">
      <div className="max-w-6xl mx-auto">
        <header className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold">Visualizations</h1>
            <p className="text-sm text-gray-500">
              {user?.organization?.name ?? "Organization"} sensor time-series
            </p>
          </div>
          <Link to="/dashboard" className="text-sm underline text-gray-600 hover:text-gray-900">
            ← Dashboard
          </Link>
        </header>

        {/* Filters */}
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
            onClick={fetchData}
            disabled={loading}
            className="px-4 py-1.5 text-sm rounded text-white disabled:opacity-50"
            style={{ backgroundColor: accent }}
          >
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>

        {error ? (
          <div className="text-sm text-red-600 mb-4">{error}</div>
        ) : (
          <div className="text-sm text-gray-600 mb-4">
            {data.length} data point{data.length === 1 ? "" : "s"}
            {hasFetched && data.length === 0 ? " — adjust filters and Refresh" : ""}
          </div>
        )}

        <div className="space-y-8">
          {/* Radiation */}
          <section>
            <h2 className="text-lg font-medium">Radiation</h2>
            <p className="text-xs text-gray-500 mb-1">
              Counts per minute (CPM) over time. The dashed line is an{" "}
              <em>example</em> threshold, not a regulatory limit.
            </p>
            <div className="mb-2">
              <StatLine label="Radiation" stat={stats.radiation} unit="CPM" />
            </div>
            {hasRadiation ? (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis {...X_AXIS_PROPS} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip labelFormatter={(l) => fmtTooltipLabel(l as number)} />
                  <Legend />
                  <ReferenceLine
                    y={EXAMPLE_RADIATION_THRESHOLD}
                    stroke="#ef4444"
                    strokeDasharray="6 4"
                    label={{ value: "example threshold", fontSize: 10, fill: "#ef4444", position: "insideTopRight" }}
                  />
                  <Line
                    type="monotone"
                    dataKey="radiation_value"
                    name="Radiation (CPM)"
                    stroke={accent}
                    dot={false}
                    connectNulls={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart message="No radiation data for this selection." />
            )}
          </section>

          {/* Air Quality */}
          <section>
            <h2 className="text-lg font-medium">Air Quality</h2>
            <p className="text-xs text-gray-500 mb-1">
              Particulate matter (µg/m³) over time. The dashed line is an{" "}
              <em>example</em> PM2.5 threshold, not a regulatory limit.
            </p>
            <div className="mb-2">
              <StatLine label="PM2.5" stat={stats.pm25} unit="µg/m³" />
              <StatLine label="PM10" stat={stats.pm10} unit="µg/m³" />
            </div>
            {hasAir ? (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis {...X_AXIS_PROPS} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip labelFormatter={(l) => fmtTooltipLabel(l as number)} />
                  <Legend />
                  <ReferenceLine
                    y={EXAMPLE_PM25_THRESHOLD}
                    stroke="#ef4444"
                    strokeDasharray="6 4"
                    label={{ value: "example PM2.5 threshold", fontSize: 10, fill: "#ef4444", position: "insideTopRight" }}
                  />
                  <Line type="monotone" dataKey="pm25" name="PM2.5" stroke={accent} dot={false} connectNulls={false} />
                  <Line type="monotone" dataKey="pm10" name="PM10" stroke="#f59e0b" dot={false} connectNulls={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart message="No air-quality data for this selection." />
            )}
          </section>

          {/* IMU Orientation */}
          <section>
            <h2 className="text-lg font-medium">IMU Orientation</h2>
            <p className="text-xs text-gray-500 mb-1">Roll and pitch (degrees) over time.</p>
            <div className="mb-2">
              <StatLine label="Roll" stat={stats.roll} unit="°" />
              <StatLine label="Pitch" stat={stats.pitch} unit="°" />
            </div>
            {hasImu ? (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis {...X_AXIS_PROPS} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip labelFormatter={(l) => fmtTooltipLabel(l as number)} />
                  <Legend />
                  <Line type="monotone" dataKey="roll" name="Roll (°)" stroke={accent} dot={false} connectNulls={false} />
                  <Line type="monotone" dataKey="pitch" name="Pitch (°)" stroke="#f59e0b" dot={false} connectNulls={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart message="No IMU data — this robot has no IMU/barometer sensor installed." />
            )}
          </section>

          {/* Barometer */}
          <section>
            <h2 className="text-lg font-medium">Barometer</h2>
            <p className="text-xs text-gray-500 mb-1">
              Pressure (hPa) and altitude (m) over time, on separate axes.
            </p>
            <div className="mb-2">
              <StatLine label="Pressure" stat={stats.pressure} unit="hPa" />
              <StatLine label="Altitude" stat={stats.altitude} unit="m" />
            </div>
            {hasBaro ? (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis {...X_AXIS_PROPS} />
                  <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
                  <Tooltip labelFormatter={(l) => fmtTooltipLabel(l as number)} />
                  <Legend />
                  <Line yAxisId="left" type="monotone" dataKey="pressure_baro" name="Pressure (hPa)" stroke={accent} dot={false} connectNulls={false} />
                  <Line yAxisId="right" type="monotone" dataKey="altitude_baro" name="Altitude (m)" stroke="#f59e0b" dot={false} connectNulls={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart message="No barometer data — this robot has no IMU/barometer sensor installed." />
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
// ─── RANGER V3 END: visualizations page ───