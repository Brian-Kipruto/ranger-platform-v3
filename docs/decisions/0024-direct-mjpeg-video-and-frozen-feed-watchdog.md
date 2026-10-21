# ADR-0024: Direct MJPEG from the Orin, one feed per robot, and a frozen-feed watchdog

- **Status:** Accepted (proven live, over the tether and over Wi-Fi)
- **Date:** 2026-10-19
- **Feature:** F14 (Drive and Video), checkpoint 5b
- **Related:** ADR-0026 (firewall), ADR-0023 (teleop), TS-039, TS-040

## Context

The Orbbec Gemini 2 is on the Orin; the console runs on the PC. Video is MB/s of
binary and must not ride the JSON telemetry path. The operator drives by this
picture, so a frozen picture that looks live is a safety problem, not a cosmetic one.

## Decision 1 — `web_video_server` on the Orin, MJPEG straight to the browser

- Bound to one address (`--video-bind`: the tether or the Wi-Fi address, never
  `0.0.0.0`), and firewalled to the console PC (ADR-0026).
- **Rejected for now: proxying through Django.** One ASGI worker per viewer, extra
  latency and code, for a gain (auth) the firewall and a single console machine
  already give. **Future upgrade:** an authenticated or proxied feed if anyone but
  the console PC must watch.
- **Quality q70** (`STREAM_QUALITY`): looks the same as q95 on screen at 2.3× less
  bandwidth (25 vs 57 kB/frame, 0.76 vs 1.7 MB/s at 30 fps). Quality barely moves
  CPU (40% vs 42%); the CPU levers are fps, resolution, or a compressed passthrough.
- `web_video_server` encodes per client: keep viewers to one or two.

## Decision 2 — One video server is one robot

`VITE_VIDEO_SERVER_URL` and `VITE_VIDEO_ROBOT_ID` are both required; missing or
malformed → `NOT CONFIGURED`, never a `localhost` fallback. Mission Control's
`DrivePanel` drives `VITE_VIDEO_ROBOT_ID` — never a picker — so the camera and the
drive panel can't belong to different robots. The dashboard DRIVE panel stays; the
one-driver lease (4409) makes two placements safe. Under `ranger_up` the URL follows
the link (ADR-0025).

## Decision 3 — A watchdog, because a dead feed doesn't error

Proven: when the camera dies, `/stream` stays HTTP 200 with zero frames and the
`<img>` keeps its last frame with no error event. With no CORS headers the page can
read neither frames nor status codes — only whether a request completes.
`/snapshot` waits for a **new** frame and hangs when none come. So:

- **At most one probe outstanding.** A `no-cors` fetch of `/snapshot?quality=50`;
  completion = frames are flowing. Next probe at most once a second.
- **STALE** when no probe has completed for 2.5 s: red outline, `FEED STALE · LAST
  FRAME`, "Do not drive on this image", the time of the last frame.
- **Recovery:** the pending probe completes the moment a frame exists → LIVE and the
  stream reconnects.
- **An open probe is abandoned after 20 s**, so a half-open connection can't wedge
  the watchdog.
- **Rejected: abort-and-reprobe every second.** Abandoned `/snapshot` requests stay
  queued on the server and are all served when frames return: +268 MB RSS per 30 s
  of outage (about 2.7 GB for 5 minutes). Single probe: +6 MB (TS-040).

Measured: last frame → STALE 2.95 s; frames back → LIVE 0.12–0.9 s; with the
threshold disabled, a dead camera shows LIVE for 38 s+.

## Decision 4 — Each MJPEG `<img>` closes its own connection

Chrome does not abort an image load when the element is removed; a removed MJPEG
`<img>` keeps streaming and the server keeps encoding for it (TS-039). `MjpegStream`
creates one `<img>` per effect run and on cleanup detaches its error handler, sets
`src = "data:,"` and removes it. One element per run because React StrictMode mounts
twice in dev; reusing the element left it aborted.

## Consequences

- One viewer costs about 0.7 of an Orin core (driver + server) and +0.38 W.
- The feed is unauthenticated on the wire; the firewall is the control.
