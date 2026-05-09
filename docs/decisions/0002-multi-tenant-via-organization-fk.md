# ADR 0002 — Multi-tenancy via Organization FK on every model

**Status:** Accepted
**Date:** 2026-05-09
**Decider:** Brian Kipruto, with architectural guidance

---

## Context

R.A.N.G.E.R. is a Robot-as-a-Service platform serving multiple organizations (tenants) — environmental firms, NGOs, mining companies, regulators, communities. Tenant data must be strictly isolated. A user from "Farm A" must never see data from "Farm B".

We need to choose a multi-tenancy model. The three common options are:

1. **Schema-per-tenant** — separate Postgres schema per tenant, switched at request time
2. **Database-per-tenant** — separate database per tenant
3. **Shared schema with `organization` FK** — single database, every tenant-scoped row carries an `organization_id` foreign key, every query filters by it

We also need to choose between a `role` enum on the user model vs Django's built-in Groups + Permissions for authorization.

---

## Decision

**Use option 3: shared schema with an `organization` FK on every tenant-scoped model. Use Django Groups (not a `role` enum) for authorization.**

Concretely:
- `accounts.Organization` is the tenant model
- `accounts.CustomUser` has a `ForeignKey(Organization, on_delete=PROTECT, null=True)`
- Every other tenant-scoped model (`Robot`, `Mission`, `SensorLog`, etc.) gets an `organization` FK as well
- Every query in DRF views and Django Channels consumers filters by `request.user.organization`
- Authorization is via Django's `Group` model and `Permission` system, NOT a custom `role` field

The `organization` FK on `CustomUser` is **nullable** so superusers (ByteAnza staff) can transcend tenancy.

---

## Options Considered

### Option A — Schema-per-tenant (rejected)

**Pros:**
- Strong isolation (each tenant's data is in a separate Postgres schema)
- Easy bulk operations per tenant (delete a schema = delete a tenant)
- Per-tenant backups straightforward

**Cons:**
- Migrations get nightmarish — every schema change has to apply to every schema individually
- Django doesn't natively support schema-per-tenant; requires `django-tenants` or similar third-party app, which has its own quirks and lock-in
- Cross-tenant queries (e.g. ByteAnza staff viewing all data) require complex query routing
- Connection pool pressure — each schema needs its own connection context
- The schema-switching middleware adds latency and complexity to every request
- Adding a new tenant requires DDL (creating a schema) which complicates auto-provisioning

### Option B — Database-per-tenant (rejected)

**Pros:**
- Strongest possible isolation
- True per-tenant resource limits (per-DB connection caps, etc.)

**Cons:**
- Operational burden multiplies linearly with tenant count — each DB needs separate backup, monitoring, migration application
- Cross-tenant aggregations (platform-wide analytics, cross-tenant ML) become impractical
- Cost scales poorly — each Postgres instance has overhead
- Wildly overkill for our scale (we'll have dozens to maybe a few hundred tenants, not thousands)

### Option C — Shared schema with `organization` FK (chosen)

**Pros:**
- **Standard Django pattern** — works with vanilla DRF, Django ORM, all third-party libraries
- **Migrations are normal** — `python manage.py migrate` runs once for everyone
- **Cross-tenant queries are trivial** for ByteAnza staff (just don't filter by org)
- **Cheap and easy** — one Postgres instance, one connection pool
- **Well-understood failure modes** — bugs in tenant isolation are findable via code review (every queryset must filter)

**Cons:**
- **Tenant isolation is enforced by application code, not the database.** A bug in a view (forgetting to filter) leaks data across tenants.
- Index sizes grow with all tenants combined; very large tenants in a shared DB can affect query plans for smaller tenants
- Per-tenant database tuning (e.g. different settings for one heavy tenant) is impossible

### Authorization: `role` enum vs Django Groups

The V2 codebase had a `role` field on `CustomUser` with values like `ADMIN`, `OPERATOR`, `VIEWER`. It was inflexible:
- Adding a new role required a migration
- One user couldn't have multiple roles
- Permission checks were `if user.role == "ADMIN" or user.role == "ORG_ADMIN":` — proliferating string comparisons

V2 itself migrated away from this to Django Groups + Permissions. We're starting V3 with that lesson learned.

---

## Consequences

### Positive

- **Standard Django ergonomics** — every Django tutorial and library Just Works
- **Trivial onboarding** for new developers familiar with Django
- **Manageable infra cost** — one DB, one Redis, scales horizontally with read replicas
- **ByteAnza staff can query across tenants** for support, ML training, analytics
- **Migrations are sane** — no per-tenant DDL coordination
- **Granular permissions** — Groups can have any combination of permissions; users can be in multiple groups (`OrgAdmin` + `BillingViewer`); custom permissions are easy

### Negative

- **Application-level isolation must be enforced rigorously.** Every view, every serializer, every Channels consumer must filter by `request.user.organization`. We need:
  - A custom DRF base view class that auto-filters by org
  - A code review checklist that includes "is this scoped to org?"
  - Integration tests that confirm cross-tenant data leakage is impossible
- **Audit logs are critical** — if isolation ever breaks, we need to know who saw what when. Hence the `audit` app.
- **Backups are platform-wide, not per-tenant.** A bad migration could affect all tenants at once. Mitigated by careful migration practices.

### Neutral

- The `organization` FK on every model adds 8 bytes per row. Negligible.

---

## Implementation patterns

### Every tenant-scoped model

```python
class Mission(models.Model):
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.PROTECT,
        related_name="missions",
    )
    # ... other fields
```

`PROTECT` not `CASCADE` — never silent-delete user data when an org is removed. Force explicit cleanup.

### Every DRF view

```python
class MissionListAPIView(generics.ListAPIView):
    serializer_class = MissionSerializer
    permission_classes = [IsAuthenticated, ...]

    def get_queryset(self):
        return Mission.objects.filter(organization=self.request.user.organization)
```

A future PR will provide a `OrgScopedMixin` that does this automatically. For Phase 1 we hand-roll it; once feature 1 ships we'll factor it out.

### Permissions via Groups

Standard pattern. Pre-defined groups (set up in admin or via a management command):

| Group | Permissions |
|-------|-------------|
| `Org Admin` | All `view_*`, `add_*`, `change_*`, `delete_*` for org-scoped models |
| `Org Operator` | `view_*` for all + `launch_mission` |
| `Org Viewer` | `view_*` only |
| `Community Viewer` | `view_*` for explicitly-public datasets only |

Custom permissions like `change_branding`, `launch_mission`, `export_sensorlog` are declared in each model's `Meta.permissions`.

---

## When to revisit

Reconsider this decision if:

1. **A specific tenant's data volume becomes massive** — e.g. one mining client generates 100x the data of others, hurting query performance for everyone. Migration path: extract that tenant to a dedicated DB while keeping others on the shared schema.
2. **Regulatory compliance requires physical separation** — e.g. a government client demands their data live in a separate Postgres instance. Same migration path.
3. **A cross-tenant data leak occurs** that's traceable to application-level filtering missing in some path. Response: add an automated test that confirms every viewset is org-scoped before merging.

---

## Related

- V3 architecture doc § Multi-Tenancy for RaaS — confirms this approach
- V2 architecture doc § "Pillar 2: Multi-Tenancy for RaaS" — same conclusion, validated by experience
- `docs/setup/03-backend-scaffold.md` §6 — where `Organization` and `CustomUser` are defined
- (Future) `docs/features/01-auth.md` — first feature that consumes the org-scoping pattern

---

*Last updated: 2026-05-09*