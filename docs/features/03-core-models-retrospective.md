# Feature 03 Retrospective — Core Data Models

> Period: 2026-06-12. Sessions: 1. Branch: `feat/core-models`.

## What worked

**Catching the hidden dependency before writing code.** Data Explorer was the
nominal next feature, but the spec process surfaced that `core` and `missions`
were empty shells — no models to explore. The admin screenshot confirmed it
(only Accounts / Auth / Token Blacklist registered). Splitting the work into
03 (models) → 04 (simulator) → 05 (Data Explorer) before touching code meant
every feature now ends with something verifiable, instead of one multi-session
monster with no checkpoint until the very end.

**Generating both apps' migrations together.** `makemigrations core missions`
let Django resolve the `core` ↔ `missions` circular relationship automatically,
splitting `core` into `0001` (tables) + `0002` (cross-app FKs). This is the V2
§9.2 pain — the hand-rolled `--fake` migration dance — handled by the engine in
one command. Zero manual intervention. The lesson held: never generate
related-app initial migrations separately.

**Lazy string FK references everywhere cross-app.** `"missions.Mission"`,
`"core.Robot"`, `"accounts.CustomUser"`. The models imported cleanly at every
checkpoint with no circular-import error — V2's §3.2.3 item 1 never had a chance
to happen.

**Integer PKs settled up front.** Confirming the PK decision in the spec
(integer `BigAutoField`, `robot_id_str` as a separate unique field) sidestepped
the entire `robot_id` → `robot_id_str` primary-key saga that cost V2 a chapter
of migration troubleshooting (§9.2). Greenfield made this free; deciding it
explicitly made it safe.

**Per-checkpoint import checks.** Importing each `models.py` via
`manage.py shell -c` before migrating caught nothing this time (the code was
clean) but kept each step independently verified, so the `migrate` had no
surprises.

## What was hard

**Nothing structural.** This was a smooth feature — the models are
well-understood (V2 is a working reference for the shapes) and the risk was
relationships/migrations, which the "generate together + lazy refs" approach
neutralized.

**One trivial operator hiccup.** An ad-hoc `python -c "django.setup()..."`
one-liner failed with `No module named 'ranger_backend.settings'` because it ran
from the outer repo dir, not the backend dir. The nested layout
(`ranger-platform-v3/ranger_backend/ranger_backend/settings/`) means bare
`python` doesn't have the path set up; `manage.py` does. Switched all import
checks to `manage.py shell -c`. Not worth a troubleshooting doc — just a habit:
import checks go through `manage.py`.

## What to do differently next time

**Pin the repo layout in the spec.** I assumed a path for the import-test
one-liner and it bit us for one round-trip. For Feature 04, confirm the exact
`manage.py` location and run everything relative to it from the first command.

**Stray working-tree changes — check at branch cut, not commit.** Three
unrelated auth-era doc edits were sitting uncommitted when `feat/core-models`
was cut, so they rode along onto the branch. Caught and committed separately at
the end (clean), but cleaner still is to `git status` *before* `git checkout -b`
and stash/commit anything unrelated first, so the feature branch starts pristine.

## Numbers

- 5 checkpoints across one session (branch/preflight, core models, missions
  models, migrations, admin, hand-verification — 0-indexed plus the verify step)
- 2 commits on the branch: `feat:` (7 files, 760 insertions) + a separate
  `docs:` for the stray auth-era edits
- 3 migrations applied (`core.0001`, `missions.0001`, `core.0002`), all OK
- 8 new tables, 0 manual migration intervention
- 0 project-level bugs; 1 operator path hiccup, self-inflicted, no code impact

## Carry-forwards for the next feature (04 — Simulator)

- The simulator writes into these models: `SensorLog` (parent) + one or more of
  `RadiationLog` / `AirQualityLog` / `ImuBaroLog` (readings), attached to a
  `Robot` and optionally a `Mission`.
- Org-scoping for any query the simulator does (or any later read) goes through
  `robot__organization` — there is no `organization` field on `SensorLog`
  (ADR 0006).
- A robot exists (`North Field Bot` / `RANGER-PRIME-001`, ByteAnza) and two
  SensorTypes (`geiger`, `pm`) — usable as the simulator's default target, or
  the simulator can create its own.
- Reading models use `primary_key=True` on their OneToOne, so creating a reading
  means `RadiationLog.objects.create(sensor_log=log, ...)` — the log must exist
  first.
- Run import/sanity checks through `manage.py shell -c`, never bare `python -c`.
- Generate any new migrations with all affected apps named together.