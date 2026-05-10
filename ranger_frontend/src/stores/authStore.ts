// ─── RANGER V3 START: auth store ───
/**
 * Auth store — the source of truth for "who is the current user."
 *
 * State shape:
 *  - user: full payload from /api/users/me/, or null if logged out
 *  - accessToken: JWT, kept in memory + mirrored to localStorage
 *  - isAuthenticated: convenience boolean derived from user presence
 *  - isHydrating: true on initial app mount while we attempt silent refresh
 *
 * Token storage rationale:
 *  - Refresh token: httpOnly SameSite=Strict cookie, set by backend on login.
 *    JS cannot read it. XSS cannot exfiltrate it. Sent automatically by the
 *    browser on /api/auth/* requests only.
 *  - Access token: in-memory primary, localStorage mirror. Mirror exists so
 *    a hard page refresh doesn't briefly flash the login page while we wait
 *    for the silent refresh. The mirror is XSS-readable but the token
 *    expires in 15 minutes and an attacker can't refresh it without the
 *    httpOnly cookie.
 *
 * Hydrate flow (called once on App mount):
 *  1. Read access token from localStorage (if any)
 *  2. Call /api/users/me/ with that token
 *  3a. 200 → set user, isAuthenticated true, isHydrating false. Done.
 *  3b. 401 → access token is dead. Try /api/auth/token/refresh/ (uses cookie).
 *  4a. Refresh succeeds → got new access. Retry /api/users/me/. Set state.
 *  4b. Refresh fails → no valid session. Clear everything, isHydrating false.
 */
import { create } from "zustand"
import { login as apiLogin, logout as apiLogout, refresh as apiRefresh, getMe } from "../api/auth"
import type { User } from "../types/auth.types"

const ACCESS_TOKEN_KEY = "ranger_access_token"

interface AuthState {
  user: User | null
  accessToken: string | null
  isAuthenticated: boolean
  isHydrating: boolean
}

interface AuthActions {
  /** Submit credentials. Throws on failure (caller shows the error). */
  login: (username: string, password: string) => Promise<void>
  /** Server-side blacklist + clear local state. Never throws. */
  logout: () => Promise<void>
  /** Called once on app mount. Attempts silent re-auth from refresh cookie. */
  hydrate: () => Promise<void>
  /**
   * Internal: set tokens after a successful login or refresh.
   * Exposed so the axios interceptor (Checkpoint 7) can update the access
   * token after a silent refresh without going through login.
   */
  setAccessToken: (token: string) => void
  /** Internal: clear everything. Used by logout and refresh-failure paths. */
  clear: () => void
  /** Returns true if the user has the named permission, or is superuser. */
  hasPermission: (code: string) => boolean
}

type AuthStore = AuthState & AuthActions

export const useAuthStore = create<AuthStore>((set, get) => ({
  // ─── State ───────────────────────────────────────────────────────
  user: null,
  // Initialise from localStorage so the FIRST API call in hydrate() can
  // try this token before falling through to refresh. If it's stale,
  // hydrate() will detect the 401 and refresh.
  accessToken: localStorage.getItem(ACCESS_TOKEN_KEY),
  isAuthenticated: false,
  isHydrating: true,

  // ─── Actions ─────────────────────────────────────────────────────
  setAccessToken: (token) => {
    localStorage.setItem(ACCESS_TOKEN_KEY, token)
    set({ accessToken: token })
  },

  clear: () => {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    set({
      user: null,
      accessToken: null,
      isAuthenticated: false,
    })
  },

  login: async (username, password) => {
    // Throws on bad credentials. We deliberately don't catch here — the
    // login form handles user-facing errors, the store stays clean.
    const { access, user } = await apiLogin({ username, password })
    localStorage.setItem(ACCESS_TOKEN_KEY, access)
    set({
      user,
      accessToken: access,
      isAuthenticated: true,
    })
  },

  logout: async () => {
    // Try to blacklist server-side. Don't block local logout on network
    // failure — user clicked logout, user gets logged out, full stop.
    try {
      await apiLogout()
    } catch {
      // Server unreachable, already logged out, etc. Local state still clears.
    }
    get().clear()
  },

hydrate: async () => {
    // hydrate() drives its own refresh flow. We pass skipRefresh:true on
    // both getMe calls so the response interceptor doesn't try to ALSO
    // refresh in parallel — that would double-fire refresh requests and
    // race against the rotation/blacklist logic.
    try {
      if (get().accessToken) {
        try {
          const user = await getMe({ skipRefresh: true })
          set({ user, isAuthenticated: true, isHydrating: false })
          return
        } catch {
          // Access token expired or invalid. Fall through to refresh.
        }
      }

      // Either no access token, or it failed. Try refresh cookie.
      const { access } = await apiRefresh()
      localStorage.setItem(ACCESS_TOKEN_KEY, access)
      set({ accessToken: access })

      // We have a fresh access token; fetch the user. Still skipRefresh
      // because if THIS call 401s, something is very wrong and we want
      // to fail loudly rather than loop.
      const user = await getMe({ skipRefresh: true })
      set({ user, isAuthenticated: true, isHydrating: false })
    } catch {
      // No valid session. Clear any stale state and finish hydrating.
      get().clear()
      set({ isHydrating: false })
    }
  },

  hasPermission: (code) => {
    const { user } = get()
    if (!user) return false
    if (user.is_superuser) return true
    return user.permissions.includes(code)
  },
}))

// ─── RANGER V3 END: auth store ───