# 052 — ~230 fontTools INFO lines per report, despite `setLevel(WARNING)`

*Date: 2026-10-31*

---

## What we saw

Every `generate_report` under dev settings printed ~230 lines like
`INFO fontTools.subset: glyf pruned`, even though `render_pdf` set the `fontTools`
logger to WARNING.

## The cause

At emit time the `fontTools` logger was at **DEBUG**. WeasyPrint wraps font
subsetting in `capture_logs('fontTools', level=WARNING)`
(`weasyprint/pdf/fonts.py`), which swaps in its own handler and sets the logger to
DEBUG for the duration, then restores the old level. Our WARNING was overridden at
exactly the moment that mattered. The records also kept propagating to Django's root
console handler.

## The fix

`fonttools.propagate = False` (with the level kept at WARNING). WeasyPrint's capture
handler lives on the `fontTools` logger itself, so it still receives everything and
re-logs real warnings through WeasyPrint's own logger; nothing reaches root.

## Prevention

`test_fonttools_subset_chatter_never_reaches_root` captures at DEBUG on root and
asserts no `fontTools` record arrives; it fails if `propagate = False` is removed.
When a logger "ignores" its level, check the effective level **at emit time**.
