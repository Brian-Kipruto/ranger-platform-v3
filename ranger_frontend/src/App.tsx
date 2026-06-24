// ─── RANGER V3 START: app root ───
import { useEffect } from "react"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import HomePage from "@/pages/HomePage"
import LoginPage from "@/pages/LoginPage"
import DashboardPage from "@/pages/DashboardPage"
import DataExplorerPage from "@/pages/DataExplorerPage"
import VisualizationsPage from "@/pages/VisualizationsPage"
import StubPage from "@/pages/StubPage"
import ProtectedRoute from "@/components/ProtectedRoute"
import AppShell from "@/components/console/AppShell"
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

        {/* ─── RANGER V3 START: shelled protected routes ─── */}
        {/*
          All authenticated screens render inside the Field Console shell
          (NavRail + TopBar + content frame). The shell is a layout route:
          ProtectedRoute guards auth, AppShell provides the frame, and each
          child renders into the shell's <Outlet />.

          Built screens: dashboard, data, visualizations.
          Stub screens (nav routes here, real feature later): mission,
          workspace, fleet, alerts, reports, ai, admin, community.
        */}
        <Route
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/data" element={<DataExplorerPage />} />
          <Route path="/visualizations" element={<VisualizationsPage />} />

          {/* unbuilt screens — clickable stubs */}
          <Route path="/mission" element={<StubPage />} />
          <Route path="/workspace" element={<StubPage />} />
          <Route path="/fleet" element={<StubPage />} />
          <Route path="/alerts" element={<StubPage />} />
          <Route path="/reports" element={<StubPage />} />
          <Route path="/ai" element={<StubPage />} />
          <Route path="/admin" element={<StubPage />} />
          <Route path="/community" element={<StubPage />} />
        </Route>
        {/* ─── RANGER V3 END: shelled protected routes ─── */}

        {/* Unknown route → home */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
export default App
// ─── RANGER V3 END: app root ───