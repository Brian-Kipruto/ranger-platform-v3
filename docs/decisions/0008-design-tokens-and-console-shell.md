# 0008 — Design tokens via Tailwind v4 @theme, retrofit-first adoption, runtime accent

**Status:** Accepted, 2026-06-24. Revisit if the design system grows enough to
warrant a dedicated package, or when real RBAC replaces group-keyed nav.

## Context

Feature 06 retrofits the UI to the Field Console design (`.dc.html` mockup). The
mockup is a self-contained visual spec — all inline styles, hardcoded violet
(`#7c6cff`) everywhere, no portable code. Three decisions had to be made on the
way in:

1. **Where do design tokens live**, and how do components consume them?
2. **How does the design system get adopted** — build it up front, or let it
   emerge from retrofitting real screens?
3. **How is the tenant accent wired**, given the mockup hardcodes one color but
   V3 is multi-tenant with `organization.theme_color`?

A fourth, smaller decision rode along: the mockup's nav is role-scoped, but V3
has no role field (ADR 0002 — perms are Django Groups). How should the nav
represent role without inventing a role enum?

## Decision

**1. Tokens in Tailwind v4 `@theme`, runtime accent in `:root`.** Fixed tokens
(surfaces, text ramp, semantic colors, fonts, keyframes) go in the v4 `@theme`
layer, becoming both CSS vars and utility classes (`bg-surface-panel`,
`text-fg-dim`, `text-ok`). The themeable `--accent*` lives in plain `:root`,
NOT `@theme`, so it's never baked into a build-time utility — it must stay
runtime-mutable.

**2. Retrofit-first, extract-as-used.** No speculative design-system feature.
Primitives (`Panel`, `MonoLabel`, `StatusDot`, etc.) are discovered by applying
them to a real screen (login first), then factored into `components/console/`
once their shape is proven — never before.

**3. Runtime accent from org, color-mix for derivations.** `--accent` defaults
to violet in `:root` (fallback). `useAccentTheme()` overrides it from
`user.organization.theme_color` at runtime on `document.documentElement`.
`--accent-weak`/`-faint` derive via `color-mix(in srgb, var(--accent) N%,
transparent)`, so soft fills follow automatically without a second runtime var.

**4. Role-nav keyed off Group name, shaped for RBAC swap.** `navGroupsForRole()`
maps the user's Django Group (Operator/Client/Community) to a nav group set.
Structured so that real RBAC (ADR 0007) changes only this one function.

## Rationale

**Why `@theme` for fixed, `:root` for accent.** v4's `@theme` is the idiomatic
home for design tokens and gives free utilities, which keeps the retrofit using
clean class names instead of arbitrary hex values everywhere. But a `@theme`
token is resolved at build time — wrong for a value that must change per-tenant
at runtime. `:root` + JS `setProperty` is the correct tool for the one dynamic
token. Splitting them by mutability, not by type, is the principled line.

**Why retrofit-first.** The handoff mandated it, and it's sound: building a
design-system feature speculatively and then rebuilding screens to fit it is
double work and risks an API that doesn't match real needs. Applying a primitive
to a real screen reveals its true shape (e.g. `Panel` needed a `bodyClassName`
escape hatch and a `noHeader` variant — only obvious once the map and filter bar
used it). Extract after proof, not before.

**Why color-mix over a parsed-hex second var.** The alternative — having the
accent hook also compute and set `--accent-weak` by parsing the hex and applying
alpha — is more code and another thing to keep in sync. `color-mix` keeps the
derivation declarative in CSS, follows `--accent` for free, and is supported in
all current evergreen browsers. The only cost is a hard floor on very old
browsers, irrelevant for an internal field console.

**Why group-keyed nav, not full-nav-for-everyone.** Full-nav-for-everyone is
simpler now but is throwaway: RBAC will need role/permission-aware nav regardless,
so a flat nav gets rebuilt later. Keying off the Group name today (which the seed
provides) builds the *structure* RBAC needs — grouped, scoped, swappable — so the
eventual change is one function, not a rewrite. It also matches the mockup, which
shows distinct per-role nav. This is the cheap-to-evolve choice, consistent with
ADR 0002's "Groups, not a role enum" stance.

## Options considered

**Tokens — A: `@theme` + `:root` split (chosen).** Idiomatic v4, free utilities,
correct handling of the one runtime value. **B: everything in `:root`, no
`@theme`.** Loses the utility classes; retrofit would use arbitrary values
everywhere — verbose and un-Tailwind-y. **C: a `tailwind.config.js`.** Wrong for
v4, which moved theming into CSS.

**Adoption — A: retrofit-first, extract-as-used (chosen).** **B: build a
design-system feature first.** Double work, speculative API, explicitly rejected
by the handoff.

**Accent derivations — A: color-mix (chosen).** **B: hook sets a second
`--accent-weak` var via hex parsing.** More code, sync risk.

**Role-nav — A: group-keyed, RBAC-shaped (chosen).** **B: full nav for everyone.**
Throwaway. **C: real permission gating now.** Out of scope; that's the ADR 0007
feature, which should set the pattern across all surfaces at once, not as a
nav-only rider.

## Consequences

**Good:**
- Clean utility-class vocabulary for the retrofit and all future UI work.
- One correct mechanism for the tenant accent; proven across three orgs.
- Primitives that fit real needs because they were extracted from real use.
- Nav structure that RBAC slots into with a one-function change.

**Costs:**
- `--accent-weak` via `color-mix` won't render on pre-2023 browsers (acceptable).
- Group-keyed nav is not real authorization — any user can still navigate to any
  route by URL; the nav just doesn't *show* the link. Real gating is ADR 0007.
- The token vocabulary (`fg` ramp, `surface` ramp) is now a contract; renaming
  later is no longer free since components consume it.

## When to revisit

- When RBAC (ADR 0007) lands: replace `navGroupsForRole()`'s group-keying with
  permission-based filtering, and add route-level guards so URL navigation is
  also gated, not just the visible nav.
- If the console design system outgrows a single `components/console/` folder and
  wants its own package / Storybook.

## Related docs

- `features/06-ui-retrofit.md` — what was built on these decisions
- `decisions/0002-multi-tenant-via-organization-fk.md` — Groups-not-role-enum,
  the constraint the role-nav respects
- `decisions/0007-data-explorer-authenticated-only.md` — the RBAC thread the
  role-nav is shaped to slot into