# ADR-0036: Cited reference levels, never limits, never PASS/FAIL

- **Status:** Accepted
- **Date:** 2026-10-30
- **Feature:** F16 (Pass 7 fork 3)
- **Related:** ADR-0035

## Context

A report a regulator reads must not overstate what a survey can show. An ambient dose
rate has no "limit": the public limit is an annual effective dose. WHO PM guidelines
are 24-hour statistics; a survey lasts minutes.

## Decision

A code registry (`reports/thresholds.py`, `REGISTRY_VERSION` printed and stored).
Each entry: quantity, value, unit, **kind**, **use**, averaging period, citation.

| Entry | Value | Kind | Use |
|---|---|---|---|
| KNRA Marsabit report (Apr 2026), Table 2.2 | 0.300 µSv/h | investigation level | per-reading: count above (and a list, except MODELLED) |
| UNSCEAR 2000, Vol. I, Annex B | 59 nGy/h | background | context only: a different quantity (Gy, terrestrial only) |
| WHO global AQG 2021, Table 3.26 | PM2.5 15 µg/m³ | guideline (24 h, 99th pct) | survey mean beside it, mismatch stated |
| WHO global AQG 2021, Table 3.26 | PM10 45 µg/m³ | guideline (24 h, 99th pct) | survey mean beside it, mismatch stated |

- Readings are "above" or "below" a level. No PASS, FAIL or "compliant" anywhere (a
  test greps the PDF).
- **Not compared, and said so:** the annual public effective-dose limit (needs an
  occupancy assumption the report does not make) and CPM (no dose meaning without
  calibration).
- A mean that rounds to the level is printed with enough decimals to show which side
  it is on (14.96, not "15.0, below the 15.0 guideline").

## Rejected

- **Converting the annual limit to a dose rate** — an occupancy assumption hidden
  inside a number.
- **Kenya EMCA (Air Quality) Regulations 2014** — not cited until the table is in hand.

## Consequences

Citations were verified before entry: WHO against the primary table; UNSCEAR against
independent summaries (the annex table number is still to confirm); KNRA against the
report title recorded in `core/marsabit.py`.
