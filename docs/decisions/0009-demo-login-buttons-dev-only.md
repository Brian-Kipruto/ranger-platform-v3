# 0009 — Demo login buttons are dev-only (production-strip register)

*Date: 2026-06-25*
*Status: Accepted (deferred remediation — tracked, not yet implemented)*

---

## Context

The Field Console login screen (F06) has three "ENTER DEMO AS" buttons —
OP / CL / PUB — below the main login form. They exist so the role-based UI can be
demoed without typing credentials for each tenant.

During F07's CP6 end-to-end pass, it was noticed that clicking CL or PUB lands on
the respective dashboard **without the user typing anything**. This prompted the
question: is this an authentication bypass?

**It is not.** Inspecting `LoginPage.tsx` (`onDemoLogin`) and
`config/demoAccounts.ts`: each button calls the real `useAuthStore.login(username,
password)` with credentials hardcoded in `demoAccounts.ts` (all three accounts,
password `RangerDemo1234!`, created by the `seed_demo` management command). The
button auto-fills and submits real credentials behind the scenes — the exact same
auth path as the main form, a real JWT is issued, the backend really validates.
The operator button only *looks* different because `operator@byteanza.com` is the
email field's placeholder text.

So the behavior is correct and intentional for development. The real concern is
**deployment**.

## Problem

If the demo buttons (and `demoAccounts.ts`) ship to production:

1. Anyone hitting the login page gets one-click access to seeded accounts across
   all three tenants.
2. A plaintext password file is bundled into the production JS.
3. If `seed_demo` is ever run against a production database, those accounts
   exist server-side too.

The code comment in `demoAccounts.ts` already says "DEV ONLY" — but a comment is
not a guard. Nothing currently prevents the buttons from rendering in a
production build.

## Options considered

1. **Remove the demo buttons entirely now.** Rejected — they're genuinely useful
   for dev/demo, and F07 is a frontend dashboard feature, not the place to change
   auth/login behavior.
2. **Gate behind `import.meta.env.DEV`.** The buttons + the `demoAccounts` import
   render only in dev builds; Vite tree-shakes them (and the password file) out
   of production. Simple, standard, zero runtime cost.
3. **Gate behind a `VITE_ENABLE_DEMO_LOGINS` env flag.** More flexible (could
   enable on a staging build), but adds a config knob and the risk of it being
   left on.

## Decision

Defer remediation (out of F07 scope — this is a login/auth concern, F07 is
Dashboard + Map), but **register it as a required production-hardening item** so
it is not forgotten:

- Gate the demo buttons behind `import.meta.env.DEV` (Option 2) as the default,
  with `VITE_ENABLE_DEMO_LOGINS` (Option 3) as an optional override only if a
  staging demo build is ever needed.
- Do **not** run `seed_demo` against any non-dev database.
- This work lands with the broader auth/RBAC hardening (see ADR 0007), or
  sooner if any production/staging deploy is attempted first.

## Consequences

- The demo buttons keep working unchanged in local dev.
- A clear, dated record exists so "strip demo logins" is on the pre-production
  checklist alongside the ADR-0007 authorization work and the ADR-0005 auth gaps
  register.
- Until implemented, **the app must not be deployed to a publicly reachable
  environment** without first applying the gate. Flagged in the F07 feature doc
  and retrospective.