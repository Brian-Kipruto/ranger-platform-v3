// ─── RANGER V3 START: auth store (stub) ───
import { create } from "zustand"

interface User {
  id: number
  username: string
  organization: string | null
}

interface AuthState {
  user: User | null
  accessToken: string | null
  isAuthenticated: boolean
  setTokens: (access: string, refresh: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: null,
  isAuthenticated: false,
  setTokens: (access, _refresh) => {
    localStorage.setItem("ranger_access_token", access)
    set({ accessToken: access, isAuthenticated: true })
  },
  logout: () => {
    localStorage.removeItem("ranger_access_token")
    set({ user: null, accessToken: null, isAuthenticated: false })
  },
}))
// ─── RANGER V3 END: auth store (stub) ───