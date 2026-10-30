// ─── RANGER V3 START: 15-mission-live ───
/**
 * mission.progress events from the dashboard socket (F15 6c).
 *
 * Deliberately thin: an event only says "mission N moved". The console then
 * re-reads that mission over HTTP, so what it shows is the database, never a
 * patched-up copy of a socket message. `seq` bumps on every event so a
 * subscriber reacts even when the same mission ticks twice.
 */
import { create } from "zustand"

export interface MissionProgress {
  mission: number
  robot: string
  missionStatus: string
  waypointOrder: number
  distanceM: number
}

interface MissionLiveStore {
  last: MissionProgress | null
  seq: number
  /** Validate + record a raw socket payload. Returns true if it was one. */
  push: (raw: unknown) => boolean
  reset: () => void
}

function parse(raw: unknown): MissionProgress | null {
  if (typeof raw !== "object" || raw === null) return null
  const m = raw as Record<string, unknown>
  if (m.type !== "mission.progress") return null
  const wp = m.waypoint as Record<string, unknown> | undefined
  if (typeof m.mission !== "number" || typeof m.robot !== "string" || typeof wp?.order !== "number") return null
  return {
    mission: m.mission,
    robot: m.robot,
    missionStatus: String(m.mission_status ?? ""),
    waypointOrder: wp.order,
    distanceM: typeof m.distance_m === "number" ? m.distance_m : NaN,
  }
}

export const useMissionLiveStore = create<MissionLiveStore>((set) => ({
  last: null,
  seq: 0,
  push: (raw) => {
    const p = parse(raw)
    if (!p) return false
    set((s) => ({ last: p, seq: s.seq + 1 }))
    return true
  },
  reset: () => set({ last: null, seq: 0 }),
}))
// ─── RANGER V3 END: 15-mission-live ───
