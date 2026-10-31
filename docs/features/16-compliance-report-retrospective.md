# F16 — Retrospective

*Date: 2026-10-31*

---

## What worked

**Independent paths for every number.** The report computes statistics in numpy and
exceedances in Python; every check ran them against raw SQL (`percentile_cont`,
`stddev`, `count(*) FILTER`). 7d ran that comparison for all seven sites in one script,
alongside both file hashes and the band on every page. Agreement between two paths
means more than one path agreeing with itself.

**Mutation checks found weak tests, not just weak code.** Four mutants survived on
first run: the cos(latitude) term (the test was circular), a distorted resize (the
canvas kept its size), the template ignoring the resolved decimals (nothing read the
printed PDF), and the path-traversal guard (a non-matching file was refused by the
integrity check, so the guard was never exercised). Each was fixed by a stronger
test, not by trusting the code.

**Reading the actual source when behaviour made no sense.** The fontTools flood
(TS-052) and the truncated logo (TS-050) were both WeasyPrint changing process state:
found by checking the effective log level at emit time and by reading
`weasyprint/images.py`, not by more guessing.

**Deterministic reproductions of timing bugs.** The same-second overwrite (TS-051)
was reproduced with a frozen clock and stubbed output before any fix, and that
reproduction became the test.

**Honesty rules made into code.** Weakest tier, never pooled, no CPM for modelled, no
located anomalies from modelled data, levels not limits, no PASS/FAIL: each is a rule
with a test that fails if it is broken, not a sentence in a doc.

**Verified citations.** WHO was checked against the primary table, UNSCEAR against
independent sources, and the KNRA title against what F10.3 had already verified. One
title I had paraphrased from memory was caught and checked before shipping.

## What didn't

**A guess presented as a likely cause.** Mission 12's 180 breaks were attributed to
"two writers interleaved" before the rows were queried. One query showed one writer
and a fast sim (TS-053). Query first.

**Removing code on untested reasoning.** I removed `verify()` as redundant; the test
I added to prove it showed it was the only check that worked after WeasyPrint's import
(TS-050).

**A layout change that broke an invariant.** Cutting the printed time to seconds made
same-second PDFs identical and file names collide (TS-051). It surfaced as one flaky
failure on the PC and never in the sandbox.

**Sandbox process limits.** A mutation batch hit the tool time limit and was killed
mid-run, leaving `views.py` with a mutation in place. It was found by grepping for
every mutation string and restored from the backup. A background run was silently
killed too. Mutations now run in small foreground batches against the relevant tests
only, restoring the file after every mutant.

**Verification steps the user could not see.** The first two tamper runs showed
nothing, because the refusal note was under a terminal window and then no click
happened while the file was tampered. Splitting into "tamper and prove it" and
"restore and prove it", with no interactive prompt, fixed it.

**A test-count expectation I miscalculated** (147 instead of 126).

## Workflow notes

- Files are placed by hand; handoffs give a hash check of files in place, not copy
  scripts.
- Two files with one name (`urls.py`) were disambiguated by hash in the table.
- A sign-off item was raised when a screenshot didn't show the expected state
  (Generate visible for a user I'd said was ungranted): one query showed a superuser.

## Carry-forwards

- **Check every `src` path a stored record can name stays inside its root**, and test
  it with a file that would otherwise pass every other check.
- **Any image validation in a process with WeasyPrint uses `verify()`.**
- **Query the data before naming a cause.**
- **Mutation runs: small foreground batches, the relevant test files, restore after
  each, and grep for leftovers if a run dies.**
- **Visual sign-off steps are non-interactive and name the exact row or element.**
- Open items: see `16-compliance-report.md`.
