# Phase 1 Retrospective

**Date:** 2026-05-09
**Duration:** approximately one day, single session
**Builder:** Brian Kipruto (physics background, learning software development)
**Outcome:** ✅ Foundation scaffold complete; React app loads, Django admin works, both backed by Postgres + Redis in Docker.

---

## What we built

| Layer | Result |
|---|---|
| System prep | Python 3.11, Node 20, Docker, GitHub SSH on Ubuntu 22.04 |
| Services | Postgres 16 + Redis 7 in Docker Compose, healthchecks passing |
| Backend | Django 5.1, split settings, 13 apps, custom user + organization, Daphne ASGI, JWT auth wired |
| Frontend | React 19 + TS + Vite 8 + Tailwind 4, dev-proxy to backend, Zustand + Axios stubs |
| Documentation | This whole `docs/` tree, including ADRs and troubleshooting entries |

Six commits on `main`, all pushed to GitHub.

---

## What worked well

### 1. Stopping at every checkpoint to verify

Every step had explicit "expected output" and we checked before moving on. Total speed wasn't faster than running everything end-to-end, but the *predictability* was much higher — when something broke we knew which step was at fault.

### 2. Documenting decisions inline

Writing ADR 0001 (Postgres in Docker) right after deciding it, while the reasoning was still fresh, made the doc much sharper than it would have been in retrospect. Same for ADR 0002 (multi-tenancy).

### 3. Pre-planning all 13 apps

Creating all the apps in Phase 1 — even though most are empty — sets the architecture in stone. We won't be tempted later to merge `alerts` and `notifications` into one because "they're both empty anyway." Each has a clear bounded concern.

### 4. Pinning everything

`requirements/*.txt` pins exact versions. `package-lock.json` pins JS deps. Means anyone (including future-you) gets the same environment from the same checkout. The fact that this matters wouldn't be obvious in Phase 1 — it pays off a year from now when a transitive dep gets a breaking update.

### 5. Multi-environment settings package up front

`base.py` / `development.py` / `production.py` from day one. Forced clear thinking about which settings are environment-specific. Avoids the V2-style trap of `if DEBUG: SOME_SETTING = X` blocks.

### 6. Splitting docs into types

`setup/`, `architecture/`, `features/`, `decisions/`, `troubleshooting/` — each has a different purpose. Means when you remember "we hit some Docker permission issue", you know to check `troubleshooting/` not `setup/`. Same for ADRs.

---

## What was harder than expected

### 1. The chicken-and-egg with Django apps + AUTH_USER_MODEL

Cost: maybe 30 minutes and three back-and-forth attempts. We registered apps in `INSTALLED_APPS` before they existed, and `AUTH_USER_MODEL` couldn't be lazily resolved as I'd assumed.

**What I'd do differently:** scaffold all 13 apps first (with `INSTALLED_APPS` empty), define `CustomUser` in `accounts/models.py`, THEN add the apps to `INSTALLED_APPS` and set `AUTH_USER_MODEL`. Strictly bottom-up.

Documented in `troubleshooting/002-startapp-chicken-and-egg.md` so it never costs us 30 minutes again.

### 2. Heredoc paste artefacts

Pasting `cat > file << 'EOF' ... EOF` blocks from chat into VS Code several times included the wrapper. Each time it required a `git diff` and manual cleanup.

**What I'd do differently:** when content is meant for paste-into-file, present it as just the file content (no wrapper). When content is meant for paste-into-terminal, leave the heredoc wrapper. Documented in `troubleshooting/004-vscode-paste-heredoc-leak.md`.

### 3. Native Postgres conflict

Installing the native `postgresql` package early meant systemd auto-started a Postgres 14 server on port 5432, which collided with our Docker Postgres 16 plan.

**What I'd do differently:** flag the "Docker for stateful services, no native installs" pattern earlier in the system-prep step, so the apt install list doesn't include `postgresql`.

Captured in ADR 0001.

### 4. Docker group membership not applying

Adding the user to the `docker` group via `usermod` doesn't take effect until full graphical logout. Cost about 15 minutes of confusion.

**What I'd do differently:** explicitly call out the logout requirement in the install step. Documented in `troubleshooting/001-docker-permission-denied.md`.

### 5. Tooling versions newer than reference docs

Vite 8, TypeScript 6, React 19, Tailwind v4 — all newer than what the V3 architecture doc assumed. None broke us, but I had to adapt the setup commands as we went (e.g. drop `baseUrl` from tsconfig).

**What I'd do differently:** check `npm list` versions immediately after `npm install` and adapt before writing config. We did this and caught the TS 6 deprecation early.

---

## Architectural decisions made

1. **Postgres in Docker, not native** (ADR 0001)
2. **Multi-tenancy via Organization FK + Django Groups** (ADR 0002)
3. **Split settings from day one** — `base.py` / `development.py` / `production.py`
4. **All 13 apps scaffolded up front** even if empty
5. **Tailwind v4 over v3** — the new plugin-based pipeline is faster and cleaner
6. **Zustand over Redux** for global state
7. **JWT in localStorage** (not httpOnly cookie) — tradeoff documented; can revisit if XSS becomes a concern
8. **Daphne for both dev and prod** — `runserver` transparently uses Daphne when it's first in `INSTALLED_APPS`

---

## Lessons for Phase 2 onward

### Process

- Continue verifying every checkpoint before moving on. Not every step is risky, but skipping verification after a critical step has cost us several times across the V2 build.
- Continue writing docs as we build. The retrospective doc you're reading was written the day Phase 1 finished — six months from now we'd never reconstruct it.
- For new features: scaffold the full directory structure first, then fill in code. Backwards (code first, then refactor into the right structure) is harder.

### Technical

- When adding new Django apps to an existing project, run `startapp` first, then add to `LOCAL_APPS`. Never the reverse.
- Pin versions; bump intentionally; document the bump.
- When in doubt about whether something is dev-only or shared, put it in `development.py` first. Promoting to `base.py` is one easy refactor; demoting is harder.
- Test cross-tenant isolation early. The `OrgScopedMixin` for DRF views is on my mind for Feature 1 — if we add it generically, every future view inherits it.

### Communication

- The pasting-from-chat fragility caused real friction. Going forward, when generating content meant for files, present it as raw content with the file path stated separately.
- Long blocks of code/markdown should be made copyable in a way that doesn't include surrounding scaffolding (heredoc wrappers, markdown fence info, etc.).

---

## Next phase

Feature 1: **Authentication flow**.

Scope:
- POST `/api/auth/token/` (login, returns access + refresh)
- POST `/api/auth/token/refresh/`
- POST `/api/auth/logout/` (blacklists refresh token)
- GET `/api/users/me/` (current user + org + permissions)
- Frontend: LoginPage, AuthContext wired to Zustand store, protected route wrapper, axios refresh interceptor (the stub from Phase 1 gets implemented)
- Documentation: `docs/features/01-auth.md`, possibly an ADR on the localStorage-vs-httpOnly-cookie choice

Estimated complexity: **Medium**.
Branch: TBD (you'll tell me).

---

*Document last updated: 2026-05-09*