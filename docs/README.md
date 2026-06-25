# R.A.N.G.E.R. Platform V3 — Documentation

This is the working knowledge base for the R.A.N.G.E.R. V3 build. It covers system setup, architecture decisions, per-feature implementation notes, and troubleshooting logs.

The goal: anyone (including future-me) should be able to read this and understand **what was built, why it was built that way, and how to recover if it breaks**.

---

## Structure

### `setup/`
Step-by-step guides for getting a development environment running from a fresh Ubuntu install. Read these in order if you're setting up a new machine.

- [`00-phase-1-retrospective.md`](./setup/00-phase-1-retrospective.md) — what we learned building Phase 1, what worked, what was harder than expected
- [`01-system-prep.md`](./setup/01-system-prep.md) — Python 3.11, Node 20, Docker, GitHub SSH, project skeleton
- [`02-services.md`](./setup/02-services.md) — PostgreSQL + Redis via Docker Compose, secrets, healthchecks
- [`03-backend-scaffold.md`](./setup/03-backend-scaffold.md) — Django 5 backend with split settings, 13 apps, custom user + organization
- [`04-frontend-scaffold.md`](./setup/04-frontend-scaffold.md) — React 19 + TypeScript + Vite + Tailwind v4 frontend


### `architecture/`
Higher-level design documentation. The *why* behind the structural choices: split settings, multi-tenancy model, panel system, ROS bridge pattern, etc.

- [`00-overview.md`](./architecture/00-overview.md) — three-tier system overview, app boundaries, data flow patterns, security architecture

*(Coming as we build.)*

### `features/`
One markdown file per feature/phase, documenting end-to-end implementation. Each file covers: what the feature does, files created/modified, data flow, API endpoints, frontend components, gotchas encountered.

- [`02-authentication.md`](./features/02-authentication.md) — JWT login, httpOnly refresh cookie, silent refresh, logout with server-side blacklist
- [`02-authentication-retrospective.md`](./features/02-authentication-retrospective.md) — what worked, what hurt, what to do differently
- [`03-core-models.md`](./features/03-core-models.md) — core + missions models: robots, sensor catalog, decoupled sensor logs, missions, waypoints
- [`03-core-models-retrospective.md`](./features/03-core-models-retrospective.md) — what worked, the migration-split win, carry-forwards
- [`04-simulator.md`](./features/04-simulator.md) — run_simulation management command: backfill + live modes, hybrid waypoint/random-walk, readings driven by installed_sensors
- [`04-simulator-retrospective.md`](./features/04-simulator-retrospective.md) — what worked, the count-mismatch red herring, carry-forwards for Data Explorer
- [`05-data-explorer.md`](./features/05-data-explorer.md) — four read endpoints over SensorLog (list, CSV export, chart-data, map-data), the null-safe flattening serializer, the Data Explorer page (table + MapLibre map), and the Visualizations page (4 Recharts charts)
- [`05-data-explorer-retrospective.md`](./features/05-data-explorer-retrospective.md) — what worked, the map-data race and robot-filter PK gap, carry-forwards
- [`06-ui-retrofit.md`](./features/06-ui-retrofit.md) — Field Console UI retrofit: design-token layer, login rebuild, app shell (nav rail + top bar), Data Explorer re-chrome, org-driven accent, seed_demo for role-based login
- [`06-ui-retrofit-retrospective.md`](./features/06-ui-retrofit-retrospective.md) — what worked, the no-role-field catch, the TS-server phantom errors, carry-forwards
- [`07-dashboard-fieldmap.md`](./features/07-dashboard-fieldmap.md) — Dashboard retrofit (KPI row, telemetry, fleet, alerts, sensor streams, comms) + shared `<FieldMap>` extraction with 3 basemaps, expand, and blip/readout overlays; real-vs-DEMO data split centralized in one config
- [`07-dashboard-fieldmap-retrospective.md`](./features/07-dashboard-fieldmap-retrospective.md) — what worked, the blank-map flexbox trap, the truncated-paste red herring, the logout regression, carry-forwards

### `decisions/`
Architecture Decision Records (ADRs). Short, dated records of important technical choices. Format: problem → options considered → decision → consequences.

- [`0001-postgres-in-docker-not-native.md`](./decisions/0001-postgres-in-docker-not-native.md) — Why we run PostgreSQL in Docker even though Ubuntu installed it natively
- [`0002-multi-tenant-via-organization-fk.md`](./decisions/0002-multi-tenant-via-organization-fk.md) — Why we use a shared schema with `organization` FK, and Django Groups instead of a `role` enum
- [`0003-refresh-token-storage.md`](./decisions/0003-refresh-token-storage.md) — Refresh token in httpOnly SameSite=Strict cookie; access token in memory + localStorage mirror
- [`0004-token-blacklist-on-logout.md`](./decisions/0004-token-blacklist-on-logout.md) — Enable simplejwt blacklist + rotation so logout actually invalidates server-side
- [`0005-auth-feature-known-gaps.md`](./decisions/0005-auth-feature-known-gaps.md) — Deferred-work register: 15 items the auth feature did NOT ship that need closing before production
- [`0006-sensorlog-tenancy-through-robot.md`](./decisions/0006-sensorlog-tenancy-through-robot.md) — Why SensorLog inherits tenancy through Robot instead of carrying its own organization FK
- [`0007-data-explorer-authenticated-only.md`](./decisions/0007-data-explorer-authenticated-only.md) — Why Feature 05 ships authenticated-only and defers custom-permission enforcement to a later feature
- [`0008-design-tokens-and-console-shell.md`](./decisions/0008-design-tokens-and-console-shell.md) — Tailwind v4 @theme tokens + :root runtime accent, retrofit-first adoption, color-mix derivations, group-keyed role nav shaped for RBAC
- [`0009-demo-login-buttons-dev-only.md`](./decisions/0009-demo-login-buttons-dev-only.md) — The OP/CL/PUB demo login buttons perform REAL seeded-account logins (not a bypass); register requirement to strip them + the plaintext demo-credentials file from production builds
- [`0010-shared-fieldmap-and-basemaps.md`](./decisions/0010-shared-fieldmap-and-basemaps.md) — Extract one `<FieldMap>` for both Data Explorer and Dashboard; accent-as-prop (paint props can't read CSS vars), `installLayers()` single re-add point on `styledata`, per-screen chrome via flags, key-aware basemap registry

### `troubleshooting/`
Error logs and fixes. Each entry records: what we saw, what caused it, how we fixed it, how to prevent it.

- [`001-docker-permission-denied.md`](./troubleshooting/001-docker-permission-denied.md) — `permission denied while trying to connect to the Docker API` after fresh install
- [`002-startapp-chicken-and-egg.md`](./troubleshooting/002-startapp-chicken-and-egg.md) — Django `startapp` fails when apps registered in `INSTALLED_APPS` don't exist yet, and the `AUTH_USER_MODEL` complication
- [`003-tsconfig-baseurl-deprecated.md`](./troubleshooting/003-tsconfig-baseurl-deprecated.md) — TypeScript 6 deprecates `baseUrl`; use `paths` alone
- [`004-vscode-paste-heredoc-leak.md`](./troubleshooting/004-vscode-paste-heredoc-leak.md) — Pasting heredoc-wrapped content from chat into VS Code includes the wrapper
- [`005-daphne-no-static-files.md`](./troubleshooting/005-daphne-no-static-files.md) — Django admin renders unstyled when served by bare `daphne` (use `runserver` for dev)
- [`006-postgres-not-running-fresh-terminal.md`](./troubleshooting/006-postgres-not-running-fresh-terminal.md) — `connection refused: 5432` after fresh terminal because Docker containers don't auto-start
- [`007-virtualenv-not-active.md`](./troubleshooting/007-virtualenv-not-active.md) — `ModuleNotFoundError: No module named 'django'` because virtualenv wasn't reactivated
- [`008-self-referential-url-include.md`](./troubleshooting/008-self-referential-url-include.md) — Self-referential `include("<app>.urls")` inside the same app's `urls.py`
- [`009-refresh-cookie-secure-flag-bug.md`](./troubleshooting/009-refresh-cookie-secure-flag-bug.md) — Refresh cookie sent with `Secure` in dev because `base.py` evaluates `not DEBUG` before `development.py` flips DEBUG to True
- [`010-vite-dynamic-import-multi-instance.md`](./troubleshooting/010-vite-dynamic-import-multi-instance.md) — Vite dev mode resolved dynamic imports as separate module instances, producing two Zustand stores that didn't share state
- [`011-mapdata-load-race.md`](./troubleshooting/011-mapdata-load-race.md) — MapLibre track points silently missing because the map-data fetch resolved before the map's `load` event
- [`012-robot-filter-pk-gap.md`](./troubleshooting/012-robot-filter-pk-gap.md) — Robot filter had no value to send: serializer exposed the string ID but the endpoint filters by integer PK
- [`013-ts-server-phantom-module-errors.md`](./troubleshooting/013-ts-server-phantom-module-errors.md) — Editor "Cannot find module" errors for files that exist; stale TS-server cache, restart fixes it, CLI compiler is authoritative
- [`014-fieldmap-blank-flex-height-collapse.md`](./troubleshooting/014-fieldmap-blank-flex-height-collapse.md) — FieldMap canvas blank (header/toggle render, tiles don't): `flex-1` + explicit height on the same div inside an unconstrained flex column collapsed the map container to 0px; build was clean
- [`015-truncated-paste-missing-export.md`](./troubleshooting/015-truncated-paste-missing-export.md) — A `has no exported member` TS error + blank-white route caused by an incomplete file paste (export lost); verify exports + line count after pasting large files

---

## Conventions

- **All documentation is markdown** — copy-paste friendly to Obsidian, GitHub renders it natively, no special tooling needed.
- **Code blocks always specify language** (e.g. ` ```bash `, ` ```python `, ` ```typescript `) for syntax highlighting.
- **Commands include their expected output** so you know what "success" looks like.
- **Dates are ISO 8601** (`2026-05-09`).
- **Code markers in source files** use `# ─── RANGER V3 START: [feature] ───` and `# ─── RANGER V3 END: [feature] ───` so you can search the codebase and find every piece of a feature.

---

## Reading order for new developers (or future-you)

1. `setup/01-system-prep.md` — get the machine ready
2. (subsequent setup docs as they're added)
3. `architecture/` — understand the big picture
4. `features/` — pick the feature you're working on, read its doc
5. `decisions/` — read these any time you're tempted to change something foundational ("why is X done this way?" — likely answered here)

---

*Last updated: 2026-06-25*