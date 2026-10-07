// ─── RANGER V3 START: dashboard page (F07 retrofit) ───
/**
 * DashboardPage — the Mission Dashboard, retrofitted to the Field Console
 * mockup's isDashboard layout (mockup ~227-410). Replaces the F02 placeholder.
 *
 * Layout:
 *   - KPI row        : 6 MetricTiles (5 DEMO + 1 real record count)
 *   - Main grid      : FieldMap (left, with blips + readout + expand) +
 *                      right column (LIVE TELEMETRY + FLEET mini)
 *   - Bottom row     : ACTIVE ALERTS · SENSOR STREAMS · COMMS LAYERS  (CP5)
 *
 * REAL vs DEMO (see dashboardPlaceholders.ts):
 *   - Robot ids/names    : REAL, derived from /api/chart-data/ (F05 pattern)
 *   - "DATA INGESTED" KPI : REAL count of the org's sensor records
 *   - Everything else now : DEMO, centralized + clearly marked, swap-ready
 *
 * The accent is set by AppShell (org theme_color → --accent). FieldMap needs a
 * hex, so we resolve it the same way the Data Explorer does.
 */
import { useEffect, useMemo, useRef, useState } from "react"
import { useAuthStore } from "@/stores/authStore"
import { getChartData, getRobotOptions } from "@/api/dataLogs"
import {
  FieldMap,
  type FieldMapBlip,
  type FieldMapHandle,
  type FieldMapReadout,
} from "@/components/map/FieldMap"
import { KpiRow } from "@/components/dashboard/KpiRow"
import { LiveTelemetry } from "@/components/dashboard/LiveTelemetry"
import { FleetMini, type FleetRow } from "@/components/dashboard/FleetMini"
import { ActiveAlerts } from "@/components/dashboard/ActiveAlerts"
import { SensorStreams } from "@/components/dashboard/SensorStreams"
import { CommsLayers } from "@/components/dashboard/CommsLayers"
import type { DataLog } from "@/types/dataLog.types"
import {
  KPI_PLACEHOLDERS,
  TELEMETRY_PLACEHOLDERS,
  FLEET_STATUS_DEMO,
  FLEET_STATUS_DEFAULT,
  BLIP_COORDS_DEMO,
} from "@/config/dashboardPlaceholders"
// ─── RANGER V3 START: 09-live-console ───
import { LiveFeed } from "@/components/dashboard/LiveFeed"
import { useLiveStore, type LivePosition } from "@/stores/liveStore"
import { SOURCE_META } from "@/types/dataLog.types"

/** No push for this long → the position is shown as STALE, not as live. */
const STALE_MS = 5_000

function isStale(p: LivePosition, now: number): boolean {
  return now - p.receivedAt > STALE_MS
}

/** Provenance decides the blip, never the transport: only a fresh `live` row
 *  is green. A stale position falls to offline rather than keep claiming. */
function liveOverlay(p: LivePosition, stale: boolean): Pick<FleetRow, "status" | "signal"> {
  if (stale) return { status: "offline", signal: "STALE" }
  if (p.source === "live") return { status: "live", signal: "LIVE" }
  return { status: "sim", signal: SOURCE_META[p.source].short }
}

/** Re-render once a second so staleness is evaluated without a new message. */
function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(t)
  }, [intervalMs])
  return now
}
// ─── RANGER V3 END: 09-live-console ───

// ─── RANGER V3 START: 11-ingest-region ───
/** Same zoom FieldMap opens at, so the one-time fly is a pan, not a zoom jump. */
const FIRST_FIX_ZOOM = 13
// ─── RANGER V3 END: 11-ingest-region ───

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user)
  const accent = user?.organization?.theme_color ?? "#0ea5e9"
  // ─── RANGER V3 START: 09-live-console ───
  const accessToken = useAuthStore((s) => s.accessToken)
  const positions = useLiveStore((s) => s.positions)
  const now = useNow(1_000)

  // A different user (or logout) must never see the previous user's
  // positions: wipe the store whenever the user changes or the page unmounts.
  const userId = user?.id
  useEffect(() => () => useLiveStore.getState().reset(), [userId])
  // ─── RANGER V3 END: 09-live-console ───

  // Real robots (id + name) derived from the chart-data endpoint, F05-style.
  const [fleet, setFleet] = useState<FleetRow[]>([])
  const [recordCount, setRecordCount] = useState<number | null>(null)
  const [chartRows, setChartRows] = useState<DataLog[]>([])
  const [selectedId, setSelectedId] = useState<string>("")

  useEffect(() => {
    let cancelled = false
    // robot options give real id/name; chart-data length gives a real count.
    Promise.all([getRobotOptions(), getChartData({})])
      .then(([robots, rows]) => {
        if (cancelled) return
        setRecordCount(rows.length)
        setChartRows(rows)
        const built: FleetRow[] = robots.map((r) => {
          const demo = FLEET_STATUS_DEMO[r.robot_id_str] ?? FLEET_STATUS_DEFAULT
          return {
            id: r.robot_id_str,
            name: r.name,
            mission: demo.mission,
            battery: demo.battery,
            signal: demo.signal,
            status: demo.status,
          }
        })
        setFleet(built)
        if (built.length > 0) setSelectedId((cur) => cur || built[0].id)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  // KPI row: override the "records" tile (index 3) with the real count.
  const kpis = useMemo(() => {
    return KPI_PLACEHOLDERS.map((k) =>
      k.label === "DATA INGESTED"
        ? { ...k, value: recordCount === null ? "…" : recordCount.toLocaleString() }
        : k
    )
  }, [recordCount])

  // ─── RANGER V3 START: 09-live-console ───
  // Staleness only changes on a 5 s boundary; keying on it (not on `now`)
  // stops the map and fleet list rebuilding every tick.
  const staleKey = fleet
    .map((r) => (positions[r.id] && isStale(positions[r.id], now) ? "1" : "0"))
    .join("")

  // Live push overrides DEMO status/signal for robots that have reported.
  // Robots with no live position keep the DEMO overlay (swap contract).
  const liveFleet: FleetRow[] = useMemo(
    () =>
      fleet.map((r, i) => {
        const p = positions[r.id]
        return p ? { ...r, ...liveOverlay(p, staleKey[i] === "1") } : r
      }),
    [fleet, positions, staleKey]
  )

  /** Live position if one has arrived, else DEMO coords. */
  const coordsFor = (id: string): { lat: number; lng: number } | undefined => {
    const p = positions[id]
    return p ? { lat: p.lat, lng: p.lon } : BLIP_COORDS_DEMO[id]
  }

  // Header tag says what the map is actually showing, not what it hopes to.
  const freshSources = Object.values(positions)
    .filter((p) => !isStale(p, now))
    .map((p) => p.source)
  const mapTag = freshSources.includes("live")
    ? "· LIVE"
    : freshSources.length > 0
      ? "· SIM"
      : "· DEMO"
  // ─── RANGER V3 END: 09-live-console ───

  // Map blips from the fleet (live position when pushed, DEMO coords otherwise).
  const blips: FieldMapBlip[] = useMemo(
    () =>
      liveFleet
        .map((r) => {
          const p = positions[r.id]
          const c = p ? { lat: p.lat, lng: p.lon } : BLIP_COORDS_DEMO[r.id]
          if (!c) return null
          return { id: r.id, lng: c.lng, lat: c.lat, status: r.status }
        })
        .filter((b): b is FieldMapBlip => b !== null),
    [liveFleet, positions]
  )

  // ─── RANGER V3 START: 11-ingest-region ───
  // The map opens on Nairobi; a robot in Rabat is ~5,000 km off-screen. Fly to
  // the selected robot's FIRST live position, once per robot — never on later
  // fixes, so the user can pan away without being snapped back.
  const fieldMap = useRef<FieldMapHandle | null>(null)
  const flownTo = useRef<Set<string>>(new Set())
  useEffect(() => {
    flownTo.current = new Set()
  }, [userId])
  const selectedLive = selectedId ? positions[selectedId] : undefined
  const selLat = selectedLive?.lat
  const selLon = selectedLive?.lon
  useEffect(() => {
    if (!selectedId || selLat === undefined || selLon === undefined) return
    if (flownTo.current.has(selectedId)) return
    flownTo.current.add(selectedId)
    fieldMap.current?.flyTo(selLon, selLat, FIRST_FIX_ZOOM)
  }, [selectedId, selLat, selLon])
  // ─── RANGER V3 END: 11-ingest-region ───

  const selectedFleet = liveFleet.find((r) => r.id === selectedId) ?? null
  const selectedCoords = selectedId ? coordsFor(selectedId) : undefined
  const readout: FieldMapReadout | null = selectedFleet
    ? {
        id: selectedFleet.id,
        call: selectedFleet.name,
        coords: selectedCoords
          ? `${selectedCoords.lat.toFixed(4)}°, ${selectedCoords.lng.toFixed(4)}°`
          : undefined,
        headingDeg: 142,
        speedMs: 1.4,
      }
    : null

  return (
    <div className="p-[18px]">
      {/* ─── RANGER V3 START: 09-live-console ─── */}
      {/* Keyed by token: a refreshed token remounts the feed with a fresh socket. */}
      {accessToken ? <LiveFeed key={accessToken} token={accessToken} /> : null}
      {/* ─── RANGER V3 END: 09-live-console ─── */}
      {/* KPI ROW */}
      <KpiRow kpis={kpis} />

      {/* MAIN GRID — field map (left) + right column */}
      <div className="mt-[14px] grid grid-cols-1 lg:grid-cols-[1.62fr_1fr] gap-[14px] items-start">
        {/* FIELD MAP */}
        <FieldMap
          ref={fieldMap /* 11-ingest-region */}
          accent={accent}
          blips={blips}
          selectedBlipId={selectedId || null}
          onSelectBlip={setSelectedId}
          readout={readout}
          showOverlays
          expandable
          headerTitle="FIELD MAP"
          headerSub={mapTag}
          height="430px"
        />

        {/* RIGHT COLUMN */}
        <div className="flex flex-col gap-[14px]">
          <LiveTelemetry
            selectedId={selectedId || "—"}
            telemetry={TELEMETRY_PLACEHOLDERS}
          />
          <FleetMini rows={liveFleet} selectedId={selectedId} onSelect={setSelectedId} />
        </div>
      </div>

      {/* BOTTOM ROW — ACTIVE ALERTS · SENSOR STREAMS · COMMS LAYERS */}
      {/* ─── RANGER V3 START: dashboard bottom row ─── */}
      <div className="mt-[14px] grid grid-cols-1 lg:grid-cols-[1.1fr_1fr_1fr] gap-[14px] items-start">
        <ActiveAlerts />
        <SensorStreams rows={chartRows} />
        <CommsLayers />
      </div>
      {/* ─── RANGER V3 END: dashboard bottom row ─── */}
    </div>
  )
}
// ─── RANGER V3 END: dashboard page (F07 retrofit) ───