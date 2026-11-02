// ─── RANGER V3 START: dashboard page (F07 retrofit) ───
/**
 * DashboardPage — the Mission Dashboard, retrofitted to the Field Console
 * mockup's isDashboard layout (mockup ~227-410). Replaces the F02 placeholder.
 *
 * Layout:
 *   - KPI row        : 4 MetricTiles, all real
 *   - Main grid      : FieldMap (left, with blips + readout + expand) +
 *                      right column (LIVE TELEMETRY + FLEET mini + DRIVE)
 *   - Bottom row     : SENSOR STREAMS, full width
 *
 * 18-polish — nothing on this page is DEMO any more:
 *   - Robots   : the union of robots in the org's stored data, its missions,
 *                and live pushes. There is no /api/robots/; a registered
 *                robot that has never logged, planned or pushed is not shown.
 *   - KPIs     : robots, reporting now (live feed), missions running
 *                (/api/missions/), records ingested (the paginated `count`,
 *                not the length of the 5,000-row-capped chart pull).
 *   - Fleet    : status from the live feed only; mission = running mission.
 *   - Map      : a blip only where a live position exists. The F07 DEMO
 *                Nairobi coordinates and the hardcoded HDG 142° · 1.4 m/s
 *                readout are gone (the live feed carries neither).
 *   - Alerts / Comms panels removed: no alerts engine, no MQTT, no LoRa.
 *
 * The accent is set by AppShell (org theme_color → --accent). FieldMap needs a
 * hex, so we resolve it the same way the Data Explorer does.
 */
import { useEffect, useMemo, useRef, useState } from "react"
import { useAuthStore } from "@/stores/authStore"
import { getChartData, getDataLogs } from "@/api/dataLogs"
import { listOrgMissions } from "@/api/missions" // 18-polish
import type { Mission } from "@/types/mission.types" // 18-polish
import {
  FieldMap,
  type FieldMapBlip,
  type FieldMapHandle,
  type FieldMapReadout,
} from "@/components/map/FieldMap"
import { KpiRow, type KpiSpec } from "@/components/dashboard/KpiRow"
import { LiveTelemetry } from "@/components/dashboard/LiveTelemetry"
import { FleetMini, type FleetRow } from "@/components/dashboard/FleetMini"
import { SensorStreams } from "@/components/dashboard/SensorStreams"
import type { DataLog } from "@/types/dataLog.types"
// ─── RANGER V3 START: 09-live-console ───
import { LiveFeed } from "@/components/dashboard/LiveFeed"
import { DrivePanel } from "@/components/dashboard/DrivePanel" // 14-teleop
import { useLiveStore, type LivePosition } from "@/stores/liveStore"
import { liveTelemetrySpecs } from "@/components/dashboard/liveTelemetrySpecs" // 13
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
  // 14-teleop: depends on `user` so the panel appears once /me has loaded.
  const canDrive = useAuthStore((s) => !!s.user && s.hasPermission("core.drive_robot"))
  const positions = useLiveStore((s) => s.positions)
  const history = useLiveStore((s) => s.history) // 13-console-readings
  const now = useNow(1_000)

  // A different user (or logout) must never see the previous user's
  // positions: wipe the store whenever the user changes or the page unmounts.
  const userId = user?.id
  useEffect(() => () => useLiveStore.getState().reset(), [userId])
  // ─── RANGER V3 END: 09-live-console ───

  // ─── RANGER V3 START: 18-polish ───
  // One pass over the three sources the page needs. Any failure shows an
  // error banner — never an empty dashboard that reads as "no robots".
  const [chartRows, setChartRows] = useState<DataLog[]>([])
  const [recordCount, setRecordCount] = useState<number | null>(null)
  const [missions, setMissions] = useState<Mission[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  // The picked robot, else the first one. Derived, not synced by an effect.
  const [pickedId, setSelectedId] = useState<string>("")

  useEffect(() => {
    let cancelled = false
    Promise.all([getChartData({}), getDataLogs({}, 1, 1), listOrgMissions()])
      .then(([rows, page, ms]) => {
        if (cancelled) return
        setChartRows(rows)
        setRecordCount(page.count)
        setMissions(ms)
      })
      .catch(() => {
        if (!cancelled) {
          setLoadError("Could not load this organization's data. Check the backend is running, then reload.")
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Robots = stored data ∪ missions ∪ live pushes, in that order. Names come
  // from stored data; a robot known only from a mission or a push shows its id.
  const liveIds = Object.keys(positions).sort().join(",")
  const fleet: FleetRow[] = useMemo(() => {
    const names = new Map<string, string>()
    for (const r of chartRows) if (!names.has(r.robot_id_str)) names.set(r.robot_id_str, r.robot_name)
    for (const m of missions) if (!names.has(m.robot_id_str)) names.set(m.robot_id_str, m.robot_id_str)
    for (const id of liveIds ? liveIds.split(",") : []) if (!names.has(id)) names.set(id, id)
    return Array.from(names, ([id, name]) => {
      const running = missions.find(
        (m) => m.robot_id_str === id && (m.status === "IN_PROGRESS" || m.status === "PAUSED")
      )
      return {
        id,
        name,
        mission: running ? (running.status === "PAUSED" ? `${running.name} (paused)` : running.name) : "—",
        signal: "NO FIX",
        status: "offline" as const,
      }
    })
  }, [chartRows, missions, liveIds])
  const selectedId = pickedId || fleet[0]?.id || ""
  // ─── RANGER V3 END: 18-polish ───

  // ─── RANGER V3 START: 09-live-console ───
  // Staleness only changes on a 5 s boundary; keying on it (not on `now`)
  // stops the map and fleet list rebuilding every tick.
  const staleKey = fleet
    .map((r) => (positions[r.id] && isStale(positions[r.id], now) ? "1" : "0"))
    .join("")

  // Live push sets status/signal; a robot with no push stays OFFLINE · NO FIX.
  const liveFleet: FleetRow[] = useMemo(
    () =>
      fleet.map((r, i) => {
        const p = positions[r.id]
        return p ? { ...r, ...liveOverlay(p, staleKey[i] === "1") } : r
      }),
    [fleet, positions, staleKey]
  )

  /** Live position if one has arrived; no fix, no coordinates (18-polish). */
  const coordsFor = (id: string): { lat: number; lng: number } | undefined => {
    const p = positions[id]
    return p ? { lat: p.lat, lng: p.lon } : undefined
  }

  // Header tag says what the map is actually showing, not what it hopes to.
  const freshSources = Object.values(positions)
    .filter((p) => !isStale(p, now))
    .map((p) => p.source)
  const mapTag = freshSources.includes("live")
    ? "· LIVE"
    : freshSources.length > 0
      ? "· SIM"
      : "· NO LIVE FIX" // 18-polish: was "· DEMO" over invented blips
  // ─── RANGER V3 END: 09-live-console ───

  // ─── RANGER V3 START: 13-console-readings ───
  // LIVE TELEMETRY from the selected robot's live rows. No row, stale, or a
  // reading missing from the newest row -> "—", never an invented number.
  const selectedPos = positions[selectedId]
  const selectedStale = selectedPos ? isStale(selectedPos, now) : true
  const telemetry = useMemo(
    () => liveTelemetrySpecs(history[selectedId], selectedStale),
    [history, selectedId, selectedStale]
  )
  // ─── RANGER V3 END: 13-console-readings ───

  // ─── RANGER V3 START: 18-polish ───
  const freshLive = freshSources.filter((src) => src === "live").length
  const freshOther = freshSources.length - freshLive
  const running = missions.filter((m) => m.status === "IN_PROGRESS").length
  const pending = missions.filter((m) => m.status === "PENDING").length
  const dash = loading || loadError ? "—" : null
  const kpis: KpiSpec[] = [
    {
      label: "ROBOTS",
      value: dash ?? String(fleet.length),
      unit: "units",
      delta: "with data, missions or a live fix",
      deltaTone: "dim",
      bar: "var(--accent)",
    },
    {
      label: "REPORTING NOW",
      value: String(freshSources.length),
      unit: "units",
      delta: freshSources.length > 0 ? `${freshLive} live · ${freshOther} sim` : "no live fix",
      deltaTone: freshLive > 0 ? "ok" : "dim",
      bar: "#4be08a",
    },
    {
      label: "MISSIONS RUNNING",
      value: dash ?? String(running),
      unit: "running",
      delta: dash ? "" : `${pending} pending`,
      deltaTone: "dim",
      bar: "#f5a623",
    },
    {
      label: "DATA INGESTED",
      value: dash ?? (recordCount ?? 0).toLocaleString(),
      unit: "records",
      delta: "this org · all tiers",
      deltaTone: "dim",
      bar: "#36c5f0",
    },
  ]
  // ─── RANGER V3 END: 18-polish ───

  // Map blips: live positions only (18-polish).
  const blips: FieldMapBlip[] = useMemo(
    () =>
      liveFleet
        .map((r) => {
          const p = positions[r.id]
          if (!p) return null
          return { id: r.id, lng: p.lon, lat: p.lat, status: r.status }
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
        // 18-polish: hardcoded HDG 142° · 1.4 m/s removed — no source.
      }
    : null

  return (
    <div className="p-[18px]">
      {/* ─── RANGER V3 START: 09-live-console ─── */}
      {/* Keyed by token: a refreshed token remounts the feed with a fresh socket. */}
      {accessToken ? <LiveFeed key={accessToken} token={accessToken} /> : null}
      {/* ─── RANGER V3 END: 09-live-console ─── */}
      {/* ─── RANGER V3 START: 18-polish ─── */}
      {loadError ? (
        <div
          role="alert"
          className="mb-[14px] px-3 py-2.5 rounded border border-alert/40 font-mono text-[11px] text-alert"
          style={{ background: "color-mix(in srgb, var(--color-alert) 10%, transparent)" }}
        >
          {loadError}
        </div>
      ) : null}
      {/* ─── RANGER V3 END: 18-polish ─── */}
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
            telemetry={telemetry /* 13-console-readings */}
          />
          <FleetMini rows={liveFleet} selectedId={selectedId} onSelect={setSelectedId} loading={loading} />
          {/* ─── RANGER V3 START: 14-teleop ─── */}
          {/* Keyed by robot: switching robots tears the drive session down. */}
          {canDrive && selectedId ? <DrivePanel key={selectedId} robotId={selectedId} /> : null}
          {/* ─── RANGER V3 END: 14-teleop ─── */}
        </div>
      </div>

      {/* BOTTOM ROW — SENSOR STREAMS (18-polish: Alerts and Comms removed) */}
      {/* ─── RANGER V3 START: dashboard bottom row ─── */}
      <div className="mt-[14px]">
        <SensorStreams rows={chartRows} loading={loading} />
      </div>
      {/* ─── RANGER V3 END: dashboard bottom row ─── */}
    </div>
  )
}
// ─── RANGER V3 END: dashboard page (F07 retrofit) ───