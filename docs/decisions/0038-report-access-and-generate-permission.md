# ADR-0038: Report access — org members read, `generate_report` writes

- **Status:** Accepted
- **Date:** 2026-10-31
- **Feature:** F16 (checkpoint 7c)
- **Related:** ADR-0002, ADR-0007, ADR-0037, missions `launch_mission` (F15)

## Decision

- **Tenancy as in `missions/views.py`.** Every queryset is the caller's org; another
  org's report or mission is a **404**, never a 403.
- **Listing and downloading**: any authenticated member of the report's org. A client
  must be able to fetch its own reports.
- **Generating**: `reports.generate_report`, granted by
  `manage.py grant_reports <user> [--revoke]` (group "Report Authors"), the same
  shape as `grant_launch`. Superusers hold it implicitly. Checked before the mission
  lookup, so a 403 says nothing about which missions exist.
- **The console hides Generate** without the permission; the server enforces it
  regardless.
- **File paths are never serialized.** Downloads go through
  `/api/reports/<id>/{pdf,csv}/`, never `MEDIA_URL`. Responses are
  `Cache-Control: private, no-store`.

## Consequences

`seed_marsabit` does not grant the permission; run `grant_reports` after a rebuild.
