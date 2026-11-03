# F18 — Polish and Cleanup (Pass S1, UI half)

*Date: 2026-11-02*
*Branch: `feat/polish-cleanup` (from `main` @ `3d0bb61`)*
*Status: **UI half closed; tenancy half parked.** Nothing in the console over-claims: only
built screens are reachable, every number on screen traces to an endpoint or carries a
tier, chrome that implied live state or missing security is gone, and configuration
hints appear in dev builds only. Signed off by click-through as `operator@knra.go.ke`,
`operator@byteanza.com` and `client@magadi.com` with no failures.*

Pass S1 in the vault. F17 is reserved for A1i. No hardware needed: this half was chosen
because the robots were out of reach.

---

## Scope

The audit (every nav entry per role, every demo seam, the ADR-0007 and ADR-0009 debts)
produced an 18-item checklist. Split on 2026-11-02:

| Done here | Parked (tenancy / auth debt) |
|---|---|
| 4 role pills · 6 Mission Control copy · 7 stubs unreachable · 8 root routes · 9 login fakes · 10 TopBar fakes · 11 states · 12 consistency · 13–16 dashboard data · 18 provenance audit | 1 role-scoped routing · 2 no-org screen · 3 community off demo surfaces · 5 tenant seed · 17 demo logins DEV-only (ADR-0009, **blocks S2**) |

Forks settled at the audit: no operator god-mode (isolation shown with two tenant
logins), community out of demo surfaces, demo logins DEV-only, unbuilt screens hidden
rather than "coming soon". Only the last is implemented in this half.

---

## What changed, by checkpoint

| CP | Commit | Change |
|---|---|---|
| 1 | `9a0c122` | Nav and router: six built screens only; stub and unknown paths → `/dashboard`; `/` → `/dashboard` (HomePage retired). TopBar: view title and clock only. Login: TOTP tiles, TLS badge, invented footer removed; "BYTEANZA LLC". Rail: "CLIENT" (ADR-0039) |
| 2 | `77432b0`, `739867d` | Dashboard real-only: 4 KPIs (robots, reporting now, missions running, records via paginated `count`), fleet status from the live feed, blips only with a fix, readout without the hardcoded heading/speed, Alerts and Comms removed, loading/empty/error states; placeholder file and two components deleted (ADR-0040) |
| 3 | `e08a36e` | Mission Control: user copy for drive/plan/camera; env vars, commands and the stream address dev-only; duplicate page label removed; camera EXPAND (CSS class on the same Panel, MJPEG not remounted) |
| 4 | `1e7ef5c` | Satellite provider status from this org's scenes (global `is_verified` dropped); Data Explorer map clause reports loading/failed instead of claiming the full track; FieldMap missing-key message dev-only |
| 5 | `0995639`, `70a9356` | Visualizations retrofitted to the console (Panels, DE filter bar, dark Recharts via hex tokens, cap stated, honest empty copy, date ticks for multi-day spans); Esc collapses map and camera; map readout moved off the scale bar; NavRail comment |

## Files

| File | Change |
|---|---|
| `src/App.tsx` | built routes only; `/` and `*` → `/dashboard` |
| `src/config/navConfig.ts` | six items; badge removed; `BUILT_PATHS` truthful |
| `src/components/console/TopBar.tsx` | title + clock |
| `src/components/console/AppShell.tsx` | role label; TopBar props |
| `src/components/console/NavRail.tsx` | comment |
| `src/pages/LoginPage.tsx` | TOTP, TLS badge, footer removed |
| `src/pages/DashboardPage.tsx` | real sources, error banner |
| `src/components/dashboard/{KpiRow,FleetMini,SensorStreams}.tsx` | real-only shapes, loading props, copy |
| `src/api/missions.ts` | `listOrgMissions()` |
| `src/pages/MissionControlPage.tsx`, `src/components/mission/MissionPlanPanel.tsx`, `src/lib/teleop.ts` | user copy, dev hints |
| `src/components/camera/CameraPanel.tsx` | copy, dev-only address, EXPAND, Esc |
| `src/pages/SatellitePage.tsx` | per-org provider status, copy |
| `src/pages/DataExplorerPage.tsx` | map/options load states |
| `src/components/map/FieldMap.tsx` | dev-only key message, Esc, readout top-left |
| `src/pages/VisualizationsPage.tsx` | console retrofit |
| *deleted* `src/config/dashboardPlaceholders.ts`, `src/components/dashboard/{ActiveAlerts,CommsLayers}.tsx` | |

No backend changes. `StubPage.tsx` and `HomePage.tsx` remain, unrouted.

## Verification

- Every checkpoint: hashes of hand-placed files, `npm run build` exit 0, eslint on the
  changed files (no new errors).
- Production bundle grepped for the removed strings: 0 hits for the fake KPI/alert/fleet
  values, "Foundation Scaffold", "GOOGLE AUTH", "Drivers group", "start teleop_relay".
  One `192.168` remains: the compiled `VITE_VIDEO_SERVER_URL` (ADR-0039 consequences).
- `vite preview` (production build): no `Dev:` lines; stale camera shows no address.
- Visual sign-off per checkpoint, then the S1d click-through as three accounts across all
  six screens: every number traced to an endpoint or a tier, no failures.

## Open

- **Parked S1 items 1, 2, 3, 5, 17.** 17 (ADR-0009) must land before S2.
- **Mission Control is pinned to one robot for every tenant** (`VITE_VIDEO_ROBOT_ID`): a
  client sees and can plan for another org's robot, and the MJPEG is unauthenticated.
  Needs an ownership check server-side (tenancy work).
- **S2:** add the production origin to the MapTiler key (TS-055); decide on the proxied
  video feed.
- Fleet screen as its own pass (demo script step 2).
- The map opens on Nairobi, not on the org's data.
- No `/api/robots/`.
- 7 `react-hooks/set-state-in-effect` errors pre-dating F18 (Satellite 6, Visualizations 1).
