# Feature 03 — Core Data Models

> Status: Shipped 2026-06-12. Branch: `feat/core-models`. Commit: `4727737`.

## What it does

Builds the data foundation the rest of the platform sits on. Two Django apps
gain real models for the first time in V3:

- **`core`** — the robot fleet, a sensor catalog, and the decoupled sensor-log
  structure (a lean parent log plus per-sensor reading tables).
- **`missions`** — missions and their ordered waypoints.

Everything is scoped to an `Organization` so tenant isolation holds from the
first row. There is no API and no frontend in this feature — just models,
migrations, admin registration, and hand-verified data. Feature 04 (simulator)
fills these tables with data; Feature 05 (Data Explorer) is the UI that reads
them.

This feature exists because V3 is greenfield: the `core` and `missions` apps
were registered in `INSTALLED_APPS` from the Phase 1 scaffold but had no models,
no migrations, and nothing in the admin. Data Explorer was the originally
intended next feature but has nothing to explore until this lands.

## Models

### `core` app

**`SensorType`** — catalog of every sensor the platform supports. Fields:
`name`, `code` (stable slug identifier, e.g. `geiger`), `unit`, `description`.
Robots declare which of these they carry.

**`Robot`** — one robot in the fleet, scoped to one `Organization` (FK,
`PROTECT`). Integer PK; the human-readable identifier is `robot_id_str`
(unique, indexed) — never the primary key. Has a `status` choice field, an
`installed_sensors` M2M to `SensorType`, and a `metadata` JSONField for
tenant-defined tags.

**`SensorLog`** — the lean parent log: `robot` (FK, `CASCADE`), `mission`
(FK to `missions.Mission`, `SET_NULL`, nullable), `timestamp` (indexed),
`latitude`/`longitude` (indexed floats). Carries the custom permissions
(see below). No `organization` FK — tenancy comes through `robot`
(see ADR 0006).

**`RadiationLog` / `AirQualityLog` / `ImuBaroLog`** — the decoupled reading
models. Each has a `OneToOneField` to `SensorLog` with `primary_key=True`, so
the parent log's id is also the reading's PK. Adding a new sensor type later is
a new reading model, never a change to `SensorLog`.

### `missions` app

**`Mission`** — a planned operation for one robot. FKs: `organization`
(`PROTECT`), `robot` (`core.Robot`, `PROTECT`), `created_by` (`CustomUser`,
`SET_NULL`, nullable). Has `name`, `description`, `status` choices (PENDING /
IN_PROGRESS / PAUSED / COMPLETED / ABORTED), and a `metadata` JSONField. Carries
the `launch_mission` custom permission.

**`Waypoint`** — an ordered point in a mission's path. FK to `Mission`
(`CASCADE` — waypoints die with their mission). `order`, `latitude`,
`longitude`, `status`. A `UniqueConstraint` on `(mission, order)` guarantees no
two waypoints in a mission share a sequence number.

## `on_delete` choices (and why)

| Relationship | Behaviour | Reason |
| --- | --- | --- |
| `Robot.organization` | `PROTECT` | Can't delete an org with robots still attached |
| `Mission.organization` | `PROTECT` | Same |
| `Mission.robot` | `PROTECT` | Deleting a robot with mission history must be deliberate |
| `Mission.created_by` | `SET_NULL` | A deleted user shouldn't drag their missions away |
| `SensorLog.robot` | `CASCADE` | A log has no meaning without its robot |
| `SensorLog.mission` | `SET_NULL` | Collected data outlives the mission plan — keep it |
| `Waypoint.mission` | `CASCADE` | A waypoint is part of the plan; dies with it |
| reading → `SensorLog` | `CASCADE` | A reading has no meaning without its parent log |

The contrast between `SensorLog.mission` (`SET_NULL`) and `Waypoint.mission`
(`CASCADE`) is intentional: waypoints are *plan*, sensor logs are *result*. You
keep results, you discard plan fragments.

## Custom permissions

Defined in model `Meta.permissions`, only truly custom codenames — never the
auto-generated `add_/change_/view_/delete_` (redefining those is what triggered
V2's `auth.E005`). They use the `app_label.codename` format the frontend auth
store already expects.

On `core.SensorLog`: `export_sensorlog`, `view_livedata`,
`view_visualization`, `view_organization_data`, `view_all_data`.
On `missions.Mission`: `launch_mission`.

## Tenancy model

Robots and Missions carry the `Organization` FK directly. Sensor logs and the
reading models inherit their tenant *through* the robot — there is no
`organization` field on `SensorLog`. Org-scoped queries on logs go via
`robot__organization=...`. The full rationale and the rejected alternative
(a denormalized FK on `SensorLog`) are in ADR 0006.

## Migrations

Generated for both apps together (`makemigrations core missions`) so Django
builds a consistent cross-app dependency graph. Django produced three:

- `core.0001_initial` — creates SensorType, Robot, SensorLog, and the three
  reading models.
- `missions.0001_initial` — creates Mission, Waypoint.
- `core.0002_initial` — adds the cross-app FKs that depend on Mission existing
  (`SensorLog.mission`, `SensorLog.robot`, `Robot.organization`,
  `Robot.installed_sensors`).

The automatic 0001/0002 split is Django resolving the `core` ↔ `missions`
circular relationship on its own — the modern engine doing what V2 had to force
by hand with `--fake` (see V2 docs §9.2). No manual intervention was needed.

Generating the apps together is the direct lesson from V2's migration history:
generating them separately invites an initial migration that depends on a
half-formed state of the other app.

## Files

**New:**
- `core/migrations/0001_initial.py`, `core/migrations/0002_initial.py`
- `missions/migrations/0001_initial.py`

**Modified (from empty stubs):**
- `core/models.py` — six models
- `core/admin.py` — registers SensorType, Robot, SensorLog; reading models as
  inlines on SensorLog
- `missions/models.py` — Mission, Waypoint
- `missions/admin.py` — registers Mission; Waypoint as inline

**Not touched:** `accounts/`, all auth code, `settings/`, frontend.

## Admin

`SensorType`, `Robot`, and `SensorLog` are registered as top-level admin
entries. The three reading models appear only as inlines on `SensorLog`, and
`Waypoint` only as an inline on `Mission` — they're meaningless standalone, so
keeping them off the index keeps it clean. `SensorLog`'s `list_filter` exposes
`robot__organization`, which is the through-the-robot tenancy surfaced as a
usable filter.

## Verification

Confirmed end-to-end before shipping:

1. Created two SensorTypes, a Robot under ByteAnza, and a SensorLog with a
   radiation reading — all via the admin, no errors.
2. Ran an org-scoped shell query proving the patterns Feature 05 depends on:

```bash
python manage.py shell -c "
from core.models import SensorLog, Robot
from accounts.models import Organization
org = Organization.objects.get(slug='byteanza')
logs = SensorLog.objects.filter(robot__organization=org)
print('logs in org:', logs.count())
l = logs.first()
print('radiation via related:', l.radiation_data.radiation_value)
print('tenant resolves through robot:', l.robot.organization == org)
"
```

Output confirmed `logs in org: 1`, `radiation via related: 42.5`,
`tenant resolves through robot: True`. The `robot__organization=` filter is
exactly what Data Explorer's `get_queryset` will use; the `radiation_data`
related access is what its serializer will flatten.

## Things that went wrong

Nothing project-level. One operator-side hiccup: an ad-hoc `python -c "..."`
one-liner to test imports failed with `No module named 'ranger_backend.settings'`
because it was run from the outer repo dir rather than the backend dir where
`manage.py` lives. Fixed by using `python manage.py shell -c "..."` instead,
which sets up the path correctly. Not a code bug and not worth a permanent
troubleshooting entry — just a reminder to run import checks through
`manage.py`, not bare `python`.