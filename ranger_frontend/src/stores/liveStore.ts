// ─── RANGER V3 START: 09-live-console ───
/**
 * Live robot positions pushed over /ws/dashboard/ (F09).
 *
 * One entry per robot; a newer row id wins, an older or duplicate one is
 * dropped (a reconnect can replay nothing, but this keeps the map monotonic
 * regardless). DashboardPage resets the store when the user changes, so one
 * org's positions can never survive into the next login on the same tab.
 */
import { create } from "zustand"
import { asDataSource, type DataSource } from "@/types/dataLog.types"

export interface LivePosition {
  id: number
  robot: string
  ts: string
  lat: number
  lon: number
  source: DataSource
  /** Browser clock at receipt (ms). Drives staleness and the lag log. */
  receivedAt: number
}

export type LiveConnection = "idle" | "connecting" | "open" | "closed"

interface LiveStore {
  positions: Record<string, LivePosition>
  connection: LiveConnection
  lastCloseCode: number | null
  /** Validate and store a raw socket payload. Returns the stored position,
   *  or null if the payload was malformed or older than what we hold. */
  upsert: (raw: unknown) => LivePosition | null
  setConnection: (connection: LiveConnection, closeCode?: number) => void
  reset: () => void
}

function parse(raw: unknown): Omit<LivePosition, "receivedAt"> | null {
  if (typeof raw !== "object" || raw === null) return null
  const m = raw as Record<string, unknown>
  if (m.type !== "sensorlog") return null
  if (
    typeof m.id !== "number" ||
    typeof m.robot !== "string" ||
    typeof m.ts !== "string" ||
    typeof m.lat !== "number" ||
    typeof m.lon !== "number"
  ) {
    return null
  }
  // Unknown source → least authoritative tier (under-claim, never over-claim).
  return { id: m.id, robot: m.robot, ts: m.ts, lat: m.lat, lon: m.lon, source: asDataSource(m.source) }
}

export const useLiveStore = create<LiveStore>((set, get) => ({
  positions: {},
  connection: "idle",
  lastCloseCode: null,

  upsert: (raw) => {
    const parsed = parse(raw)
    if (!parsed) return null
    const current = get().positions[parsed.robot]
    if (current && current.id >= parsed.id) return null
    const pos: LivePosition = { ...parsed, receivedAt: Date.now() }
    set((s) => ({ positions: { ...s.positions, [pos.robot]: pos } }))
    return pos
  },

  setConnection: (connection, closeCode) =>
    set({ connection, lastCloseCode: closeCode ?? null }),

  reset: () => set({ positions: {}, connection: "idle", lastCloseCode: null }),
}))
// ─── RANGER V3 END: 09-live-console ───
