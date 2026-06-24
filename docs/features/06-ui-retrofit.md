# Feature 06 — UI Retrofit (Field Console)

> Status: Shipped 2026-06-24. Branch: `feat/ui-retrofit` (cut from `main`
> after the F03→F05 stack merged).
> Commits: `275730d` (seed_demo), `1ca2a3a` (frontend retrofit), plus the
> docs commit that adds this file.

## What it does

Retrofits the existing authenticated UI to the **Field Console** design
(`RANGER V3 Field Console.dc.html`) — a fixed-dark, full-viewport "mission
control" look. Two screens get the full treatment (Login, Data Explorer) and
the app shell that frames every authenticated page gets built. **No backend
logic, no API, no auth-flow changes** — this is pure presentation, with one
exception called out below (the seed command, which only *adds* data).

Three things shipped:

- **Login rebuild** (`/login`). The plain Feature 02 form rebuilt as the
  mockup's two-column "Secure Access" screen — radar-ring identity panel, mTLS
  badge, real Operator ID + Passphrase inputs, static 2FA TOTP tiles, three
  one-click role-demo buttons, corner ticks, footer telemetry strip. The auth
  logic underneath (`useAuthStore.login`, `?next=` redirect, react-hook-form +
  zod, server-error banner) is unchanged.
- **App shell** (`AppShell` + `NavRail` + `TopBar`). Wraps all authenticated
  routes: collapsible grouped nav rail, top bar with view code/label, status
  pills, live UTC clock, role-switch chrome, and the content frame. This is
  also where the **org-driven accent** activates.
- **Data Explorer retrofit** (`/data`). The Feature 05 page re-chromed into
  console panels — search/filter bar, summary metric tiles, the TanStack table
  and MapLibre map dropped into `<Panel>`s. Every piece of 05's logic (table,
  map, track, fly-to, export, pagination, stats) is preserved untouched; only
  the markup/styling changed.

## The accent-follows-org mechanism (the headline)

The mockup hardcodes violet (`#7c6cff`) everywhere. In V3 the accent is
**tenant-themeable**, driven from `organization.theme_color`:

- `index.css` defines `--accent: #7c6cff` in `:root` as the *fallback* (a tenant
  with no color set sees violet).
- `useAccentTheme()` (run in `AppShell`) reads `user.organization.theme_color`
  and sets `--accent` (and a derived `--accent-hover`) on
  `document.documentElement` at runtime. On logout it removes the override, so
  the stylesheet fallback takes over again.
- `--accent-weak` / `--accent-faint` derive from `--accent` via `color-mix`, so
  soft fills follow the tenant accent automatically — no second runtime var.

Proven end to end across three tenants: ByteAnza renders **teal** (`#0ea5e9`),
Magadi Soda Co. renders **amber** (`#f5a623`), and Community (no org) falls back
to **violet**. The seed command creates two differently-themed orgs precisely so
this is visibly demonstrable, not just asserted.

Semantic colors (ok/warn/alert/info) are FIXED `@theme` tokens — they encode
meaning and never follow the tenant accent.

## Token layer

`index.css` was rewritten from the minimal slate scaffold to the full console
token system, in Tailwind v4's `@theme` layer (NOT a `tailwind.config.js`):

- **Surfaces** (`--color-surface-0` … `-panel`), **borders**, **text ramp**
  (`--color-fg` … `-faint`), **semantic** (`--color-ok/warn/alert/info`),
  **fonts** (`--font-ui` = Space Grotesk, `--font-mono` = IBM Plex Mono, loaded
  via Google Fonts link in `index.html`), and the keyframes the retrofitted
  screens use (`rngPulse`, `rngBlink`, `rngPing`, `rngSweep`).
- The text ramp uses `fg` not `text` (so utilities read `text-fg-dim`, not the
  awkward `text-text-dim`). Surfaces are `bg-surface-*`, semantics `text-ok`.
- `--accent*` lives in `:root` (not `@theme`) so it's never baked into a build-
  time utility — it must stay runtime-mutable.

## Console primitives

Extracted as the retrofit needed them (discover-the-API-by-using-it), not
pre-built. All in `src/components/console/`:

| Primitive | Role |
| --- | --- |
| `MonoLabel` | uppercase wide-tracked IBM Plex Mono text (every label/chrome string) |
| `StatusDot` | semantic pulse dot (online/OK indicators) |
| `CornerTicks` | four L-bracket framing marks (login) |
| `Panel` | bordered surface card with optional mono header (the workhorse) |
| `MetricTile` | KPI tile: left accent bar, label, value, sub (Data Explorer stats) |
| `NavRail` | collapsible grouped nav rail |
| `TopBar` | view header + status pills + clock + role chrome |
| `AppShell` | composes the above + content frame; runs the accent hook |

Plus `src/lib/utils.ts` (`cn()` — clsx + tailwind-merge), used by the primitives.

## App shell & routing

`App.tsx` now wraps the protected routes in a **layout route**:
`ProtectedRoute` (auth guard) → `AppShell` (frame) → page via `<Outlet />`.

- **Built screens** render real pages: `/dashboard`, `/data`, `/visualizations`.
- **Stub screens** route to `StubPage` (a "not built yet" placeholder inside the
  shell) so the nav looks complete and nothing breaks on click: `/mission`,
  `/workspace`, `/fleet`, `/alerts`, `/reports`, `/ai`, `/admin`, `/community`.

The nav is **role-scoped** (see ADR 0008): `navConfig.ts` maps the user's Django
Group name (Operator / Client / Community, from the seed) to a nav group set
matching the mockup. Operator/superuser gets the full nav; client swaps PLATFORM
for an ACCOUNT group; community gets the trimmed PUBLIC group only. The
structure is deliberately shaped so that when real RBAC lands (ADR 0007), the
only thing that changes is `navGroupsForRole()` — swap "key off group name" for
"filter by `hasPermission()`". The component, routing, and rendering all stay.

## seed_demo command

`accounts/management/commands/seed_demo.py` — idempotent, creates the data the
role-demo login buttons authenticate against:

- **Groups:** Operator, Client, Community (permission buckets; perms attached
  when ADR 0007 work lands — empty for now).
- **Orgs:** ByteAnza (`byteanza`, teal `#0ea5e9`), Magadi Soda Co.
  (`magadi-soda`, amber `#f5a623`) — two colors to prove the accent wiring.
- **Users:** `operator@byteanza.com` (superuser, ByteAnza), `client@magadi.com`
  (Magadi), `community@public.com` (no org). Username == email by design:
  simplejwt authenticates on `username`, the login shows the email in the
  Operator ID field, so the thing displayed is the thing submitted. Shared dev
  password printed on completion; mirrored in `src/config/demoAccounts.ts`.

Never modifies existing users (so the real superuser account is safe to re-run
against). Also guarantees the `byteanza` org exists, which `run_simulation`'s
seed-robot path depends on.

## Static chrome (rendered, not wired)

Per the feature's decisions, these render to match the mockup but have no logic
yet — the UI is ready for when the real feature lands:

- **2FA TOTP tiles** (login) — visual only; real 2FA is a future feature.
- **TopBar role switch** — the active pill reflects the real role; clicking does
  nothing. Real role-switching is the RBAC/ADR-0007 thread.
- **TopBar search (⌘K)** — placeholder; command palette deferred.
- **Status pills (LIVE/MQTT/OFF)** — static; no fleet endpoint yet.
- **Alerts bell** — static; alerts feature is future.

## Files

**New (frontend):** `src/lib/utils.ts`, `src/components/console/{MonoLabel,
StatusDot, CornerTicks, Panel, MetricTile, NavRail, TopBar, AppShell}.tsx`,
`src/config/{demoAccounts,navConfig}.ts`, `src/hooks/useAccentTheme.ts`,
`src/pages/StubPage.tsx`.
**Modified (frontend):** `index.html` (fonts + title), `src/index.css` (token
layer), `src/App.tsx` (shell layout route + stubs), `src/pages/LoginPage.tsx`
(rebuild), `src/pages/DataExplorerPage.tsx` (re-chrome).
**New (backend):** `accounts/management/commands/seed_demo.py` (+ package inits).

No migrations. No API changes.

## What this deliberately did NOT touch

- Dashboard, Visualizations, HomePage — still on their old styling inside the
  shell (accepted mismatch; retrofitted in later features).
- Real RBAC / permission gating (ADR 0007 thread).
- Any backend logic, endpoint, serializer, or auth flow.

## Related docs

- `decisions/0008-design-tokens-and-console-shell.md` — the design-system
  adoption model and role-nav shape
- `decisions/0002-multi-tenant-via-organization-fk.md` — why Groups, not a role
  field (the constraint the role-nav works around)
- `decisions/0007-data-explorer-authenticated-only.md` — the RBAC thread the
  role-nav is built to slot into
- `features/05-data-explorer.md` — the logic the Data Explorer retrofit preserves
- `features/02-authentication.md` — the login logic the rebuild preserves
- `troubleshooting/013-ts-server-phantom-module-errors.md` — the editor cache
  gotcha hit during the retrofit