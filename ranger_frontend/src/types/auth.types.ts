// ─── RANGER V3 START: auth types ───
/**
 * TypeScript mirrors of the backend auth payloads.
 *
 * These types are the contract between Django and React. If the backend
 * UserMeSerializer changes, this file changes. The auth feature tests
 * lock down the backend shape so drift between the two has to be deliberate.
 */

export interface Organization {
  id: number
  name: string
  slug: string
  theme_color: string
  /** Absolute URL to the org's logo, or null if none uploaded. */
  logo_url: string | null
}

export interface Group {
  id: number
  name: string
}

export interface User {
  id: number
  username: string
  email: string
  organization: Organization | null
  groups: Group[]
  /**
   * Permission codes in "app_label.codename" format
   * (e.g. "missions.launch_mission"). Empty array for superusers — use
   * is_superuser to short-circuit permission checks.
   */
  permissions: string[]
  is_superuser: boolean
  is_staff: boolean
  mfa_enabled: boolean
  phone: string
}

// ─── Request / response shapes ─────────────────────────────────────

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  /** JWT access token. Lives ~15min. Frontend stores in memory + localStorage mirror. */
  access: string
  user: User
}

export interface RefreshResponse {
  /** New access token. The refresh cookie is rotated server-side automatically. */
  access: string
}

// ─── RANGER V3 END: auth types ───