# ADR 0001 — PostgreSQL in Docker, not natively installed

**Status:** Accepted
**Date:** 2026-05-09
**Decider:** Brian Kipruto, with architectural guidance

---

## Context

During the initial system setup for R.A.N.G.E.R. V3 on Ubuntu 22.04, we needed to decide where PostgreSQL would run during development:

1. **Natively installed** via `apt install postgresql` (auto-starts as a systemd service on port 5432)
2. **In a Docker container** managed via `docker compose`

This decision affects how the dev environment matches production, how easy it is to onboard a new developer, and how we handle multiple projects on the same machine.

In our case, the `postgresql` package had already been installed during early system prep before this decision was made — so we had to choose whether to keep it or disable it.

## Decision

**Run PostgreSQL exclusively in Docker. Disable the native service.**

```bash
sudo systemctl stop postgresql
sudo systemctl disable postgresql
```

The native `postgresql-client` library headers (`libpq-dev`) remain installed because Python's `psycopg` package needs them at compile time. The native server itself is stopped and won't auto-start on reboot.

## Options Considered

### Option A — Native Postgres only (rejected)

**Pros:**
- Slightly faster (no Docker overhead)
- One less moving piece to debug
- Familiar to people coming from traditional Linux server admin

**Cons:**
- **Version drift between dev and prod.** Production will likely run Postgres 16+. Ubuntu 22.04 ships Postgres 14. Developers would test against 14 and deploy to 16, which means subtle bugs (different default behaviors, new features, etc.) would only surface in production.
- Hard to run multiple isolated databases per project. Every project shares the same Postgres instance with the same default data directory.
- Cleanup is messy if you ever want to fully remove Postgres — config files in `/etc/postgresql/`, data in `/var/lib/postgresql/`, systemd unit files.
- Onboarding a new developer requires extensive `apt` setup + manual user/role creation, all with platform-specific quirks (different on Mac, Windows-WSL, etc.).

### Option B — Docker only (chosen)

**Pros:**
- **Version parity with production.** We pin `postgres:16-alpine` in `docker-compose.yml`, exactly what we'll deploy.
- **Per-project isolation.** Each project's `docker-compose.yml` defines its own Postgres with its own data volume. No conflicts when juggling multiple projects.
- **Trivial onboarding.** A new developer runs `docker compose up` and they have the exact same database as everyone else, regardless of OS.
- **Easy reset.** `docker compose down -v` wipes the database completely, useful when migrations get tangled.
- Stable upgrade path — bump the image tag, rebuild, done.

**Cons:**
- Slight overhead (Docker layer adds maybe 50-100ms latency, irrelevant during dev).
- Docker daemon needs to be running.
- Initial Docker install is itself a setup step (but we needed Docker for Redis anyway).

### Option C — Both (rejected)

Running both means port collisions on 5432 unless we remap, plus the cognitive burden of remembering which Postgres a given app is talking to. No upside over Option B.

## Consequences

### Positive

- The dev DB matches prod's major version (Postgres 16), which catches version-specific bugs early.
- New machines/developers can be set up in minutes — clone repo, `docker compose up`, done.
- We can spin up additional databases (e.g., a test DB for parallel pytest runs) without polluting the system.
- If the Postgres data ever gets corrupted (failed migration, schema drift, etc.), we can `docker compose down -v` and rebuild from scratch.

### Negative

- Running `psql` locally requires either entering the container (`docker exec -it ranger_postgres psql -U ranger -d ranger_v3`) or installing `postgresql-client-16` (the matching client) on the host. We picked the former — it's one command and it's always the right version.
- The Docker daemon is now a dev-environment dependency. If Docker isn't running, the app can't start. Acceptable cost.

### Neutral

- We still have `libpq-dev` and `postgresql-client-14` on the host (came in with `postgresql-contrib`). That's fine — they're just libraries, no running service.

## Implementation

The Postgres container is defined in the project root `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: ranger_postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

Connection settings come from `.env` (and example values from `.env.example`):

```bash
POSTGRES_DB=ranger_v3
POSTGRES_USER=ranger
POSTGRES_PASSWORD=<set to a strong random string>
POSTGRES_HOST=localhost   # because we map container port 5432 to host 5432
POSTGRES_PORT=5432
```

## When to revisit

Reconsider this decision if:

1. Production moves to a managed Postgres service that uses a different major version we can't easily match in a container (unlikely — RDS, Cloud SQL, etc. all support recent Postgres).
2. Docker overhead becomes a measurable bottleneck during dev (extremely unlikely on modern hardware).
3. We add team members on Windows where Docker Desktop has known performance issues with bind mounts (we're already using a named volume, so this is fine).

## Related

- `docs/setup/01-system-prep.md` § 4 — practical steps to disable native Postgres
- `docker-compose.yml` — the actual implementation
- (Future) `docs/architecture/database.md` — overall data architecture

---

*ADR template inspired by Michael Nygard's "Documenting Architecture Decisions" (2011).*