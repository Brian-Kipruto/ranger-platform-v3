# 011 — Map points silently missing (map-data fetch vs MapLibre load race)

> Feature 05b. Severity: medium (silent data loss in the UI, no error).

## Symptom

On the Data Explorer page, the MapLibre map rendered the basemap correctly and
clicking a table row flew the map to that point and dropped a highlight marker —
but the ~230 teal track points never appeared. No console error, no network
error. The map looked alive; the data layer was just empty.

## Diagnosis

The contrast was the clue: row-click worked, track points didn't. The yellow
highlight marker is added directly in the click handler (no dependency on the
GeoJSON source). The track points go through
`map.getSource("track").setData(fc)`. So the failure was specifically in
getting the fetched GeoJSON into the source — and that path has a race.

The map-data `useEffect` fires when `appliedFilters` changes, which includes the
initial mount (empty filters → fetch). But the `"track"` source and its circle
layer are created inside `map.on("load", ...)`, which fires asynchronously after
the map finishes initialising. On first load the fetch could resolve **before**
the `load` event, so `map.getSource("track")` returned `undefined`. The code
guarded against that by doing nothing if the source was missing — so the fetched
track was silently discarded and never re-applied. Row-click worked later only
because by then `load` had fired.

So: the data fetch won the race against map load, and the result was dropped on
the floor. No error because the undefined-source branch was a deliberate (but
incomplete) guard.

## Fix

Close the race from both sides:

1. Stash the most recent fetched track in a ref (`pendingTrack`).
2. In the `load` handler, after creating the source/layer, apply
   `pendingTrack.current` if a fetch already landed.
3. Add a `mapReady` state flag, set true in the `load` handler, and include it
   in the map-data effect's dependency array — so if the map finishes loading
   *after* the effect first ran, the effect re-runs and applies the data to the
   now-existing source.

Whichever wins — fetch first or load first — the track gets applied. Belt and
suspenders, because async map-load timing isn't something to leave to chance.

## Lesson

Any time data is pushed into a map source from an async fetch, the map's `load`
(or `style.load`) event is a second async actor and the two can race. Don't just
no-op when the source is missing — stash the data and re-apply on load, and/or
gate the data effect on a "map ready" flag. The failure mode is silent (empty
layer, no error), which makes it easy to ship.

## Related

- `features/05-data-explorer.md`