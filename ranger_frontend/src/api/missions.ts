// ─── RANGER V3 START: 15-mission-plan ───
/**
 * Mission planning API (F15 / Pass 6a). Thin wrappers over the shared axios
 * instance (JWT + silent refresh), same pattern as api/satellite.ts.
 * Tenancy is server-side: these only ever see the caller's org.
 */
import axios from "axios"
import { api } from "./client"
import type { Mission, MissionWrite } from "../types/mission.types"
import type { Paginated } from "../types/satellite.types"

/** The org's missions for one robot, newest first. One page of 1000 (DRF's
 *  cap) — a robot with more planned missions than that is not tier 1. */
export async function listMissions(robotIdStr: string): Promise<Mission[]> {
  const { data } = await api.get<Paginated<Mission>>("/missions/", { params: { limit: 1000 } })
  return data.results.filter((m) => m.robot_id_str === robotIdStr)
}

export async function createMission(body: MissionWrite): Promise<Mission> {
  const { data } = await api.post<Mission>("/missions/", body)
  return data
}

/** Full replace. 409 unless the mission is still PENDING. */
export async function replaceMission(id: number, body: MissionWrite): Promise<Mission> {
  const { data } = await api.put<Mission>(`/missions/${id}/`, body)
  return data
}

/** DRF error body -> one readable line per field, for the panel. */
export function errorLines(err: unknown): string[] {
  if (!axios.isAxiosError(err)) return [String(err)]
  const status = err.response?.status
  const data = err.response?.data
  if (!data || typeof data !== "object") return [`${status ?? "network"}: ${err.message}`]
  const lines: string[] = []
  for (const [k, v] of Object.entries(data as Record<string, unknown>)) {
    const msg = Array.isArray(v) ? v.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join(" ") : String(v)
    lines.push(k === "detail" || k === "non_field_errors" ? msg : `${k}: ${msg}`)
  }
  return lines.length ? lines : [`${status}: request failed`]
}
// ─── RANGER V3 END: 15-mission-plan ───
