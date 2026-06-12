# 008 — Self-referential URL include in app `urls.py`

**Date:** 2026-05-10
**Symptom seen during:** Auth feature, Checkpoint 1 (wiring the new accounts URLconf)

## Symptom

Caught in code review before causing a runtime error. The pattern that would break:

```python
# accounts/urls.py
urlpatterns = [
    path("users/me/", views.UserMeView.as_view()),
    path("api/", include("accounts.urls")),   # ← this is itself
]
```

Django would either crash on startup with `RecursionError` during URL resolution, or 500 on every request once it tries to walk the include tree.

## Cause

Confusion about which `urls.py` does what. There are two:

- **Project URLconf** (`ranger_backend/ranger_backend/urls.py`): the front door. Owns top-level prefixes (`admin/`, `api/`, `media/`) and decides which app handles each prefix via `include(...)`.
- **App URLconf** (`ranger_backend/accounts/urls.py`): lists routes relative to wherever the project mounted that app. **Never includes itself.** Never knows or cares what prefix the project chose.

The mistake was treating the app `urls.py` as if it had to declare its own prefix.

## Fix

Project file:

```python
# ranger_backend/ranger_backend/urls.py
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),    # mount point
]
```

App file:

```python
# accounts/urls.py
urlpatterns = [
    path("users/me/", views.UserMeView.as_view()),         # → /api/users/me/
    path("auth/token/", views.CustomTokenObtainPairView.as_view()),  # → /api/auth/token/
]
```

The app file declares routes; the project file declares where those routes live in the URL tree.

## Prevention

When adding a new feature's URLconf:

1. Open the project `urls.py` first. Add the include there.
2. Then write the app `urls.py` from scratch with relative paths only.
3. Never put `include("<app>.urls")` inside `<app>/urls.py`.