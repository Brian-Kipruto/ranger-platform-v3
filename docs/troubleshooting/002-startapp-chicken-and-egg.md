# Django — `startapp` chicken-and-egg with `INSTALLED_APPS` and `AUTH_USER_MODEL`

**First encountered:** 2026-05-09 (Checkpoint 3)
**Severity:** Blocks app creation entirely
**Frequency:** Always when scaffolding apps after registering them in settings

---

## Symptom

Running `python manage.py startapp accounts` (or any other app) fails with:

```
ModuleNotFoundError: No module named 'accounts'
```

After commenting out `LOCAL_APPS` from `INSTALLED_APPS`, a second error appears:

```
django.core.exceptions.ImproperlyConfigured: AUTH_USER_MODEL refers to model
'accounts.CustomUser' that has not been installed
```

After also commenting out `AUTH_USER_MODEL`, you can finally run `startapp` successfully. But uncommenting `AUTH_USER_MODEL` again brings back another error:

```
LookupError: App 'accounts' doesn't have a 'CustomUser' model.
```

---

## Root cause

Django's `startapp` (and every other `manage.py` command) runs `django.setup()` first. `django.setup()`:

1. Loads `INSTALLED_APPS`
2. Imports each registered app — fails if the app folder doesn't exist on disk
3. Loads `django.contrib.admin`, which imports `django.contrib.auth.admin`, which calls `get_user_model()` — fails if `AUTH_USER_MODEL` references a model class that doesn't exist

**`AUTH_USER_MODEL` is NOT lazily resolved.** It's resolved at admin-load time, which happens during every command. The `accounts` app folder existing isn't enough — the `CustomUser` class also has to be defined in `accounts/models.py`.

This creates a 3-stage chicken-and-egg:

| Stage | Required state | What you need |
|-------|----------------|---------------|
| 1 | App folder exists on disk | `startapp accounts` (but this won't run if any app is missing) |
| 2 | `CustomUser` defined in `accounts/models.py` | The model code |
| 3 | `AUTH_USER_MODEL = "accounts.CustomUser"` in settings | Settings config |

You can't start at stage 3, walk back to stage 1, then forward — Django demands all three at once.

---

## Diagnostic flow

If you see `ModuleNotFoundError: No module named '<app>'`:
- Check whether the app folder exists in `ranger_backend/`
- If not, you've registered it in `INSTALLED_APPS` before creating it

If you see `AUTH_USER_MODEL refers to model 'X.Y' that has not been installed`:
- Check whether app `X` is in `INSTALLED_APPS`
- Check whether `Y` is defined in `X/models.py`
- Both must be true

---

## Fix (the right sequence)

**Order of operations to avoid the issue entirely:**

1. Scaffold the Django project (`django-admin startproject`)
2. Convert `settings.py` → `settings/` package
3. **Initially leave `LOCAL_APPS = []` (empty) and DO NOT set `AUTH_USER_MODEL` yet**
4. Run `startapp` for every app — succeeds because `LOCAL_APPS` is empty
5. Edit `accounts/models.py` to define `CustomUser` and `Organization`
6. Now populate `LOCAL_APPS` with all 13 app names
7. Now set `AUTH_USER_MODEL = "accounts.CustomUser"`
8. `python manage.py check` — passes
9. `python manage.py makemigrations accounts && migrate` — works

---

## Fix (the recovery sequence if you hit the issue mid-setup)

If `INSTALLED_APPS` and `AUTH_USER_MODEL` are already set:

1. Comment out `LOCAL_APPS` in the `INSTALLED_APPS` line:
```python
   INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS  # LOCAL_APPS added back later
```
2. Comment out `AUTH_USER_MODEL`:
```python
   # AUTH_USER_MODEL = "accounts.CustomUser"
```
3. Verify check passes:
```bash
   python manage.py check
```
4. Run `startapp` for all apps:
```bash
   for app in accounts core missions ...; do
     python manage.py startapp $app
   done
```
5. Define `CustomUser` and `Organization` in `accounts/models.py` (full content)
6. Restore `INSTALLED_APPS` to include `LOCAL_APPS`
7. Restore `AUTH_USER_MODEL`
8. `python manage.py check` — should pass
9. `python manage.py makemigrations accounts && migrate`

---

## Why this isn't documented better in Django

Django's docs assume you scaffold one app at a time, registering each after creation. Real-world projects with split settings + many pre-planned apps + a custom user model hit this issue, but the typical "tutorial" flow doesn't.

The V3 build registers all apps up front (because the architecture demands them), which is why we hit it.

---

## Prevention going forward

When adding a NEW app to an existing project:
1. `python manage.py startapp <name>` first (works because the project already loads cleanly)
2. THEN add `<name>` to `LOCAL_APPS` in `base.py`
3. THEN run `python manage.py check`

Never reverse this order.

---

## Related

- [`docs/setup/03-backend-scaffold.md`](../setup/03-backend-scaffold.md) §5 — where this came up
- Django docs: [Substituting a custom User model](https://docs.djangoproject.com/en/5.1/topics/auth/customizing/#substituting-a-custom-user-model) — covers the `AUTH_USER_MODEL` constraint but not the chicken-and-egg flow

---

*Last updated: 2026-05-09*