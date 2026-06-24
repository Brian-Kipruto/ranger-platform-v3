// ─── RANGER V3 START: CornerTicks primitive ───
/**
 * CornerTicks — four L-bracket framing marks, absolutely positioned in the
 * corners of the nearest positioned ancestor. A console-chrome detail from
 * the mockup's login screen.
 */
import { cn } from "@/lib/utils"

interface CornerTicksProps {
  /** tick arm length in px (default 24) */
  size?: number
  /** inset from the edge in px (default 22) */
  inset?: number
  className?: string
}

export function CornerTicks({ size = 24, inset = 22, className }: CornerTicksProps) {
  const base = "absolute border-border-strong-2"
  const dim = { width: size, height: size }
  return (
    <div className={cn("pointer-events-none", className)} aria-hidden="true">
      <div className={cn(base, "border-t border-l")} style={{ top: inset, left: inset, ...dim }} />
      <div className={cn(base, "border-t border-r")} style={{ top: inset, right: inset, ...dim }} />
      <div className={cn(base, "border-b border-l")} style={{ bottom: inset, left: inset, ...dim }} />
      <div className={cn(base, "border-b border-r")} style={{ bottom: inset, right: inset, ...dim }} />
    </div>
  )
}
// ─── RANGER V3 END: CornerTicks primitive ───