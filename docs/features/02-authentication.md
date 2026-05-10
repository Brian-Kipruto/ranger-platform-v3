# Feature 02 — Authentication

> Status: Shipped 2026-05-10. Branch: `feat/auth`. Commits: `b14ac43` (backend), `8b926b0` (frontend).

## What it does

End-to-end login/logout/session-management for the platform. A user can:

- Sign in with username + password, get a JWT access token + an httpOnly refresh cookie
- Stay logged in across page reloads via silent refresh (no re-prompt unless their refresh cookie has expired or been blacklisted)
- Hit a protected URL while logged out and get bounced to `/login?next=<original-path>` so they land where they intended after signing in
- Log out, which invalidates the refresh token server-side (not just clears the client) so a stolen refresh token can't outlive the user's intent

The frontend `useAuthStore` (Zustand) is the source of truth for "who is the current user" and exposes `hasPermission(code)` so future features can gate UI on permissions without changes to this layer.

## Endpoints

| Method | URL                          | Auth        | Returns                                                   |
| ------ | ---------------------------- | ----------- | --------------------------------------------------------- |
| POST   | `/api/auth/token/`           | None        | 200 `{access, user}` + `Set-Cookie: ranger_refresh`. 401 on bad creds. |
| POST   | `/api/auth/token/refresh/`   | Cookie      | 200 `{access}` + rotated refresh cookie. 401 if no/dead cookie. |
| POST   | `/api/auth/logout/`          | Bearer      | 205, blacklists refresh, deletes cookie. Idempotent.      |
| GET    | `/api/users/me/`             | Bearer      | 200 user payload (see below). 401 unauthed.               |

### `/api/users/me/` payload shape

```json
{
  "id": 1,
  "username": "kipruto",
  "email": "...",
  "organization": {
    "id": 1,
    "name": "ByteAnza",
    "slug": "byteanza",
    "theme_color": "#0ea5e9",
    "logo_url": null
  },
  "groups": [{"id": 1, "name": "Org Admin"}],
  "permissions": ["missions.launch_mission", "core.export_sensorlog"],
  "is_superuser": false,
  "is_staff": false,
  "mfa_enabled": false,
  "phone": ""
}
```

Permissions are `app_label.codename` strings to match Django's `user.has_perm()` format. Superusers get `permissions: []` and rely on `is_superuser` short-circuiting in the frontend's `hasPermission()` — shipping the full perm list for a superuser would be hundreds of strings every page load.

## Files

### Backend (`ranger_backend/`)

**New:**
- `accounts/serializers.py` — `OrganizationNestedSerializer`, `GroupNestedSerializer`, `UserMeSerializer`, `CustomTokenObtainPairSerializer`
- `accounts/views.py` — `UserMeView`, `CustomTokenObtainPairView`, `CookieTokenRefreshView`, `LogoutView` + `_set_refresh_cookie`/`_delete_refresh_cookie` helpers
- `accounts/urls.py` — routes the four endpoints under `/api/`
- `accounts/tests/__init__.py` + `accounts/tests/test_auth.py` — 19 tests covering all four endpoints + rotation + blacklist

**Modified:**
- `ranger_backend/settings/base.py` — added `rest_framework_simplejwt.token_blacklist` to `THIRD_PARTY_APPS`, flipped `BLACKLIST_AFTER_ROTATION` to `True`, added `REFRESH_COOKIE` config dict
- `ranger_backend/urls.py` — `include("accounts.urls")` under `/api/`

**Deleted:**
- `accounts/tests.py` (replaced by `tests/` package)

### Frontend (`ranger_frontend/src/`)

**New:**
- `types/auth.types.ts` — TS mirrors of backend payloads (`User`, `Organization`, `Group`, `LoginRequest`, `LoginResponse`, `RefreshResponse`)
- `api/auth.ts` — typed wrappers for `login`, `logout`, `refresh`, `getMe`
- `pages/LoginPage.tsx` — react-hook-form + zod, handles `?next=` redirect
- `pages/DashboardPage.tsx` — placeholder so post-login has somewhere to land
- `components/ProtectedRoute.tsx` — auth check + hydration-aware rendering

**Modified:**
- `api/client.ts` — `withCredentials: true`, full silent-refresh interceptor with single-flight queue
- `stores/authStore.ts` — full rewrite from Phase 1 stub
- `App.tsx` — wired router, calls `hydrate()` on mount

## Data flow

### Login

User submits LoginPage form
→ authStore.login(u, p)
→ POST /api/auth/token/ {username, password}
→ Backend: CustomTokenObtainPairView
validates, generates {access, refresh}, embeds user via UserMeSerializer
pops refresh from body, attaches to Set-Cookie
→ Response: 200 {access, user}, Set-Cookie: ranger_refresh
→ Store: user, accessToken (memory + localStorage), isAuthenticated=true
→ LoginPage: navigate(next || "/dashboard")

### Silent refresh on page reload (hydrate)
App mounts → useEffect → hydrate()
→ If localStorage has access token: try GET /api/users/me/
→ 200: store the user, done
→ 401: fall through
→ POST /api/auth/token/refresh/ (browser sends ranger_refresh cookie)
→ 200: rotate cookie, get new access, store it, retry GET /me/
→ 401: clear() everything, isHydrating=false

### Silent refresh on expired access token (interceptor)
Any request returns 401
→ axios response interceptor catches it
→ Skip if URL is in AUTH_URLS (login/refresh/logout) or _retry already true
→ Single-flight: if refreshPromise is null, create it; else await existing
→ On refresh success: retry original request with new access token
→ On refresh failure: useAuthStore.clear(), reject original error to caller

The single-flight queue is the load-bearing piece. Without it, 5 concurrent expired-token requests fire 5 concurrent refresh calls; rotation+blacklist kills 4 of them; the user sees random failures. With it, all 5 await one promise, get one new access token, all retries succeed.

### Logout
User clicks Log out → authStore.logout()
→ POST /api/auth/logout/ with Bearer access (cookie auto-sent)
→ Backend: LogoutView reads cookie, blacklists token, returns 205 with cookie deletion
→ Frontend: clear() — wipes user, accessToken, localStorage, isAuthenticated=false
→ DashboardPage: navigate("/login")

## Storage

| Item              | Where                                | Why                                       |
| ----------------- | ------------------------------------ | ----------------------------------------- |
| Refresh token     | httpOnly SameSite=Strict cookie      | XSS can't read it. See ADR-0003.          |
| Access token      | Zustand store (memory) + localStorage mirror | Memory primary; mirror survives hard refresh without flashing the login page. |
| User payload      | Zustand store (memory)               | Re-fetched on hydrate via `/api/users/me/` |
| Blacklist (server)| Postgres via simplejwt's blacklist app | Logout / refresh-rotation actually invalidate. See ADR-0004. |

## Config knobs

In `settings/base.py`:

- `SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]` — currently 15 minutes
- `SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]` — currently 7 days
- `SIMPLE_JWT["ROTATE_REFRESH_TOKENS"]` — `True` (every refresh issues a new refresh token)
- `SIMPLE_JWT["BLACKLIST_AFTER_ROTATION"]` — `True` (old refresh dies the moment it's rotated)
- `REFRESH_COOKIE["max_age"]` — derived from `REFRESH_TOKEN_LIFETIME`
- `REFRESH_COOKIE["path"]` — `/api/auth/` (browser only sends cookie on auth endpoints, minimizing exposure)

The `secure` flag on the refresh cookie is **not** in the config dict — it's computed at request time inside `_set_refresh_cookie` as `not settings.DEBUG`. This is deliberate; see `troubleshooting/008-refresh-cookie-secure-flag-bug.md` for why putting it in the config dict produced the wrong value in dev.

## Tests

`accounts/tests/test_auth.py` — 19 tests, all green.

Run: `python manage.py test accounts -v 2`

Coverage:
- `UserMeTests` (3): unauthed 401, authed payload shape, superuser permissions short-circuit
- `LoginTests` (7): valid creds, refresh cookie set with right flags, wrong password, unknown user, inactive user, missing fields, login user payload matches `/users/me/`
- `RefreshTests` (4): valid cookie, rotation invalidates old refresh, no cookie, invalid cookie clears itself
- `LogoutTests` (5): unauthed 401, returns 205 + clears cookie, blacklists in DB, post-logout refresh fails, idempotent without cookie

## Things that went wrong

(Each has a full troubleshooting doc; this is the index.)

- Postgres not running on a fresh terminal session — `006`
- Virtualenv not activated on a fresh terminal session — `007`
- Self-referential URL include in app `urls.py` — `008` (caught at code review)
- Refresh cookie `Secure` flag set in dev because `base.py` evaluates before `development.py` — `009`
- Vite dev mode resolved dynamic imports as multiple module instances, producing two Zustand stores that didn't share state — `010`

The dynamic-import multi-instance one was the most painful — passed all curl tests, looked fine in code review, only manifested when `clear()` appeared not to clear state in the actual browser. Static imports fixed it.

## Frontend dev affordance: temporary window expose

During Checkpoint 7's interceptor testing we briefly attached `useAuthStore` to `window` from `App.tsx` so we could inspect store state from the browser console. That code was removed in Checkpoint 8. If you need it again for a future debug session, the pattern is:

```typescript
import { useAuthStore } from "@/stores/authStore"
;(window as unknown as { useAuthStore: typeof useAuthStore }).useAuthStore = useAuthStore
```

Keep it in a marker block tagged `TEMPORARY` so it's obvious to remove.
