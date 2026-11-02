// ─── RANGER V3 START: app root ───
import { useEffect } from "react"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import LoginPage from "@/pages/LoginPage"
import DashboardPage from "@/pages/DashboardPage"
import DataExplorerPage from "@/pages/DataExplorerPage"
import VisualizationsPage from "@/pages/VisualizationsPage"
import SatellitePage from "@/pages/SatellitePage"
import MissionControlPage from "@/pages/MissionControlPage"
// ─── RANGER V3 START: 16-report-download ───
import ReportsPage from "@/pages/ReportsPage"
// ─── RANGER V3 END: 16-report-download ───
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
        {/* ─── RANGER V3 START: 18-polish ─── */}
        {/* No public landing: the Phase-1 scaffold page is retired. "/" goes
            to the console; ProtectedRoute bounces the unauthenticated to /login. */}
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        {/* ─── RANGER V3 END: 18-polish ─── */}

        {/* Auth */}
        <Route path="/login" element={<LoginPage />} />

        {/* ─── RANGER V3 START: shelled protected routes ─── */}
        {/*
          All authenticated screens render inside the Field Console shell
          (NavRail + TopBar + content frame). The shell is a layout route:
          ProtectedRoute guards auth, AppShell provides the frame, and each
          child renders into the shell's <Outlet />.

          18-polish: only built screens are routed — dashboard, mission, data,
          visualizations, satellite, reports. Unbuilt screens are not reachable
          by URL either; StubPage stays in the code, unrouted.
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
          <Route path="/satellite" element={<SatellitePage />} />
          <Route path="/mission" element={<MissionControlPage />} />
          {/* ─── RANGER V3 START: 16-report-download ─── */}
          <Route path="/reports" element={<ReportsPage />} />
          {/* ─── RANGER V3 END: 16-report-download ─── */}
        </Route>
        {/* ─── RANGER V3 END: shelled protected routes ─── */}

        {/* Unknown route (incl. the retired stub paths) → console */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
export default App
// ─── RANGER V3 END: app root ───