# 009 — Refresh cookie `Secure` flag set in dev

**Date:** 2026-05-10
**Symptom seen during:** Auth feature, Checkpoint 3 (testing cookie-based refresh)

## Symptom

Login response in dev included `Secure` in the `Set-Cookie` header: Set-Cookie: ranger_refresh=...; HttpOnly; Max-Age=604800; Path=/api/auth/; SameSite=Strict; Secure

`Secure` means "only send this cookie over HTTPS." Dev runs over HTTP. Result: the cookie sets, but **the browser never sends it back** on subsequent requests. Refresh and logout would silently break.

curl ignored the `Secure` flag in its cookie jar, so curl-based testing accidentally hid the bug. Caught when planning browser-based testing in Checkpoint 6.

## Cause

The Django settings module structure splits config across files:

- `base.py` defines defaults including `DEBUG = False`
- `development.py` does `from .base import *` and then overrides `DEBUG = True`

`REFRESH_COOKIE` was defined in `base.py` as:

```python
REFRESH_COOKIE = {
    "secure": not DEBUG,
    # ...
}
```

The order of evaluation:

1. Python loads `base.py`
2. `DEBUG = False` (the default)
3. `REFRESH_COOKIE = {"secure": not DEBUG, ...}` → **`secure: True`** (because DEBUG is still False at this moment)
4. Python loads `development.py`
5. `DEBUG = True` overrides
6. But `REFRESH_COOKIE["secure"]` is already frozen at `True`

The dict was evaluated once at module-import time, before the dev override could take effect.

## Fix

Two options. We picked option 2.

### Option 1: define `REFRESH_COOKIE` in each environment file separately

Pros: clean separation. Cons: duplicates the dict.

### Option 2: defer the `secure` evaluation to request time

In `base.py`, drop `secure` from the config dict entirely:

```python
REFRESH_COOKIE = {
    "name": "ranger_refresh",
    "path": "/api/auth/",
    "httponly": True,
    "samesite": "Strict",
    # 'secure' is computed at request time in views (reads settings.DEBUG)
    # because base.py is evaluated before development.py overrides DEBUG.
    "max_age": int(SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
}
```

In `accounts/views.py`, inside `_set_refresh_cookie`:

```python
response.set_cookie(
    # ...
    secure=not settings.DEBUG,   # read at request time, always correct
    # ...
)
```

`settings.DEBUG` is read fresh on every request. Dev server reads `True`. Production reads `False` and the cookie auto-upgrades to HTTPS-only.

## Prevention

For any setting that's environment-dependent and gets baked into a dict or other compound structure: **don't evaluate the dependency at module-import time**. Either:

- Define the structure in each environment-specific settings file
- Evaluate the environment-dependent piece lazily (e.g. inside a function that reads `settings.X`)

The general pattern: anything in `base.py` that references `DEBUG`, `ENVIRONMENT`, etc. is suspicious unless the override file rebuilds the whole structure.

## Detection during testing

Browser tests catch this; curl tests don't. When adding any cookie-related backend feature, plan for at least one test in a real browser before declaring done. Curl is good for plumbing checks; the cookie security flags only matter to actual browsers.