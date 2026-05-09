# 03 — Django Backend Scaffold

**Date completed:** 2026-05-09
**Prerequisites:** [`02-services.md`](./02-services.md) (Postgres + Redis healthy in Docker)
**Goal:** Stand up a production-shaped Django 5 backend with split settings, all 13 apps registered, custom user model migrated, Daphne ASGI server running, JWT auth wired.

This is the biggest single setup checkpoint. The end state is a Django backend that's ready for any feature without further structural changes.

---

## Contents

1. [Python virtualenv + requirements files](#1-python-virtualenv--requirements-files)
2. [Scaffold the Django project](#2-scaffold-the-django-project)
3. [Convert settings.py into a settings package](#3-convert-settingspy-into-a-settings-package)
4. [Wire up manage.py, asgi.py, wsgi.py, urls.py](#4-wire-up-managepy-asgipy-wsgipy-urlspy)
5. [Create the 13 apps](#5-create-the-13-apps)
6. [CustomUser + Organization models](#6-customuser--organization-models)
7. [Migrate, superuser, smoke test](#7-migrate-superuser-smoke-test)
8. [Commit](#8-commit)

---

## 1. Python virtualenv + requirements files

### Virtualenv at project root (not inside ranger_backend/)

The virtualenv lives at `~/projects/ranger-platform-v3/.venv/`, NOT inside the backend directory. Reason: the frontend tooling (Vite, npm) needs the project root to be clean of Python artefacts, and we may add other Python tooling (Celery workers, robot-side Python scripts) that share the venv.

```bash
cd ~/projects/ranger-platform-v3
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

> **Activation reminder:** every new terminal needs `source .venv/bin/activate`. The prompt prefix `(.venv)` confirms it's active.

### Three-tier requirements files

We split requirements across three files for clean dev/prod separation:

```
ranger_backend/requirements/
├── base.txt          ← shared production dependencies
├── development.txt   ← -r base.txt + dev-only tools
└── production.txt    ← -r base.txt + prod-only tools
```

Why three files: lets us run `pip install -r development.txt` locally and `pip install -r production.txt` on the server, with shared deps maintained in one place. Also keeps `pytest`, `ipython`, etc. out of production images (smaller, more secure).

The `-r base.txt` directive at the top of `development.txt` and `production.txt` includes everything from base.

### Pinned versions matter

Every package has `==X.Y.Z`. Without pins, `latest` can drift between machines/deploys. We bump versions intentionally and document in commit messages.

Key choices:
- **Django 5.1.4** — current LTS-track release
- **Channels 4.2 + Daphne 4.1** — required for WebSockets + ASGI
- **psycopg[binary] 3.2** — modern Postgres driver (psycopg2 is legacy)
- **djangorestframework-simplejwt 5.3** — JWT with refresh-token rotation support

### Install

```bash
pip install -r ranger_backend/requirements/development.txt
```

Verify:

```bash
django-admin --version       # 5.1.4
python -c "import channels; print(channels.__version__)"  # 4.2.0
python -c "import psycopg; print(psycopg.__version__)"    # 3.2.3
```

> **Compile failure on psycopg?** Make sure `libpq-dev` is installed (system prep §3). The `psycopg[binary]` variant ships precompiled wheels for most platforms, but falls back to source compilation on edge cases.

---

## 2. Scaffold the Django project

```bash
cd ~/projects/ranger-platform-v3/ranger_backend
django-admin startproject ranger_backend .
```

The **trailing dot** is critical — it tells Django to scaffold *into* the current directory, not a nested subdirectory. Result:

```
ranger_backend/
├── manage.py                 ← project entry point
└── ranger_backend/           ← project package
    ├── __init__.py
    ├── settings.py           ← will become settings/
    ├── urls.py
    ├── asgi.py
    └── wsgi.py
```

The two `ranger_backend/` directories (outer and inner) is normal Django convention. The outer is the project root; the inner is the Python package.

---

## 3. Convert settings.py into a settings package

The default `settings.py` is one big file. We split it into three:

- `settings/base.py` — settings shared across all environments
- `settings/development.py` — local dev overrides (DEBUG, CORS, browsable API)
- `settings/production.py` — hardened production (HSTS, SSL redirects)

This avoids the V2-era trap where conditional `if DEBUG: ...` blocks in a single file caused settings to be silently overridden in unexpected order. With a package, each environment has explicit ownership of its own overrides.

```bash
cd ~/projects/ranger-platform-v3/ranger_backend/ranger_backend
rm settings.py
mkdir settings
touch settings/__init__.py
```

The empty `__init__.py` makes `settings` a Python package.

### `settings/base.py` — what it must contain

Critical settings (each is in the actual file):

- **`BASE_DIR` and `PROJECT_ROOT`** — `BASE_DIR` is the backend dir, `PROJECT_ROOT` goes one more level up to the project root (where `.env` lives).
- **`load_dotenv(PROJECT_ROOT / ".env")`** — loads `.env` BEFORE any setting reads `os.getenv()`. Order matters.
- **`env()` helper** — wraps `os.getenv` with optional `required=True` so missing critical secrets fail fast at startup, not silently as `None`.
- **`SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)`** — never hardcode.
- **`INSTALLED_APPS`** as `DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS` — three lists, concatenated. Easy to scan, easy to reorder.
- **`daphne` first in `DJANGO_APPS`** — must come before `django.contrib.staticfiles` so it overrides `runserver` to be ASGI-aware.
- **`AUTH_USER_MODEL = "accounts.CustomUser"`** — set BEFORE first migration. Cannot be changed once data exists.
- **`CHANNEL_LAYERS`** with Redis backend — wires Channels to the Docker Redis on `localhost:6379`.
- **`DATABASES["default"]`** with `django.db.backends.postgresql` — Docker Postgres on `localhost:5432`.
- **`SIMPLE_JWT`** dict with `ACCESS_TOKEN_LIFETIME=15m`, `REFRESH_TOKEN_LIFETIME=7d`, `ROTATE_REFRESH_TOKENS=True` — security best practice; refresh tokens rotate on each use so a stolen refresh token only works once.
- **`AUTH_PASSWORD_VALIDATORS`** with `MinimumLengthValidator(min_length=12)` — V3 doc requires 12+ char passwords.
- **`TIME_ZONE = "Africa/Nairobi"`** — the platform operates in Kenya.

### `settings/development.py` — what it overrides

- `DEBUG = True`
- Adds `BrowsableAPIRenderer` to DRF — lets you browse the API in a browser
- Adds `SessionAuthentication` to DRF — lets admin-logged-in users hit DRF endpoints from the browsable UI
- `CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]` — only allows Vite dev server
- Verbose console logging

### `settings/production.py` — what it hardens

- `DEBUG = False`
- `SECURE_SSL_REDIRECT = True`, `SECURE_HSTS_SECONDS = 1 year`, `HSTS_PRELOAD = True`
- `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`
- `SECURE_PROXY_SSL_HEADER` so Django trusts an upstream nginx's `X-Forwarded-Proto` header

This file is currently a stub — full hardening lives in the deployment phase.

---

## 4. Wire up manage.py, asgi.py, wsgi.py, urls.py

`startproject` generated these files referencing the now-deleted `ranger_backend.settings` (single file). Each needs to point at the right environment-specific settings module.

| File | Default | Updated to |
|------|---------|-----------|
| `manage.py` | `ranger_backend.settings` | `ranger_backend.settings.development` |
| `asgi.py` | `ranger_backend.settings` | `ranger_backend.settings.development` |
| `wsgi.py` | `ranger_backend.settings` | `ranger_backend.settings.production` |

Different defaults are deliberate:
- `manage.py` runs locally during development
- `asgi.py` is also primarily local/dev (for Daphne); production overrides via `DJANGO_SETTINGS_MODULE` env var
- `wsgi.py` is only used in production (Gunicorn behind nginx); defaults straight to production settings

### `asgi.py` is the most important one

The default `asgi.py` is HTTP-only. We extend it to route WebSocket traffic too:

```python
django_asgi_app = get_asgi_application()  # initialize Django first

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

websocket_urlpatterns = []  # filled in when ros_bridge / api WS routes ship

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns)),
})
```

`AllowedHostsOriginValidator` enforces `ALLOWED_HOSTS` for WebSocket origin checks too, which is non-obvious but important for security.

### `urls.py` is minimal at this stage

Just `/admin/` and a debug-only static-files line. Per-app URLs get included as features ship.

---

## 5. Create the 13 apps

The apps mirror the architecture in the V3 doc:

| App | Purpose |
|-----|---------|
| `accounts` | CustomUser, Organization, auth-related models |
| `core` | Robot, SensorType, SensorLog (lean), per-sensor logs |
| `missions` | Mission, Waypoint, ActionType, MissionAction |
| `ros_bridge` | rosbridge integration (Phase 2) |
| `visualization` | Saved layouts, dashboard widgets |
| `alerts` | AlertRule, AlertEvent, Notification |
| `reports` | ComplianceReport, ReportTemplate |
| `billing` | Subscription, UsageRecord, Invoice |
| `platform_config` | SavedView, branding, tenant config |
| `ai_assistant` | Gemma 2 chat sessions, NL mission planning |
| `community` | SurveyRequest, PublicDataset (community portal) |
| `fleet` | SoftwareRelease, UpdateDeployment (OTA) |
| `audit` | AuditLog (every API action tracked) |

Most apps are scaffolded empty in Phase 1 — their models ship with their respective features.

### The chicken-and-egg problem

`startapp` runs `django.setup()` internally, which loads `INSTALLED_APPS`, which fails if any listed app doesn't exist yet. Same for `AUTH_USER_MODEL = "accounts.CustomUser"` — Django tries to resolve the user model at startup.

**Solution:** temporarily comment out `LOCAL_APPS` in `INSTALLED_APPS` AND `AUTH_USER_MODEL`, run `startapp` for all 13 apps, then restore both.

See [`troubleshooting/002-startapp-chicken-and-egg.md`](../troubleshooting/002-startapp-chicken-and-egg.md) for the diagnostic flow.

```bash
# After commenting out INSTALLED_APPS and AUTH_USER_MODEL:
for app in accounts core missions ros_bridge visualization alerts \
          reports billing platform_config ai_assistant community \
          fleet audit; do
  python manage.py startapp $app
done
```

Then restore both settings and verify:

```bash
python manage.py check
# Expected: System check identified no issues (0 silenced).
```

---

## 6. CustomUser + Organization models

In `accounts/models.py`, two models:

### `Organization`
- `name`, `slug` (unique), `logo` (ImageField), `theme_color` (hex string, e.g. `#0ea5e9`)
- `is_active` flag
- Custom permission `change_branding` declared in `Meta.permissions`
- `created_at`, `updated_at` audit fields

### `CustomUser(AbstractUser)`
- Extends `AbstractUser` (keeps Django's password hashing, groups, sessions)
- `organization` FK with `on_delete=PROTECT` and `null=True` — superusers can transcend tenancy
- `phone`, `mfa_enabled` (TOTP setup ships in a later phase)
- `created_at`, `updated_at`

### Why `PROTECT` on the organization FK?

If someone tries to delete an Organization with users still in it, Django refuses. Compare to `CASCADE` which would silently delete every user. `PROTECT` requires explicit cleanup before deletion — the safer default.

### Why no `role` field?

V2's `role` enum was inflexible and got migrated to Django Groups. We skip the mistake and use Groups from day one. "Org Admin", "Org Operator", "Org Viewer" are Groups with associated permissions, not enum values.

See [`decisions/0002-multi-tenant-via-organization-fk.md`](../decisions/0002-multi-tenant-via-organization-fk.md) for the multi-tenancy rationale.

---

## 7. Migrate, superuser, smoke test

### First migration

```bash
python manage.py makemigrations accounts
# Creates accounts/migrations/0001_initial.py (Organization + CustomUser)

python manage.py migrate
# Applies our migration plus Django's built-ins (auth, admin, sessions, contenttypes)
```

Verify the database actually has the tables:

```bash
docker exec -it ranger_postgres psql -U ranger -d ranger_v3 -c "\dt"
```

Expected ~11 tables including `accounts_customuser`, `accounts_customuser_groups`, `accounts_customuser_user_permissions`, `accounts_organization`.

### Superuser

```bash
python manage.py createsuperuser
```

Required password >= 12 chars (we set `MinimumLengthValidator` to 12). Leave `organization`, `phone`, `mfa_enabled` blank — superusers don't belong to a tenant.

### Smoke test

```bash
python manage.py runserver
```

Note the output: `Starting ASGI/Daphne version 4.1.2 development server`. Because `daphne` is first in `INSTALLED_APPS`, even `runserver` boots through Daphne. You get Channels support without thinking about it.

Open `http://localhost:8000/admin/`, log in. You should see:
- ACCOUNTS section with "Custom users" and "Organizations"
- AUTHENTICATION AND AUTHORIZATION section with "Groups"

Create a test Organization (e.g. "ByteAnza") to confirm forms work.

### Daphne directly (NOT for daily dev work)

```bash
daphne -p 8000 ranger_backend.asgi:application
```

This starts standalone Daphne, but **the admin will appear unstyled** because Daphne doesn't serve static files. `runserver` includes a dev-only static file handler; bare Daphne does not.

For day-to-day development, use `runserver` — it boots through Daphne anyway (because `daphne` is first in `INSTALLED_APPS`), so you get full ASGI/Channels/WebSocket support PLUS static file serving PLUS auto-reload on code changes.

Use bare `daphne` only when:
- Reproducing a production-only issue
- Measuring cold-start time without the reloader
- Testing the exact ASGI startup sequence

In production, neither approach handles statics — nginx (or another reverse proxy) serves `/static/` and proxies everything else to Daphne behind it.

See [`troubleshooting/005-daphne-no-static-files.md`](../troubleshooting/005-daphne-no-static-files.md) for full detail.

---

## 8. Commit

```bash
cd ~/projects/ranger-platform-v3
git status   # confirm: ranger_backend/ untracked, no .venv/, no __pycache__/, no .env

git add ranger_backend/
git commit -m "feat: django 5 backend scaffold with custom user + organization"
git push
```

---

## End state

- All 13 Django apps registered in `INSTALLED_APPS`
- Custom user model migrated; Organization model migrated
- One superuser exists
- Postgres has all expected tables
- Daphne serves both HTTP and (eventually) WebSocket traffic
- DRF + JWT installed; no auth endpoints yet (that's Feature 1)
- CORS allows the Vite dev server (port 5173)

**Next:** [`04-frontend-scaffold.md`](./04-frontend-scaffold.md) — React + TypeScript + Vite + Tailwind v4 frontend.

---

## Things that went wrong

### 1. The `startapp` chicken-and-egg

Tried to register `LOCAL_APPS` and `AUTH_USER_MODEL` in `base.py` BEFORE creating the app folders. Django's `startapp` itself runs `django.setup()`, which fails if any registered app doesn't exist on disk.

Detail: [`troubleshooting/002-startapp-chicken-and-egg.md`](../troubleshooting/002-startapp-chicken-and-egg.md).

**Lesson:** scaffold all app folders BEFORE editing `base.py`, OR comment out the references temporarily.

### 2. `AUTH_USER_MODEL` resolved at admin-load time, not lazily

After commenting out `LOCAL_APPS`, the next error was `AUTH_USER_MODEL refers to model 'accounts.CustomUser' that has not been installed`. Django's auth admin imports run at startup and try to resolve the user model immediately — not lazily as I'd assumed.

**Lesson:** the `accounts` app's `models.py` MUST contain the `CustomUser` class before `python manage.py check` will pass with `AUTH_USER_MODEL` set. The two-pronged fix: comment out both `LOCAL_APPS` AND `AUTH_USER_MODEL` for the `startapp` loop; restore `LOCAL_APPS` immediately after; create the model file before restoring `AUTH_USER_MODEL`.

---

*Document last updated: 2026-05-09*