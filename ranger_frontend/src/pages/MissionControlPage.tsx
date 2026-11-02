// ─── RANGER V3 START: mission control page ───
/**
 * MissionControlPage — the "see and drive" screen for the robot that owns the
 * video feed (F14 fork 7). Camera large, DrivePanel beside it. The robot is
 * VITE_VIDEO_ROBOT_ID, never a picker: one video server = one robot, so the
 * camera and the drive panel can't point at different robots. The dashboard
 * DRIVE panel stays; the one-driver lease (4409) makes two placements safe.
 * The mission map, waypoint list, and command panel land in later passes.
 *
 * F15 fork 7: map | camera in equal halves on top, mission plan | drive below.
 * Everything stays mounted: a tab or hidden camera would either reconnect the
 * MJPEG on every toggle or keep the Orin encoding for nobody.
 */
import { MonoLabel } from "@/components/console/MonoLabel"
import { CameraPanel } from "@/components/camera/CameraPanel"
// ─── RANGER V3 START: 14-mission-drive ───
import { Panel } from "@/components/console/Panel"
import { DrivePanel } from "@/components/dashboard/DrivePanel"
import { useAuthStore } from "@/stores/authStore"
import { VIDEO_CONFIG } from "@/lib/video"
// ─── RANGER V3 END: 14-mission-drive ───
// ─── RANGER V3 START: 15-mission-plan ───
import { FieldMap, type FieldMapBlip } from "@/components/map/FieldMap"
// ─── RANGER V3 START: 15-mission-live ───
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { LiveFeed } from "@/components/dashboard/LiveFeed"
import { useLiveStore } from "@/stores/liveStore"
import { useMissionLiveStore } from "@/stores/missionLiveStore"
// ─── RANGER V3 END: 15-mission-live ───
import { MissionPlanPanel } from "@/components/mission/MissionPlanPanel"
import { useMissionPlan } from "@/components/mission/useMissionPlan"
// ─── RANGER V3 END: 15-mission-plan ───
// ─── RANGER V3 START: 14-mission-drive ───

function DriveNote({ title, lines }: { title: string; lines: string[] }) {
  return (
    <Panel title="DRIVE">
      <div className="flex flex-col gap-2 p-[13px]">
        <MonoLabel size="sm" tone="soft" tracking="0.13em">{title}</MonoLabel>
        {lines.map((l) => (
          <p key={l} className="font-mono text-[11px] text-fg-faint leading-[1.7]">{l}</p>
        ))}
      </div>
    </Panel>
  )
}
// ─── RANGER V3 END: 14-mission-drive ───

// ─── RANGER V3 START: 15-mission-live ───
/** Same rule as the dashboard: no push for 5 s -> offline, and only a fresh
 *  `live`-sourced row is green; anything simulated draws as "sim". */
const STALE_MS = 5_000
const MAP_MIN_PX = 260
const MAP_FALLBACK = "45vh"

/** Map viewport height = camera panel height minus the map's own header, on
 *  the two-column layout only. Stacked (narrow) keeps the 45vh default. */
function useMatchedMapHeight() {
  const cameraRef = useRef<HTMLDivElement | null>(null)
  const mapWrapRef = useRef<HTMLDivElement | null>(null)
  const [height, setHeight] = useState<number | string>(MAP_FALLBACK)
  const heightRef = useRef<number | string>(MAP_FALLBACK)
  useLayoutEffect(() => {
    const cam = cameraRef.current
    const wrap = mapWrapRef.current
    if (!cam || !wrap) return
    const wide = window.matchMedia("(min-width: 1024px)")
    const measure = () => {
      if (!wide.matches) {
        if (heightRef.current !== MAP_FALLBACK) setHeight((heightRef.current = MAP_FALLBACK))
        return
      }
      const viewport = wrap.querySelector<HTMLElement>(".maplibregl-map")?.parentElement
      const header = viewport ? wrap.offsetHeight - viewport.offsetHeight : 0
      const next = Math.max(MAP_MIN_PX, Math.round(cam.offsetHeight - header))
      if (heightRef.current !== next) setHeight((heightRef.current = next))
    }
    const ro = new ResizeObserver(measure)
    ro.observe(cam)
    wide.addEventListener("change", measure)
    measure()
    return () => {
      ro.disconnect()
      wide.removeEventListener("change", measure)
    }
  }, [])
  return { cameraRef, mapWrapRef, height }
}
// ─── RANGER V3 END: 15-mission-live ───

export default function MissionControlPage() {
  // ─── RANGER V3 START: 14-mission-drive ───
  const canDrive = useAuthStore((s) => !!s.user && s.hasPermission("core.drive_robot"))
  const robotId = VIDEO_CONFIG.ok ? VIDEO_CONFIG.robotId : null

  let drive
  if (!robotId) {
    // 18-polish: user copy always; the env-var / command hint only in dev builds.
    drive = <DriveNote title="DRIVE UNAVAILABLE" lines={["No robot is paired with this console.", ...(import.meta.env.DEV ? ["Dev: set VITE_VIDEO_ROBOT_ID."] : [])]} />
  } else if (!canDrive) {
    drive = <DriveNote title="NO DRIVE PERMISSION" lines={["This account is not authorized to drive.", ...(import.meta.env.DEV ? ["Dev: needs core.drive_robot (grant_drive)."] : [])]} />
  } else {
    // keyed by robot: a config change tears the drive session down
    drive = <DrivePanel key={robotId} robotId={robotId} />
  }
  // ─── RANGER V3 END: 14-mission-drive ───
  // ─── RANGER V3 START: 15-mission-plan ───
  const accent = useAuthStore((s) => s.user?.organization?.theme_color ?? "#0ea5e9")
  const plan = useMissionPlan(robotId)
  // ─── RANGER V3 END: 15-mission-plan ───
  // ─── RANGER V3 START: 15-mission-live ───
  const accessToken = useAuthStore((s) => s.accessToken)
  const userId = useAuthStore((s) => s.user?.id)
  // A different user (or leaving the page) must never see the last one's feed.
  useEffect(() => () => {
    useLiveStore.getState().reset()
    useMissionLiveStore.getState().reset()
  }, [userId])
  const pos = useLiveStore((s) => (robotId ? s.positions[robotId] : undefined))
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1_000)
    return () => clearInterval(t)
  }, [])
  const stale = pos ? now - pos.receivedAt > STALE_MS : true
  const blips: FieldMapBlip[] = useMemo(() => {
    if (!pos) return []
    const status: FieldMapBlip["status"] = stale ? "offline" : pos.source === "live" ? "live" : "sim"
    return [{ id: pos.robot, lat: pos.lat, lng: pos.lon, status }]
  }, [pos, stale])
  const { cameraRef, mapWrapRef, height } = useMatchedMapHeight()
  // ─── RANGER V3 END: 15-mission-live ───

  return (
    <div className="p-[18px] flex flex-col gap-[18px]">
      {/* 18-polish: the "MSN · MISSION CONTROL" label repeated the TopBar title; removed */}
      {/* ─── RANGER V3 START: 15-mission-plan ─── */}
      {/* 15-mission-live: this page owns its own socket (the dashboard's unmounts with it) */}
      {accessToken ? <LiveFeed key={accessToken} token={accessToken} /> : null}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-[14px] items-start">
        <div ref={mapWrapRef}>
          <FieldMap
            accent={accent}
            height={height}
            expandable
            headerTitle="MAP"
            headerSub={robotId ?? undefined}
            waypoints={plan.mapWaypoints}
            onMapClick={plan.locked ? undefined : plan.addPoint}
            fitToWaypointsKey={plan.fitKey}
            blips={blips}
            showOverlays /* blips only: no readout is passed */
          />
        </div>
        <div ref={cameraRef}>
          <CameraPanel />
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-[14px] items-start">
        <MissionPlanPanel plan={plan} robotId={robotId} />
        {drive}
      </div>
      {/* ─── RANGER V3 END: 15-mission-plan ─── */}
    </div>
  )
}
// ─── RANGER V3 END: mission control page ───
