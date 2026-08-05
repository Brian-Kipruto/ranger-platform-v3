# 016 — `geo_db_type` AttributeError: contrib.gis installed but ENGINE still plain postgresql

*Date: 2026-08-03*

---

## What we saw

F10.1 CP3. Applying the first geometry migration:

```
Applying core.0004_sensorlog_location...Traceback (most recent call last):
  ...
  File ".../django/contrib/gis/db/models/fields.py", line 122, in db_type
    return connection.ops.geo_db_type(self)
AttributeError: 'DatabaseOperations' object has no attribute 'geo_db_type'
```

What made it confusing is everything that had already passed:

- `python manage.py check` — **no issues**
- `python manage.py makemigrations --check --dry-run` — **No changes detected**
- `core.0003_enable_postgis` (`CreateExtension("postgis")`) — **applied OK**
- `SELECT PostGIS_Version()` — **3.5, USE_GEOS=1, USE_PROJ=1**
- GeoDjango's own library check — `GDAL b'3.4.1' | GEOS b'3.10.2'`

So PostGIS was installed, the extension was created, GeoDjango could load its
libraries, and the models validated. It still failed.

## What caused it

CP2 had **two** edits to `ranger_backend/settings/base.py`. Only the first
landed:

```python
# Edit A — applied
DJANGO_APPS = [
    ...
    "django.contrib.gis",
]

# Edit B — NOT applied
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",          # ← still this
        # should have been:
        # "ENGINE": "django.contrib.gis.db.backends.postgis",
    }
}
```

`geo_db_type()` lives on the **PostGIS backend's** `DatabaseOperations`. Adding
`django.contrib.gis` to `INSTALLED_APPS` makes the geometry *fields* importable
and model definitions valid — but the field asks the *connection* how to render
its column type, and the plain postgresql backend has no such method.

Every earlier check passed because none of them touched that path:

- `check` validates model definitions, not whether the backend can render them
- `CreateExtension` is a raw `CREATE EXTENSION` — works on either backend
- `makemigrations` compares model state to migration state; both were consistent
- `PostGIS_Version()` asks Postgres, not Django

The first thing that actually needs `geo_db_type` is `add_field` on a geometry
column — i.e. the very first geometry migration.

## How we fixed it

```bash
cd ~/projects/ranger-platform-v3/ranger_backend
sed -i 's|"ENGINE": "django.db.backends.postgresql",|"ENGINE": "django.contrib.gis.db.backends.postgis",|' ranger_backend/settings/base.py
python manage.py migrate
```

The failed migration left nothing behind — Django wraps each migration in a
transaction on Postgres, so `showmigrations` still showed `[ ]` and the column
did not exist. Re-running applied all six cleanly.

## How to prevent it

**Verify the resolved ENGINE, not the file.** After any settings change to
`DATABASES`, ask the connection what it actually got:

```bash
python manage.py shell -c "from django.db import connection; print(connection.settings_dict['ENGINE'])"
```

Expect `django.contrib.gis.db.backends.postgis`. This is the authoritative
check — it survives split settings, `.env` overrides, and half-applied edits,
none of which grepping `base.py` would catch.

More generally: this is the same class of bug as troubleshooting 015
(truncated paste). When a handoff says "two edits to one file", verify **both**
landed before running the thing that depends on them.
