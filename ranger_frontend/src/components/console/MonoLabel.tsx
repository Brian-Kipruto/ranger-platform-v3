// ─── RANGER V3 START: MonoLabel primitive ───
/**
 * MonoLabel — uppercase, wide-tracked IBM Plex Mono text. The console's
 * label/telemetry-chrome typeface. Extracted from the Field Console mockup,
 * where every label, status string, and metric caption uses this treatment.
 */
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

type Size = "xs" | "sm" | "md"
type Tone = "faint" | "dim" | "muted" | "soft" | "fg" | "accent" | "ok" | "warn" | "alert" | "info"

const sizeMap: Record<Size, string> = {
  xs: "text-[9px]",
  sm: "text-[10px]",
  md: "text-[11px]",
}

const toneMap: Record<Tone, string> = {
  faint: "text-fg-faint",
  dim: "text-fg-dim",
  muted: "text-fg-muted",
  soft: "text-fg-soft",
  fg: "text-fg",
  accent: "text-[var(--accent)]",
  ok: "text-ok",
  warn: "text-warn",
  alert: "text-alert",
  info: "text-info",
}

interface MonoLabelProps {
  children: ReactNode
  size?: Size
  tone?: Tone
  /** letter-spacing; defaults to the console's 0.14em wide tracking */
  tracking?: string
  className?: string
}

export function MonoLabel({
  children,
  size = "sm",
  tone = "dim",
  tracking = "0.14em",
  className,
}: MonoLabelProps) {
  return (
    <span
      className={cn("font-mono uppercase", sizeMap[size], toneMap[tone], className)}
      style={{ letterSpacing: tracking }}
    >
      {children}
    </span>
  )
}
// ─── RANGER V3 END: MonoLabel primitive ───