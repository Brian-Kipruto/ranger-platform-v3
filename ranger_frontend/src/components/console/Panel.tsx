// ─── RANGER V3 START: Panel primitive ───
/**
 * Panel — the console's workhorse surface card. A bordered panel on the
 * --surface-panel background, with an optional mono-uppercase header bar.
 *
 * Variants:
 *  - default: header bar with title (left) + optional `right` slot
 *  - noHeader: just the bordered surface, caller supplies all chrome
 *    (used by the map panel, which has its own header row)
 */
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import { MonoLabel } from "./MonoLabel"

interface PanelProps {
  children: ReactNode
  /** header title — rendered as a MonoLabel. Omit (with noHeader) for bare panels. */
  title?: ReactNode
  /** right-aligned header slot (status, count, action button) */
  right?: ReactNode
  noHeader?: boolean
  /** surface token, default surface-panel */
  surface?: string
  className?: string
  /** className for the body wrapper */
  bodyClassName?: string
}

export function Panel({
  children,
  title,
  right,
  noHeader = false,
  surface = "bg-surface-panel",
  className,
  bodyClassName,
}: PanelProps) {
  return (
    <div className={cn(surface, "border border-border rounded-[10px] overflow-hidden", className)}>
      {!noHeader && (title || right) ? (
        <div className="flex items-center justify-between px-[13px] py-[11px] border-b border-border">
          {typeof title === "string" ? (
            <MonoLabel size="md" tone="soft" tracking="0.13em">
              {title}
            </MonoLabel>
          ) : (
            title
          )}
          {right ? <div className="flex items-center gap-2">{right}</div> : null}
        </div>
      ) : null}
      <div className={bodyClassName}>{children}</div>
    </div>
  )
}
// ─── RANGER V3 END: Panel primitive ───