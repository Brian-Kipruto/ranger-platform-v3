// ─── RANGER V3 START: dashboard FleetMini ───
/**
 * FleetMini — the right-column "FLEET" mini-list (mockup ~322-345). Rows show
 * status dot, robot id, mission, signal, battery. Clicking a row selects that
 * robot (drives LiveTelemetry + the map's selected blip).
 *
 * Robot IDS + NAMES are REAL (derived from /api/chart-data/ in DashboardPage).
 * Status / mission / battery / signal are DEMO overlay (FLEET_STATUS_DEMO),
 * until a real fleet endpoint exists. Each row is a FleetRow built in the page.
 */
import { Panel } from "@/components/console/Panel"
import { MonoLabel } from "@/components/console/MonoLabel"
import { StatusDot } from "@/components/console/StatusDot"
import type { FieldMapBlip } from "@/components/map/FieldMap"

export interface FleetRow {
  id: string            // robot_id_str (real)
  name: string          // robot_name (real)
  mission: string       // DEMO
  battery: number       // DEMO
  signal: string        // DEMO
  status: FieldMapBlip["status"] // DEMO
}

const STATUS_DOT: Record<FieldMapBlip["status"], "ok" | "warn" | "alert" | "info"> = {
  live: "ok",
  mqtt: "warn",
  offline: "alert",
  idle: "info",
}

const STATUS_COLOR: Record<FieldMapBlip["status"], string> = {
  live: "var(--color-ok)",
  mqtt: "var(--color-warn)",
  offline: "var(--color-alert)",
  idle: "var(--color-info)",
}

interface FleetMiniProps {
  rows: FleetRow[]
  selectedId: string
  onSelect: (id: string) => void
}

export function FleetMini({ rows, selectedId, onSelect }: FleetMiniProps) {
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
              <span className="font-mono text-[10px] text-fg-muted w-[34px] text-right">
                {r.battery}%
              </span>
            </button>
          )
        })}
        {rows.length === 0 ? (
          <div className="px-[13px] py-[20px] text-center font-mono text-[10px] text-fg-faint border-t border-border-soft">
            NO ROBOTS · FETCH DATA IN DATA EXPLORER FIRST
          </div>
        ) : null}
      </div>
    </Panel>
  )
}
// ─── RANGER V3 END: dashboard FleetMini ───