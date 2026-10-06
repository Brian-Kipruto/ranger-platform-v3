// ─── RANGER V3 START: StatusDot primitive ───
/**
 * StatusDot — small semantic status dot, optionally pulsing. Used for
 * online/OK indicators (login green dot, top-bar LIVE dot, fleet rows).
 */
import { cn } from "@/lib/utils"

type Status = "ok" | "warn" | "alert" | "info" | "accent" | "sim" // sim: 09-live-console

const colorVar: Record<Status, string> = {
  ok: "var(--color-ok)",
  warn: "var(--color-warn)",
  alert: "var(--color-alert)",
  info: "var(--color-info)",
  accent: "var(--accent)",
  sim: "#7a828f", // 09-live-console: = SOURCE_META.simulated.color
}

interface StatusDotProps {
  status?: Status
  /** diameter in px (default 7) */
  size?: number
  pulse?: boolean
  className?: string
}

export function StatusDot({ status = "ok", size = 7, pulse = false, className }: StatusDotProps) {
  return (
    <span
      className={cn("inline-block rounded-full", pulse && "animate-rng-pulse", className)}
      style={{ width: size, height: size, background: colorVar[status] }}
    />
  )
}
// ─── RANGER V3 END: StatusDot primitive ───