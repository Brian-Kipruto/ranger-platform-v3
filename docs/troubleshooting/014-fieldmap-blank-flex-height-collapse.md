# 014 — FieldMap renders blank (flex-1 collapsed the map container to 0px)

*Date: 2026-06-25*

---

## What we saw

After refactoring the Data Explorer onto the new shared `<FieldMap>` component
(F07 CP2), the Data Explorer map area was **completely blank** — no tiles, no
track. But the map panel's header rendered fine, including the new SAT / VECTOR /
TOPO basemap toggle buttons. `npx tsc -b` and `npm run build` were both clean.
No console errors.

So: the component mounted, the header rendered, but the map canvas showed
nothing.

## What caused it

The first version of `<FieldMap>` structured the viewport like this:

```tsx
<div className="...flex flex-col">          {/* outer wrapper, flex column */}
  <div>...header...</div>                    {/* flex-none */}
  <div className="relative flex-1" style={{ height }}>   {/* viewport */}
    <div ref={mapContainer} className="absolute inset-0" />
  </div>
</div>
```

The viewport div had **both** `flex-1` and an explicit `height`. Inside a
`flex flex-col` parent that itself had no height constraint, `flex-1`
(`flex-basis: 0`) won and computed the viewport height as **0px** — the explicit
`height` was overridden by the flex sizing. The map container (`absolute inset-0`)
then filled a 0px-tall parent, so MapLibre rendered 0px tall and showed nothing.

This is exactly the failure mode the original Data Explorer code warned about in
a comment ("The container needs an explicit height or MapLibre renders 0px
tall") — reintroduced by the new component's layout. The original DE map worked
because its container was a plain `<div style={{height:"68vh"}}>` with no flex
ancestor competing for the height.

The basemap toggle still showed because it lives in the header, which had its own
intrinsic height and was unaffected.

## How we fixed it

Drop `flex-1` from the viewport so the explicit `height` is authoritative, and
let the container fill it directly:

```tsx
<div className="relative" style={{ height }}>
  <div ref={mapContainer} className="absolute inset-0 w-full h-full" />
</div>
```

The outer `flex flex-col` was also removed (no flex children depend on it now —
header + viewport stack as normal blocks). For the expand-to-fullscreen case, the
viewport height becomes `calc(100vh - 54px)` when expanded; `map.resize()` runs
on the next animation frame after the size change.

## How to prevent it

- **When a map (or any element needing explicit pixel height) lives inside a
  flex container, don't also give it `flex-1`.** Pick one: either the flex parent
  sizes it (and the parent must have a real height), or the element sizes itself
  with an explicit height (and no `flex-1`). Mixing them collapses to 0.
- **A clean `tsc -b` / `vite build` does NOT catch this** — it's a runtime layout
  result, not a type or syntax error. The build passing told us nothing here.
- **When porting a working map setup into a new component, port its container
  sizing model too**, not just the JS lifecycle. The DE map's "plain div with
  explicit height" was load-bearing; wrapping it in flex broke it.
- Symptom signature to recognize: map **header/controls render but the canvas is
  blank**, with no errors → suspect a 0px-tall map container first.