# 018 — Earth Engine 403s with a valid key: the service account needs TWO IAM roles

*Date: 2026-08-05*

---

## What we saw

F10.2 CP0. A freshly created service account, a freshly downloaded JSON key at
`~/ranger-secrets/`, the path correctly in `.env`, the Cloud project registered
for Earth Engine. Every call failed:

```
ee.ee_exception.EEException: Caller does not have required permission to use
project ranger-eo. Grant the caller the roles/serviceusage.serviceUsageConsumer
role ...
```

The trap is what this looks like from the outside: **identical to a bad key**.
Same exception type, same 403, same failure point inside `ee.Initialize()`. The
natural response is to re-download the key, re-check the path, re-check the
email, and re-register the project — all of which were already correct, and none
of which changes anything.

## What caused it

Earth Engine access for a service account requires **two** IAM roles on the
Cloud project, and creating a service account grants neither:

| Role | What breaks without it |
|---|---|
| **Service Usage Consumer** (`roles/serviceusage.serviceUsageConsumer`) | The account cannot call the Earth Engine API *at all* — 403 on `ee.Initialize()` |
| **Earth Engine Resource Writer** (`roles/earthengine.writer`) | Initialization succeeds but computation and asset access fail later |

The Earth Engine signup flow registers the *project*. It does not touch IAM for
*accounts within* the project. So every check you can perform on the key itself
passes, and the thing that is actually missing is invisible from the key.

## How we fixed it

Google Cloud Console → **IAM & Admin → IAM** → find the service account
principal (`ranger-gee@ranger-eo.iam.gserviceaccount.com`) → **Edit** → add both
roles → Save. Propagation is usually seconds, occasionally a minute or two.

Then verify with the command that exists for exactly this:

```bash
cd ~/projects/ranger-platform-v3/ranger_backend
python manage.py check_gee
```

```
credentials OK
  chirps      ok      UCSB-CHG/CHIRPS/DAILY
  era5_land   ok      ECMWF/ERA5_LAND/HOURLY
  ...
10 collection(s) resolved, 0 problem(s)
```

## How to prevent it

**Read the exception text, not its type.** `gee_client._translate` exists
because Earth Engine reports configuration errors, auth failures, and quota
exhaustion as the same `ee.EEException` with different prose. Callers cannot
branch on prose, so the module translates once — and
`GEEAuthenticationError`'s message names this specific cause, because it is the
overwhelmingly likely one:

```python
"Earth Engine rejected the service account. Most often this is missing IAM
 roles rather than a bad key — the account needs both Service Usage Consumer
 and Earth Engine Resource Writer."
```

If you are setting up a new environment, grant both roles *before* the first
call. It is thirty seconds ahead of time and an hour of misdirected debugging
afterwards.

**Related gotcha, same setup session:** the key file lives at
`~/ranger-secrets/`, deliberately outside the repository. Google scans public
repositories and auto-disables any service-account key it finds. The repo is
public today and going private; neither fact makes committing a key survivable.
`.env` is gitignored and `.env.example` documents the three `GEE_*` variables
without values.
