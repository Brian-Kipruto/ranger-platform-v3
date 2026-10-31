# ADR-0037: Reports are immutable, hashed, and refused if altered

- **Status:** Accepted
- **Date:** 2026-10-31
- **Feature:** F16 (Pass 7 forks 5, 8; checkpoint 7c)
- **Related:** ADR-0033, TS-051

## Context

A report someone has handed to a regulator must stay what it was. Marsabit sites run
to 2,347 rows: too many for the body, but the full data must travel with the report.

## Decision

- **A `Report` row per generation**: org (copied from the mission), mission, user,
  time, format version, row count, weakest tier, a `summary` of everything printed,
  and **SHA-256 of the PDF and of the CSV**. `save()` refuses updates; regenerating
  makes a new row and new files. PROTECT on mission and org.
- **The full data travels in the PDF** as an embedded CSV attachment (the same
  format as `/api/data-logs/export/`, one helper for both), and is also stored
  beside the PDF so the console can serve it (PDF viewers often hide attachments).
- **Writes are atomic and never overwrite**: temp file, fsync, `os.link` (fails if
  the target exists). Names carry a random token. A failure at any step leaves no
  row and no file.
- **Downloads re-hash** the file and compare with the recorded hash. A mismatch is a
  409 and the bytes are not served. Stored paths must resolve inside `media/reports/`.
- **The browser re-hashes** downloads where `crypto.subtle` exists (https,
  localhost) and refuses to save a mismatch.
- **Only COMPLETED missions** are reported on.

## Rejected

- **Regenerating the CSV from the DB on download** — rows can change after the
  report; the hash would not match what the PDF embeds.
- **Extracting the CSV from the PDF on download** — would make `pypdf` a
  production dependency.
- **An appendix of every row** — 50+ pages nobody reads.

## Consequences

Reports made before 7c have no stored CSV (CSV download greyed; regenerate). Deleting
a row in admin leaves its files on disk.
