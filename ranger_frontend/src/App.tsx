// ─── RANGER V3 START: app root ───
import { useEffect } from "react"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import HomePage from "@/pages/HomePage"
import LoginPage from "@/pages/LoginPage"
import DashboardPage from "@/pages/DashboardPage"
import DataExplorerPage from "@/pages/DataExplorerPage"
import VisualizationsPage from "@/pages/VisualizationsPage"
import ProtectedRoute from "@/components/ProtectedRoute"
import { useAuthStore } from "@/stores/authStore"

function App() {
  const hydrate = useAuthStore((s) => s.hydrate)

  // Run silent re-auth once on mount. If a refresh cookie is present,
  // this populates the store and the user lands on /dashboard without
  // a login prompt. If not, isHydrating flips to false and ProtectedRoute
  // bounces them to /login.
  useEffect(() => {
    hydrate()
  }, [hydrate])

  return (
    <BrowserRouter>
      <Routes>
        {/* Public landing — keep the Phase 1 page accessible */}
        <Route path="/" element={<HomePage />} />

        {/* Auth */}
        <Route path="/login" element={<LoginPage />} />

        {/* Protected */}
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        {/* ─── RANGER V3 START: data explorer route ─── */}
        <Route
          path="/data"
          element={
            <ProtectedRoute>
              <DataExplorerPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/visualizations"
          element={
            <ProtectedRoute>
              <VisualizationsPage />
            </ProtectedRoute>
          }
        />
        {/* ─── RANGER V3 END: data explorer route ─── */}

        {/* Unknown route → home */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
export default App
// ─── RANGER V3 END: app root ───