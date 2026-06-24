# Feature 06 Retrospective — UI Retrofit (Field Console)

> Period: 2026-06-24. Sessions: ~1 (seed → tokens → login → shell → data
> explorer → docs). Branch: `feat/ui-retrofit`.

## What worked

**Reading the real backend before wiring "real" role buttons.** The decision to
make the demo buttons log in for real forced a look at `accounts/models.py` —
which surfaced the load-bearing fact early: **there is no `role` field**, perms
are Django Groups (the model comment says so outright, and ADR 0002 locked it).
The mockup's whole role concept (Operator/Client/Community) had no backing field.
Catching that before building meant the seed created Groups + the role-nav keyed
off group names, instead of inventing a fake role enum that would've fought the
existing design. Cloning the repo and grepping the auth chain beat asking for
files one at a time.

**Two clean commits, code separate from docs, seed separate from frontend.** The
seed is backend and additive; the retrofit is pure frontend. Keeping them as
distinct commits (`275730d`, `1ca2a3a`) kept the "F06 is frontend re-presentation"
rule technically honest — the one backend touch is an isolated management command,
changing no models, no migrations, no auth logic. Anyone reading the history sees
exactly what was data-setup vs. presentation.

**Extract-as-used, not pre-build.** The adoption model (discover the primitive
API by applying it to a real screen, then factor it) held up. `Panel`,
`MonoLabel`, `StatusDot`, `CornerTicks` proved their shape on the login screen
before the shell reused them; `MetricTile` and the `Panel` header/`bodyClassName`
variants emerged from the Data Explorer needing them. No speculative design-system
feature got built and then rebuilt.

**The token rename was free because it happened before any component used it.**
The first `index.css` draft had `--color-text-*`, which produced the awkward
`text-text-dim` utility. Renaming to `--color-fg-*` (→ `text-fg-dim`) cost one
script and one rebuild because zero components had consumed the tokens yet. Doing
the CP0 token-reference doc *before* writing TSX is what made the rename cheap —
the naming got eyeballed in isolation.

**The accent-follows-org proof was designed in from the start.** Seeding two
orgs with *different* `theme_color`s (teal + amber) meant the single most
important wiring claim — that `--accent` is runtime-driven, not hardcoded — was
visually provable by just clicking OP then CL and watching the whole shell repaint.
The violet community fallback proved the third path. No "trust me, it's wired."

**`tsc -b --force` + `vite build` in scratch before every handoff.** Same
discipline as F05. Every checkpoint compiled clean against the real libs before
the files left the scratch dir, so the only errors that ever reached the editor
were the phantom TS-server-cache ones (troubleshooting 013), which a restart
cleared. No real type error survived to the browser.

## What was hard

**The TS-server phantom-module errors (troubleshooting 013).** Twice, dropping
new files in produced a wall of red "Cannot find module
'@/components/console/...'" errors in the editor — for files sitting *right there*
in the tree. Alarming the first time, because it looks like a path-alias or
tsconfig break. The tell: `tsc -b --force` on the CLI was clean, and the files
existed. It's the editor's TS server not re-indexing new files; "Restart TS
Server" clears it instantly. The standing reminder had flagged this exact failure
mode, and it still cost a beat to trust the CLI over the editor's red squiggles.

**Username-vs-email login mismatch.** simplejwt authenticates on `username`, but
the mockup displays an email in the Operator ID field, and the demo buttons need
"what's shown == what's submitted" to feel real. First seed used short usernames
(`operator`) with email addresses as a separate field — which would've meant the
button submits `operator` while the field shows `operator@byteanza.com`. The fix
(usernames == emails) required deleting and re-seeding the three demo users, cheap
because they're throwaway. Worth catching before the buttons were wired, not after.

**Keeping the Data Explorer's logic genuinely untouched through a full re-chrome.**
The temptation in a visual retrofit is to "tidy" logic while you're in there. The
discipline was to rewrite *only* the `return` JSX and the import block, leaving
all 300 lines of hooks/handlers/table-config/map-effects byte-for-byte. The
verification — table still sorts, map still flies on row-click, export still
downloads — confirmed the re-chrome didn't disturb the engine. The `accent` JS
const survived because the MapLibre paint reads it (paint can't read CSS vars, so
the JS const is correctly the right tool there, not a leftover).

## Carry-forwards

1. **Static chrome awaiting real features.** The 2FA tiles, role switch, ⌘K
   search, status pills, and alerts bell all render but do nothing. Each is a
   visual placeholder for a future feature (2FA, RBAC role-switching, command
   palette, fleet/live status, alerts). The markup being ready is the point.
2. **Un-retrofitted pages inside the shell.** Dashboard, Visualizations, and
   HomePage still wear their old light-card styling inside the console frame.
   Accepted and expected; they get retrofitted as they're revisited. The shell
   already frames them correctly — only their innards lag.
3. **Role-nav is group-keyed, ready for RBAC.** `navGroupsForRole()` keys off
   Django Group name today. When ADR 0007's authorization work lands, that one
   function swaps to permission-based filtering; nothing else in the nav changes.
4. **The `.dc.html` mockup stays the visual spec.** Attach it to the next UI
   feature's handoff — Dashboard and the Foxglove-style Workspace are the richest
   un-built screens in it.
5. **MapTiler key still needs HTTP-origin restriction before production**
   (carried from F05, unchanged).

## What to do differently

- **Trust the CLI compiler immediately on phantom editor errors.** Restart the TS
  server *first* when new-file module errors appear, before reading them as real.
  Troubleshooting 013 now documents it; the reflex should be automatic next time.
- **Decide username scheme at seed-design time**, not after. The email-as-username
  call was right but came after a first seed; folding the auth-field reality into
  the seed spec up front avoids the re-seed.