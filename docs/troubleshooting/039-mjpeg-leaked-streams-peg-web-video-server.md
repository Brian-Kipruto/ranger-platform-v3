# 039 — `web_video_server` at 100% CPU: leaked MJPEG streams from one tab

*Date: 2026-10-19*

---

## What we saw

After a few camera kill/restart cycles, `web_video_server` sat at 100% of a core and
the camera topic dropped to 5–10 Hz. With only one `/mission` tab open, the Orin
showed **two** established `:8080` connections, each growing ~3.4 MB per 2 s — both
full 30 fps streams. Their byte totals dated them: one from page load, one from the
reconnect.

## The cause

Two things stacked:

1. **`web_video_server` encodes per client.** Every open stream is its own JPEG
   encode per frame. An old raw `/stream` tab was also still open: three streams, one
   core.
2. **Chrome does not abort an image load when the `<img>` is removed.** The watchdog's
   reconnect remounted the `<img>`; the old one kept streaming and the server kept
   encoding for it. Leaving the page leaked the same way.

The first fix (set `src` to `data:,` on unmount, reusing the element) then showed
**"NO STREAM" while LIVE** in dev: React StrictMode mounts → cleans up → mounts; the
cleanup aborted the element and the second mount reused it without restoring `src`.

## The fix

`MjpegStream` creates a fresh `<img>` per effect run; cleanup detaches its error
handler, sets `src = "data:,"` (aborts the load, closes the connection) and removes
it. Proven: one stream after a camera reconnect, a `web_video_server` reconnect and a
page round trip; zero after leaving the page.

## Prevention

- Count clients when CPU looks wrong: `ss -tni state established '( sport = :8080 )'`
  — a connection whose `bytes_sent` grows ~3 MB / 2 s is a stream.
- Anything that must release a resource on unmount owns a fresh one per effect run.
