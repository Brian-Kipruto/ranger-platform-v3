# 020 — A rewritten renderer changed nothing on screen: `max-age` served an hour-old PNG without asking

*Date: 2026-08-07*

---

## What we saw

F10.3 CP4.1 replaced the raster renderer. Index layers had been rendering as a
flat wash — NDVI over arid Marsabit occupies roughly 0.11–0.17 of a −1…1 ramp,
so every pixel landed in the same two adjacent colours — and the fix was a
percentile stretch to the scene's own range, plus a legend reporting that
range.

The backend landed. Tests passed. The screen did not change.

```
NDVI  — flat pale yellow-green rectangle, no structure
legend — absent
```

Neither symptom moved after any of:

- replacing `render.py`, `views.py` and the frontend files
- `Ctrl+Shift+R` on the page
- DevTools → Network → *Disable cache*
- deleting every cached PNG under `media/satellite/`

The renderer looked broken, and it was the only thing that had just changed.

## The clue that pointed elsewhere

`render_png` writes a JSON sidecar beside every PNG it produces, unconditionally,
before the response is built. So:

```bash
$ ls -l ranger_backend/media/satellite/knra/s2/
...T37NCE.ndvi.png          # exists
...T37NCE.ndvi.png.json     # DOES NOT EXIST
```

A missing sidecar means `render_png` never ran. Not "ran and produced bad
pixels" — never ran at all. And `cached_or_render` treats a missing sidecar as
a cache miss, so it could not have been skipped.

That rules out the renderer entirely and leaves one possibility: **the request
never reached Django.**

## The cause

The render endpoint originally answered with:

```python
response["Cache-Control"] = "private, max-age=3600"
```

`max-age=3600` tells the browser its stored copy is *fresh for an hour* — not
"check with the server", but "do not ask". Every subsequent request for that
URL was answered from disk cache locally. Django logged nothing because nothing
arrived. The pixels on screen were produced by code that no longer existed on
disk.

Confirmed by simulating both code paths against the scene's real band
percentiles (B4 p2/p50/p98 = 1810/2480/2991, B8 = 2565/3242/3757):

| Ramp domain | Unique colours | Channel spread |
|---|---|---|
| Percentile (new) | 670 | R 26–245, G 54–231, B 42–159 |
| Absolute −1…1 (old) | 163 | R 151–245, G 184–231, B 113–159 |

The absolute-domain range *is* pale yellow-green. The screen was showing old
code's output, exactly.

## Why the hard reload didn't help

This is the part that made the diagnosis take an hour instead of a minute.

`Ctrl+Shift+R` forces revalidation for **the document and the subresources the
reload itself fetches**. It does not extend to an XHR fired later by JavaScript
— and this PNG is fetched by axios when the user clicks a layer, well after
load. That request follows ordinary cache rules and hit the same fresh entry.

So the standard remedy for "I changed it and the browser is showing the old
one" genuinely does not apply here, which made the browser look innocent.

Deleting the server-side PNGs was equally useless for the same reason: nothing
was asking the server for them.

## The fix

Two halves, deliberately redundant.

**Server** — revalidate rather than assume:

```python
etag = f'"{png.stat().st_mtime_ns:x}-{layer.key}"'
if request.headers.get("If-None-Match") == etag:
    return HttpResponseNotModified()
response["Cache-Control"] = "private, no-cache, max-age=0"
response["ETag"] = etag
```

`no-cache` does **not** mean "do not store". It means "store it, but ask before
reusing it". An unchanged render answers 304 with no body — the same bandwidth
saving, none of the staleness. The ETag includes the layer key so an NDVI
response can never satisfy a BSI request.

**Client** — don't depend on what a browser already holds:

```ts
headers: { "Cache-Control": "no-cache" }
```

The server fix only governs responses fetched *from now on*. Entries already
stored under `max-age=3600` stay fresh until they expire, so without the client
header the bug persists for an hour after the fix ships — on exactly the
machine you are testing on.

## The lesson

**`max-age` on anything under active development can make a code change
invisible for its full duration, and the symptom is indistinguishable from a
bug in the code you just changed.**

Three things made this expensive:

1. The failure had no error. No log line, no console warning, no failed
   request — the browser succeeded, quickly, with the wrong bytes.
2. The obvious remedy (hard reload) genuinely does not cover JS-initiated
   XHRs, so ruling out caching *felt* justified.
3. Every piece of evidence pointed at the thing that had just changed.

What broke the deadlock was an artefact the new code writes unconditionally.
The sidecar was added for the legend, not for debugging, but "this file exists
if and only if the new function ran" turned an ambiguous visual symptom into a
one-line filesystem check. Cheap side effects that prove execution are worth
more than they look.

`no-cache` + ETag should be the default for any authenticated, regenerable
artefact. The bandwidth argument for `max-age` is worth almost nothing here —
a 304 is a few hundred bytes — and the cost is a class of bug that hides
itself.

## Related

- ADR-0013 §1 — raster delivery via rendered PNG, and why not tile URLs
- 013 — TS server phantom module errors (same family: a stale cache presenting
  as a code defect)
