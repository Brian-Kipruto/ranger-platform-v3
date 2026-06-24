// ─── RANGER V3 START: TopBar ───
/**
 * TopBar — Field Console top bar. View code/label/sub (from the active route),
 * a ⌘K-styled search placeholder (non-functional this feature), static
 * LIVE/MQTT/OFF status pills, a live UTC clock, static role-switch chrome,
 * and an alerts bell.
 *
 * Static chrome (no logic yet, wired in later features):
 *  - search button (command palette deferred)
 *  - status counts (no fleet endpoint yet)
 *  - role switch (real role-switching is the RBAC/ADR-0007 thread)
 *  - alerts bell (alerts feature is future)
 */
import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"
import { MonoLabel } from "./MonoLabel"
import { StatusDot } from "./StatusDot"
import type { ConsoleRole } from "@/config/navConfig"

interface TopBarProps {
  viewCode: string
  viewLabel: string
  viewSub: string
  role: ConsoleRole
}

// Static role-switch chrome — mirrors the mockup's three role pills. The
// active pill reflects the real logged-in role; clicking does nothing yet.
const ROLE_PILLS: { key: ConsoleRole; short: string; color: string }[] = [
  { key: "operator", short: "OP", color: "var(--accent)" },
  { key: "client", short: "CL", color: "var(--color-ok)" },
  { key: "community", short: "PUB", color: "var(--color-info)" },
]

function useClock(): string {
  const [clock, setClock] = useState(() => new Date().toISOString().slice(11, 19))
  useEffect(() => {
    const t = setInterval(() => setClock(new Date().toISOString().slice(11, 19)), 1000)
    return () => clearInterval(t)
  }, [])
  return clock
}

export function TopBar({ viewCode, viewLabel, viewSub, role }: TopBarProps) {
  const clock = useClock()

  return (
    <div className="h-[54px] flex-none flex items-center gap-4 px-[18px] border-b border-border bg-surface-2">
      {/* view identity */}
      <div className="flex items-center gap-[11px] min-w-0">
        <MonoLabel size="md" tone="accent" tracking="0.12em">{viewCode}</MonoLabel>
        <span className="text-[15px] font-semibold text-fg whitespace-nowrap">{viewLabel}</span>
        <span className="font-mono text-[10px] text-fg-faint whitespace-nowrap">{viewSub}</span>
      </div>

      {/* search placeholder (⌘K — non-functional this feature) */}
      <button
        type="button"
        className="ml-auto cursor-default flex items-center gap-2.5 bg-surface-3 border border-border-strong rounded-[7px] px-3 py-2 min-w-[260px] text-fg-faint hover:border-[#39414f] transition-colors"
        aria-label="Search (coming soon)"
      >
        <span className="w-[13px] h-[13px] border-[1.5px] border-fg-faint rounded-full inline-block" />
        <span className="text-[12px] flex-1 text-left">Search robots, missions, topics…</span>
        <span className="font-mono text-[10px] border border-border-strong-2 rounded px-1.5 py-px text-fg-dim">⌘K</span>
      </button>

      {/* status pills (static) */}
      <div className="flex items-center gap-[7px] font-mono text-[10px] tracking-[0.08em] text-fg-muted px-2.5 py-1.5 border border-border rounded-[7px]">
        <StatusDot status="ok" pulse size={7} />
        3 LIVE
        <span className="text-border-strong-2">·</span>
        <span className="text-warn">1 MQTT</span>
        <span className="text-border-strong-2">·</span>
        <span className="text-fg-faint">1 OFF</span>
      </div>

      {/* clock */}
      <div className="font-mono text-[11px] text-fg-soft tracking-[0.06em]">
        {clock}
        <span className="text-fg-faint text-[9px]"> UTC</span>
      </div>

      {/* role switch (static chrome) */}
      <div className="flex bg-surface-3 border border-border-strong rounded-[7px] p-0.5">
        {ROLE_PILLS.map((r) => {
          const active = r.key === role
          return (
            <span
              key={r.key}
              title={r.key}
              className="cursor-default rounded-[5px] px-[9px] py-[5px] font-mono text-[10px] tracking-[0.08em]"
              style={{
                background: active ? "var(--accent-weak)" : "transparent",
                color: active ? r.color : "var(--color-fg-dim)",
              }}
            >
              {r.short}
            </span>
          )
        })}
      </div>

      {/* alerts bell (static) */}
      <button
        type="button"
        className={cn(
          "relative cursor-default w-[34px] h-[34px] rounded-[7px] bg-surface-3 border border-border-strong",
          "text-fg-muted flex items-center justify-center"
        )}
        aria-label="Alerts"
      >
        <span className="w-[13px] h-[13px] border-[1.5px] border-current border-b-0 rounded-t-[7px]" />
        <span className="absolute top-1.5 right-1.5 w-[7px] h-[7px] rounded-full bg-alert border-[1.5px] border-[#0e1015]" />
      </button>
    </div>
  )
}
// ─── RANGER V3 END: TopBar ───