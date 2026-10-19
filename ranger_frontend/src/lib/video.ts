// ─── RANGER V3 START: 14-video ───
/**
 * Robot video config and feed liveness (F14 5b).
 *
 * The feed is MJPEG from ROS web_video_server on the robot, fetched directly by
 * the browser (fork 4: no Django proxy; bound to the tether address, firewalled
 * to the console PC at 4d).
 *
 * One video server = one robot. VITE_VIDEO_ROBOT_ID names the robot that feed
 * belongs to, so Mission Control can never pair one robot's camera with another
 * robot's drive panel. Both must be set; there is no localhost fallback.
 *
 * Why a watchdog: when the camera dies, an open MJPEG <img> keeps showing its
 * last frame and never errors (proven: /stream stays 200 with 0 frames). A
 * frozen frame looks live, which is dangerous while driving. web_video_server
 * sends no CORS headers, so the page can't read frames or status codes; it can
 * only see whether a request completes. /snapshot waits for a NEW frame and
 * hangs when none come (proven: code=000 at timeout), so a completed snapshot
 * request = frames are flowing.
 *
 * At most ONE probe is outstanding. Each hanging /snapshot stays queued on
 * web_video_server until frames return, then all are served at once: aborting
 * and re-probing every second during a 30 s outage left ~30 queued and cost
 * +268 MB RSS on recovery (92 -> 361 MB, kept by the allocator); 5 min would be
 * ~2.7 GB. So a probe stays open until it completes; STALE = no completed probe
 * for STALE_AFTER_MS. A dead server fails fast and is retried each second; an
 * open probe is abandoned after PROBE_MAX_OPEN_MS so a half-open connection
 * can't wedge the watchdog (bound: 3 queued per minute of outage).
 * Worst case ~2.5 s from the last frame to STALE; LIVE as soon as a fresh frame
 * exists.
 */
import { useCallback, useEffect, useState } from "react"

export const COLOR_TOPIC = "/camera/color/image_raw"

/**
 * JPEG quality per stream (web_video_server default 95). Measured on the Orin,
 * 640x480@30, one viewer: q95 57 kB/frame (1.7 MB/s, wvs 42% CPU), q70 25 kB
 * (0.76 MB/s, 40%), q50 14 kB (0.44 MB/s, 37%). q70 looks the same as q95 on
 * screen at 2.3x less bandwidth; quality barely moves CPU. The probe only needs
 * to complete, so it asks for the cheapest frame.
 */
export const STREAM_QUALITY = 70
export const PROBE_QUALITY = 50

export const PROBE_INTERVAL_MS = 1000 // at most one probe start per second
export const STALE_AFTER_MS = 2500 // no completed probe for this long = STALE
export const PROBE_MAX_OPEN_MS = 20000 // abandon a probe open longer than this
const CHECK_MS = 250

const ROBOT_ID_RE = /^[A-Za-z0-9._-]+$/

export type VideoConfig =
  | {
      ok: true
      baseUrl: string
      robotId: string
      streamUrl: string
      snapshotUrl: string
    }
  | { ok: false; problems: string[] }

export function parseVideoConfig(rawUrl: string | undefined, rawRobotId: string | undefined): VideoConfig {
  const problems: string[] = []
  const url = (rawUrl ?? "").trim()
  const robotId = (rawRobotId ?? "").trim()

  let baseUrl = ""
  if (!url) {
    problems.push("VITE_VIDEO_SERVER_URL not set")
  } else {
    try {
      const u = new URL(url)
      if (u.protocol !== "http:" && u.protocol !== "https:") throw new Error("scheme")
      baseUrl = u.origin
    } catch {
      problems.push(`VITE_VIDEO_SERVER_URL invalid: ${url}`)
    }
  }

  if (!robotId) {
    problems.push("VITE_VIDEO_ROBOT_ID not set")
  } else if (!ROBOT_ID_RE.test(robotId)) {
    problems.push(`VITE_VIDEO_ROBOT_ID invalid: ${robotId}`)
  }

  if (problems.length) return { ok: false, problems }

  // raw slashes, as proven with curl; don't assume web_video_server URL-decodes
  const topic = COLOR_TOPIC
  return {
    ok: true,
    baseUrl,
    robotId,
    streamUrl: `${baseUrl}/stream?topic=${topic}&type=mjpeg&quality=${STREAM_QUALITY}`,
    snapshotUrl: `${baseUrl}/snapshot?topic=${topic}&quality=${PROBE_QUALITY}`,
  }
}

export const VIDEO_CONFIG: VideoConfig = parseVideoConfig(
  import.meta.env.VITE_VIDEO_SERVER_URL as string | undefined,
  import.meta.env.VITE_VIDEO_ROBOT_ID as string | undefined,
)

export type FeedState = "connecting" | "live" | "stale"

export interface FeedLiveness {
  state: FeedState
  /** bump = remount the stream <img> (fresh connection) */
  streamKey: number
  /** wall-clock ms of the last probe that saw a frame */
  lastOkAt: number | null
  reconnect: () => void
}

export function useFeedLiveness(snapshotUrl: string): FeedLiveness {
  const [state, setState] = useState<FeedState>("connecting")
  const [streamKey, setStreamKey] = useState(0)
  const [lastOkAt, setLastOkAt] = useState<number | null>(null)

  const reconnect = useCallback(() => setStreamKey((k) => k + 1), [])

  useEffect(() => {
    let cancelled = false
    let inflight: AbortController | null = null
    let inflightSince = 0
    let lastStart = -Infinity
    let lastOk = performance.now() // grace from mount: "connecting", not STALE
    let stale = false
    let startTimer: number | undefined

    const startProbe = () => {
      if (cancelled || inflight) return
      const ctrl = new AbortController()
      inflight = ctrl
      inflightSince = performance.now()
      lastStart = inflightSince
      // no-cors: opaque response, but it only resolves if the server answered,
      // and /snapshot only answers once a fresh frame exists.
      fetch(snapshotUrl, { mode: "no-cors", cache: "no-store", signal: ctrl.signal })
        .then(() => {
          if (cancelled || inflight !== ctrl) return
          inflight = null
          lastOk = performance.now()
          setLastOkAt(Date.now())
          if (stale) {
            stale = false
            console.info(`[video] LIVE ${new Date().toISOString()} (recovered, reconnecting stream)`)
            setStreamKey((k) => k + 1) // the old <img> connection is dead or frozen
          }
          setState("live")
          schedule()
        })
        .catch(() => {
          if (cancelled || inflight !== ctrl) return
          inflight = null // server unreachable: nothing left queued on it
          schedule()
        })
    }

    const schedule = () => {
      window.clearTimeout(startTimer)
      const wait = Math.max(0, lastStart + PROBE_INTERVAL_MS - performance.now())
      startTimer = window.setTimeout(startProbe, wait)
    }

    const check = window.setInterval(() => {
      const now = performance.now()
      if (inflight && now - inflightSince > PROBE_MAX_OPEN_MS) {
        inflight.abort() // its catch sees inflight !== ctrl and does nothing
        inflight = null
        startProbe()
      }
      if (!stale && now - lastOk > STALE_AFTER_MS) {
        stale = true
        console.info(`[video] STALE ${new Date().toISOString()} (no frame for ${Math.round(now - lastOk)} ms)`)
        setState("stale")
      }
    }, CHECK_MS)

    startProbe()
    return () => {
      cancelled = true
      window.clearTimeout(startTimer)
      window.clearInterval(check)
      inflight?.abort()
    }
  }, [snapshotUrl])

  return { state, streamKey, lastOkAt, reconnect }
}
// ─── RANGER V3 END: 14-video ───
