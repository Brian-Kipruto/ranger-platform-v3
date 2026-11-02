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
 * Config, the robot pairing and the frozen-frame watchdog live in lib/video.ts.
 *
 * 18-polish: EXPAND → fullscreen, the same way FieldMap does it — a CSS class
 * on the same Panel, never a portal or a second <img>. The MJPEG element is
 * not remounted by expanding, so the stream is not reopened and the Orin is
 * not asked to encode twice.
 */
import { useEffect, useRef, useState } from "react"
import { Panel } from "@/components/console/Panel"
import { MonoLabel } from "@/components/console/MonoLabel"
// ─── RANGER V3 START: 14-video ───
import {
  VIDEO_CONFIG,
  useAutoProfile,
  useFeedLiveness,
  type FeedState,
  type VideoMode,
  type VideoProfile,
} from "@/lib/video"

const STATUS: Record<FeedState, { text: string; tone: "ok" | "warn" | "alert" }> = {
  connecting: { text: "● CONNECTING", tone: "warn" },
  live: { text: "● LIVE", tone: "ok" },
  stale: { text: "● FEED STALE", tone: "alert" },
}

function fmtTime(ms: number | null): string {
  return ms === null ? "never" : new Date(ms).toLocaleTimeString([], { hour12: false })
}

interface CameraPanelProps {
  /** header label for the robot this feed belongs to */
  robotLabel?: string
}

export function CameraPanel({ robotLabel }: CameraPanelProps) {
  if (!VIDEO_CONFIG.ok) {
    return (
      <Panel
        title={`${robotLabel ?? "CAMERA"} · COLOR`}
        right={<MonoLabel size="xs" tone="alert">● NOT CONFIGURED</MonoLabel>}
      >
        <div className="relative bg-black aspect-[4/3] flex flex-col items-center justify-center gap-3 p-6">
          <MonoLabel size="md" tone="soft" tracking="0.13em">NO CAMERA PAIRED</MonoLabel>
          {/* 18-polish: config diagnostics only in dev builds */}
          {import.meta.env.DEV ? (
            <>
              {VIDEO_CONFIG.problems.map((p) => (
                <p key={p} className="font-mono text-[11px] text-alert text-center">{p}</p>
              ))}
              <p className="font-mono text-[11px] text-fg-faint max-w-[380px] text-center leading-[1.7]">
                Dev: set both in ranger_frontend/.env and restart the dev server.
              </p>
            </>
          ) : null}
        </div>
      </Panel>
    )
  }
  return (
    <LiveCamera
      robotLabel={robotLabel ?? VIDEO_CONFIG.robotId}
      baseUrl={VIDEO_CONFIG.baseUrl}
      streamUrls={VIDEO_CONFIG.streamUrls}
      snapshotUrl={VIDEO_CONFIG.snapshotUrl}
    />
  )
}

/**
 * An MJPEG <img> that closes its HTTP connection when it unmounts. Chrome does
 * not abort an in-flight image load when the element is removed, so a removed
 * MJPEG <img> keeps streaming and web_video_server keeps JPEG-encoding for it
 * (proven: two live streams from one /mission tab after a reconnect, ~1/3 of an
 * Orin core each). Pointing src at an empty data URI aborts the load. Covers
 * both reconnects (keyed remount) and leaving the page.
 *
 * The <img> is created per effect run, not rendered by React: StrictMode runs
 * mount -> cleanup -> mount in dev, and reusing one element left it aborted
 * ("NO STREAM" while LIVE). Each run owns its element and its error handler, so
 * the abort's own error event goes to a handler that is already detached.
 */
function MjpegStream({ src, alt, onError }: { src: string; alt: string; onError: () => void }) {
  const box = useRef<HTMLDivElement>(null)
  const onErrorRef = useRef(onError)
  useEffect(() => {
    onErrorRef.current = onError
  }, [onError])

  useEffect(() => {
    const parent = box.current
    if (!parent) return
    const img = document.createElement("img")
    img.alt = alt
    img.className = "w-full h-full object-contain"
    img.onerror = () => onErrorRef.current()
    img.src = src
    parent.appendChild(img)
    return () => {
      img.onerror = null
      img.src = "data:," // aborts the MJPEG load, closing the connection
      img.remove()
    }
  }, [src, alt])

  return <div ref={box} className="w-full h-full" />
}

interface LiveCameraProps {
  robotLabel: string
  baseUrl: string
  streamUrls: Record<VideoProfile, string>
  snapshotUrl: string
}

// ─── RANGER V3 START: 14-video-lowbw ───
const MODES: VideoMode[] = ["auto", "high", "low"]

function ModeToggle({ mode, onChange }: { mode: VideoMode; onChange: (m: VideoMode) => void }) {
  return (
    <div className="flex rounded border border-border overflow-hidden" role="group" aria-label="video quality">
      {MODES.map((m) => (
        <button
          key={m}
          onClick={() => onChange(m)}
          aria-pressed={mode === m}
          className={
            "font-mono text-[9px] px-2 py-[2px] tracking-[0.1em] " +
            (mode === m ? "bg-info/20 text-info" : "text-fg-faint hover:text-fg-soft")
          }
        >
          {m.toUpperCase()}
        </button>
      ))}
    </div>
  )
}
// ─── RANGER V3 END: 14-video-lowbw ───

function LiveCamera({ robotLabel, baseUrl, streamUrls, snapshotUrl }: LiveCameraProps) {
  // ─── RANGER V3 START: 14-video-lowbw ───
  const [mode, setMode] = useState<VideoMode>("auto")
  const auto = useAutoProfile()
  const { state, streamKey, lastOkAt, reconnect } = useFeedLiveness(snapshotUrl, auto.onProbe, auto.onStale)
  const profile: VideoProfile = mode === "auto" ? auto.profile : mode
  // a profile change is a new stream: the key remounts MjpegStream, which closes the old one
  const imgKey = `${streamKey}-${profile}`
  // ─── RANGER V3 END: 14-video-lowbw ───
  // the <img> that errored; a new key means a fresh attempt
  const [erroredKey, setErroredKey] = useState<string | null>(null)
  const imgFailed = erroredKey === imgKey
  const status = STATUS[state]
  // ─── RANGER V3 START: 18-polish ───
  const [expanded, setExpanded] = useState(false)
  // ─── RANGER V3 END: 18-polish ───

  return (
    <Panel
      // 18-polish: expanded = fixed fullscreen; the body flexes to fill it
      className={expanded ? "fixed inset-0 z-50 rounded-none flex flex-col" : undefined}
      bodyClassName={expanded ? "flex-1 min-h-0" : undefined}
      title={`${robotLabel} · COLOR`}
      right={
        <div className="flex items-center gap-3">
          <ModeToggle mode={mode} onChange={setMode} />
          {/* 18-polish: same control and styling as FieldMap's EXPAND */}
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="cursor-pointer font-mono text-[9px] rounded px-2 py-[3px] border border-border-strong-2 text-fg-muted hover:text-fg-soft hover:border-[#39414f] transition-colors"
          >
            {expanded ? "COLLAPSE ✕" : "EXPAND →"}
          </button>
          <MonoLabel size="xs" tone={status.tone}>
            {status.text}
            {state === "live" ? ` · ${profile.toUpperCase()}` : ""}
          </MonoLabel>
        </div>
      }
    >
      <div
        className={
          "relative bg-black flex items-center justify-center " +
          (expanded ? "h-full " : "aspect-[4/3] ") + // 18-polish
          (state === "stale" ? "outline outline-2 -outline-offset-2 outline-alert" : "")
        }
      >
        {!imgFailed ? (
          <MjpegStream
            key={imgKey}
            // _r forces a new HTTP connection on reconnect; web_video_server ignores it
            src={`${streamUrls[profile]}&_r=${streamKey}`}
            alt={`${robotLabel} live camera feed`}
            onError={() => setErroredKey(imgKey)}
          />
        ) : null}

        {state === "stale" ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/60">
            <MonoLabel size="md" tone="alert" tracking="0.13em">FEED STALE · LAST FRAME</MonoLabel>
            <p className="font-mono text-[11px] text-fg-soft text-center leading-[1.7]">
              Do not drive on this image.
              <br />
              {/* 18-polish: the stream address is shown in dev builds only */}
              No new frame since {fmtTime(lastOkAt)} · retrying{import.meta.env.DEV ? ` ${baseUrl}` : ""}
            </p>
            <button
              onClick={reconnect}
              className="font-mono text-[10px] px-3 py-1 rounded border border-border text-fg-soft hover:text-fg"
            >
              RECONNECT
            </button>
          </div>
        ) : null}

        {imgFailed && state !== "stale" ? (
          <div className="flex flex-col items-center gap-3">
            <MonoLabel size="sm" tone="soft" tracking="0.13em">NO STREAM{import.meta.env.DEV ? ` FROM ${baseUrl}` : ""}</MonoLabel>
            <button
              onClick={reconnect}
              className="font-mono text-[10px] px-3 py-1 rounded border border-border text-fg-soft hover:text-fg"
            >
              RECONNECT
            </button>
          </div>
        ) : null}
      </div>
    </Panel>
  )
}
// ─── RANGER V3 END: 14-video ───
// ─── RANGER V3 END: camera panel ───
