// ─── RANGER V3 START: axios client ───
import axios from "axios"

export const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
  // Required for the refresh cookie. Without this, the browser doesn't
  // send the ranger_refresh cookie on /api/auth/token/refresh/ or /logout/,
  // and login can't set the cookie either. Vite dev proxy makes the
  // request same-origin, so this is "send cookies on same-origin requests."
  withCredentials: true,
})

// ─── Request interceptor: attach access token ───────────────────────
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("ranger_access_token")
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ─── Response interceptor: silent refresh + retry on 401 ────────────
//
// On 401, attempt to refresh the access token via the httpOnly refresh
// cookie, then retry the original request transparently. Callers never
// see the 401 unless refresh itself fails.
//
// Single-flight: if a refresh is already in flight, concurrent 401s wait
// on the same promise rather than triggering parallel refreshes. Without
// this, N simultaneous expired-token requests would queue N refresh calls,
// and rotation+blacklist would fail all but one.
//
// Allowlist: requests to login, refresh, and logout themselves are NOT
// intercepted — a 401 from login means wrong password, a 401 from refresh
// means the cookie is dead, neither should trigger another refresh.
//
// _retry flag: prevents infinite loops if refresh succeeds but the retried
// original request still 401s for some other reason.
//
// _skipAuthRefresh flag: set on a per-request basis to opt out of the
// interceptor entirely. Used by authStore.hydrate() so it can manage the
// refresh flow itself without the interceptor racing against it.

import type { AxiosError, InternalAxiosRequestConfig } from "axios"
import { useAuthStore } from "../stores/authStore"
import { refresh as apiRefresh } from "./auth"

interface RetryConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
  _skipAuthRefresh?: boolean
}

// Endpoints whose 401s should NOT trigger a refresh attempt.
const AUTH_URLS = ["/auth/token/", "/auth/token/refresh/", "/auth/logout/"]

const isAuthUrl = (url?: string): boolean => {
  if (!url) return false
  return AUTH_URLS.some((authUrl) => url.includes(authUrl))
}

// Module-level single-flight: only one refresh request can be in flight
// at a time. Concurrent 401s await this same promise.
let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  // Static imports at the top of this file create a circular dependency
  // (client → authStore → auth → client). It's safe because both imports
  // are only USED inside functions that run after all modules have loaded.
  // Earlier we used dynamic imports to avoid the cycle; that introduced a
  // worse bug — Vite dev mode resolves dynamic imports as separate module
  // instances, producing two Zustand stores that didn't share state.
  const { access } = await apiRefresh()
  useAuthStore.getState().setAccessToken(access)
  return access
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryConfig | undefined

    // No request config (network error before send), no 401, already retried,
    // explicitly opted out, or hitting an auth URL: pass through.
    if (
      !originalRequest ||
      error.response?.status !== 401 ||
      originalRequest._retry ||
      originalRequest._skipAuthRefresh ||
      isAuthUrl(originalRequest.url)
    ) {
      return Promise.reject(error)
    }

    originalRequest._retry = true

    try {
      // Single-flight: start a refresh OR await the in-flight one.
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          // Clear the promise when done so the next 401 can trigger a fresh
          // refresh. .finally runs whether refresh succeeded or threw.
          refreshPromise = null
        })
      }
      const newAccess = await refreshPromise

      // Retry the original request with the new access token.
      originalRequest.headers.Authorization = `Bearer ${newAccess}`
      return api(originalRequest)
    } catch (refreshError) {
      // Refresh failed — session is dead. Clear local state. The caller
      // sees the original 401 (which is the truth: they're not authenticated).
      useAuthStore.getState().clear()
      return Promise.reject(error)
    }
  }
)
// ─── RANGER V3 END: axios client ───
