# R.A.N.G.E.R. Platform V3 — Documentation

This is the working knowledge base for the R.A.N.G.E.R. V3 build. It covers system setup, architecture decisions, per-feature implementation notes, and troubleshooting logs.

The goal: anyone (including future-you) should be able to read this and understand **what was built, why it was built that way, and how to recover if it breaks**.

---

## Structure

### `setup/`
Step-by-step guides for getting a development environment running from a fresh Ubuntu install. Read these in order if you're setting up a new machine.

- [`01-system-prep.md`](./setup/01-system-prep.md) — Python 3.11, Node 20, Docker, GitHub SSH, project skeleton

### `architecture/`
Higher-level design documentation. The *why* behind the structural choices: split settings, multi-tenancy model, panel system, ROS bridge pattern, etc.

*(Coming as we build.)*

### `features/`
One markdown file per feature/phase, documenting end-to-end implementation. Each file covers: what the feature does, files created/modified, data flow, API endpoints, frontend components, gotchas encountered.

*(Coming as we build.)*

### `decisions/`
Architecture Decision Records (ADRs). Short, dated records of important technical choices. Format: problem → options considered → decision → consequences.

- [`0001-postgres-in-docker-not-native.md`](./decisions/0001-postgres-in-docker-not-native.md) — Why we run PostgreSQL in Docker even though Ubuntu installed it natively

### `troubleshooting/`
Error logs and fixes. Each entry records: what we saw, what caused it, how we fixed it, how to prevent it.

*(Coming as we hit issues.)*

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