// ─── RANGER V3 START: nav config ───
/**
 * Field Console navigation config.
 *
 * Nav is grouped (OPERATIONS / ANALYSIS / ...) and scoped by role, mirroring
 * the mockup's navGroups. Today "role" is derived from the user's Django
 * Group name (Operator / Client / Community), which the seed_demo command
 * sets up. There is no real permission gating yet — that's the ADR 0007
 * authorization-debt thread.
 *
 * WHY THIS SHAPE: when real RBAC lands, the ONLY thing that changes is
 * navGroupsForRole() — swap "key off group name" for "filter items by
 * user.permissions / hasPermission()". The NavRail component, the NavItem
 * shape, routing, and rendering all stay. So this is the cheap-to-evolve
 * structure, not throwaway.
 *
 * `built: false` items route to a stub placeholder (the screen isn't
 * implemented yet) but are fully clickable, so the nav looks complete.
 */

export type ConsoleRole = "operator" | "client" | "community"

export interface NavItem {
  /** stable id, also the mockup's short code source */
  id: string
  /** 2-3 char mono code chip (DSH, MSN, DAT, ...) */
  code: string
  label: string
  /** route path this item navigates to */
  path: string
  /** false → routes to the "not built yet" stub */
  built: boolean
  /** optional badge count (e.g. alerts) */
  badge?: number
}

export interface NavGroup {
  label: string
  items: NavItem[]
}

// Maps a Django Group name (from user.groups[].name) to a console role.
// Superusers and anyone in the Operator group get the full operator nav.
export function roleFromGroups(groupNames: string[], isSuperuser: boolean): ConsoleRole {
  if (isSuperuser || groupNames.includes("Operator")) return "operator"
  if (groupNames.includes("Client")) return "client"
  if (groupNames.includes("Community")) return "community"
  // Default to the most restrictive view if no known group.
  return "community"
}

// The three screens that actually exist today.
const BUILT_PATHS = new Set(["/dashboard", "/data", "/visualizations"])

// Item factory — `path` decides built vs stub automatically.
function item(id: string, code: string, label: string, path: string, badge?: number): NavItem {
  return { id, code, label, path, built: BUILT_PATHS.has(path), badge }
}

// Full operator/superuser nav (also the base the others trim from).
const OPERATOR_GROUPS: NavGroup[] = [
  {
    label: "OPERATIONS",
    items: [
      item("dashboard", "DSH", "Dashboard", "/dashboard"),
      item("mission", "MSN", "Mission Control", "/mission"),
      item("workspace", "VIZ", "Workspace", "/workspace"),
      item("fleet", "FLT", "Fleet", "/fleet"),
    ],
  },
  {
    label: "ANALYSIS",
    items: [
      item("data", "DAT", "Data Explorer", "/data"),
      item("visualizations", "CHT", "Visualizations", "/visualizations"),
      item("alerts", "ALT", "Alerts", "/alerts", 1),
      item("reports", "RPT", "Reports", "/reports"),
    ],
  },
  {
    label: "INTELLIGENCE",
    items: [item("ai", "AI", "AI Assistant", "/ai")],
  },
  {
    label: "PLATFORM",
    items: [
      item("admin", "ADM", "Admin Console", "/admin"),
      item("community", "PUB", "Community", "/community"),
    ],
  },
]

const CLIENT_GROUPS: NavGroup[] = [
  {
    label: "OPERATIONS",
    items: [
      item("dashboard", "DSH", "Dashboard", "/dashboard"),
      item("mission", "MSN", "Mission Control", "/mission"),
      item("workspace", "VIZ", "Workspace", "/workspace"),
      item("fleet", "FLT", "Fleet", "/fleet"),
    ],
  },
  {
    label: "ANALYSIS",
    items: [
      item("data", "DAT", "Data Explorer", "/data"),
      item("visualizations", "CHT", "Visualizations", "/visualizations"),
      item("alerts", "ALT", "Alerts", "/alerts", 1),
      item("reports", "RPT", "Reports", "/reports"),
    ],
  },
  {
    label: "INTELLIGENCE",
    items: [item("ai", "AI", "AI Assistant", "/ai")],
  },
  {
    label: "ACCOUNT",
    items: [item("admin", "ADM", "Billing & Team", "/admin")],
  },
]

const COMMUNITY_GROUPS: NavGroup[] = [
  {
    label: "PUBLIC",
    items: [
      item("community", "MAP", "Public Map", "/community"),
      item("data", "DAT", "Open Data", "/data"),
      item("reports", "RPT", "Public Reports", "/reports"),
    ],
  },
]

export function navGroupsForRole(role: ConsoleRole): NavGroup[] {
  switch (role) {
    case "operator":
      return OPERATOR_GROUPS
    case "client":
      return CLIENT_GROUPS
    case "community":
      return COMMUNITY_GROUPS
  }
}

// View metadata for the TopBar (code / label / sub), keyed by route path.
export const VIEW_META: Record<string, { code: string; label: string; sub: string }> = {
  "/dashboard": { code: "DSH", label: "Mission Dashboard", sub: "// fleet overview" },
  "/data": { code: "DAT", label: "Data Explorer", sub: "// sensor logs" },
  "/visualizations": { code: "CHT", label: "Visualizations", sub: "// time-series" },
  "/mission": { code: "MSN", label: "Mission Control", sub: "// live operations" },
  "/workspace": { code: "VIZ", label: "Visualization Workspace", sub: "// ROS 2 panels" },
  "/fleet": { code: "FLT", label: "Fleet", sub: "// units & health" },
  "/alerts": { code: "ALT", label: "Alerts", sub: "// threshold monitor" },
  "/reports": { code: "RPT", label: "Compliance Reports", sub: "// generated PDFs" },
  "/ai": { code: "AI", label: "R.A.N.G.E.R. Assistant", sub: "// Gemma 2 on-device" },
  "/admin": { code: "ADM", label: "Admin Console", sub: "// orgs · billing" },
  "/community": { code: "PUB", label: "Community Portal", sub: "// public data" },
}
// ─── RANGER V3 END: nav config ───