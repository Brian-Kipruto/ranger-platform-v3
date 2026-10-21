# 040 — `web_video_server` RSS jumps after an outage: queued `/snapshot` probes

*Date: 2026-10-19*

---

## What we saw

A long-lived `web_video_server` at RSS 1.3 GB (16.7% of the Orin's RAM). Steady state
was flat; from a fresh 92 MB, a 30 s camera outage with `/mission` open left it at
**361 MB, flat** (+268 MB) once frames returned.

## The cause

The first watchdog design aborted each `/snapshot` probe after 1 s and sent another
every second. The browser abort closes the client side, but the server keeps each
request queued until a frame exists — then serves them all at once. ~30 queued
probes × ~9 MB each burst on recovery, and the allocator keeps the peak. A 5-minute
outage would be about 2.7 GB.

## The fix

**At most one probe outstanding** (ADR-0024): the probe stays open until it
completes; STALE is "no completed probe for 2.5 s"; a dead server fails fast and is
retried each second; an open probe is abandoned only after 20 s. Proven: same 30 s
outage, **+6 MB**. Sandbox harness: 2 probes per 30 s hang (old design 24).

## Prevention

- A probe that "times out" client-side may still cost the server. Ask what an
  abandoned request does on the other end.
- `stack_up.sh`'s own frame check waits for the publisher first, then makes at most
  two long `/snapshot` requests.
