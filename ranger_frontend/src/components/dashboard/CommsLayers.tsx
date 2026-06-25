// ─── RANGER V3 START: dashboard CommsLayers ───
/**
 * CommsLayers — the bottom-row "COMMS LAYERS" panel (mockup ~397-415). The
 * communication stack (ROS 2 DDS → rosbridge → Channels → MQTT → LoRa) with a
 * load bar + status per layer. STATIC chrome — these become real telemetry in
 * F08+ when the live pipeline (rosbridge / Channels) is wired.
 */
import { Panel } from "@/components/console/Panel"
import { MonoLabel } from "@/components/console/MonoLabel"
import { COMMS_PLACEHOLDERS } from "@/config/dashboardPlaceholders"

export function CommsLayers() {
  return (
    <Panel
      title="COMMS LAYERS"
      right={<MonoLabel size="xs" tone="faint" tracking="0.1em" className="opacity-60">STATIC</MonoLabel>}
    >
      <div className="px-[13px] py-[10px]">
        {COMMS_PLACEHOLDERS.map((c) => (
          <div
            key={c.n}
            className="flex items-center gap-[11px] py-2 border-b border-border-soft last:border-b-0"
          >
            <span className="font-mono text-[10px] w-[18px]" style={{ color: "var(--accent)" }}>
              {c.n}
            </span>
            <div className="flex-1 min-w-0">
              <div className="text-[11.5px] text-fg-soft whitespace-nowrap overflow-hidden text-ellipsis">
                {c.name}
              </div>
              <div className="font-mono text-[8.5px] text-fg-faint mt-px">{c.proto}</div>
            </div>
            <div className="w-[54px] h-1 bg-surface-3 rounded-sm overflow-hidden flex-none">
              <div
                className="h-full rounded-sm"
                style={{ width: `${c.load}%`, background: c.color }}
              />
            </div>
            <span
              className="font-mono text-[9px] w-[62px] text-right"
              style={{ color: c.color }}
            >
              {c.status}
            </span>
          </div>
        ))}
      </div>
    </Panel>
  )
}
// ─── RANGER V3 END: dashboard CommsLayers ───