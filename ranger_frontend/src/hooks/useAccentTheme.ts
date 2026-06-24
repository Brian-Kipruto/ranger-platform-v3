// ─── RANGER V3 START: useAccentTheme ───
/**
 * useAccentTheme — drives the runtime --accent CSS variable from the
 * logged-in user's organization.theme_color.
 *
 * The mockup hardcodes violet (#7c6cff) everywhere. In the real app the
 * accent is tenant-themeable: ByteAnza renders teal (#0ea5e9), Magadi renders
 * amber, and a tenant with no color set falls back to the violet default
 * baked into index.css.
 *
 * Also derives --accent-hover. --accent-weak / --accent-faint are defined in
 * index.css via color-mix against --accent, so they follow automatically.
 *
 * On logout (user → null) the inline override is removed, so the stylesheet
 * fallback (violet) takes over again — which is what the login screen shows.
 */
import { useEffect } from "react"
import { useAuthStore } from "@/stores/authStore"

const FALLBACK_ACCENT = "#7c6cff"

// Lighten a hex color toward white for the hover token. Cheap, dependency-free.
function lighten(hex: string, amount = 0.18): string {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  if (!m) return hex
  const mix = (c: number) => Math.round(c + (255 - c) * amount)
  const r = mix(parseInt(m[1], 16))
  const g = mix(parseInt(m[2], 16))
  const b = mix(parseInt(m[3], 16))
  return `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`
}

export function useAccentTheme(): void {
  const themeColor = useAuthStore((s) => s.user?.organization?.theme_color)

  useEffect(() => {
    const root = document.documentElement
    if (themeColor) {
      root.style.setProperty("--accent", themeColor)
      root.style.setProperty("--accent-hover", lighten(themeColor))
    } else {
      // Logged out / no org → clear overrides, fall back to stylesheet default.
      root.style.removeProperty("--accent")
      root.style.removeProperty("--accent-hover")
    }
    return () => {
      // On unmount, clear so a stale accent doesn't bleed across sessions.
      root.style.removeProperty("--accent")
      root.style.removeProperty("--accent-hover")
    }
  }, [themeColor])
}

export { FALLBACK_ACCENT }
// ─── RANGER V3 END: useAccentTheme ───