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
import { useEffect, useMemo, useState } from "react"
import { useAuthStore } from "@/stores/authStore"
import { getChartData, getRobotOptions } from "@/api/dataLogs"
import { FieldMap, type FieldMapBlip, type FieldMapReadout } from "@/components/map/FieldMap"
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

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user)
  const accent = user?.organization?.theme_color ?? "#0ea5e9"

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

  // Map blips from the fleet (DEMO coords until live positions exist).
  const blips: FieldMapBlip[] = useMemo(
    () =>
      fleet
        .map((r) => {
          const c = BLIP_COORDS_DEMO[r.id]
          if (!c) return null
          return { id: r.id, lng: c.lng, lat: c.lat, status: r.status }
        })
        .filter((b): b is FieldMapBlip => b !== null),
    [fleet]
  )

  const selectedFleet = fleet.find((r) => r.id === selectedId) ?? null
  const selectedCoords = selectedId ? BLIP_COORDS_DEMO[selectedId] : undefined
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
      {/* KPI ROW */}
      <KpiRow kpis={kpis} />

      {/* MAIN GRID — field map (left) + right column */}
      <div className="mt-[14px] grid grid-cols-1 lg:grid-cols-[1.62fr_1fr] gap-[14px] items-start">
        {/* FIELD MAP */}
        <FieldMap
          accent={accent}
          blips={blips}
          selectedBlipId={selectedId || null}
          onSelectBlip={setSelectedId}
          readout={readout}
          showOverlays
          expandable
          headerTitle="FIELD MAP"
          headerSub="· LIVE"
          height="430px"
        />

        {/* RIGHT COLUMN */}
        <div className="flex flex-col gap-[14px]">
          <LiveTelemetry
            selectedId={selectedId || "—"}
            telemetry={TELEMETRY_PLACEHOLDERS}
          />
          <FleetMini rows={fleet} selectedId={selectedId} onSelect={setSelectedId} />
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