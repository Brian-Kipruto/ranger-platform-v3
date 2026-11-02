// ─── RANGER V3 START: TopBar ───
/**
 * TopBar — Field Console top bar: view code/label/sub (from the active route)
 * and a live UTC clock.
 *
 * 18-polish: removed the static chrome that looked like working controls or
 * live state but was neither —
 *  - ⌘K search button (no command palette exists)
 *  - "3 LIVE · 1 MQTT · 1 OFF" status pill (hardcoded; there is no MQTT)
 *  - OP / CL / PUB role pills (looked like a switch, did nothing; the user's
 *    org and role are shown in the NavRail footer)
 *  - alerts bell with a permanent red dot (no alerts feature)
 * Each can come back when something real drives it.
 */
import { useEffect, useState } from "react"
import { MonoLabel } from "./MonoLabel"

interface TopBarProps {
  viewCode: string
  viewLabel: string
  viewSub: string
}

function useClock(): string {
  const [clock, setClock] = useState(() => new Date().toISOString().slice(11, 19))
  useEffect(() => {
    const t = setInterval(() => setClock(new Date().toISOString().slice(11, 19)), 1000)
    return () => clearInterval(t)
  }, [])
  return clock
}

export function TopBar({ viewCode, viewLabel, viewSub }: TopBarProps) {
  const clock = useClock()

  return (
    <div className="h-[54px] flex-none flex items-center gap-4 px-[18px] border-b border-border bg-surface-2">
      {/* view identity */}
      <div className="flex items-center gap-[11px] min-w-0">
        <MonoLabel size="md" tone="accent" tracking="0.12em">{viewCode}</MonoLabel>
        <span className="text-[15px] font-semibold text-fg whitespace-nowrap">{viewLabel}</span>
        <span className="font-mono text-[10px] text-fg-faint whitespace-nowrap">{viewSub}</span>
      </div>

      {/* clock */}
      <div className="ml-auto font-mono text-[11px] text-fg-soft tracking-[0.06em]">
        {clock}
        <span className="text-fg-faint text-[9px]"> UTC</span>
      </div>
    </div>
  )
}
// ─── RANGER V3 END: TopBar ───
