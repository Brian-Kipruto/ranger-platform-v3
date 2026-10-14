// ─── RANGER V3 START: 13-reading-source ───
/**
 * Provenance over positions AND readings (F13, ADR-0020). Pure: no React.
 *
 * Until F13 one label per row covered everything. Now the row's `source` is
 * the position's, and each reading carries its own. A set of LIVE positions
 * with SIMULATED radiation used to produce no banner at all — the over-claim
 * this module exists to make impossible.
 */
import {
  MEASURED_SOURCES,
  SOURCE_META,
  type DataSource,
  type MapProvenanceSummary,
  type ReadingKind,
} from "@/types/dataLog.types"

/** Most to least authoritative: a stable order for every breakdown. */
export const SOURCE_ORDER: readonly DataSource[] = ["live", "reported", "modelled", "simulated"]

const READING_LABEL: Record<ReadingKind, string> = {
  radiation: "RADIATION",
  air_quality: "PM",
  imu_baro: "IMU",
}

type Counts = Partial<Record<DataSource, number>>

function sum(c: Counts): number {
  return Object.values(c).reduce((a, b) => a + (b ?? 0), 0)
}

function nonMeasured(c: Counts): number {
  return (Object.keys(c) as DataSource[])
    .filter((t) => !MEASURED_SOURCES.includes(t))
    .reduce((a, t) => a + (c[t] ?? 0), 0)
}

/** "SIM 774" / "LIVE 10 · SIM 774" — counted from the values themselves. */
export function sourceBreakdown(sources: (DataSource | null | undefined)[]): string {
  const c: Counts = {}
  for (const s of sources) if (s) c[s] = (c[s] ?? 0) + 1
  return SOURCE_ORDER.filter((t) => c[t])
    .map((t) => `${(SOURCE_META[t] ?? SOURCE_META.simulated).short} ${(c[t] ?? 0).toLocaleString()}`)
    .join(" · ")
}

/** Distinct sources in stable order (for chips). */
export function distinctSources(sources: (DataSource | null | undefined)[]): DataSource[] {
  const seen = new Set(sources.filter((s): s is DataSource => !!s))
  return SOURCE_ORDER.filter((t) => seen.has(t))
}

/** Should a reading's cell show its own chip? Only when it is NOT what the
 *  position chip already says: one chip per row stays readable, and an
 *  unlabelled reading cell always means "same as the position". */
export function readingDiffers(reading: DataSource | null, position: DataSource): boolean {
  return reading !== null && reading !== position
}

export interface ProvenanceBanner {
  color: string
  headline: string
  note: string
}

/**
 * Banner over the FULL filtered set (uncapped server summary).
 *   - nothing non-measured anywhere          -> null (the default is honest)
 *   - positions AND every reading one tier T -> "ALL N POINTS ... T"
 *   - otherwise                              -> MIXED, every non-measured
 *     part counted: points and each reading kind separately
 */
export function provenanceBanner(prov: MapProvenanceSummary | undefined): ProvenanceBanner | null {
  if (!prov || prov.total === 0) return null
  const readings = prov.readings ?? {}
  const kinds = (Object.keys(READING_LABEL) as ReadingKind[]).filter((k) => sum(readings[k] ?? {}) > 0)

  const parts: string[] = []
  const posNon = nonMeasured(prov.by_source)
  if (posNon > 0) parts.push(`POINTS ${posNon.toLocaleString()}/${prov.total.toLocaleString()}`)
  for (const k of kinds) {
    const c = readings[k] ?? {}
    const n = nonMeasured(c)
    if (n > 0) parts.push(`${READING_LABEL[k]} ${n.toLocaleString()}/${sum(c).toLocaleString()}`)
  }
  if (parts.length === 0) return null

  // The citation: one note -> quote it; several -> never pick one.
  const note =
    prov.notes.length === 1
      ? prov.notes[0]
      : prov.notes.length > 1
        ? `${prov.notes.length}${prov.notes_truncated ? "+" : ""} distinct citations ` +
          `across this set — hover a chip for the per-row provenance.`
        : ""

  const tiers = new Set<DataSource>(Object.keys(prov.by_source) as DataSource[])
  for (const k of kinds) for (const t of Object.keys(readings[k] ?? {})) tiers.add(t as DataSource)
  if (tiers.size === 1) {
    const only = [...tiers][0]
    if (!MEASURED_SOURCES.includes(only)) {
      const meta = SOURCE_META[only] ?? SOURCE_META.simulated
      return {
        color: meta.color,
        // "AND THEIR READINGS" only when reading counts were seen: a banner
        // must not assert what it did not check.
        headline:
          `ALL ${prov.total.toLocaleString()} POINTS ${kinds.length > 0 ? "AND THEIR READINGS " : ""}ARE ` +
          `${meta.label.toUpperCase()} — NOT MEASUREMENTS`,
        note,
      }
    }
  }
  return {
    color: SOURCE_META.modelled.color,
    headline: `MIXED PROVENANCE — NOT MEASUREMENTS: ${parts.join(" · ")}`,
    note: note || "Chips mark every value whose source differs from its position's.",
  }
}
// ─── RANGER V3 END: 13-reading-source ───
