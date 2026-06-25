// ─── RANGER V3 START: dashboard SensorStreams ───
/**
 * SensorStreams — the bottom-row "SENSOR STREAMS" panel (mockup ~375-395).
 * REAL DATA: radiation (CPM) + PM2.5 (µg/m³) series from /api/chart-data/,
 * rendered as filled area sparklines with a dashed WHO-reference threshold line.
 *
 * The page fetches chart-data once and passes the rows down (so the dashboard
 * doesn't double-fetch). This panel only renders — it's display logic over the
 * real series. Threshold values are illustrative references (WHO), labeled as
 * such; precise alert thresholds belong to the Alerts feature.
 */
import { useMemo } from "react"
import { Panel } from "@/components/console/Panel"
import { MonoLabel } from "@/components/console/MonoLabel"
import type { DataLog } from "@/types/dataLog.types"

interface StreamDef {
  name: string
  unit: string
  color: string
  fill: string
  threshold: number
  note: string
  pick: (r: DataLog) => number | null
}

const STREAMS: StreamDef[] = [
  {
    name: "RADIATION · CPM",
    unit: "CPM",
    color: "#4be08a",
    fill: "rgba(75,224,138,0.10)",
    threshold: 300,
    note: "WHO ref threshold shown · nominal",
    pick: (r) => r.radiation_value,
  },
  {
    name: "AIR QUALITY · PM2.5",
    unit: "µg/m³",
    color: "#f5a623",
    fill: "rgba(245,166,35,0.10)",
    threshold: 35,
    note: "WHO 24h guideline 35 µg/m³",
    pick: (r) => r.pm25,
  },
]

const W = 200
const H = 40

/** Build area + line + threshold-Y for a numeric series over a W×H viewbox. */
function buildStream(values: number[], threshold: number) {
  if (values.length === 0) return { line: "", area: "", threshY: H, last: null as number | null }
  const max = Math.max(threshold, ...values) || 1
  const min = 0
  const rng = max - min || 1
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1 || 1)) * W
    const y = H - ((v - min) / rng) * H
    return [x, y] as const
  })
  const line = pts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ")
  const area = `0,${H} ${line} ${W},${H}`
  const threshY = (H - ((threshold - min) / rng) * H).toFixed(1)
  return { line, area, threshY, last: values[values.length - 1] }
}

export function SensorStreams({ rows }: { rows: DataLog[] }) {
  // Cap to a recent window so the sparkline reads cleanly.
  const windowRows = useMemo(() => rows.slice(-40), [rows])

  return (
    <Panel
      title="SENSOR STREAMS"
      right={<MonoLabel size="xs" tone="ok">LIVE · REAL</MonoLabel>}
    >
      <div className="p-[13px] flex flex-col gap-[14px]">
        {STREAMS.map((s) => {
          const values = windowRows
            .map(s.pick)
            .filter((v): v is number => v !== null && v !== undefined && !Number.isNaN(v))
          const built = buildStream(values, s.threshold)
          return (
            <div key={s.name}>
              <div className="flex items-baseline justify-between">
                <MonoLabel size="sm" tone="muted" tracking="0.08em">{s.name}</MonoLabel>
                <span className="font-mono text-[13px]" style={{ color: s.color }}>
                  {built.last !== null ? built.last.toFixed(1) : "—"}{" "}
                  <span className="text-[9px] text-fg-faint">{s.unit}</span>
                </span>
              </div>
              <svg
                viewBox={`0 0 ${W} ${H}`}
                preserveAspectRatio="none"
                className="mt-[7px] w-full h-[38px] block"
              >
                <line
                  x1={0}
                  y1={built.threshY}
                  x2={W}
                  y2={built.threshY}
                  stroke="#ff5d5d"
                  strokeWidth={0.6}
                  strokeDasharray="2 2"
                  opacity={0.5}
                />
                {built.area ? <polyline points={built.area} fill={s.fill} stroke="none" /> : null}
                {built.line ? (
                  <polyline points={built.line} fill="none" stroke={s.color} strokeWidth={1.3} />
                ) : null}
              </svg>
              <div className="font-mono text-[8.5px] text-fg-faint mt-[3px]">
                {values.length > 0 ? s.note : "NO DATA · FETCH IN DATA EXPLORER FIRST"}
              </div>
            </div>
          )
        })}
      </div>
    </Panel>
  )
}
// ─── RANGER V3 END: dashboard SensorStreams ───