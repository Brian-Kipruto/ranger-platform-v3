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
- [`08-ros-bridge-gps.md`](./features/08-ros-bridge-gps.md) — first robot-side code: `robot/gps_node.py` (NMEA → `NavSatFix` on `/fix`, GPS on the Orin header UART), `nmea_sim` over a socat pty, and `ros_ingest` writing `SensorLog` via rosbridge with a `--source` flag defaulting to `simulated`; sim-verified end to end, real-sky sign-off pending
- [`08-ros-bridge-gps-retrospective.md`](./features/08-ros-bridge-gps-retrospective.md) — what worked, the plan that assumed untested hardware, the destroyed module, the stale handoff, the `App.tsx` regression found during WIP cleanup, carry-forwards including `--region` for Rabat and field time
- [`10-1-postgis-foundation.md`](./features/10-1-postgis-foundation.md) — F10 epic, sub-feature 1: PostGIS + GeoDjango, geometry as source of truth on SensorLog/Waypoint, Mission AOI, expand→migrate→contract migrations, contract-diff verification, first pytest suite
- [`10-1-postgis-foundation-retrospective.md`](./features/10-1-postgis-foundation-retrospective.md) — what worked, the passing-checks-with-wrong-ENGINE trap, the ROS/pytest collision, the file-rename friction, carry-forwards to F10.2
- [`10-2-gee-integration.md`](./features/10-2-gee-integration.md) — F10 epic, sub-feature 2: Earth Engine client, 10-dataset catalog, four provenance tiers, 12,081 modelled Marsabit points, clipped COG retrieval with PostGIS-asserted footprints, seven org-scoped read endpoints
- [`10-2-gee-integration-retrospective.md`](./features/10-2-gee-integration-retrospective.md) — what worked, the three stale-state traps, the warning that explained itself away, the frontend provenance gap, carry-forwards to F10.3
- [`10-3-satellite-view.md`](./features/10-3-satellite-view.md) — F10 epic, sub-feature 3: provenance surfaced across the console, uncapped provenance summary on `/map-data/`, COG→PNG render endpoint with a per-(dataset, layer) calibration registry, scene-stretched ramps with a reported range, the Satellite Integration screen, and the ground sensor track drawn over the imagery
- [`10-3-satellite-view-retrospective.md`](./features/10-3-satellite-view-retrospective.md) — what worked, the same count-vs-set bug three times, the `.distinct()` on an ordered queryset, the test whose right and wrong answers coincided, misreading `is_verified` off its name, carry-forwards to F10.4

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
- [`0011-geospatial-db-postgis-now-timescaledb-later.md`](./decisions/0011-geospatial-db-postgis-now-timescaledb-later.md) — PostGIS adopted for F10, TimescaleDB deferred; geometry(Point,4326) 2D as sole source of truth with lat/lon as derived properties; one sanctioned write path via `core.geo.point_from_latlon`
- [`0012-satellite-eo-gee-cog-pipeline.md`](./decisions/0012-satellite-eo-gee-cog-pipeline.md) — GEE as primary provider (and the noncommercial-licensing problem it defers), four provenance tiers defaulting to the weakest, three-way tenancy asymmetry, `getDownloadURL` → clipped COG on disk rather than expiring tile URLs, EPSG:4326 with raw pixel values, footprint read from the raster and asserted in PostGIS, `cog_path` never serialized

- [`0013-raster-delivery-and-layer-semantics.md`](./decisions/0013-raster-delivery-and-layer-semantics.md) — PNG rendered from our own COGs rather than expiring GEE tile URLs or a tile server overbuilt for 300 m sites; a layer is a `(dataset, layer)` pair with declared calibration, because an additive offset does not cancel in a normalised ratio and Landsat NDVI from raw DNs renders convincingly and wrong; captions state what each number is NOT; provenance summaries computed on the uncapped set
- [`0014-robot-code-in-repo-gps-on-header-uart.md`](./decisions/0014-robot-code-in-repo-gps-on-header-uart.md) — robot code in `robot/` beside the platform as plain `rclpy` scripts (not a separate repo, not yet a colcon package); GPS on the 40-pin header UART `/dev/ttyTHS1` because JetPack 6.2.2 ships no CH340 driver
- [`0015-ros-ingest-provenance-timestamps-threading.md`](./decisions/0015-ros-ingest-provenance-timestamps-threading.md) — `--source` defaults to `simulated` (not derived from the robot's frame_id); robot header stamps guarded by a clock-skew check; gate on fix status because NaN arrives as `null`; every skip counted; callback enqueues, main thread writes

### `analysis/`
Findings produced BY the platform, with method and limits stated. Distinct from `features/` (what we built) and `decisions/` (why we built it that way).

- [`A01-vegetation-index-vs-gamma-dose.md`](./analysis/A01-vegetation-index-vs-gamma-dose.md) — tested whether NDVI/BSI explain gamma dose variance across the seven KNRA sites; they do not (rho +0.39 and +0.18, n=7, threshold 0.786), and the sign is opposite to soil-water attenuation. Variance appears lithological — Forole carries ~7x Boji's ⁴⁰K. Includes the rule F10.4 must follow: correlation only against `live`/`reported` tiers, never `modelled`

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
- [`016-geodjango-app-without-postgis-engine.md`](./troubleshooting/016-geodjango-app-without-postgis-engine.md) — `AttributeError: 'DatabaseOperations' object has no attribute 'geo_db_type'`; `django.contrib.gis` was installed but `DATABASES.ENGINE` was still plain postgresql — `check`, `makemigrations`, and `CreateExtension` all pass regardless
- [`017-ros-pythonpath-breaks-pytest.md`](./troubleshooting/017-ros-pythonpath-breaks-pytest.md) — pytest exits before collection because ROS 2's `PYTHONPATH` leaks a Python 3.10 plugin into the 3.11 venv; run `PYTHONPATH= pytest`
- [`018-gee-service-account-missing-iam-roles.md`](./troubleshooting/018-gee-service-account-missing-iam-roles.md) — Earth Engine 403s identically for a bad key and a valid key missing IAM roles; the account needs both Service Usage Consumer and Earth Engine Resource Writer
- [`019-stale-catalog-blank-cloud-property.md`](./troubleshooting/019-stale-catalog-blank-cloud-property.md) — `--max-cloud` silently did nothing because catalog rows carried a blank `cloud_property` since the field was added; `check_gee` verifies the catalog against the world but nothing verified the database against the catalog
- [`020-max-age-served-stale-render.md`](./troubleshooting/020-max-age-served-stale-render.md) — a rewritten renderer changed nothing on screen because `Cache-Control: max-age=3600` let the browser answer from disk without contacting Django; `Ctrl+Shift+R` does not cover an XHR fired later by JS, so the hard reload appeared to exonerate the cache
- [`022-ch340-no-driver-on-jetpack.md`](./troubleshooting/022-ch340-no-driver-on-jetpack.md) — CH340 enumerates on the Orin but never becomes `/dev/ttyUSB*`: `lsusb -t` shows `Driver=` empty, JetPack 6.2.2 ships no `ch341.ko`; moved to header UART, proven by one-wire loopback
- [`023-gps-tx-rx-not-crossed.md`](./troubleshooting/023-gps-tx-rx-not-crossed.md) — GPS silent on the header: solid `0x00` at 38400/115200 means the RX line is held low; GPS RX was on the Orin's RX pin. `xxd` across bauds, and prove each half on a known-good bench
- [`024-reversed-polarity-killed-gps.md`](./troubleshooting/024-reversed-polarity-killed-gps.md) — NEO-M8N destroyed by a few seconds of reversed supply while rewiring powered; power off, count pins by touch, keep spares
- [`025-orin-clock-unsynced-no-dns.md`](./troubleshooting/025-orin-clock-unsynced-no-dns.md) — Orin clock four months behind: NTP active but zero packets because DNS doesn't resolve over the USB NAT (`ping 8.8.8.8` hides it); DNS in `resolved.conf`; field time still open
- [`026-brltty-claims-ch340.md`](./troubleshooting/026-brltty-claims-ch340.md) — `/dev/ttyUSB0` appears and vanishes on Ubuntu 22.04 because `brltty` claims the CH340; `apt remove brltty`
- [`027-roslibpy-callback-synchronous-only-operation.md`](./troubleshooting/027-roslibpy-callback-synchronous-only-operation.md) — `ros_ingest` receives every fix and writes nothing: roslibpy callbacks run on the Twisted reactor thread, where Django raises `SynchronousOnlyOperation`; enqueue in the callback, write on the main thread

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

*Last updated: 2026-09-28*