// ─── RANGER V3 START: MetricTile primitive ───
/**
 * MetricTile — a KPI/summary tile: left accent bar, mono uppercase label,
 * large value with unit, optional mono sub/delta line. From the mockup's
 * dashboard KPI row; reused for the Data Explorer summary stats.
 */
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import { MonoLabel } from "./MonoLabel"

interface MetricTileProps {
  label: string
  value: ReactNode
  unit?: string
  /** CSS color for the left bar; defaults to the runtime accent */
  bar?: string
  /** small mono line under the value (e.g. "min 9.1 · max 18.4") */
  sub?: ReactNode
  className?: string
}

export function MetricTile({ label, value, unit, bar = "var(--accent)", sub, className }: MetricTileProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden bg-surface-panel border border-border rounded-lg px-[14px] py-[13px]",
        className
      )}
    >
      <div className="absolute left-0 top-0 bottom-0 w-0.5" style={{ background: bar }} />
      <MonoLabel size="xs" tone="dim" tracking="0.14em">
        {label}
      </MonoLabel>
      <div className="mt-2 flex items-baseline gap-[8px]">
        <span className="text-[26px] font-semibold text-fg tracking-[-0.02em]">{value}</span>
        {unit ? <span className="font-mono text-[11px] text-fg-dim">{unit}</span> : null}
      </div>
      {sub ? <div className="mt-[5px] font-mono text-[10px] text-fg-dim">{sub}</div> : null}
    </div>
  )
}
// ─── RANGER V3 END: MetricTile primitive ───