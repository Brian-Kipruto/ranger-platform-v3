# 049 — No robot blip on the mission map: `FieldMap` draws blips only with `showOverlays`

*Date: 2026-10-30 · caught in the sandbox before handoff*

---

## What we saw

6c browser run: waypoints ticked green live, the label stepped to `3/3 ·
COMPLETED` — and `.maplibregl-marker` counted 3 (the waypoints), not 4. The live rows
were arriving (the same socket carried the progress events).

## The cause

`MissionControlPage` passed `blips` but not `showOverlays`. `FieldMap`'s blip effect
returns early unless `showOverlays` is true (it defaults to false; Data Explorer relies
on that).

## The fix

Pass `showOverlays`. No `readout` is passed, so the telemetry readout stays hidden
(`showOverlays && readout`).

## Prevention

A new `FieldMap` caller checks the prop that gates what it wants drawn:
`showOverlays` (blips, readout), `waypoints`, `onMapClick`.
