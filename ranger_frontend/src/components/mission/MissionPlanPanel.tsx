// ─── RANGER V3 START: 15-mission-plan ───
/**
 * MissionPlanPanel — pick or start a mission, name it, set the completion
 * threshold, reorder/remove waypoints, Save (F15 / Pass 6a). Waypoints are
 * added by clicking the map; this panel never takes typed coordinates.
 * Reorder is ↑/↓ buttons: no drag library for a list of at most 50.
 */
import { Panel } from "@/components/console/Panel"
import { MonoLabel } from "@/components/console/MonoLabel"
import { MAX_WAYPOINTS, THRESHOLD_M } from "@/types/mission.types"
import type { useMissionPlan } from "./useMissionPlan"

type Plan = ReturnType<typeof useMissionPlan>

const btn = "px-2 py-[2px] rounded border border-border text-[11px] font-mono text-fg-soft disabled:opacity-30"
const input = "w-full bg-transparent border border-border rounded-md px-2 py-1 text-[12px] font-mono text-fg disabled:opacity-60"

export function MissionPlanPanel({ plan, robotId }: { plan: Plan; robotId: string | null }) {
  const { missions, selected, selectedId, draft, dirty, saving, errors, note, locked, canSave, thresholdOk } = plan
  const status = selected ? selected.status : "NEW"

  return (
    <Panel
      title="MISSION PLAN"
      right={<MonoLabel size="xs" tone={dirty ? "accent" : "soft"}>{dirty ? `${status} · UNSAVED` : status}</MonoLabel>}
    >
      <div className="p-[13px] flex flex-col gap-[11px]">
        {!robotId ? (
          <p className="font-mono text-[11px] text-fg-faint leading-[1.7]">
            No robot is paired with this console. Set VITE_VIDEO_ROBOT_ID.
          </p>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <select
                className={input}
                value={selectedId ?? ""}
                onChange={(e) => plan.select(e.target.value === "" ? null : Number(e.target.value))}
              >
                <option value="">+ New mission</option>
                {missions.map((m) => (
                  <option key={m.id} value={m.id}>
                    #{m.id} {m.name} [{m.status}]
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-[1fr_96px] gap-2">
              <label className="flex flex-col gap-1">
                <MonoLabel size="xs" tone="soft">NAME</MonoLabel>
                <input className={input} value={draft.name} disabled={locked} maxLength={200}
                  onChange={(e) => plan.edit({ ...draft, name: e.target.value })} />
              </label>
              <label className="flex flex-col gap-1">
                <MonoLabel size="xs" tone="soft">REACH (M)</MonoLabel>
                <input className={input} value={draft.threshold} disabled={locked} inputMode="decimal"
                  onChange={(e) => plan.edit({ ...draft, threshold: e.target.value })} />
              </label>
            </div>
            {!thresholdOk && (
              <p className="font-mono text-[11px] text-alert">
                Reach must be {THRESHOLD_M.min}–{THRESHOLD_M.max} m.
              </p>
            )}

            <div className="flex items-center justify-between">
              <MonoLabel size="xs" tone="soft">
                WAYPOINTS {draft.points.length}/{MAX_WAYPOINTS}
              </MonoLabel>
              {!locked && (
                <MonoLabel size="xs" tone="faint">CLICK THE MAP TO ADD</MonoLabel>
              )}
            </div>

            <ol className="flex flex-col gap-[3px] max-h-[32vh] overflow-y-auto">
              {draft.points.length === 0 && (
                <li className="font-mono text-[11px] text-fg-faint">No waypoints yet.</li>
              )}
              {draft.points.map((p, i) => (
                <li key={i} className="flex items-center gap-2 font-mono text-[11px] text-fg-soft">
                  <span className="w-[22px] text-right text-fg">{i + 1}</span>
                  <span className="flex-1 tabular-nums">
                    {p.lat.toFixed(6)}, {p.lon.toFixed(6)}
                  </span>
                  {!locked && (
                    <>
                      <button type="button" className={btn} disabled={i === 0} onClick={() => plan.move(i, -1)}
                        aria-label={`Move waypoint ${i + 1} up`}>↑</button>
                      <button type="button" className={btn} disabled={i === draft.points.length - 1}
                        onClick={() => plan.move(i, 1)} aria-label={`Move waypoint ${i + 1} down`}>↓</button>
                      <button type="button" className={btn} onClick={() => plan.remove(i)}
                        aria-label={`Remove waypoint ${i + 1}`}>✕</button>
                    </>
                  )}
                </li>
              ))}
            </ol>

            {locked && selected && (
              <p className="font-mono text-[11px] text-fg-faint">
                {selected.status} missions are read-only.
              </p>
            )}
            {errors.map((e) => (
              <p key={e} className="font-mono text-[11px] text-alert break-words">{e}</p>
            ))}
            {note && <MonoLabel size="xs" tone="accent">{note}</MonoLabel>}

            {!locked && (
              <button type="button" onClick={plan.save} disabled={!canSave}
                className="self-end px-3 py-1 rounded-md bg-[var(--accent)] text-white text-[11px] font-mono disabled:opacity-40">
                {saving ? "SAVING…" : selectedId === null ? "SAVE" : "SAVE CHANGES"}
              </button>
            )}
          </>
        )}
      </div>
    </Panel>
  )
}
// ─── RANGER V3 END: 15-mission-plan ───
