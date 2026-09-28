// ─── RANGER V3 START: camera panel ───
/**
 * CameraPanel — live MJPEG feed from a robot camera, served by ROS
 * web_video_server. This is intentionally a plain <img> pointing at the
 * stream endpoint: web_video_server does the MJPEG encoding, the browser
 * decodes it natively, no decode logic needed here.
 *
 * The feed is a SEPARATE transport from the telemetry path (rosbridge →
 * SensorLog). Video is MB/s of binary and must not go through the JSON/
 * WebSocket sensor path. Great on LAN; degrades over LTE (drop fps/res).
 *
 * URL comes from VITE_VIDEO_SERVER_URL so localhost-dev vs on-robot (the
 * Orin's address) is a one-line .env change, no code edit.
 */
import { useState } from "react"
import { Panel } from "@/components/console/Panel"
import { MonoLabel } from "@/components/console/MonoLabel"

const VIDEO_BASE =
  (import.meta.env.VITE_VIDEO_SERVER_URL as string | undefined) ??
  "http://localhost:8080"

// Orbbec Gemini 2 color topic (confirmed via `ros2 topic list`).
const COLOR_TOPIC = "/camera/color/image_raw"

const STREAM_URL = `${VIDEO_BASE}/stream?topic=${COLOR_TOPIC}&type=mjpeg`

interface CameraPanelProps {
  /** header label for the robot this feed belongs to */
  robotLabel?: string
}

export function CameraPanel({ robotLabel = "RANGER PRIME" }: CameraPanelProps) {
  const [status, setStatus] = useState<"live" | "offline">("live")

  return (
    <Panel
      title={`${robotLabel} · COLOR`}
      right={
        <MonoLabel size="xs" tone={status === "live" ? "ok" : "alert"}>
          {status === "live" ? "● LIVE" : "● OFFLINE"}
        </MonoLabel>
      }
    >
      <div className="relative bg-black aspect-video flex items-center justify-center">
        {status === "live" ? (
          // key forces a fresh <img> (reconnect) if we ever toggle back to live
          <img
            key="camera-stream"
            src={STREAM_URL}
            alt={`${robotLabel} live camera feed`}
            className="w-full h-full object-contain"
            onError={() => setStatus("offline")}
          />
        ) : (
          <div className="flex flex-col items-center gap-3 py-[60px]">
            <MonoLabel size="md" tone="soft" tracking="0.13em">
              CAMERA OFFLINE
            </MonoLabel>
            <p className="font-mono text-[11px] text-fg-faint max-w-[360px] text-center leading-[1.7]">
              No stream from {VIDEO_BASE}. Confirm the camera driver and
              web_video_server are running on the robot / dev host.
            </p>
            <button
              onClick={() => setStatus("live")}
              className="font-mono text-[10px] px-3 py-1 rounded border border-border text-fg-soft hover:text-fg"
            >
              RETRY
            </button>
          </div>
        )}
      </div>
    </Panel>
  )
}
// ─── RANGER V3 END: camera panel ───
