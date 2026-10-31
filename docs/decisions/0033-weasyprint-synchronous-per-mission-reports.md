# ADR-0033: WeasyPrint, synchronous, one report per mission

- **Status:** Accepted
- **Date:** 2026-10-30
- **Feature:** F16 (Pass 7 forks 1, 2, 4)
- **Related:** ADR-0037 (immutable reports), TS-050, TS-052

## Context

A completed mission must become a PDF a client can hand to a regulator: tables,
a map, citations, provenance on every page. The finale is in December 2026; there is
no Celery in the stack yet, and a Marsabit site runs to 2,347 rows.

## Decision

- **WeasyPrint 66.0** (HTML/CSS → PDF). The report is a document: headings, tables
  that break between rows, `@page` margin boxes for the provenance band and footer,
  PDF metadata from `<meta>`. A Django template is the whole layout.
- **Synchronous.** `POST /api/reports/` returns when the PDF exists (~1–3 s for a
  Marsabit site). Async generation with Celery is post-finale.
- **One mission per report.** No multi-mission or date-range reports for the finale.

## Rejected

- **ReportLab.** Precise, but every table and page break is code; layout changes
  cost more than they should for a document.
- **Async (Celery) now.** A queue, a worker and a polling UI for a job that finishes
  in seconds, before the finale.

## Consequences

- System libraries on the PC: `libpango-1.0-0`, `libpangoft2-1.0-0`
  (`libharfbuzz-subset0` optional). Install record in `features/16-compliance-report.md`.
- WeasyPrint changes process-global state on import: Pillow's
  `LOAD_TRUNCATED_IMAGES` (TS-050) and the `fontTools` logger during subsetting
  (TS-052). Anything else that shares the process must assume both.
- WeasyPrint output is byte-deterministic within one wall-clock second (TS-051).
