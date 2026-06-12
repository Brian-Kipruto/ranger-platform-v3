# 0006 — SensorLog tenancy through Robot, not a denormalized FK

**Status:** Accepted, 2026-06-12. Revisit if log-listing query performance
becomes a measured problem.

## Context

Feature 03 introduced `core.SensorLog` and its decoupled reading models
(`RadiationLog`, `AirQualityLog`, `ImuBaroLog`). The platform is multi-tenant:
every query must be scoped to the requesting user's `Organization`, and no
cross-tenant data leakage is permissible (V3 spec §7.3).

`Robot` and `Mission` both carry a direct `organization` FK. The open question
was whether `SensorLog` should *also* carry its own `organization` FK, or
inherit tenancy through its `robot`.

This is the foundational query pattern for Feature 05 (Data Explorer): every
data-listing endpoint will filter sensor logs by organization, so the choice
ripples through all later data-display features.

## Decision

`SensorLog` does **not** carry an `organization` FK. It inherits its tenant
through `robot`. Org-scoped queries filter via `robot__organization=...`:

```python
SensorLog.objects.filter(robot__organization=request.user.organization)
```

## Options considered

**Option A — tenancy through the robot (chosen).**
No `organization` field on `SensorLog`. The robot is the single source of truth
for which org a log belongs to.

- A sensor log physically cannot belong to a different org than the robot that
  produced it, so a separate FK would be redundant by definition.
- A redundant FK is a desync risk: if a robot were ever reassigned between orgs
  (unlikely, but possible), every historical log's `organization` would need
  rewriting to stay consistent, or it would silently go stale.
- Cost: org-scoped log queries traverse one join (`robot__organization`). On
  indexed FKs this is cheap, and `SensorLog.robot` is indexed.

**Option B — denormalized `organization` FK on `SensorLog`.**
Add `organization` directly to `SensorLog` (and arguably the reading models).

- Faster org-scoped queries: filter on a local column, no join.
- This is what large-scale row-level-security setups often do deliberately.
- Cost: every write must set it correctly and keep it consistent with
  `robot.organization`; it's a denormalization that buys speed we have no
  evidence we need yet.

The V2 reference implementation filtered through related models in much the same
spirit (its `DataLogListAPIView` enforced org via `request.user.organization`
against related querysets), so Option A is also the path of least surprise
relative to prior art.

## Consequences

**Good:**
- One source of truth for a log's tenant. No desync class of bug.
- No write-time burden to populate/maintain a redundant field.
- Simpler models; the reading models stay pure readings.

**Costs:**
- Org-scoped log queries carry a join. If Data Explorer's listing endpoint shows
  measurable latency on large tables, this is the first thing to revisit.
- Any future raw-SQL or analytics path must remember to join through `robot`
  rather than expecting a local `organization` column.

## When to revisit

- If Feature 05's `/api/data-logs/` listing shows measured latency attributable
  to the `robot__organization` join on a large `SensorLog` table.
- Before any analytics/reporting feature that scans sensor logs at scale
  (e.g. Compliance Reports, V3 Phase 7) — at that point a denormalized
  `organization` column, or a materialized view, may be worth the write cost.
- The fix, if needed, is additive: add the column, backfill from
  `robot.organization`, set it on write. No data loss, reversible.

## Related docs

- `features/03-core-models.md` — what was built
- `decisions/0002-multi-tenant-via-organization-fk.md` — the org-FK tenancy
  model this extends
- V3 Architecture spec §7.3 (Data Security — tenant isolation)