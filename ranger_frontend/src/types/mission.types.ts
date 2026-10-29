// ─── RANGER V3 START: 15-mission-plan ───
/**
 * Mission planning shapes (F15 / Pass 6a). Mirror missions/serializers.py.
 * Waypoints are named {lat, lon}, never positional pairs — the backend
 * rejects arrays, and a swapped pair is refused by its region check.
 */
export type MissionStatus = "PENDING" | "IN_PROGRESS" | "PAUSED" | "COMPLETED" | "ABORTED"
export type WaypointStatus = "PENDING" | "COMPLETED" | "SKIPPED"

export interface LatLon {
  lat: number
  lon: number
}

export interface Waypoint extends LatLon {
  id: number
  order: number
  status: WaypointStatus
  completed_at: string | null
}

export interface Mission {
  id: number
  name: string
  description: string
  robot: number
  robot_id_str: string
  status: MissionStatus
  threshold_m: number
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
  waypoints: Waypoint[]
}

export interface MissionWrite {
  name: string
  description: string
  robot_id_str: string
  threshold_m: number
  waypoints: LatLon[]
}

/** Bounds enforced server-side (missions/models.py, serializers.py). */
export const THRESHOLD_M = { default: 5, min: 1, max: 50 } as const
export const MAX_WAYPOINTS = 50
// ─── RANGER V3 END: 15-mission-plan ───
