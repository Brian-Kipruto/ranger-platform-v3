# ADR-0039: Route built screens only; dev diagnostics in dev builds only

- **Status:** Accepted
- **Date:** 2026-11-02
- **Feature:** F18 (Pass S1, checkpoints 1 and 3–4)
- **Related:** ADR-0007, ADR-0008, ADR-0009, ADR-0024

## Context

The F06 nav listed twelve screens per operator, six of them `StubPage` ("NOT BUILT"),
so the shell looked complete. The TopBar carried static chrome that read as live state
(`3 LIVE · 1 MQTT · 1 OFF`, an alert bell with a permanent red dot, ⌘K search, OP/CL/PUB
pills that looked like a switch). The login card showed 2FA TOTP tiles, an
`mTLS · TLS 1.3` badge and a footer with invented coordinates and a build hash. `/` served
the Phase-1 scaffold page. Several user-facing messages named env vars, management
commands and the Orin's LAN address.

## Decision

- **A nav entry is a claim the screen works.** The nav and the router list only built
  screens: Dashboard, Mission Control, Data Explorer, Visualizations, Satellite, Reports.
  Stub paths and unknown paths redirect to `/dashboard`; `/` does too (ProtectedRoute
  sends the logged-out to `/login`). `StubPage`, `HomePage` and the `VIEW_META` entries
  stay in the code, unrouted.
- **Chrome that implies state or a control is removed until something real drives it**:
  the TopBar keeps the view title and the UTC clock; the login card keeps the form and
  decoration that claims nothing.
- **Users see state, never configuration.** Env-var names, command names (`grant_drive`,
  `teleop_relay`, `fetch_scenes`) and stream addresses render only under
  `import.meta.env.DEV`, prefixed `Dev:`. Production builds carry user copy.

## Options rejected

- **"Coming soon" entries.** Honest, but a judge clicking one mid-demo sees an
  unfinished product. A greyed, unrouted SOON chip remains possible if the pitch wants
  breadth on screen.
- **Delete the dev hints.** They are how the bench is run; gating keeps them for dev.

## Consequences

- Role-scoped *routing* is not done: every role can still reach every built screen by
  URL (parked with the ADR-0007 tenancy work).
- `VITE_VIDEO_SERVER_URL` is still compiled into the bundle: the browser fetches the
  MJPEG directly (ADR-0024). Hiding the address from copy does not hide it from the
  network; the proxied feed does.
