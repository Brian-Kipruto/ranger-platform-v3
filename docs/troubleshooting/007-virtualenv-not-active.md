# 007 — Virtualenv not active on a fresh terminal

**Date:** 2026-05-10
**Symptom seen during:** Auth feature, Checkpoint 1 (running shell after fresh terminal)

## Symptom
ModuleNotFoundError: No module named 'django'
ImportError: Couldn't import Django. Are you sure it's installed and available
on your PYTHONPATH environment variable? Did you forget to activate a virtual environment?

The shell prompt is missing the `(.venv)` prefix.

## Cause

Bash sessions don't automatically activate Python virtualenvs. Opening a fresh terminal, or running `deactivate`, drops you back to the system Python which has no project packages installed.

## Fix

```bash
cd ~/projects/ranger-platform-v3
source .venv/bin/activate
```

Prompt should now show `(.venv) brian@Kipruto:...`. Retry the command.

## Prevention

The `(.venv)` prefix in the shell prompt is the single source of truth for "is the virtualenv active." If it's not there, every Python command that touches project dependencies will fail with module-not-found errors.

Possible automations (not implemented):

- `direnv` with `.envrc` to auto-activate when entering the project directory
- A shell function `ranger` that does `cd && source .venv/bin/activate && docker compose up -d`

Until then: prompt watch.