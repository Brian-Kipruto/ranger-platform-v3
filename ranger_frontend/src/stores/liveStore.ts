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

// ─── RANGER V3 START: 13-console-readings ───
/** Each reading carries ITS OWN source (ADR-0020); `LivePosition.source` is
 *  the position's. A live robot with a simulated tube = live position +
 *  simulated radiation, and the console shows both. Missing values are null. */
export interface LiveRadiation { cpm: number | null; doseRateUsvh: number | null; source: DataSource }
export interface LiveAirQuality { pm25: number | null; pm10: number | null; source: DataSource }
export interface LiveImuBaro {
  roll: number | null
  pitch: number | null
  /** Compass heading, degrees clockwise from magnetic north. null = uncalibrated. */
  yaw: number | null
  pressureHpa: number | null
  altitudeM: number | null
  source: DataSource
}
/** Absent key = that reading was not on this row. Never a zero stand-in. */
export interface LiveReadings {
  radiation?: LiveRadiation
  airQuality?: LiveAirQuality
  imuBaro?: LiveImuBaro
}

/** Samples kept per robot for the telemetry sparklines (~1 min at 1 Hz). */
export const HISTORY_MAX = 60

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null
}

function obj(v: unknown): Record<string, unknown> | null {
  return typeof v === "object" && v !== null && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null
}

/** Tolerant: a malformed reading is dropped, never guessed. An unknown
 *  source falls to the least authoritative tier (under-claim). */
export function parseReadings(raw: unknown): LiveReadings {
  const r = obj(raw)
  const out: LiveReadings = {}
  if (!r) return out
  const rad = obj(r.radiation)
  if (rad) {
    out.radiation = { cpm: num(rad.cpm), doseRateUsvh: num(rad.dose_rate_usvh), source: asDataSource(rad.source) }
  }
  const aq = obj(r.air_quality)
  if (aq) out.airQuality = { pm25: num(aq.pm25), pm10: num(aq.pm10), source: asDataSource(aq.source) }
  const imu = obj(r.imu_baro)
  if (imu) {
    out.imuBaro = {
      roll: num(imu.roll),
      pitch: num(imu.pitch),
      yaw: num(imu.yaw),
      pressureHpa: num(imu.pressure_hpa),
      altitudeM: num(imu.altitude_m),
      source: asDataSource(imu.source),
    }
  }
  return out
}
// ─── RANGER V3 END: 13-console-readings ───

export interface LivePosition {
  id: number
  robot: string
  ts: string
  lat: number
  lon: number
  source: DataSource
  /** 13-console-readings: the readings saved on this row, each self-labelled. */
  readings: LiveReadings
  /** Browser clock at receipt (ms). Drives staleness and the lag log. */
  receivedAt: number
}

export type LiveConnection = "idle" | "connecting" | "open" | "closed"

interface LiveStore {
  positions: Record<string, LivePosition>
  /** 13-console-readings: last HISTORY_MAX positions per robot, oldest first. */
  history: Record<string, LivePosition[]>
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
  return {
    id: m.id,
    robot: m.robot,
    ts: m.ts,
    lat: m.lat,
    lon: m.lon,
    source: asDataSource(m.source),
    readings: parseReadings(m.readings), // 13-console-readings
  }
}

export const useLiveStore = create<LiveStore>((set, get) => ({
  positions: {},
  history: {},
  connection: "idle",
  lastCloseCode: null,

  upsert: (raw) => {
    const parsed = parse(raw)
    if (!parsed) return null
    const current = get().positions[parsed.robot]
    if (current && current.id >= parsed.id) return null
    const pos: LivePosition = { ...parsed, receivedAt: Date.now() }
    set((s) => ({
      positions: { ...s.positions, [pos.robot]: pos },
      history: {
        ...s.history,
        [pos.robot]: [...(s.history[pos.robot] ?? []), pos].slice(-HISTORY_MAX),
      },
    }))
    return pos
  },

  setConnection: (connection, closeCode) =>
    set({ connection, lastCloseCode: closeCode ?? null }),

  reset: () => set({ positions: {}, history: {}, connection: "idle", lastCloseCode: null }),
}))
// ─── RANGER V3 END: 09-live-console ───
