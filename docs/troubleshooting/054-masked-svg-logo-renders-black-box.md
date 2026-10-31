# 054 — The ByteAnza logo renders as a light mark in a black box

*Date: 2026-10-31*

---

## What we saw

`ranger_frontend/src/assets/byteanza-logo.svg` embedded in a WeasyPrint test page:
a light-grey logo inside a solid black rectangle, on white and on dark backgrounds.

## The cause

The SVG is a wrapper around embedded PNGs shaped by `<mask>`. WeasyPrint's SVG
renderer ignores the mask. Underneath, the mark is light grey for dark UIs, so even
masked correctly it would be near-invisible on a white page.

## The fix

The report's producer line is text only: "Produced with R.A.N.G.E.R. · ByteAnza".
The brand mark was not recoloured.

## Open

A dark-on-light raster of the ByteAnza logo placed in `ranger_backend/reports/assets/`
can be wired into the producer line.
