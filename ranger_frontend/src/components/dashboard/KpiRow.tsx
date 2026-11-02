// ─── RANGER V3 START: dashboard KpiRow ───
/**
 * KpiRow — the dashboard's KPI strip, built from the F06 MetricTile primitive.
 *
 * 18-polish: every tile is real. The F07 row had six tiles, five of them DEMO
 * (fleet 4, missions 2, alerts 3, 128 km², 99.2 % SLA). The ones with a real
 * source now read it (DashboardPage); the ones without one were removed rather
 * than labelled — a DEMO tag beside a confident number is still a number on
 * screen. So the `demo` flag and its tag are gone, and the spec type lives here
 * now that dashboardPlaceholders.ts is deleted.
 */
import { MetricTile } from "@/components/console/MetricTile"

export interface KpiSpec {
  label: string
  value: string
  unit: string
  delta: string
  deltaTone: "ok" | "warn" | "alert" | "dim"
  bar: string // left-bar color (hex or token-ish)
}

const TONE_COLOR: Record<KpiSpec["deltaTone"], string> = {
  ok: "var(--color-ok)",
  warn: "var(--color-warn)",
  alert: "var(--color-alert)",
  dim: "var(--color-fg-dim)",
}

export function KpiRow({ kpis }: { kpis: KpiSpec[] }) {
  return (
    <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
      {kpis.map((k) => (
        <MetricTile
          key={k.label}
          label={k.label}
          value={k.value}
          unit={k.unit}
          bar={k.bar}
          sub={<span style={{ color: TONE_COLOR[k.deltaTone] }}>{k.delta}</span>}
        />
      ))}
    </div>
  )
}
// ─── RANGER V3 END: dashboard KpiRow ───
