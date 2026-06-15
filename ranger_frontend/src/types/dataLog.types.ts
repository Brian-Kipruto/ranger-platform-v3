// ─── RANGER V3 START: data log types ───
/**
 * TypeScript mirrors of the Feature 05a backend payloads.
 *
 * Contract between Django and React, same discipline as auth.types.ts: if
 * DataLogSerializer / the map-data view change, this file changes. The flat
 * shape matches the serializer exactly — every reading field is top-level and
 * nullable, because a SensorLog may have no reading of a given type (the seed
 * robot has no imu_baro, so roll/pitch/yaw/pressure_baro/altitude_baro are
 * null on all ~230 of its rows).
 */

/** One flattened sensor log row — the shape of /api/data-logs/ results[] and
 *  /api/chart-data/ array items. Reading fields are null when that reading is
 *  absent. */
export interface DataLog {
  id: number
  robot_id: number
  robot_id_str: string
  robot_name: string
  mission_id: number | null
  mission_name: string | null
  timestamp: string // ISO 8601
  latitude: number
  longitude: number
  // Radiation (null if no radiation_data)
  radiation_value: number | null
  dose_rate_usvh: number | null
  // Air quality (null if no air_quality_data)
  pm25: number | null
  pm10: number | null
  // IMU / baro (null if no imu_baro_data)
  roll: number | null
  pitch: number | null
  yaw: number | null
  pressure_baro: number | null
  altitude_baro: number | null
}

/** DRF PageNumberPagination envelope for /api/data-logs/. */
export interface PaginatedDataLogs {
  count: number
  next: string | null
  previous: string | null
  results: DataLog[]
}

/** Filters shared by all four endpoints. All optional; empty = no filter.
 *  robot_id / mission_id are the integer PKs (not robot_id_str). Dates are
 *  YYYY-MM-DD, inclusive; date_end extends to end-of-day server-side. */
export interface DataLogFilters {
  robot_id?: number | string
  mission_id?: number | string
  date_start?: string
  date_end?: string
}

// ─── Map (GeoJSON) shapes — /api/map-data/ ─────────────────────────
/** Thin per-point properties the map endpoint returns (enough to color a
 *  marker / fill a popup), NOT the full row. */
export interface MapPointProperties {
  id: number
  timestamp: string
  radiation_value: number | null
  pm25: number | null
}

/** A single GeoJSON Point feature. coordinates are [lng, lat] (GeoJSON spec
 *  order — the reverse of how we say "lat/lng"). */
export interface MapFeature {
  type: "Feature"
  geometry: {
    type: "Point"
    coordinates: [number, number] // [longitude, latitude]
  }
  properties: MapPointProperties
}

/** The /api/map-data/ response. */
export interface MapFeatureCollection {
  type: "FeatureCollection"
  features: MapFeature[]
}

// ─── Filter dropdown option shapes ─────────────────────────────────
/** Minimal robot shape for the filter dropdown. id is the integer PK that
 *  the list endpoint's robot_id filter expects. */
export interface RobotOption {
  id: number
  robot_id_str: string
  name: string
}

/** Minimal mission shape for the filter dropdown. */
export interface MissionOption {
  id: number
  name: string
}
// ─── RANGER V3 END: data log types ───