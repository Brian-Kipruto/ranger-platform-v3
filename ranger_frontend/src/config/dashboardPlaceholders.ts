// ─── RANGER V3 START: dashboard placeholders ───
/**
 * ALL placeholder / demo data for the Dashboard lives in THIS ONE FILE.
 *
 * WHY ONE FILE: the dashboard ships visually complete in F07, but several of
 * its data sources don't exist yet (no fleet/live/alerts endpoints — see the
 * F07 carried-forward threads). Rather than scatter fake data inline across
 * components (which makes the "wire it for real later" swap a hunt-and-peck
 * across files), every fake value is centralized here and clearly marked DEMO.
 *
 * THE SWAP CONTRACT: when a real endpoint lands (Fleet list, live telemetry
 * WebSocket, Alerts), the corresponding component stops importing from here and
 * reads the real source instead. The component's PROPS shapes (below) are the
 * contract that survives the swap — they're written to match what the real
 * endpoints will plausibly return, so the change is localized.
 *
 * Anything NOT marked DEMO on the dashboard is real:
 *   - SENSOR STREAMS  → real /api/chart-data/ (CP5)
 *   - one KPI tile    → real record count (CP4, wired in DashboardPage)
 *   - FLEET ids/names → real, derived from /api/chart-data/ (status is DEMO)
 */

import type { FieldMapBlip } from "@/components/map/FieldMap"

// ─── KPI row ───────────────────────────────────────────────────────
// Six tiles. Most are DEMO until their source exists; DashboardPage overrides
// the "records" tile with a real count. `demo: true` drives a subtle muted
// affordance so live vs placeholder is visually honest.
export interface KpiSpec {
  label: string
  value: string
  unit: string
  delta: string
  deltaTone: "ok" | "warn" | "alert" | "dim"
  bar: string // left-bar color (hex or token-ish)
  demo: boolean
}

export const KPI_PLACEHOLDERS: KpiSpec[] = [
  { label: "FLEET ACTIVE", value: "4", unit: "units", delta: "▲ 2 since 06:00", deltaTone: "ok", bar: "var(--accent)", demo: true },
  { label: "LIVE MISSIONS", value: "2", unit: "running", delta: "1 queued", deltaTone: "dim", bar: "#4be08a", demo: true },
  { label: "OPEN ALERTS", value: "3", unit: "events", delta: "1 critical", deltaTone: "alert", bar: "#ff5d5d", demo: true },
  // index 3 — overridden with a REAL record count in DashboardPage:
  { label: "DATA INGESTED", value: "—", unit: "records", delta: "this org", deltaTone: "dim", bar: "#36c5f0", demo: false },
  { label: "AREA SURVEYED", value: "128", unit: "km²", delta: "this month", deltaTone: "dim", bar: "#f5a623", demo: true },
  { label: "SLA UPTIME", value: "99.2", unit: "%", delta: "30-day avg", deltaTone: "ok", bar: "#4be08a", demo: true },
]

// ─── Live telemetry (selected robot) ───────────────────────────────
// Four mini stat tiles with sparklines. DEMO: deterministic series so it
// doesn't jitter on every render. Real source = live telemetry WS (F08+).
export interface TelemetrySpec {
  label: string
  value: string
  unit: string
  color: string
  series: number[] // sampled values; component renders the sparkline
}

// deterministic sine-based demo series (no Math.random → stable across renders)
function demoSeries(base: number, amp: number, n = 24, phase = 0): number[] {
  return Array.from({ length: n }, (_, i) => base + amp * Math.sin((i + phase) / 3))
}

export const TELEMETRY_PLACEHOLDERS: TelemetrySpec[] = [
  { label: "RADIATION", value: "14.2", unit: "CPM", color: "#4be08a", series: demoSeries(14, 2.2, 24, 0) },
  { label: "PM2.5", value: "29", unit: "µg/m³", color: "#f5a623", series: demoSeries(24, 5, 24, 2) },
  { label: "PRESSURE", value: "842", unit: "hPa", color: "#36c5f0", series: demoSeries(842, 1.5, 24, 1) },
  { label: "TEMP", value: "24.6", unit: "°C", color: "#cdd2da", series: demoSeries(24.5, 0.8, 24, 4) },
]

// ─── Fleet (statuses + missions are DEMO; ids/names come from real data) ──
// DashboardPage derives the real robot list from /api/chart-data/ and merges
// it with this DEMO status/mission/battery/signal overlay (keyed by robot_id_str,
// falling back to a default for robots without an entry).
export interface FleetStatusDemo {
  status: FieldMapBlip["status"]
  mission: string
  battery: number
  signal: string
}

export const FLEET_STATUS_DEMO: Record<string, FleetStatusDemo> = {
  "RANGER-PRIME-001": { status: "live", mission: "Magadi Soda Flats Survey", battery: 78, signal: "LIVE" },
  "RNG-02": { status: "mqtt", mission: "Athi Basin Patrol", battery: 54, signal: "MQTT" },
  "RNG-03": { status: "offline", mission: "Docked — Nakuru", battery: 12, signal: "OFF" },
  "RNG-04": { status: "live", mission: "Tsavo Boundary Scan", battery: 91, signal: "LIVE" },
  "RNG-05": { status: "idle", mission: "Standby", battery: 66, signal: "IDLE" },
}

export const FLEET_STATUS_DEFAULT: FleetStatusDemo = {
  status: "idle",
  mission: "—",
  battery: 0,
  signal: "IDLE",
}

// Coordinates for the dashboard map blips (DEMO positions near Nairobi until
// live positions exist). Keyed by robot_id_str.
export const BLIP_COORDS_DEMO: Record<string, { lng: number; lat: number }> = {
  "RANGER-PRIME-001": { lng: 36.8219, lat: -1.2921 },
  "RNG-02": { lng: 36.8252, lat: -1.289 },
  "RNG-03": { lng: 36.819, lat: -1.2955 },
  "RNG-04": { lng: 36.824, lat: -1.2945 },
  "RNG-05": { lng: 36.8205, lat: -1.2905 },
}

// ─── Active alerts (DEMO until the Alerts feature/endpoint exists) ──
// Real source = the Alerts feature (threshold engine + /api/alerts/). ACK here
// is local-only (hides the row); no backend call. Severity drives color.
export interface AlertSpec {
  id: string
  severity: "critical" | "warning" | "info"
  code: string
  time: string
  message: string
  meta: string
}

export const ALERTS_PLACEHOLDERS: AlertSpec[] = [
  {
    id: "a1",
    severity: "critical",
    code: "PM25-EXCEED",
    time: "14:32:08",
    message: "PM2.5 reached 42 µg/m³ — exceeds WHO 24h guideline (35)",
    meta: "RANGER-PRIME-001 · SECTOR G-7 · -1.901°, 36.273°",
  },
  {
    id: "a2",
    severity: "warning",
    code: "BATT-LOW",
    time: "14:18:55",
    message: "Battery at 12% — return-to-dock advised",
    meta: "RNG-03 · ATHI · docked",
  },
  {
    id: "a3",
    severity: "info",
    code: "BAG-COMPLETE",
    time: "13:59:10",
    message: "Recording magadi_0623.mcap finalized (1.4 GB · 6 topics)",
    meta: "RNG-04 · NAKURU",
  },
]

export const ALERT_SEVERITY_COLOR: Record<AlertSpec["severity"], string> = {
  critical: "#ff5d5d",
  warning: "#f5a623",
  info: "#36c5f0",
}

// ─── Comms layers (STATIC chrome — these become real in F08+) ──
// The communication stack the platform will use. Load/status are illustrative
// until the live pipeline (rosbridge / Channels / MQTT) is wired in F08.
export interface CommLayerSpec {
  n: string
  name: string
  proto: string
  status: string
  load: number // 0-100
  color: string
}

export const COMMS_PLACEHOLDERS: CommLayerSpec[] = [
  { n: "L1", name: "ROS 2 DDS", proto: "DDS/UDP · LAN", status: "NOMINAL", load: 82, color: "#4be08a" },
  { n: "L2", name: "rosbridge WS", proto: "WebSocket :9090", status: "NOMINAL", load: 54, color: "#4be08a" },
  { n: "L3", name: "Django Channels", proto: "WS · Redis", status: "NOMINAL", load: 33, color: "#4be08a" },
  { n: "L4", name: "MQTT Heartbeat", proto: "MQTT 5.0/TLS", status: "DEGRADED", load: 21, color: "#f5a623" },
  { n: "L5", name: "LoRa Fallback", proto: "SX1276 · 868MHz", status: "STANDBY", load: 4, color: "#5a6071" },
]
// ─── RANGER V3 END: dashboard placeholders ───