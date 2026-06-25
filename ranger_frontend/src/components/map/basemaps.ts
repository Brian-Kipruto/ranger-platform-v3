// ─── RANGER V3 START: field map basemaps ───
/**
 * Basemap registry for the shared <FieldMap>.
 *
 * Three MapTiler styles, all covered by the single VITE_MAPTILER_KEY:
 *   - vector → streets-v2   (the Data Explorer's existing default)
 *   - sat    → satellite
 *   - topo   → outdoor-v2   (topo / outdoor)
 *
 * WHY A REGISTRY: F07 turns the mockup's dead SAT/VECTOR toggle into three real
 * modes. Switching calls map.setStyle(styleUrl(mode)). Because setStyle wipes
 * all sources/layers, <FieldMap> re-installs its data layers on the `styledata`
 * event — see FieldMap.installLayers(). This file only owns the URLs.
 *
 * KEY-AWARE: if VITE_MAPTILER_KEY is unset, styleUrl() returns null and the
 * map renders the "MAP UNAVAILABLE" fallback (same as F05/F06). The key's plan
 * is assumed to include satellite + outdoor (confirmed: these worked in V2).
 * If a given style 404s at runtime, MapLibre fires an `error` event — FieldMap
 * surfaces it without crashing, leaving the previous style in place.
 */

export type BasemapMode = "vector" | "sat" | "topo"

const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY as string | undefined

/** MapTiler style slugs per mode. Centralized so a slug change is one edit. */
const STYLE_SLUG: Record<BasemapMode, string> = {
  vector: "streets-v2",
  sat: "satellite",
  topo: "outdoor-v2",
}

/** Ordered list for rendering the toggle (matches mockup order: SAT/VECTOR + TOPO). */
export const BASEMAP_ORDER: BasemapMode[] = ["sat", "vector", "topo"]

/** Short uppercase labels for the toggle chips. */
export const BASEMAP_LABEL: Record<BasemapMode, string> = {
  vector: "VECTOR",
  sat: "SAT",
  topo: "TOPO",
}

/** True when a MapTiler key is present (so the map can render at all). */
export const MAP_KEY_PRESENT = !!MAPTILER_KEY

/**
 * Full style.json URL for a mode, or null when no key is configured.
 * All three modes share the same key; if the key lacks a style's plan tier,
 * the request 404s at runtime (handled by FieldMap's error listener), it does
 * not throw here.
 */
export function styleUrl(mode: BasemapMode): string | null {
  if (!MAPTILER_KEY) return null
  return `https://api.maptiler.com/maps/${STYLE_SLUG[mode]}/style.json?key=${MAPTILER_KEY}`
}

export const DEFAULT_BASEMAP: BasemapMode = "vector"
// ─── RANGER V3 END: field map basemaps ───