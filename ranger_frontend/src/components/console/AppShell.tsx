// ─── RANGER V3 START: AppShell ───
/**
 * AppShell — the Field Console application frame. Wraps all authenticated
 * pages: NavRail (left) + TopBar (top) + scrollable content frame.
 *
 * Responsibilities:
 *  - Activates the org-driven --accent via useAccentTheme().
 *  - Derives the console role from the user's Django groups (roleFromGroups).
 *  - Builds the role-scoped nav (navGroupsForRole).
 *  - Resolves the TopBar's view code/label/sub from the active route.
 *  - Renders the page (Outlet) inside the console content frame.
 *
 * Rail collapse state lives here (session-local; not persisted this feature).
 */
import { useMemo, useState } from "react"
import { Outlet, useLocation } from "react-router-dom"
import { useAuthStore } from "@/stores/authStore"
import { useAccentTheme } from "@/hooks/useAccentTheme"
import { NavRail } from "./NavRail"
import { TopBar } from "./TopBar"
import {
  roleFromGroups,
  navGroupsForRole,
  VIEW_META,
  type ConsoleRole,
} from "@/config/navConfig"

// Two-letter initials from a username/email. operator@byteanza.com → OP.
function initialsFrom(username: string): string {
  const local = username.split("@")[0]
  const parts = local.split(/[.\-_]/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return local.slice(0, 2).toUpperCase()
}

const ROLE_LABEL: Record<ConsoleRole, string> = {
  operator: "BYTEANZA · OPERATOR",
  client: "CLIENT · ADMIN",
  community: "COMMUNITY · READ-ONLY",
}

export default function AppShell() {
  useAccentTheme()

  const user = useAuthStore((s) => s.user)
  const { pathname } = useLocation()
  const [collapsed, setCollapsed] = useState(false)

  const groupNames = useMemo(() => (user?.groups ?? []).map((g) => g.name), [user])
  const role: ConsoleRole = useMemo(
    () => roleFromGroups(groupNames, !!user?.is_superuser),
    [groupNames, user]
  )
  const navGroups = useMemo(() => navGroupsForRole(role), [role])

  const meta = VIEW_META[pathname] ?? { code: "—", label: "RANGER", sub: "" }

  const railUser = {
    name: user?.organization?.name ? `${user.username}` : user?.username ?? "—",
    role: user?.organization?.name
      ? `${user.organization.name.toUpperCase()} · ${role.toUpperCase()}`
      : ROLE_LABEL[role],
    initials: user ? initialsFrom(user.username) : "··",
  }

  return (
    <div className="fixed inset-0 flex bg-surface-0">
      <NavRail groups={navGroups} collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} user={railUser} />

      <div className="flex-1 flex flex-col min-w-0">
        <TopBar viewCode={meta.code} viewLabel={meta.label} viewSub={meta.sub} role={role} />
        <div
          className="flex-1 overflow-y-auto"
          style={{
            background:
              "radial-gradient(900px 500px at 70% -5%, var(--accent-faint), transparent 60%), var(--color-surface-1)",
          }}
        >
          <Outlet />
        </div>
      </div>
    </div>
  )
}
// ─── RANGER V3 END: AppShell ───