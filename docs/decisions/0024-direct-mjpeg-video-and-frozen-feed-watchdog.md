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

## Addendum (2026-10-24) — low-bandwidth profiles, auto with hysteresis

Outdoors at the house the Orin's Wi-Fi **send** rate fell to 6.5–19.5 Mbit/s (MCS 0–2,
single stream) at −57 to −72 dBm while drive kept working; HIGH (~6 Mbit/s) didn't fit
and the feed sat on STALE (TS-044). Decision:

- **Two profiles**, both plain `web_video_server` request parameters (it scales and
  encodes; nothing changes on the Orin): **HIGH** 640×480 q70 (25.4 kB/frame,
  ~6 Mbit/s) and **LOW** 320×240 q40 (4.8 kB/frame, ~1 Mbit/s).
- **The probe shrinks** to 160×120 q30 (1.9 kB) so it barely loads the link.
- **AUTO** (default): down to LOW after 2 consecutive probes slower than 600 ms, or on
  STALE; up to HIGH only after probes faster than 200 ms continuously for 15 s. A pure
  function (`nextAuto`) holds the rules.
- **Manual AUTO / HIGH / LOW** toggle on the panel; the status reads `LIVE · LOW`.
- A profile change is a new stream: the `<img>` remounts and the old connection closes
  (Decision 4 still holds; one stream per tab verified after switches).
- **The watchdog is unchanged.** If even LOW gets no frame for 2.5 s, it is STALE.

**Measured (2026-10-24, same walk as before):** AUTO went LOW on the first STALE and
back to HIGH ~15 s after the link recovered indoors, with no flapping. Outside, at
−63 to −75 dBm and mostly 6.5 Mbit/s, the feed was LIVE ~85% of a minute (before:
~0%), with 6 stalls of 0.03–6.1 s where the link delivered nothing. When the link
collapses the probe doesn't come back slow, it doesn't come back — STALE, not RTT, is
what triggered the step down. Sandbox (fake timers, real hook): saturated → LOW in
2.9 s; marginal 300 ms → stays LOW; recovery → HIGH only after the 15 s hold; three
threshold mutants each change the timeline.

**Not done, on purpose:** loosening STALE to hide link dropouts, and a still lower
tier. The remaining stalls are RF (TS-044): antennas, then router placement.
