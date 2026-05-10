# 006 — Postgres not running on a fresh terminal

**Date:** 2026-05-10
**Symptom seen during:** Auth feature, Checkpoint 0 (running first migration of the session)

## Symptom

Any Django management command that touches the DB fails with: psycopg.OperationalError: connection failed: connection to server at "127.0.0.1",
port 5432 failed: Connection refused
Is the server running on that host and accepting TCP/IP connections?

## Cause

The development stack runs Postgres + Redis as Docker containers (see ADR-0001). Containers don't auto-start on system boot. Opening a fresh terminal — or rebooting — leaves the containers stopped, so the backend can't reach them.

## Fix

```bash
cd ~/projects/ranger-platform-v3
docker compose up -d postgres redis
```

Verify:

```bash
docker compose ps
# postgres + redis should both show "Up"
```

Then retry whatever command failed.

## Prevention

This is the first step on any fresh terminal session. Combined with virtualenv activation (see `007`), the canonical fresh-terminal start sequence is:

```bash
cd ~/projects/ranger-platform-v3
source .venv/bin/activate          # prompt should show (.venv)
docker compose up -d postgres redis
```

Could be automated with a shell function or a Makefile target if it becomes annoying.