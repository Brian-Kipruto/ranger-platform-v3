# 055 — Map blank on `vite preview`, fine on the dev server

*Date: 2026-11-02*

---

## What we saw

`npx vite preview --port 4173` after `npm run build`, logged in, `/mission`: the map
panel draws its controls, the scale bar and a bare "MapLibre" attribution, but no tiles
and no MapTiler attribution. The same page on `localhost:5173` renders the basemap.
Not "MAP UNAVAILABLE", so `VITE_MAPTILER_KEY` was compiled in.

## The cause (likely; not yet confirmed in DevTools)

The MapTiler key is restricted to allowed origins, and `http://localhost:4173` is not
one of them. The style request is refused, so neither tiles nor the style's own
attribution load.

## How to confirm

DevTools → Network on `:4173`, filter `maptiler`: the style request
(`api.maptiler.com/maps/…/style.json?key=…`) returns 403. On `:5173` it returns 200.

## The fix

MapTiler Cloud → the key → Allowed origins: add each origin that serves the console
(the preview port for local checks; the production domain before S2). Do not remove the
restriction.

## Prevent

The S2 deploy checklist includes "production origin added to the MapTiler key", and the
first post-deploy check is the basemap, not the login.
