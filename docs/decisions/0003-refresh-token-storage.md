# 0003 — Refresh token storage: httpOnly cookie + SameSite=Strict

**Status:** Accepted, 2026-05-10.

## Context

The auth feature needs to keep users logged in across page reloads. JWT auth has two tokens:

- **Access token:** short-lived (~15 min), sent on every API request as a Bearer header
- **Refresh token:** long-lived (~7 days), used to obtain new access tokens

Where each token lives matters for security and UX. The access token has to be JS-readable (something has to attach it to the Authorization header) so it must be in memory or localStorage. The refresh token has the longer life and a bigger blast radius if stolen — its storage location is the actual decision.

## Threat model

The platform handles environmental compliance data for B2B clients (mining companies, NGOs, regulators). Sensitive enough that XSS exfiltrating a 7-day refresh token is a meaningful concern: an attacker with the refresh can mint access tokens for a week, undetected.

Phase 1's V2 docs already flagged XSS as a real concern; the V3 architecture spec (§7.1) explicitly mandates httpOnly cookies for refresh tokens.

## Options considered

### A) localStorage for both tokens
Simplest. JS reads/writes both tokens directly. Auth store handles all flow.
- ✗ XSS reads localStorage trivially. Refresh token compromise = 7-day exposure window.
- ✗ Doesn't match V3 spec.
- ✓ No CORS/cookie complications, no CSRF surface.

### B) httpOnly cookie for refresh, in-memory for access (chosen)
Refresh lives in a cookie JS can't read. Access lives in Zustand state with a localStorage mirror so hard reloads don't flash the login page.
- ✓ Refresh token survives XSS (httpOnly).
- ✓ Browser auto-sends cookie on `/api/auth/*` requests; no manual handling.
- ✓ `SameSite=Strict` neutralizes CSRF without a separate CSRF dance (see ADR considerations below).
- ✗ Access token mirror in localStorage is XSS-readable. Access token expires in 15 min though, and an attacker can't refresh it without the cookie.
- ✗ Cookie + CORS interaction (need `withCredentials: true`, exact origin allowlist) is one more thing to get right.

### C) httpOnly cookies for both
Refresh AND access tokens as httpOnly cookies. Backend reads access from cookie too.
- ✓ Maximal XSS resistance.
- ✗ Substantial backend changes — JWT auth class would need a custom variant that reads from cookies.
- ✗ Forces every API endpoint into the cookie-CSRF model.
- ✗ Loses the natural fit with `Authorization: Bearer` for non-browser clients (CLIs, robots calling the API).

### D) Both in localStorage with backend session-cookie hybrid
Out of scope; would require Django sessions for refresh, which fights with stateless JWT.

## CSRF mitigation for option B

Once refresh lives in a cookie, the refresh endpoint is theoretically CSRF-vulnerable. Three mitigations considered:

1. **Double-submit cookie pattern** — separate JS-readable CSRF cookie, sent as header on refresh
2. **Django CSRF middleware on the refresh endpoint** — fetch CSRF token via dedicated endpoint
3. **`SameSite=Strict` and rely on it alone** (chosen)

`SameSite=Strict` means modern browsers don't send the refresh cookie on requests originating from any other site. Browser support is >95%. The trade-off: the refresh cookie won't be sent if a user clicks an external link to a deep page (so they'd need to re-login from a fresh tab). For an internal B2B platform, that's acceptable — users don't land here from external links mid-session.

If we later add public-portal flows or OAuth callbacks where Strict bites us, we upgrade to option (2). Documenting now so the decision is auditable later.

## Decision

**Option B with `SameSite=Strict`.** Refresh token in httpOnly + SameSite=Strict cookie scoped to `Path=/api/auth/`. Access token in Zustand memory with a localStorage mirror.

Cookie is `Secure` in production (`DEBUG=False`) and not Secure in dev (HTTP localhost). The flag is computed at request time inside the cookie-setting helper rather than in the config dict — see troubleshooting/009 for why.

## Consequences

**Good:**
- Refresh token immune to XSS exfiltration.
- No CSRF dance needed for the auth feature scope.
- Browser auto-handles cookie sending; minimal frontend code.

**Costs:**
- Vite dev proxy is required (`/api` proxied to backend) so requests look same-origin and `withCredentials: true` works without CORS preflight headaches.
- Production deployment must terminate TLS and set `DEBUG=False` so the `Secure` flag activates.
- The `Path=/api/auth/` scope means future endpoints outside `/api/auth/` can't read the refresh cookie. We don't need them to — listing it here so the constraint is explicit.

## When to revisit

- If we add public-portal flows or third-party OAuth callbacks where SameSite=Strict prevents legitimate flows → upgrade to double-submit CSRF (option 1)
- If a robot or non-browser client needs to use the refresh flow → add a separate refresh endpoint that reads from `Authorization: Bearer` instead of cookie
- If we hit XSS in the wild that exfiltrates an access token → consider option (C) and accept the backend complexity