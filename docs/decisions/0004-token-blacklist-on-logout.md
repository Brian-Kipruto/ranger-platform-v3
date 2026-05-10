# 0004 — Token blacklist on logout (and on rotation)

**Status:** Accepted, 2026-05-10.

## Context

Stateless JWT has a known weakness: tokens are valid until their expiry, period. The server can't revoke them. If a refresh token is stolen, it stays good for 7 days regardless of what the user does — including clicking "Log out."

Two fixes possible:

1. Keep stateful refresh tokens in a blacklist DB table; check on every refresh
2. Shorten refresh token lifetimes drastically and accept the UX cost (re-login frequently)

Option 2 fights the whole point of a 7-day refresh token. Option 1 is what `djangorestframework-simplejwt`'s `token_blacklist` app does.

## Decision

**Enable `rest_framework_simplejwt.token_blacklist` and turn on `BLACKLIST_AFTER_ROTATION`.**

This means:
- Every refresh token issued is recorded in the `OutstandingToken` table
- When a refresh token is used to mint a new one (rotation), the old one is added to `BlacklistedToken`
- When a user logs out, we explicitly blacklist their current refresh token
- Refresh requests check both tables; blacklisted tokens are rejected

## Why now and not later

Without the blacklist, "Log out" is theater: it clears the client's tokens but a malicious party who already has the refresh can still use it for 7 days. For a security-sensitive platform mandated to have audit trails (V3 §7.5), shipping logout-as-theater would have been a real bug, not just an oversight.

The cost is one extra DB table + a tiny check on every refresh. Trivial.

## Consequences

**Good:**
- Logout actually invalidates server-side. UX assumption matches reality.
- Token rotation is meaningful — a stolen refresh can be used at most once before rotation kills the original (and ideally the attacker's stolen copy too).
- Visible in Django admin: `/admin/token_blacklist/blacklistedtoken/` shows every revoked token, useful for incident review.

**Costs:**
- One extra DB table (`OutstandingToken`) grows ~1 row per login. For a fleet of 100 users logging in daily for a year, that's 36,500 rows. Trivial.
- Refresh endpoint does one extra DB lookup. Sub-millisecond.
- The access token still can't be revoked. A stolen access token is good for up to 15 minutes regardless. Documented limit, not a fix in scope.

## When to revisit

- If `OutstandingToken` table growth becomes operationally meaningful (millions of rows) → add a periodic cleanup job that purges tokens past their natural expiry
- If we need true real-time revocation including access tokens → consider switching to opaque tokens with a session table (loses statelessness, but real-time revocation is the point)