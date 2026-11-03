# F18 — Retrospective

*Date: 2026-11-02*

---

## What worked

**An audit with a fixed list before any code.** Every nav entry per role, every seam,
both ADR debts, then an 18-item fence. When the hardware was out of reach the list split
cleanly into a UI half to build now and a tenancy half to park, without re-planning.

**Delete, don't label.** Removing the DEMO data outright (ADR-0040) left nothing to
audit later; a labelled fake is still on screen and still has to be remembered.

**Sign-off screenshots found what the audit missed.** The login's TLS badge and fake
footer, the global `is_verified` showing another tenant's retrievals, Visualizations
never having been retrofitted, the clock-only ticks running backwards, a "no data"
message that was false for KNRA: each surfaced from a screenshot, not from reading code.

**Dev hints gated, not deleted.** `import.meta.env.DEV` kept the bench usable while
production builds lost every env var, command name and address — proven by grepping the
bundle and by `vite preview`.

**Fullscreen without a remount.** Expanding the camera as a CSS class on the same Panel
kept the MJPEG connection (TS-039's lesson) and matched FieldMap's behaviour.

## What didn't

**The audit missed fakes.** The login footer, the TLS badge, the Satellite tenancy leak
and the un-retrofitted Visualizations page were all in the code at the audit and were
not in it. The audit read the dashboard seams by grep for DEMO/placeholder; fakes that
were never labelled as fakes don't match that grep. Read every rendered string.

**The swap contract didn't hold.** "All placeholder data lives in one file" was false:
the `HDG 142° · 1.4 m/s` readout was hardcoded in `DashboardPage`.

**I shipped a false empty state.** CP2's "NO DATA IN THIS ORGANIZATION" was wrong for an
org with data but no PM2.5. Caught in sign-off; fixed in `739867d`.

**Order slips at commit time.** CP2 was committed before the corrected `SensorStreams`
was placed (the hash check printed the old hash and the commit went ahead), so the fix
needed its own commit. CP5 was committed before its hash check. Both ended clean, but
the gate is hash → build → sign-off → commit.

**A preview check with the wrong expectation.** I warned the preview might not proxy
`/api`; it did, and the blank map was the MapTiler origin restriction instead (TS-055).

## Workflow notes

- Hand placement with an in-place `git hash-object` check every time; no copy scripts.
- Dev and production behaviour diverge on purpose now: sign-off for user copy needs the
  production preview, not the dev server.
- Pre-existing lint errors were checked against `3d0bb61` before being called
  pre-existing.

## Carry-forwards

- **Audit by rendered string, not by label.** Grep for literals in JSX, not for "DEMO".
- **Any per-tenant view reading a model without an organization FK is a leak candidate.**
- **Empty states say what is absent, never why.**
- **Hash, build, sign off, then commit — in that order.**
