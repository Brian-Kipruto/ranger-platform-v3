# Feature 07 — Dashboard Retrofit + Shared FieldMap

*Date: 2026-06-25*
*Branch: `feat/dashboard-fieldmap` (cut from `main` after F06 merge)*
*Type: Frontend-only (no new backend endpoints, no new models)*

---

## What this feature does

Two things, both pure frontend, both reusing the F06 console primitives:

1. **Retrofits `/dashboard`** from the F02 placeholder ("Logged in as… → Data
   Explorer") to the Field Console mockup's `isDashboard` layout: a 6-tile KPI
   row, a main grid (field map + live telemetry + fleet mini), and a bottom row
   (active alerts + sensor streams + comms layers).

2. **Extracts a reusable `<FieldMap>`** from the Data Explorer's inline MapLibre
   setup, then upgrades it with three capabilities the DE map never had:
   - **Three real basemaps** — VECTOR / SAT / TOPO (MapTiler styles).
   - **Expand-to-fullscreen** with `map.resize()`.
   - **Overlays** — robot blip markers + a bottom-left telemetry readout.

   The Data Explorer is then refactored onto the same `<FieldMap>`, so the
   extraction is proven by two consumers and the DE map gains the basemap
   toggle for free.

### Real vs. DEMO data (important)

The dashboard ships visually complete, but several of its data sources don't
exist yet (no fleet/live/alerts endpoints — see carried-forward threads). The
split:

| Surface              | Source            | Status |
|----------------------|-------------------|--------|
| Robot ids / names    | `/api/chart-data/`| **REAL** (derived, F05 pattern) |
| "DATA INGESTED" KPI  | `/api/chart-data/`| **REAL** record count |
| SENSOR STREAMS       | `/api/chart-data/`| **REAL** radiation + PM2.5 series |
| Other 5 KPIs         | placeholder       | DEMO (tagged) |
| LIVE TELEMETRY       | placeholder       | DEMO (deterministic series) |
| Fleet status/battery | placeholder       | DEMO overlay on real ids |
| Map blip positions   | placeholder       | DEMO coords |
| ACTIVE ALERTS        | placeholder       | DEMO (local-state ACK) |
| COMMS LAYERS         | placeholder       | DEMO (static) |

**All DEMO data is centralized in one file** —
`src/config/dashboardPlaceholders.ts` — and clearly marked, so the "wire it for
real later" swap is a localized change. Anything not marked DEMO on screen is
real.

---

## Files created

```
src/components/map/basemaps.ts                 # MapTiler style registry (key-aware)
src/components/map/FieldMap.tsx                 # the shared map component
src/config/dashboardPlaceholders.ts            # ALL dashboard demo data, one file
src/components/dashboard/KpiRow.tsx             # 6-tile KPI strip
src/components/dashboard/LiveTelemetry.tsx      # 4 mini sparkline tiles
src/components/dashboard/FleetMini.tsx          # selectable robot mini-list
src/components/dashboard/ActiveAlerts.tsx       # alert rows + local ACK
src/components/dashboard/SensorStreams.tsx      # REAL radiation + PM2.5 area-sparks
src/components/dashboard/CommsLayers.tsx        # static comms stack
```

## Files modified

```
src/pages/DashboardPage.tsx                     # full retrofit (was placeholder)
src/pages/DataExplorerPage.tsx                  # map block → <FieldMap> (−89 lines)
src/components/console/NavRail.tsx              # + SIGN OUT button (logout regression fix)
src/components/console/AppShell.tsx             # wires logout → NavRail
```

---

## `<FieldMap>` — the shared map

The component is a faithful port of the DE map's MapLibre invariants (the
error-prone bits that bit V2 and F05), plus the three upgrades:

**Ported invariants:**
- Map instance in a ref, never state (not React-reactive).
- Init runs once, guarded by a `map.current` check (React 19 StrictMode
  double-invokes effects in dev), cleaned up on unmount.
- Container needs an explicit height or MapLibre renders 0px tall.
- `maplibre-gl.css` must be imported.
- GeoJSON coords are `[lng, lat]`.
- **Paint props can't read CSS vars** → the accent is a hex string **prop**,
  never `var(--accent)`. Callers resolve `org.theme_color` and pass it in.

**Upgrade 1 — three basemaps.** `map.setStyle(styleUrl(mode))` swaps the
MapTiler style. Because `setStyle` wipes all sources/layers, every data layer is
(re)added in ONE place — `installLayers()` — called on the initial `load` AND on
every `styledata` event. This is the core mechanism; without the `styledata`
re-add, the track points vanish when you switch basemaps.

**Upgrade 2 — expand.** A `fixed inset-0 z-50` fullscreen toggle on the same
container (no re-init). `map.resize()` fires on the next animation frame after
the size change, so tiles don't clip.

**Upgrade 3 — overlays.** Robot blips are real `maplibregl.Marker`s keyed by
robot id (so they auto-track pan/zoom — no manual `map.project` on every move),
diffed on change. Status drives color; live blips get a ping ring, the selected
blip gets a sweep ring. The telemetry readout is an absolutely-positioned HTML
box, bottom-left.

The component takes `showOverlays` / `expandable` flags so the **Data Explorer
opts out** of both (`showOverlays={false}`, no `expandable`) and behaves exactly
as before, while the **Dashboard opts in**.

---

## Dashboard data flow

```
DashboardPage
  ├─ getRobotOptions()  → real robot id/name list (F05 derivation)
  ├─ getChartData({})   → real rows → record count + SensorStreams series
  ├─ merges FLEET_STATUS_DEMO overlay (status/battery/mission) by robot_id_str
  ├─ builds blips from BLIP_COORDS_DEMO (DEMO positions)
  └─ selectedId state drives: LiveTelemetry header, map readout, selected blip,
     and the FleetMini highlighted row (click a fleet row → selects that robot)
```

The chart-data endpoint is fetched **once** and shared between the record-count
KPI and SensorStreams (no double fetch).

---

## Logout regression (caught in CP6)

The F02 placeholder DashboardPage had a "Log out" button. When this feature
rewrote DashboardPage, that button was dropped, leaving no way to sign out from
the UI. Fix: logout moved to the **NavRail footer** (app-wide, available on every
screen — the correct home in a shell layout, not page-local). AppShell wires
`useAuthStore.logout()` + navigate to `/login`. Reuses the exact F02 logout flow
(server-side blacklist + local clear). See retrospective.

---

## Verification (CP6 E2E)

Logged in as all three demo roles:
- **Accent follows tenant** — ByteAnza blue, Magadi amber, community violet.
  Confirms the multi-tenant `--accent` driver end-to-end (KPI bars, nav, map,
  basemap toggle all shift).
- **Nav trims per role** — community sees only PUBLIC group; client sees
  ACCOUNT (Billing & Team); operator sees full set.
- **Empty-state is graceful** — client/community orgs have no logged data →
  dashboard + DE show `NO DATA` empty-states, no crash. (Also confirms tenant
  data isolation: Magadi correctly sees 0 of ByteAnza's 430 records.)
- **SIGN OUT works** from the nav rail on every screen.
- **DE unaffected** — row flyTo + highlight + basemap toggle all still work.

---

## Carried-forward threads (still open after F07)

1. **Authorization debt (ADR 0007).** Re-confirmed in CP6: role-nav hides links
   but enforces nothing — any logged-in user can URL-navigate to any route, and
   every read endpoint returns whatever their org can see. Tenant *data*
   isolation holds (org-scoped querysets), but intra-tenant role gating + route
   guards are unbuilt. First feature with a real permission boundary should set
   the V3 RBAC pattern across all read endpoints, then swap `navGroupsForRole()`
   to permission-based.
2. **Demo login buttons must be stripped from production (NEW — ADR 0009).** The
   OP/CL/PUB "ENTER DEMO AS" buttons (F06) perform REAL logins via hardcoded
   seeded credentials in `config/demoAccounts.ts`. Working as designed for dev,
   but a one-click login to seeded accounts + a plaintext password file in the
   bundle must not ship to prod. Gate behind `import.meta.env.DEV` (or a
   `VITE_ENABLE_DEMO_LOGINS` flag) and don't seed demo accounts in prod.
3. **No `/api/robots/` or `/api/missions/` LIST endpoints.** Dashboard FLEET +
   blips derive ids from `/api/chart-data/`. Real list endpoints localize this.
4. **No WebSocket / live data.** LIVE TELEMETRY, map blip positions, fleet
   status, comms-layer load are all DEMO/static until the live pipeline exists.
   This is exactly what the Workspace + ros_bridge work builds.
5. **Alerts are placeholder.** ACTIVE ALERTS uses demo data + local-only ACK
   until the Alerts feature (threshold engine + `/api/alerts/`) lands.
6. **MapTiler key** still needs HTTP-origin restriction before production.
   Confirmed the key's plan covers satellite + outdoor (the 3 basemaps work).

---

## See also

- ADR 0009 — demo login buttons are dev-only (production-strip register)
- ADR 0010 — shared FieldMap extraction + basemap strategy
- Troubleshooting 014 — FieldMap blank-map (flex-1 collapsed the viewport height)
- `07-dashboard-fieldmap-retrospective.md`