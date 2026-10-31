# 050 — A truncated logo passes validation: WeasyPrint sets Pillow's `LOAD_TRUNCATED_IMAGES`

*Date: 2026-10-30 · caught by a test that passed alone and failed in the full suite*

---

## What we saw

`test_truncated_image_falls_back` passed on its own and failed in the full suite:
a logo cut to 200 of 740 bytes came back as an embeddable image.

## The cause

`weasyprint/images.py` sets `PIL.ImageFile.LOAD_TRUNCATED_IMAGES = True` at import,
process-wide. After WeasyPrint has been imported (any earlier test that rendered a
report, or the first report in a server process), Pillow **decodes a truncated file
silently**, padding the missing pixels. `Image.verify()` still raises on truncation
with the flag set; decoding does not.

| | flag False | flag True (after WeasyPrint) |
|---|---|---|
| `Image.open(...).convert("RGBA")` | raises | **accepted** |
| `Image.open(...).verify()` | raises | raises |

## The fix

`reports/branding.py` calls `verify()` before decoding, with the reason in the code.
I had removed it as "redundant" on reasoning I hadn't tested; the test caught it.

## Prevention

- The test pins **both** flag states with `monkeypatch`, so it cannot pass or fail by
  test order.
- Anything that validates uploaded images in a process that has imported WeasyPrint
  must use `verify()`.
