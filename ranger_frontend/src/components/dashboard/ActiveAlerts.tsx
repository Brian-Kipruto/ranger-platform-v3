// ─── RANGER V3 START: dashboard ActiveAlerts ───
/**
 * ActiveAlerts — the bottom-row "ACTIVE ALERTS" panel (mockup ~346-373).
 * Severity-colored alert rows with an ACK button. ACK is LOCAL ONLY (hides the
 * row in component state) — no backend. DEMO until the Alerts feature lands;
 * real source = a threshold engine + /api/alerts/ (carried-forward thread 5).
 */
import { useState } from "react"
import { Panel } from "@/components/console/Panel"
import { MonoLabel } from "@/components/console/MonoLabel"
import { ALERTS_PLACEHOLDERS, ALERT_SEVERITY_COLOR } from "@/config/dashboardPlaceholders"

export function ActiveAlerts() {
  const [ackd, setAckd] = useState<string[]>([])
  const open = ALERTS_PLACEHOLDERS.filter((a) => !ackd.includes(a.id))

  return (
    <Panel
      title="ACTIVE ALERTS"
      right={
        <span className="flex items-center gap-2">
          <MonoLabel size="xs" tone="alert">{open.length} OPEN</MonoLabel>
          <MonoLabel size="xs" tone="faint" tracking="0.1em" className="opacity-60">DEMO</MonoLabel>
        </span>
      }
    >
      <div className="p-2">
        {open.length === 0 ? (
          <div className="px-2 py-[20px] text-center font-mono text-[10px] text-fg-faint">
            NO OPEN ALERTS
          </div>
        ) : (
          open.map((a) => {
            const color = ALERT_SEVERITY_COLOR[a.severity]
            return (
              <div key={a.id} className="flex gap-[10px] px-2 py-[9px] rounded-md items-start">
                <span
                  className="w-[3px] self-stretch rounded-sm flex-none"
                  style={{ background: color }}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-[7px]">
                    <span className="font-mono text-[10px] tracking-[0.08em]" style={{ color }}>
                      {a.code}
                    </span>
                    <span className="font-mono text-[9px] text-fg-faint">{a.time}</span>
                  </div>
                  <div className="text-[12px] text-fg-soft mt-[3px] leading-[1.4]">{a.message}</div>
                  <div className="font-mono text-[9px] text-fg-dim mt-[3px]">{a.meta}</div>
                </div>
                <button
                  onClick={() => setAckd((s) => [...s, a.id])}
                  className="flex-none cursor-pointer font-mono text-[9px] text-fg-muted bg-transparent border border-border-strong-2 px-2 py-1 rounded hover:border-[#39414f] hover:text-fg-soft transition-colors"
                >
                  ACK
                </button>
              </div>
            )
          })
        )}
      </div>
    </Panel>
  )
}
// ─── RANGER V3 END: dashboard ActiveAlerts ───