# 0005 — Auth feature: known gaps before production

**Status:** Accepted as backlog, 2026-05-10. Revisit before onboarding any non-developer user with real data.

## Context

Feature 02 (authentication) shipped a working login/logout/silent-refresh flow with httpOnly refresh cookies, server-side token blacklist, and a permissions-aware frontend store. The architecture is sound and applies uniformly to every user who logs in — this is not a "Brian-only happy path."

But the V3 architecture spec (§2.6, §7) lists security features that the auth feature did NOT implement, and the dev environment has assumptions that production cannot inherit. None of these are in scope of "Phase 2: Authentication" as built. All of them are in scope of "trustworthy enough that a paying client can use this."

This ADR is a deferred-work register: a checked-in record of what's missing, why it's not blocking dev work right now, and the bar at which each becomes blocking. It exists so these items don't quietly fall out of memory between auth-shipping (today) and client-onboarding (some future date).

## Gaps as of 2026-05-10

### Auth-flow gaps (require app code)

**1. MFA / 2FA — not implemented**
The `CustomUser.mfa_enabled` field exists. Nothing reads it, nothing enforces it, no TOTP setup endpoint, no recovery codes. V3 spec calls for `django-otp`. Endpoints `/api/auth/2fa/enable/` and `/api/auth/2fa/verify/` are listed in the spec but not built.
*Becomes blocking when:* any client whose security policy mandates MFA. In B2B environmental compliance, that's most of them. Treat as required for first paying client.

**2. Rate limiting — not implemented**
`/api/auth/token/` accepts unlimited login attempts per second. A bot can brute-force passwords without any throttling beyond Postgres latency. V3 spec calls for `django-ratelimit`. Not installed.
*Becomes blocking when:* the platform is publicly reachable. The moment we deploy behind a real domain, this is needed before announcing the URL anywhere.

**3. Account lockout — not implemented**
V3 spec: 5 failed login attempts → 15 min lockout. No counter, no lockout state, no unlock flow. Combined with #2, brute-forcing weak passwords is currently unrestricted.
*Becomes blocking when:* same trigger as rate limiting.

**4. Password reset / forgot-password — not implemented**
A user who forgets their password has no self-service recovery. Only path: ask a Django admin to reset via the admin panel.
*Becomes blocking when:* any user who can't be hand-held by ByteAnza staff. Self-service reset is table stakes for a B2B SaaS UX.

**5. Email verification on user creation — not implemented**
Phase 1 / V2's invitation flow assigns an email to new users with no verification that the address belongs to them. Combined with the typo risk on hand-entered emails, this is a real liability.
*Becomes blocking when:* email is used for password resets (i.e. as soon as #4 ships).

**6. Session management UI — not implemented**
V3 spec lists `/api/users/sessions/` (list active sessions) and force-logout endpoints. Useful for "I left my laptop logged in at the office — kill that session." Not built.
*Becomes blocking when:* clients ask, or after the first incident where someone's account was compromised and we needed a per-session revocation tool. (Note: "logout" today blacklists the current session's refresh token. There's no way to nuke ALL of a user's sessions at once.)

**7. IP allowlisting per organization — not implemented**
V3 spec calls for it. Some enterprise clients will require it. No model field, no middleware.
*Becomes blocking when:* a client contractually requires it. Defer.

**8. Audit logging — not implemented**
V3 spec mandates: every API call logged with user, action, resource, IP, timestamp. The `audit` Django app exists in `INSTALLED_APPS` but is empty. No model, no middleware, no admin view.
*Becomes blocking when:* compliance review (SOC 2, GDPR-strict clients). Earlier than people think.

### Endpoint-level gaps (will surface as we add features)

**9. Permission enforcement on per-feature endpoints**
The `permissions` list flows correctly from backend to frontend store. But there are no real CRUD endpoints yet. When missions / sensors / fleet endpoints land, each view needs `permission_classes` set correctly AND organization-scoped querysets (`queryset.filter(organization=request.user.organization)`).
*Becomes blocking when:* the second multi-tenant feature ships. The first feature might still be reviewable; by the second we need a base class or DRF mixin to enforce both org-scoping and permission checks consistently. Easy to forget per-view.

**10. CSRF on non-auth state-changing endpoints**
Currently every authenticated request uses `Authorization: Bearer`, which is naturally CSRF-resistant (CSRF needs ambient credentials like cookies; Bearer headers must be explicitly set). Not a current bug. But if we ever serve session-cookie-authed endpoints (e.g. for the public community portal), CSRF protection on POST/PATCH/DELETE becomes mandatory there.
*Becomes blocking when:* any endpoint accepts cookie auth. The community portal in Phase 10 is the likely first.

### Deployment / infrastructure gaps

**11. HTTPS termination — not configured**
Dev runs HTTP on `localhost`. The refresh cookie has `Secure` deferred to `not settings.DEBUG`, so it correctly auto-upgrades to HTTPS-only when `DEBUG=False`. But we have no deployed environment yet. V3 spec calls for nginx + Let's Encrypt + HSTS headers.
*Becomes blocking when:* first deploy. Day 1 of staging. Without HTTPS the entire cookie scheme is theater.

**12. HSTS, CSP, secure headers — not configured**
The V3 spec calls for Content Security Policy headers and HSTS. Not configured. Django has `SECURE_HSTS_SECONDS`, `SECURE_CONTENT_TYPE_NOSNIFF`, etc. — these need values in `production.py`.
*Becomes blocking when:* same as #11.

**13. CORS allowlist hardening**
`CORS_ALLOWED_ORIGINS` in `development.py` is set to localhost. Production needs an explicit allowlist of real frontend domains. `CORS_ALLOW_CREDENTIALS = True` is already set (correctly).
*Becomes blocking when:* first deploy.

**14. Secret management**
Currently `.env` file at project root. Production needs proper secret management — env vars from the platform (DigitalOcean App Platform, AWS Secrets Manager, etc.) or a secrets file outside source control. `JWT_SIGNING_KEY` rotation also has no story; rotating it would invalidate every outstanding token.
*Becomes blocking when:* first deploy. Some kind of secret management is needed before production keys exist.

**15. Database backups, encryption at rest**
V3 spec calls for "Encryption at rest: PostgreSQL + filesystem encryption." Docker volume in dev is unencrypted. Managed Postgres on the deploy target should give us encryption at rest by default. Backup strategy: nothing yet.
*Becomes blocking when:* first real client data lands. Before that, every deploy is throwaway.

**16. Periodic cleanup of expired JWT tokens**
The `OutstandingToken` table grows by one row per login and one row per refresh-rotation. Never auto-deleted. simplejwt ships a management command:

```bash
python manage.py flushexpiredtokens
```

This deletes Outstanding tokens past their natural expiry AND cascades to any Blacklisted entries pointing to them. Safe to run anytime; idempotent.

Rough back-of-envelope: 100 users × daily login × ~30 rotations per session × 365 days = ~1M rows per year. Postgres handles it fine but the table is unbounded.

*Becomes blocking when:* table size is noticeable operationally, or first production deploy (run as a daily Celery beat task — see V3 spec's Celery integration in Phase 8). For now: run manually if the dev DB feels cluttered.

## Decision

These are deferred. The auth feature shipped is "dev-grade complete and architecturally sound." Production-grade requires the items above.

**Hard rule: no real client onboarding until at minimum #1 (MFA), #2 (rate limiting), #3 (lockout), #4 + #5 (password reset + email verification), #11 (HTTPS), #12 (HSTS/CSP), #13 (CORS), #14 (secrets) are shipped.**

The others (#6, #7, #8, #15, #16) become blocking on specific triggers documented above and should be tracked but aren't necessarily day-1 blockers.
## Consequences

**Good:**
- The gaps are written down. Future-Brian (or the next contributor) doesn't have to rediscover them.
- The triggers are explicit. We don't have to guess "is it time yet?" — each item says when.
- This serves as a pre-launch checklist when the moment arrives.

**Costs:**
- The list will grow as we build out features. Need to revisit and update this ADR (or supersede with a new one) when major shifts happen — e.g. when MFA ships, this ADR's #1 entry is struck through with a link to the feature doc that closed it.

## When to revisit

- Before any deploy to a publicly reachable URL: items #11-14 minimum
- Before any non-ByteAnza-staff user logs in: items #1-5 minimum
- Before first paying B2B client: full review of all 15
- When a client contractually requires something on the list (IP allowlist, audit log access): jump that item to the front

Update this document as items ship. Don't delete entries when closed — strike them through with a link to the closing feature/PR/commit so the history is traceable.

## Related docs

- V3 Architecture spec §7 (Security Architecture) — original mandate for most of these items
- V3 Architecture spec §2.6 (New Features — Security) — checklist of security features by phase
- `features/02-authentication.md` — what was actually built
- `decisions/0003-refresh-token-storage.md` — why the cookie scheme works (and what it depends on at deploy time)
- `decisions/0004-token-blacklist-on-logout.md` — server-side revocation mechanism