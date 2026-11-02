// ─── RANGER V3 START: dashboard FleetMini ───
/**
 * FleetMini — the right-column "FLEET" mini-list (mockup ~322-345). Rows show
 * status dot, robot id, running mission, signal. Clicking a row selects that
 * robot (drives LiveTelemetry + the map's selected blip).
 *
 * 18-polish: every field is real. Status/signal come from the live feed only
 * (no fix → OFFLINE · NO FIX); mission is the robot's running mission or "—".
 * The DEMO overlay (invented missions, battery %) is gone, and so is the
 * battery column — nothing reports battery yet.
 */
import { Panel } from "@/components/console/Panel"
import { MonoLabel } from "@/components/console/MonoLabel"
import { StatusDot } from "@/components/console/StatusDot"
import type { FieldMapBlip } from "@/components/map/FieldMap"

export interface FleetRow {
  id: string            // robot_id_str (real)
  name: string          // robot_name (real)
  mission: string       // running mission name, or "—"
  signal: string        // LIVE / SIM / STALE / NO FIX
  status: FieldMapBlip["status"]
}

const STATUS_DOT: Record<FieldMapBlip["status"], "ok" | "warn" | "alert" | "info" | "sim"> = {
  live: "ok",
  sim: "sim", // 09-live-console
  mqtt: "warn",
  offline: "alert",
  idle: "info",
}

const STATUS_COLOR: Record<FieldMapBlip["status"], string> = {
  live: "var(--color-ok)",
  sim: "#7a828f", // 09-live-console: = SOURCE_META.simulated.color
  mqtt: "var(--color-warn)",
  offline: "var(--color-alert)",
  idle: "var(--color-info)",
}

interface FleetMiniProps {
  rows: FleetRow[]
  selectedId: string
  onSelect: (id: string) => void
  /** 18-polish: true until the first fetch settles, so "no robots" is never
   *  shown for "not loaded yet". */
  loading?: boolean
}

export function FleetMini({ rows, selectedId, onSelect, loading = false }: FleetMiniProps) {
  return (
    <Panel
      title="FLEET"
      right={<MonoLabel size="xs" tone="accent">{rows.length} UNITS</MonoLabel>}
    >
      <div>
        {rows.map((r) => {
          const selected = r.id === selectedId
          return (
            <button
              key={r.id}
              onClick={() => onSelect(r.id)}
              className="w-full flex items-center gap-[10px] px-[13px] py-[9px] cursor-pointer text-left border-t border-border-soft transition-colors hover:bg-surface-3"
              style={selected ? { background: "var(--color-surface-3)" } : undefined}
            >
              <StatusDot status={STATUS_DOT[r.status]} pulse={r.status === "live"} size={8} />
              <span className="font-mono text-[11px] text-fg-soft w-[120px] truncate text-left">
                {r.id}
              </span>
              <span className="text-[11px] text-fg-dim flex-1 truncate text-left">
                {r.mission}
              </span>
              <span className="font-mono text-[10px]" style={{ color: STATUS_COLOR[r.status] }}>
                {r.signal}
              </span>
            </button>
          )
        })}
        {rows.length === 0 ? (
          <div className="px-[13px] py-[20px] text-center font-mono text-[10px] text-fg-faint border-t border-border-soft">
            {loading ? "LOADING…" : "NO ROBOTS IN THIS ORGANIZATION"}
          </div>
        ) : null}
      </div>
    </Panel>
  )
}
// ─── RANGER V3 END: dashboard FleetMini ───