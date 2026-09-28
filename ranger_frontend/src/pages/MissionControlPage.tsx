// ─── RANGER V3 START: mission control page ───
/**
 * MissionControlPage — first real cut of Mission Control. For now it hosts the
 * live camera feed (Orbbec color via ROS web_video_server). The mission map,
 * waypoint list, and command panel land in later passes; this replaces the
 * StubPage so the screen shows real live data instead of a placeholder.
 */
import { MonoLabel } from "@/components/console/MonoLabel"
import { CameraPanel } from "@/components/camera/CameraPanel"

export default function MissionControlPage() {
  return (
    <div className="p-[18px] flex flex-col gap-[18px]">
      <div className="flex items-center justify-between">
        <MonoLabel size="md" tone="soft" tracking="0.13em">
          MSN · MISSION CONTROL
        </MonoLabel>
        <MonoLabel size="xs" tone="ok">● LIVE FEED</MonoLabel>
      </div>

      {/* Camera feed — the first real Mission Control element. */}
      <div className="max-w-[860px]">
        <CameraPanel robotLabel="RANGER PRIME" />
      </div>
    </div>
  )
}
// ─── RANGER V3 END: mission control page ───
