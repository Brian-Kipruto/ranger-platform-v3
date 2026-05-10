// ─── RANGER V3 START: auth api ───
/**
 * Typed wrappers for the four auth endpoints.
 *
 * Why wrappers and not direct axios calls everywhere?
 *  - Single source of truth for endpoint URLs and shapes
 *  - Easy to mock in tests (mock this module, not axios)
 *  - Type errors at the call site if the backend contract changes
 *
 * All four functions throw on non-2xx (axios default). The auth store
 * is responsible for catching and translating those into UI state.
 */
import { api } from "./client"
import type {
  LoginRequest,
  LoginResponse,
  RefreshResponse,
  User,
} from "../types/auth.types"

/** POST /api/auth/token/ — returns {access, user}, sets refresh cookie. */
export async function login(credentials: LoginRequest): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>("/auth/token/", credentials)
  return data
}

/**
 * POST /api/auth/token/refresh/ — returns new access, rotates refresh cookie.
 * Reads the refresh token from the cookie automatically; no body needed.
 */
export async function refresh(): Promise<RefreshResponse> {
  const { data } = await api.post<RefreshResponse>("/auth/token/refresh/")
  return data
}

/**
 * POST /api/auth/logout/ — server blacklists the refresh, clears cookie.
 * Caller must clear in-memory access token separately.
 */
export async function logout(): Promise<void> {
  await api.post("/auth/logout/")
}

/**
 * GET /api/users/me/ — current user payload.
 *
 * `skipRefresh` opts out of the response interceptor's silent-refresh
 * retry logic. Used by authStore.hydrate(), which manages refresh
 * explicitly and doesn't want the interceptor racing against it.
 */
export async function getMe(opts?: { skipRefresh?: boolean }): Promise<User> {
  const { data } = await api.get<User>("/users/me/", {
    // The flag is read by the response interceptor in client.ts.
    ...(opts?.skipRefresh ? { _skipAuthRefresh: true } : {}),
  } as Record<string, unknown>)
  return data
}

// ─── RANGER V3 END: auth api ───