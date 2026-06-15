// ─── RANGER V3 START: dashboard placeholder ───
/**
 * Placeholder dashboard. Real implementation lands in a later feature
 * (Phase 2 of the V3 build plan). For now this exists so the auth feature
 * has a "logged-in landing page" to redirect to and a logout button to
 * exercise the logout flow from real UI.
 */
import { useAuthStore } from "@/stores/authStore"
import { useNavigate } from "react-router-dom"
import { Link } from "react-router-dom"

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate("/login", { replace: true })
  }

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-2xl mx-auto">
        <header className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <button
            onClick={handleLogout}
            className="px-4 py-2 text-sm border rounded hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            Log out
          </button>
        </header>

        <section className="space-y-2 text-sm">
          <p>
            Logged in as <strong>{user?.username}</strong>
            {user?.email ? ` (${user.email})` : null}
          </p>
          {user?.organization ? (
            <p>
              Organization: <strong>{user.organization.name}</strong>
            </p>
            
          ) : null}
          <p><Link to="/data" className="underline">→ Data Explorer</Link></p>
          <p className="text-gray-500">
            Real dashboard widgets ship in a later feature.
          </p>
        </section>
      </div>
    </div>
  )
}
// ─── RANGER V3 END: dashboard placeholder ───