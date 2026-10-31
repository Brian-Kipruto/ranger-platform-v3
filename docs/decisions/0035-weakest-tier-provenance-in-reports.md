# ADR-0035: Reports are labelled by their weakest tier, per reading, never pooled

- **Status:** Accepted
- **Date:** 2026-10-30
- **Feature:** F16 (Pass 7 fork 7)
- **Related:** ADR-0020 (per-reading provenance), ADR-0034, A01

## Context

Since ADR-0020 every reading carries its own `source`, separate from the row's
(position) source. A mission can mix tiers: live positions with a simulated tube.
A report that summarises them must not let a weak tier pass as a strong one.

## Decision

1. **Per-reading sources drive the tables.** Positions by the row's source, each
   reading kind by its own.
2. **Never pooled.** Statistics and reference comparisons are computed per tier. A
   kind with readings in two tiers gets two rows.
3. **The headline is the weakest tier present** across positions and every reading
   kind, plus the full kind × tier count matrix. Never the majority: one simulated
   reading in ten thousand live ones makes the report "contains simulated data".
4. **Every page is marked.** MODELLED or SIMULATED puts a band in the top margin of
   every page; SIMULATED adds a diagonal watermark. The tier is also written to the
   PDF's Subject and Keywords. LIVE and REPORTED carry no band. Band colours are fixed
   and never take a tenant's accent.
5. **Derived values are not reported as data.** MODELLED CPM (back-calculated from
   the published dose rate) is not summarised; an all-null quantity (an uncalibrated
   tube's dose rate) prints one line, not an empty stats row.
6. **No located anomalies from modelled data.** For MODELLED readings the report
   gives the count and fraction above a level, not a per-reading list: their
   positions and times are placed, not measured.

## Rejected

- **The majority tier in the header** — hides the weak part of a mixed mission.
- **Labelling readings by the row's source** — contradicts ADR-0020.

## Consequences

A Marsabit report says MODELLED on every page, omits CPM, and gives Forole's
34 readings above 0.3 µSv/h as a count, not as locations.
