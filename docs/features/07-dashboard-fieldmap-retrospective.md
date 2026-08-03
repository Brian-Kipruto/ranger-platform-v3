# Feature 07 — Retrospective

*Date: 2026-06-25*

---

## What worked

**The shared-FieldMap extraction earned its keep immediately.** Refactoring the
Data Explorer onto `<FieldMap>` removed 89 lines from `DataExplorerPage.tsx` and
the DE map gained the 3-basemap toggle for free. Two consumers (DE + Dashboard)
validate the component contract, and the `showOverlays` / `expandable` flags let
each opt into exactly the chrome it needs without forking the map logic.

**Centralizing all DEMO data in one file** (`dashboardPlaceholders.ts`) keeps the
dashboard honest and the future swap trivial. Each placeholder is tagged, the
component props are written to match what the real endpoints will plausibly
return, and "wire it for real" becomes "change which source this one component
reads from." The real surfaces (record count, sensor streams, robot ids) sit
alongside without contamination.

**Reusing F06 primitives paid off.** KpiRow is `MetricTile`s, the panels are
`Panel`, labels are `MonoLabel`, status uses `StatusDot`. Almost no new styling
primitives were needed — the dashboard is composition over F06's vocabulary.

**The blip-as-Marker decision was right.** Using real `maplibregl.Marker`s
(instead of an SVG overlay synced via `map.project` on every `move`) means blips
track pan/zoom for free. The only cost is rebuilding the marker element on
selection/status change, which is cheap.

---

## What hurt

**The CP2 blank-map bug — a self-inflicted flexbox trap.** The first `<FieldMap>`
put `flex-1` AND an explicit `height` on the same viewport div inside a flex
column with no height constraint. `flex-1` won and collapsed the viewport to
0px, so MapLibre rendered nothing — the exact "container needs explicit height"
footgun the DE comments warn about, reintroduced by my own layout. The basemap
toggle still rendered (it's in the header), which made it look like the map
mounted but the tiles failed. Fix: drop `flex-1`, make the height authoritative.
(Troubleshooting 014.) Lesson: when porting a working map, port its container
sizing model too, not just its JS.

**A truncated paste masqueraded as a TypeScript error.** Pasting `ActiveAlerts.tsx`
into the editor truncated it, so the file lacked its `export`. The symptom was a
misleading `Module has no exported member 'ActiveAlerts'` plus a blank-white
route (the whole module graph failed to load). `npx tsc -b` passed in the
sandbox but failed on the real machine for a file the sandbox claimed exported
something — that mismatch is the tell. Lesson + new workflow guard: after pasting
any file over ~60 lines, `grep -n "export" <file>` to confirm the expected
exports landed.

**`tsc` quietly accepted a stray `)`.** A leftover paren after a JSX element
parsed as a JSX text child (valid TS, renders a literal `)` on screen) rather
than a syntax error. A clean typecheck does NOT catch a stray character that
renders. Lesson: the sandbox build passing is necessary but not sufficient —
eyeballing the actual UI is what catches render-level mistakes.

**The logout regression.** Rewriting DashboardPage for the retrofit silently
dropped the placeholder's "Log out" button, leaving no UI logout path. Caught in
CP6 by the user, not by me. Lesson: when a rewrite replaces a page that had
behavior beyond layout (a logout button, in this case), inventory that behavior
before replacing. The fix (logout in the NavRail footer) is actually better than
the original — app-wide instead of page-local — but it should have been caught at
CP4, not CP6.

---

## Workflow notes

**Sandbox `tsc -b` + `npm run build` caught real bugs before handoff** (the
unused-props error in CP1, the restored-function-line break in CP3). The
build-before-handoff discipline is working — every file shipped compiled.

**But sandbox verification has two blind spots, both hit this feature:** it can't
catch a paste that truncates on the user's side, and it can't catch render-level
issues that compile fine (stray `)`, 0px map, missing logout button). Those need
the user's eyes on the running app. The CP-by-CP screenshot loop is what closes
that gap — keep it.

**Bare `tsc` is not on the user's PATH.** Use `npx tsc -b` (or `npm run build`,
which calls it). Installing `node-typescript` via apt would pull a wrong global
version — don't.

---

## Carry-forwards (for F08 and beyond)

- **ADR 0007 authorization debt is now urgent for F08.** F07 surfaces are all
  read-only, so "any logged-in user can hit any route" is cosmetic. F08's
  Workspace adds command/control surfaces (Nav2 goals, e-stop) where a read-only
  community user reaching a POST endpoint goes from cosmetic to genuinely
  dangerous. RBAC + route guards should be tackled before or alongside any
  write/command capability.
- **ADR 0009: demo login buttons are dev-only.** Strip from prod before any
  deployment. Tracked.
- **The live pipeline is the big unbuilt dependency.** Everything DEMO on the
  dashboard (telemetry, blip positions, fleet status, comms load) becomes real
  only when rosbridge → Channels → WS exists. That's F08 territory.
- **`react-grid-layout` is NOT yet installed** despite being assumed "in the
  stack" — it'll need adding when the Workspace panel grid is built.