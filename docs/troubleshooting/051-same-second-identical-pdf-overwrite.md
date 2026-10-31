# 051 — Two reports in the same second overwrote each other

*Date: 2026-10-30 · a flaky "1 failed" on the PC that never reproduced in the sandbox*

---

## What we saw

One full-suite run on the PC: `1 failed`. The next run: all green. The sandbox never failed.

## The cause

7b cut the printed "Generated" time to whole seconds. WeasyPrint is byte-deterministic
within one wall-clock second: its PDF `CreationDate` is the only varying field. Two
generations of the same mission in the same second produced **identical bytes**, so
the same SHA-256, so the same file name (`…-{stamp}-{sha8}.pdf`). `os.replace`
overwrote the first file, and two `Report` rows pointed at one file. The PC is fast
enough to land both runs of `test_regenerating_makes_a_new_report` in one second;
the sandbox is not.

Reproduced deterministically by freezing `timezone.now` and stubbing `render_pdf` to
return constant bytes: both rows got the same path.

## The fix

- A random token in every file name (`secrets.token_hex(4)`).
- `_write_atomic` uses `os.link` (fails if the target exists) instead of
  `os.replace`. A future collision is a loud error, never a silent overwrite.
- Checked on the PC that no two existing rows shared a file (0 rows).

## Prevention

A timing-dependent failure gets a deterministic reproduction (frozen clocks, stubbed
output) before a fix, and the fix gets the reproduction as its test.
