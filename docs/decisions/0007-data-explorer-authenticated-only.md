# 0007 — Data Explorer ships authenticated-only; custom perms gated later

**Status:** Accepted, 2026-06-15. Revisit when a feature needs per-permission
gating of read endpoints (likely the Community Portal or a Viewer-tier role).

## Context

Feature 03 defined custom permissions on `core.SensorLog`
(`export_sensorlog`, `view_livedata`, `view_visualization`,
`view_organization_data`, `view_all_data`) and `launch_mission` on
`missions.Mission`. Feature 05 builds the first read API over these models —
the question was whether to enforce those custom permissions now (V2 parity:
V2 §3.2.2 added explicit `check_permissions` for `core.view_sensorlog` /
`core.view_visualization`, and an `@permission_required` decorator on the CSV
export) or ship authenticated-only and gate later.

The decision had to be made by first reading how Feature 02's existing DRF
views enforce auth, per the 04→05 handoff.

## Decision

Feature 05 ships **authenticated-only**. Every endpoint uses
`permission_classes = (IsAuthenticated,)` (or inherits the DRF default) and
the org-scoping queryset; no custom-permission checks. The Feature 03
model-level permissions remain defined but unenforced for now.

## Rationale

Reading `accounts/views.py` settled it by precedent. Every existing V3 view —
`UserMeView`, `CustomTokenObtainPairView`, `CookieTokenRefreshView`,
`LogoutView` — uses **only** `permission_classes` with DRF/simplejwt built-ins.
There is no `check_permissions` override, no `@permission_required`, and no
custom permission class anywhere in the V3 codebase yet.

Enforcing V2's custom-permission pattern in Feature 05 would mean inventing a
permission-check style that exists nowhere else in V3, as a rider on a feature
whose job is data display. That is a cross-cutting authorization decision that
deserves its own feature and its own consistent pattern across all endpoints —
not a one-off bolted onto the Data Explorer.

Gating later is purely **additive**: the permissions already exist on the
models (Feature 03), the frontend auth store already exposes `hasPermission()`
(Feature 02), and adding enforcement is a matter of adding permission classes /
checks to existing views plus conditionally rendering UI. No data migration, no
schema change, no rework of what 05 builds.

## Options considered

**Option A — authenticated-only now (chosen).** Matches the established V3 view
pattern. Lowest surface area. Defers authorization design to a feature that can
do it consistently.

**Option B — enforce Feature 03 custom perms now (V2 parity).** Closer to V2's
shipped behavior. But it introduces a permission-enforcement style with no
existing V3 precedent, scoped to one feature, risking divergence when the next
feature does it differently. The V2 implementation itself was scattered
(per-view `check_permissions`, a decorator on the function view) — not a pattern
worth porting piecemeal.

## Consequences

**Good:**
- One consistent auth pattern across all V3 views (IsAuthenticated + org scope).
- No premature authorization design; the eventual gating feature sets the
  pattern once, everywhere.
- Smaller, safer Feature 05.

**Costs:**
- Any authenticated user in an org can currently read/export/visualize that
  org's data, regardless of role. Acceptable while every user is effectively an
  org operator; **not** acceptable once Viewer/Community tiers exist.
- The Feature 03 custom permissions sit defined-but-unused until then, which can
  read as dead config to someone unaware of the plan (this ADR is the pointer).

## When to revisit

- Before shipping any role that should see a **subset** of data or be denied
  export/visualization — Community Viewer is the obvious trigger
  (`view_organization_data`, `view_visualization`, withhold `export_sensorlog`).
- At that point, enforce across **all** read endpoints at once, establishing the
  V3 permission-check pattern, and gate the corresponding UI via
  `hasPermission()`.

## Related docs

- `features/05-data-explorer.md` — what was built
- `features/02-authentication.md` — the view/auth pattern this follows and the
  `hasPermission()` frontend hook
- `features/03-core-models.md` — where the custom permissions are defined
- V2 software docs §3.2.2 (the V2 enforcement pattern, not ported)