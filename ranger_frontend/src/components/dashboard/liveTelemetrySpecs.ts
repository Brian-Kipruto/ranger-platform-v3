// ─── RANGER V3 START: 13-console-readings ───
/**
 * LIVE TELEMETRY tiles from the live feed (F13 5d). Replaces the F07 DEMO
 * series, which showed invented numbers under a "LIVE" title.
 *
 * Rules (each one is a way the panel could lie, closed):
 *   - A tile's value comes from the NEWEST row only. A reading that wasn't on
 *     that row shows "—": an older value is not current (no carry-forward).
 *   - Every value carries its reading's own source chip (ADR-0020): a live
 *     robot with a simulated tube shows radiation as SIM.
 *   - Stale feed (no push for STALE_MS) -> every tile "—", no chip.
 *   - Heading null = uncalibrated magnetometer: "—", with the reason on hover.
 *   - The sparkline is the recent history of that metric, gaps skipped.
 */
import type { DataSource } from "@/types/dataLog.types"
import type { LivePosition, LiveReadings } from "@/stores/liveStore"

export interface TelemetrySpec {
  label: string
  value: string
  unit: string
  color: string
  series: number[] // sampled values; component renders the sparkline
  /** The displayed value's own provenance. Omitted when there is no value. */
  source?: DataSource
  /** Why the value is what it is (shown on hover). */
  note?: string
}

interface Metric {
  label: string
  unit: string
  color: string
  digits: number
  pick: (r: LiveReadings) => { value: number | null; source: DataSource } | null
  nullNote?: string
}

const METRICS: Metric[] = [
  {
    label: "RADIATION", unit: "CPM", color: "#4be08a", digits: 0,
    pick: (r) => (r.radiation ? { value: r.radiation.cpm, source: r.radiation.source } : null),
  },
  {
    label: "PM2.5", unit: "µg/m³", color: "#f5a623", digits: 1,
    pick: (r) => (r.airQuality ? { value: r.airQuality.pm25, source: r.airQuality.source } : null),
  },
  {
    label: "PRESSURE", unit: "hPa", color: "#36c5f0", digits: 1,
    pick: (r) => (r.imuBaro ? { value: r.imuBaro.pressureHpa, source: r.imuBaro.source } : null),
  },
  {
    label: "HEADING", unit: "°", color: "#cdd2da", digits: 0,
    pick: (r) => (r.imuBaro ? { value: r.imuBaro.yaw, source: r.imuBaro.source } : null),
    nullNote: "Magnetometer not calibrated yet: no heading is published until it is",
  },
]

export function liveTelemetrySpecs(
  history: LivePosition[] | undefined,
  stale: boolean,
): TelemetrySpec[] {
  const latest = history && history.length > 0 ? history[history.length - 1] : undefined
  return METRICS.map((m) => {
    const series = (history ?? [])
      .map((p) => m.pick(p.readings)?.value)
      .filter((v): v is number => typeof v === "number")
    const base = { label: m.label, unit: m.unit, color: m.color, series }
    if (!latest) return { ...base, value: "—", note: "No live data for this robot" }
    if (stale) return { ...base, value: "—", note: "Stale: no update in the last few seconds" }
    const picked = m.pick(latest.readings)
    if (!picked) return { ...base, value: "—", note: "Not on the latest row" }
    if (picked.value === null) {
      // No chip on "—": a chip labels a value, and there is none.
      return { ...base, value: "—", note: m.nullNote ?? "No value on the latest row" }
    }
    return { ...base, value: picked.value.toFixed(m.digits), source: picked.source }
  })
}
// ─── RANGER V3 END: 13-console-readings ───
