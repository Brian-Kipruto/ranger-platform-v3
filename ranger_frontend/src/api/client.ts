// ─── RANGER V3 START: axios client ───
import axios from "axios"

export const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
})

// JWT interceptor — attaches access token from local storage
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("ranger_access_token")
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Refresh logic stub — wired up properly in the auth feature
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // TODO: implement refresh flow when auth feature ships
      console.warn("401 received — auth refresh not yet implemented")
    }
    return Promise.reject(error)
  }
)
// ─── RANGER V3 END: axios client ───