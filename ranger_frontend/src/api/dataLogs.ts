// ─── RANGER V3 START: data logs api ───
/**
 * Typed wrappers over the Feature 05a endpoints. Every call goes through the
 * shared `api` axios instance (api/client.ts), so the JWT access token is
 * attached automatically and 401s trigger the silent-refresh interceptor.
 * That's why the CSV export works with a Bearer token here and not V2's
 * session-cookie window.open hack — production has no session cookie.
 */
import { api } from "./client"
import type {
  DataLog,
  PaginatedDataLogs,
  DataLogFilters,
  MapFeatureCollection,
  RobotOption,
  MissionOption,
} from "../types/dataLog.types"

/** Build a params object from filters, dropping empty values so we never
 *  send robot_id="" (which the backend would treat as a real filter). */
function buildParams(filters: DataLogFilters): Record<string, string> {
  const params: Record<string, string> = {}
  if (filters.robot_id) params.robot_id = String(filters.robot_id)
  if (filters.mission_id) params.mission_id = String(filters.mission_id)
  if (filters.date_start) params.date_start = filters.date_start
  if (filters.date_end) params.date_end = filters.date_end
  return params
}

/** GET /api/data-logs/ — paginated table feed. page is 1-based (DRF). limit
 *  maps to the StandardResultsSetPagination `limit` query param. */
export async function getDataLogs(
  filters: DataLogFilters,
  page: number,
  limit: number
): Promise<PaginatedDataLogs> {
  const { data } = await api.get<PaginatedDataLogs>("/data-logs/", {
    params: { ...buildParams(filters), page, limit },
  })
  return data
}

/** GET /api/map-data/ — full filtered track as a GeoJSON FeatureCollection,
 *  decoupled from table pagination. Coordinates are [lng, lat]. */
export async function getMapData(
  filters: DataLogFilters
): Promise<MapFeatureCollection> {
  const { data } = await api.get<MapFeatureCollection>("/map-data/", {
    params: buildParams(filters),
  })
  return data
}

/** GET /api/chart-data/ — unpaginated, ascending, point-capped. Flat rows for
 *  time-series charts. Same shape as the list endpoint, no pagination envelope. */
export async function getChartData(filters: DataLogFilters): Promise<DataLog[]> {
  const { data } = await api.get<DataLog[]>("/chart-data/", {
    params: buildParams(filters),
  })
  return data
}

/** GET /api/data-logs/export/ — CSV download. Fetched as a blob through the
 *  api instance (JWT attached), then turned into a synthetic download so the
 *  browser saves the file without leaving the page. */
export async function exportCsv(filters: DataLogFilters): Promise<void> {
  const response = await api.get<Blob>("/data-logs/export/", {
    params: buildParams(filters),
    responseType: "blob",
  })
  const blob = new Blob([response.data], { type: "text/csv" })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = "ranger_sensor_logs.csv"
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

/**
 * Filter dropdown options.
 *
 * Feature 05 does NOT build /api/robots/ or /api/missions/ (they're in the V3
 * arch doc but out of that feature's scope, and don't exist yet). Rather than
 * expand scope, we derive the available robots and missions from a one-shot
 * unpaginated pull of the chart-data endpoint (which returns every row for the
 * org, each carrying robot_id/robot_id_str/robot_name and mission_id/
 * mission_name). De-duplicated client-side.
 *
 * F10.3 CP0: this used to be TWO exported functions, each making its own
 * /chart-data/ call. The Data Explorer called both on mount, so filling two
 * dropdowns cost two full capped pulls (MAX_CHART_POINTS = 5000 rows each)
 * before /map-data/ fetched a third. That was free at 435 simulated Nairobi
 * points and is not free at 12,081 modelled Marsabit ones. One call now.
 *
 * NOTE: this derives options only from robots/missions that have LOGGED data.
 * A robot with zero logs won't appear. That's acceptable for a data explorer
 * (you can't explore data that doesn't exist), and when real /api/robots/ and
 * /api/missions/ endpoints land, swapping this function to hit them is a
 * localized change — the dropdown components consume RobotOption[] /
 * MissionOption[] either way.
 */
export interface FilterOptions {
  robots: RobotOption[]
  missions: MissionOption[]
}

export async function getFilterOptions(): Promise<FilterOptions> {
  const { data } = await api.get<DataLog[]>("/chart-data/")

  const robotsSeen = new Map<number, RobotOption>()
  const missionsSeen = new Map<number, MissionOption>()

  for (const row of data) {
    if (!robotsSeen.has(row.robot_id)) {
      robotsSeen.set(row.robot_id, {
        id: row.robot_id, // integer PK — the list endpoint's robot_id filter
        robot_id_str: row.robot_id_str,
        name: row.robot_name,
      })
    }
    if (row.mission_id !== null && !missionsSeen.has(row.mission_id)) {
      missionsSeen.set(row.mission_id, {
        id: row.mission_id,
        name: row.mission_name ?? `Mission ${row.mission_id}`,
      })
    }
  }

  return {
    robots: Array.from(robotsSeen.values()),
    missions: Array.from(missionsSeen.values()),
  }
}

/** @deprecated Use getFilterOptions() — this makes a second full pull.
 *  Kept so any other caller keeps compiling; delete once none remain. */
export async function getRobotOptions(): Promise<RobotOption[]> {
  return (await getFilterOptions()).robots
}

/** @deprecated See getRobotOptions. */
export async function getMissionOptions(): Promise<MissionOption[]> {
  return (await getFilterOptions()).missions
}
// ─── RANGER V3 END: data logs api ───