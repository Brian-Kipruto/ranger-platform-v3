// ─── RANGER V3 START: NavRail ───
/**
 * NavRail — the Field Console left navigation. Collapsible (232px ↔ 64px),
 * grouped nav scoped by role, footer user block + collapse toggle.
 *
 * Nav data comes from navConfig (role-keyed). Active state is derived from
 * the current route. Items route via React Router; `built: false` items still
 * route (to the StubPage) so the nav looks complete.
 */
import { NavLink, useLocation } from "react-router-dom"
import { cn } from "@/lib/utils"
import { MonoLabel } from "./MonoLabel"
import type { NavGroup } from "@/config/navConfig"

interface NavRailProps {
  groups: NavGroup[]
  collapsed: boolean
  onToggle: () => void
  user: { name: string; role: string; initials: string }
}

export function NavRail({ groups, collapsed, onToggle, user }: NavRailProps) {
  const { pathname } = useLocation()
  const open = !collapsed

  return (
    <div
      className="flex-none bg-surface-2 border-r border-border flex flex-col transition-[width] duration-200"
      style={{ width: collapsed ? 64 : 232 }}
    >
      {/* header — logo */}
      <div className="h-[54px] flex-none flex items-center gap-[11px] px-[14px] border-b border-border">
        <div
          className="w-[30px] h-[30px] flex-none rounded-md flex items-center justify-center font-bold text-[15px]"
          style={{
            border: "1.5px solid var(--accent)",
            color: "var(--accent)",
            boxShadow: "inset 0 0 12px var(--accent-weak)",
          }}
        >
          R
        </div>
        {open ? (
          <div className="overflow-hidden">
            <div className="font-semibold text-[13px] tracking-[0.04em] text-fg leading-none">RANGER</div>
            <MonoLabel size="xs" tone="faint" tracking="0.16em" className="mt-[3px] block">
              V3 FIELD CONSOLE
            </MonoLabel>
          </div>
        ) : null}
      </div>

      {/* nav groups */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden px-[10px] py-3">
        {groups.map((grp) => (
          <div key={grp.label} className="mb-4">
            {open ? (
              <div className="font-mono text-[9px] tracking-[0.18em] text-[#454c59] px-2 pb-2 uppercase">
                {grp.label}
              </div>
            ) : null}
            {grp.items.map((it) => {
              const active = pathname === it.path
              return (
                <NavLink
                  key={it.id}
                  to={it.path}
                  title={it.label}
                  className={cn(
                    "w-full flex items-center gap-[11px] cursor-pointer mb-[3px] rounded-[7px] text-left no-underline transition-colors",
                    collapsed ? "p-2 justify-center" : "px-[9px] py-2 justify-start",
                    active ? "text-fg" : "text-fg-muted hover:bg-surface-panel"
                  )}
                  style={
                    active
                      ? { background: "var(--accent-weak)", boxShadow: "inset 2px 0 0 var(--accent)" }
                      : undefined
                  }
                >
                  <span
                    className="font-mono text-[10px] font-semibold w-[26px] h-[22px] flex-none flex items-center justify-center rounded-[5px] tracking-[0.02em]"
                    style={{
                      border: active ? "1px solid color-mix(in srgb, var(--accent) 50%, transparent)" : "1px solid #232932",
                      background: active ? "var(--accent-weak)" : "var(--color-surface-3)",
                      color: active ? "var(--accent-hover)" : "var(--color-fg-dim)",
                    }}
                  >
                    {it.code}
                  </span>
                  {open ? (
                    <span className="flex-1 text-left text-[13px] tracking-[0.01em]">{it.label}</span>
                  ) : null}
                  {open && it.badge ? (
                    <span className="font-mono text-[9px] min-w-[16px] h-4 px-1 rounded-lg bg-alert text-white flex items-center justify-center">
                      {it.badge}
                    </span>
                  ) : null}
                </NavLink>
              )
            })}
          </div>
        ))}
      </div>

      {/* footer — user + collapse toggle */}
      <div className="flex-none border-t border-border p-[10px]">
        <div className="flex items-center gap-2.5 px-2 py-[7px] rounded-md">
          <div
            className="w-[30px] h-[30px] flex-none rounded-md flex items-center justify-center text-[12px] font-semibold text-white"
            style={{ background: "linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 55%, #000))" }}
          >
            {user.initials}
          </div>
          {open ? (
            <div className="overflow-hidden flex-1">
              <div className="text-[12px] text-fg-soft leading-[1.1] whitespace-nowrap overflow-hidden text-ellipsis">
                {user.name}
              </div>
              <MonoLabel size="xs" tone="faint" tracking="0.04em" className="mt-[2px] block whitespace-nowrap normal-case">
                {user.role}
              </MonoLabel>
            </div>
          ) : null}
        </div>
        <button
          onClick={onToggle}
          className="mt-1.5 w-full cursor-pointer bg-transparent border border-border rounded-md py-[7px] text-fg-faint font-mono text-[10px] tracking-[0.12em] hover:text-fg-muted hover:border-border-strong-2 transition-colors"
        >
          {collapsed ? "»" : "« COLLAPSE"}
        </button>
      </div>
    </div>
  )
}
// ─── RANGER V3 END: NavRail ───