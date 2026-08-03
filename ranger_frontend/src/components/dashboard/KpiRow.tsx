// ─── RANGER V3 START: dashboard KpiRow ───
/**
 * KpiRow — the dashboard's six-tile KPI strip (mockup lines ~230-243).
 * Built entirely from the F06 MetricTile primitive. Tiles marked `demo` get a
 * subtle muted treatment (a tiny DEMO tag) so placeholder data is visually
 * honest next to the real ones.
 */
import { MetricTile } from "@/components/console/MetricTile"
import { MonoLabel } from "@/components/console/MonoLabel"
import type { KpiSpec } from "@/config/dashboardPlaceholders"

const TONE_COLOR: Record<KpiSpec["deltaTone"], string> = {
  ok: "var(--color-ok)",
  warn: "var(--color-warn)",
  alert: "var(--color-alert)",
  dim: "var(--color-fg-dim)",
}

export function KpiRow({ kpis }: { kpis: KpiSpec[] }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
      {kpis.map((k) => (
        <MetricTile
          key={k.label}
          label={k.label}
          value={k.value}
          unit={k.unit}
          bar={k.bar}
          sub={
            <span className="flex items-center justify-between gap-2">
              <span style={{ color: TONE_COLOR[k.deltaTone] }}>{k.delta}</span>
              {k.demo ? (
                <MonoLabel size="xs" tone="faint" tracking="0.1em" className="opacity-60">
                  DEMO
                </MonoLabel>
              ) : null}
            </span>
          }
        />
      ))}
    </div>
  )
}
// ─── RANGER V3 END: dashboard KpiRow ───