# F16 — Compliance Report

*Date: 2026-10-31 (7a → 7d built and proven 2026-10-30 → 31)*
*Branch: `feat/compliance-report` (from `main` @ `1a9a723`)*
*Status: **closed.** From a COMPLETED mission, the platform generates a PDF a client can hand to a regulator: provenance per reading and on every page, per-tier statistics, cited reference levels, an offline survey map with the mission's own satellite scene, tenant branding, and the full data embedded as a CSV whose hash, like the PDF's, is recorded and re-checked on every download. Proven on all seven KNRA Marsabit sites against raw SQL, with a tampered file refused in the browser and served again after restore.*

Pass 7 in the vault. No hardware needed.

---

## What this feature does

**Generate.** `generate_report(mission, user=)` (and `POST /api/reports/`,
`manage.py generate_report --mission <pk>`) reads the mission's rows from Postgres,
summarises them, renders HTML with Django templates and WeasyPrint, embeds the CSV,
and writes the PDF and CSV to `media/reports/<org>/` atomically. COMPLETED missions
only. Every run is a new immutable `Report` row (ADR-0033, ADR-0037).

**What the PDF says.**

| Section | Content |
|---|---|
| Masthead | tenant logo (validated, downscaled) + org name, accent rule; producer line |
| Header | mission, instrument, survey window (UTC, from row timestamps), rows, generated, **weakest provenance** |
| Provenance | kind × tier count matrix (position, radiation, air_quality, imu_baro) |
| Statistics | per tier, never pooled: n, min, mean, SD (sample), P50/P95/P99 (linear), max |
| Reference levels | cited levels by kind and use; count above, survey mean vs guideline; what is not compared and why |
| Survey map | detail panel (+ track rules) and satellite context panel (ADR-0034) |
| Sources cited | reference-level citations, then data-provenance notes |
| Data | the embedded CSV's name and SHA-256 |

Every MODELLED or SIMULATED page carries a band in the top margin; SIMULATED adds a
watermark; the tier is in the PDF metadata (ADR-0035). Reference levels follow
ADR-0036.

**Console (7c).** `/reports`: a Generate panel (COMPLETED missions only, hidden
without `reports.generate_report`) and the org's reports, newest first, with a
provenance chip and PDF/CSV buttons. Downloads are hashed in the browser where
`crypto.subtle` exists and refused on mismatch (ADR-0037, ADR-0038).

### Forks settled

| # | Fork | Settled |
|---|---|---|
| 1 | PDF engine | WeasyPrint 66.0 — ADR-0033 |
| 2 | Sync vs async | synchronous; Celery post-finale — ADR-0033 |
| 3 | Thresholds | cited registry; levels not limits; no PASS/FAIL — ADR-0036 |
| 4 | Scope | one mission per report — ADR-0033 |
| 5 | Store it | immutable `Report` row with PDF + CSV hashes — ADR-0037 |
| 6 | Offline map | Pillow, detail + satellite context, honest tracks — ADR-0034 |
| 7 | Provenance arithmetic | per reading, never pooled, weakest tier, every page — ADR-0035 |
| 8 | Huge missions | summary + exceedance count/list; full data as embedded CSV — ADR-0037 |

---

## API

| Method | Path | Who | Result |
|---|---|---|---|
| GET | `/api/reports/` | org members | the org's reports, newest first (paths never serialized) |
| POST | `/api/reports/` `{"mission": id}` | `reports.generate_report` | 201; 403 no permission; 404 other org; 409 not COMPLETED / no rows |
| GET | `/api/reports/<id>/pdf/` | org members | 200 bytes + `X-Ranger-Sha256`; 404 other org; 409 missing/altered/escaping path |
| GET | `/api/reports/<id>/csv/` | org members | as PDF; 404 for reports made before 7c |

## Commands

```bash
python manage.py generate_report --mission <pk> [--user <username>]
python manage.py grant_reports <username> [--revoke]
```

`generate_report` prints the report id, rows, weakest tier, path and both hashes,
ending `PASS report generated`.

---

## Install record

PC (`brian@Kipruto`), 2026-10-30:

| What | Where | Note |
|---|---|---|
| `libpango-1.0-0`, `libpangoft2-1.0-0` | apt | required by WeasyPrint (pango ≥ 1.44); already present |
| `libharfbuzz-subset0` | apt | optional; without it fontTools subsets fonts |
| `weasyprint==66.0` | `requirements/base.txt` | released 2025-07; wheel, pure Python |
| `pypdf==6.20.1` | `requirements/development.txt` | tests only: read PDF text and attachments |

Check:

```bash
python -c "import weasyprint; weasyprint.HTML(string='<p>ok</p>').write_pdf(); print('PASS weasyprint', weasyprint.__version__)"
```

Expected: `PASS weasyprint 66.0`.

---

## Evidence

**7a (`cf2eff8`).** Forole (mission 8, 1,819 rows): the PDF's dose-rate row matched
psql's `percentile_cont`/`stddev` to 4 decimals (n 1819, mean 0.1405, SD 0.0849,
P50 0.1259, P95 0.2053, P99 0.6754, max 0.9585). PDF and embedded-CSV SHA-256 matched
`sha256sum`; CSV rows 1,819. Suite 755.

**7b (`0a54ad1`, `7104a8f`, `91e44c5`, `d3afe44`).**
- Map: the real Forole Sentinel-2 scene with the survey box; mission 12 drawn as a
  track with 2 breaks (TS-053), coloured by CPM.
- Reference levels: Forole 34 of 1,819 above 0.3 µSv/h, equal to SQL; mission 12
  PM2.5 mean 14.9613 → "below", equal to SQL `avg(pm25) > 15` = f, printed 14.96.
- Marking: band on all pages of both, `provenance-modelled` / `provenance-simulated`
  in Keywords.
- Branding: masthead and accent, fixed band colours; 5 runs of the report tests clean
  after TS-051.
- Suite 831.

**7c (`9308a48`).**
- Report #17 tampered on disk (hash changed): the console showed `409: Integrity check
  failed…`, nothing saved. Restored in 7 ms: `PDF SAVED · SHA-256 VERIFIED IN BROWSER`.
- `operator@byteanza.com` (superuser) sees only ByteAnza's 8 reports, none of KNRA's.
- Suite 853; frontend build clean; lint at the pre-existing 9.

**7d — the Marsabit showcase.** One report per KNRA site, each checked against raw SQL
and its files:

| Mission | Site | Rows (= SQL) | Above 0.3 µSv/h (= SQL) | Scene | Report |
|---|---|---|---|---|---|
| 2 | kargi | 2,347 | 0 | s2 2026-08-05 | #19 |
| 3 | boji | 2,023 | 0 | s2 2026-08-05 | #20 |
| 4 | gamura | 2,237 | 0 | s2 2026-08-05 | #21 |
| 5 | dukana-w1 | 1,279 | 0 | s2 2026-08-05 | #22 |
| 6 | dukana-w2 | 687 | 0 | s2 2026-08-05 | #23 |
| 7 | balesa | 1,689 | 0 | s2 2026-08-05 | #24 |
| 8 | forole | 1,819 | 34 | s2 2026-08-05 | #25 |

Rows sum to 12,081, the KNRA Table 3.1 total. Every report: weakest MODELLED, all rows
modelled, no per-reading list, no track, band on every page, PDF and CSV hashes
correct. `PASS 7d`.

---

## Tests

`reports/`: `test_stats` (tier rules, PostgreSQL-matching statistics), `test_map`
(projection, track rules, colouring, scene choice), `test_thresholds` (registry,
comparisons, wording in the PDF), `test_marking`, `test_branding`, `test_generate`
(refusals, atomicity, hashes, collisions, logging), `test_api` (tenancy, permission,
integrity, traversal; every refusal followed by the owner succeeding, timed). Every
rule above was mutation-checked; mutants that survived exposed weak tests, which were
fixed before delivery.

---

## Open items

- **Hidden Generate panel not seen in the browser.** The revoke and re-grant ran back
  to back; covered only by the 403 tests and the UI permission check.
- **Reports made before 7c** have no stored CSV; regenerate if needed.
- **KNRA crest**: not shown unless KNRA uploads it as the org logo.
- **ByteAnza logo**: needs a dark-on-light raster (TS-054).
- **UNSCEAR annex table number** to confirm; **Kenya EMCA air-quality values** not
  cited until the table is in hand.
- **Live tube**: dose rate only once calibrated; CPM is never compared.
- **Async generation** (Celery) post-finale.
