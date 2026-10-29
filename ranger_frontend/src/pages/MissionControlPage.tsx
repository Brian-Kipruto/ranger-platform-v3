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
import { FieldMap } from "@/components/map/FieldMap"
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

export default function MissionControlPage() {
  // ─── RANGER V3 START: 14-mission-drive ───
  const canDrive = useAuthStore((s) => !!s.user && s.hasPermission("core.drive_robot"))
  const robotId = VIDEO_CONFIG.ok ? VIDEO_CONFIG.robotId : null

  let drive
  if (!robotId) {
    drive = <DriveNote title="DRIVE UNAVAILABLE" lines={["No robot is paired with the video feed.", "Set VITE_VIDEO_ROBOT_ID."]} />
  } else if (!canDrive) {
    drive = <DriveNote title="NO DRIVE PERMISSION" lines={["Needs core.drive_robot (Drivers group).", "Ask an admin to run grant_drive."]} />
  } else {
    // keyed by robot: a config change tears the drive session down
    drive = <DrivePanel key={robotId} robotId={robotId} />
  }
  // ─── RANGER V3 END: 14-mission-drive ───
  // ─── RANGER V3 START: 15-mission-plan ───
  const accent = useAuthStore((s) => s.user?.organization?.theme_color ?? "#0ea5e9")
  const plan = useMissionPlan(robotId)
  // ─── RANGER V3 END: 15-mission-plan ───

  return (
    <div className="p-[18px] flex flex-col gap-[18px]">
      <div className="flex items-center justify-between">
        <MonoLabel size="md" tone="soft" tracking="0.13em">
          MSN · MISSION CONTROL
        </MonoLabel>
      </div>

      {/* ─── RANGER V3 START: 15-mission-plan ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-[14px] items-start">
        <FieldMap
          accent={accent}
          height="45vh"
          expandable
          headerTitle="MAP"
          headerSub={robotId ?? undefined}
          waypoints={plan.mapWaypoints}
          onMapClick={plan.locked ? undefined : plan.addPoint}
          fitToWaypointsKey={plan.fitKey}
        />
        <CameraPanel />
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
