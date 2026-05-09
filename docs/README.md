# R.A.N.G.E.R. Platform V3 — Documentation

This is the working knowledge base for the R.A.N.G.E.R. V3 build. It covers system setup, architecture decisions, per-feature implementation notes, and troubleshooting logs.

The goal: anyone (including future-you) should be able to read this and understand **what was built, why it was built that way, and how to recover if it breaks**.

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

*(Coming as we build.)*

### `decisions/`
Architecture Decision Records (ADRs). Short, dated records of important technical choices. Format: problem → options considered → decision → consequences.

- [`0001-postgres-in-docker-not-native.md`](./decisions/0001-postgres-in-docker-not-native.md) — Why we run PostgreSQL in Docker even though Ubuntu installed it natively
- [`0002-multi-tenant-via-organization-fk.md`](./decisions/0002-multi-tenant-via-organization-fk.md) — Why we use a shared schema with `organization` FK, and Django Groups instead of a `role` enum

### `troubleshooting/`
Error logs and fixes. Each entry records: what we saw, what caused it, how we fixed it, how to prevent it.

- [`001-docker-permission-denied.md`](./troubleshooting/001-docker-permission-denied.md) — `permission denied while trying to connect to the Docker API` after fresh install
- [`002-startapp-chicken-and-egg.md`](./troubleshooting/002-startapp-chicken-and-egg.md) — Django `startapp` fails when apps registered in `INSTALLED_APPS` don't exist yet, and the `AUTH_USER_MODEL` complication
- [`003-tsconfig-baseurl-deprecated.md`](./troubleshooting/003-tsconfig-baseurl-deprecated.md) — TypeScript 6 deprecates `baseUrl`; use `paths` alone
- [`004-vscode-paste-heredoc-leak.md`](./troubleshooting/004-vscode-paste-heredoc-leak.md) — Pasting heredoc-wrapped content from chat into VS Code includes the wrapper
- [`005-daphne-no-static-files.md`](./troubleshooting/005-daphne-no-static-files.md) — Django admin renders unstyled when served by bare `daphne` (use `runserver` for dev)

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

*Last updated: 2026-05-09*