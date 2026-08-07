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

// ─── provenance (F10.2 backend, F10.3 CP0 frontend) ────────────────
/** SensorLog.source — the four provenance tiers, most to least
 *  authoritative. Mirrors core.models.SensorLog.Source EXACTLY; if that
 *  TextChoices changes, this changes. */
export type DataSource = "live" | "reported" | "modelled" | "simulated"

/** Display metadata per tier.
 *
 *  Colours are HEX LITERALS, not CSS vars, and deliberately so: these feed
 *  MapLibre paint expressions as well as React styles, and paint props
 *  cannot read CSS variables (see the FieldMap header invariants). One
 *  definition, both consumers.
 *
 *  The palette matches the console's semantic tokens: ok / info / warn /
 *  dim. Measured tiers read as "good", generated tiers as "caution". */
export const SOURCE_META: Record<
  DataSource,
  { label: string; short: string; color: string }
> = {
  live: { label: "Live sensor", short: "LIVE", color: "#4be08a" },
  reported: { label: "Reported measurement", short: "RPT", color: "#36c5f0" },
  modelled: { label: "Modelled", short: "MOD", color: "#f5a623" },
  simulated: { label: "Simulated", short: "SIM", color: "#7a828f" },
}

/** Tiers backed by a real instrument reading a real place. Everything else
 *  is generated and must never be presented as a measurement. */
export const MEASURED_SOURCES: readonly DataSource[] = ["live", "reported"]

/** Narrowing helper for payloads that predate the field or carry a tier we
 *  do not know about yet. Falls back to the LEAST authoritative tier — the
 *  same direction the backend default leans (see SensorLog.Source), so an
 *  unknown value under-claims instead of asserting a measurement. */
export function asDataSource(value: unknown): DataSource {
  return typeof value === "string" && value in SOURCE_META
    ? (value as DataSource)
    : "simulated"
}

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
  // Provenance (F10.2). Present on EVERY row out of DataLogSerializer —
  // never optional, because a type that lets you forget it is a type that
  // invites 12,081 modelled points rendering as measurements.
  source: DataSource
  provenance_note: string
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
  // F10.2 emits `source` here; F10.3 CP0 adds `provenance_note` so a marker
  // popup can cite the derivation rather than only naming the tier.
  source: DataSource
  provenance_note: string
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

/** Provenance over the FULL filtered set (F10.3 CP0.5).
 *
 *  Computed server-side on the UNCAPPED queryset. `features` is capped at
 *  MAX_CHART_POINTS, so nothing derived from features.length may be
 *  presented as describing the set — that is the whole reason this block
 *  exists. */
export interface MapProvenanceSummary {
  /** Rows the filters select, before the map's point cap. */
  total: number
  /** tier -> count, over all `total` rows. */
  by_source: Partial<Record<DataSource, number>>
  /** Distinct provenance_note strings. Several sites = several notes; never
   *  pick one and present it as the citation for the set. */
  notes: string[]
  notes_truncated: boolean
  /** How many features the map actually received. */
  returned: number
  /** returned < total — the map is showing a sample. */
  truncated: boolean
}

/** The /api/map-data/ response. */
export interface MapFeatureCollection {
  type: "FeatureCollection"
  features: MapFeature[]
  provenance: MapProvenanceSummary
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