# Django Admin — unstyled when served by `daphne` directly

**First encountered:** 2026-05-09 (after Phase 1 wrap-up)
**Severity:** Cosmetic only — admin still works, just unstyled
**Frequency:** Whenever running `daphne` directly instead of `runserver`

---

## Symptom

Running:

```bash
daphne -p 8000 ranger_backend.asgi:application
```

Then visiting `http://localhost:8000/admin/login/`, the page renders but:
- No styling (white background, default browser fonts)
- "Toggle theme" links appear three times in a row instead of as styled buttons
- Black squares where icons should be (broken SVG references)
- Form fields are basic browser-default text inputs

Compare to running:

```bash
python manage.py runserver
```

…which serves the admin with its full dark/light themed UI.

---

## Root cause

`runserver` includes a development static file handler. When `DEBUG=True`, it serves files from each app's `static/` directory automatically — including Django admin's CSS, JS, and SVG icons that live in `django/contrib/admin/static/admin/`.

`daphne` is just an ASGI server. It serves your ASGI application (defined in `asgi.py`) and nothing else. It does NOT serve static files.

When the admin HTML loads in the browser, it references `<link rel="stylesheet" href="/static/admin/css/base.css">`. The browser requests that URL. Daphne routes the request through Django's URL config. Django's URL config has no route for `/static/...` (because in production, nginx is supposed to serve those before Django ever sees the request). Result: 404 for every static file, hence the unstyled page.

---

## Fix (development)

**Use `runserver`, not `daphne`, for daily development work:**

```bash
cd ~/projects/ranger-platform-v3/ranger_backend
python manage.py runserver
```

This gives you:
- ✅ Static file serving (admin works styled)
- ✅ Auto-reload on file changes
- ✅ ASGI / Channels / WebSocket support (because `daphne` is first in `INSTALLED_APPS`, `runserver` boots through Daphne anyway)
- ✅ Same port (8000)

The output line confirms ASGI mode:
```
Starting ASGI/Daphne version 4.1.2 development server at http://127.0.0.1:8000/
```

---

## When to use `daphne` directly

Two niche scenarios:

1. **Testing production-shaped startup.** Daphne without auto-reload behaves more like the production server, useful for measuring cold-start time or testing without reloader-induced reloads.
2. **Reproducing a bug that only happens in production.** If something works under `runserver` but breaks in production, running locally with bare Daphne can isolate the difference.

For everything else (admin work, frontend dev, building features) — `runserver`.

---

## Fix (production)

In production, never serve static files from Django/Daphne. Use nginx (or another reverse proxy):

```nginx
location /static/ {
    alias /path/to/staticfiles/;
    expires 30d;
}

location / {
    proxy_pass http://localhost:8000;
    # ... ASGI proxy settings
}
```

And run `python manage.py collectstatic` during deploy to gather all static files into `STATIC_ROOT`. The full production-deploy setup is documented in a future deployment phase.

---

## Why this isn't more obvious

Django's docs cover both `runserver` and standalone ASGI servers, but rarely highlight that switching from one to the other strips static-file serving. Channels' docs assume you know nginx will handle statics in production. Easy gotcha to hit when you're new to ASGI.

---

## Related

- [`docs/setup/03-backend-scaffold.md`](../setup/03-backend-scaffold.md) §7 — clarifies which command to use when
- Django docs: [How to deploy static files](https://docs.djangoproject.com/en/5.1/howto/static-files/deployment/)
- Django docs: [`runserver` static file behavior](https://docs.djangoproject.com/en/5.1/howto/static-files/#serving-static-files-during-development)

---

*Last updated: 2026-05-09*