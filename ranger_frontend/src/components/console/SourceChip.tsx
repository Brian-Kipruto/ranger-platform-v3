// ─── RANGER V3 START: source chip ───
/**
 * SourceChip — the provenance tier of a single reading, as a coloured chip.
 *
 * Exists because the Data Explorer showed 12,081 MODELLED Marsabit points
 * with real instrument names (KNRA-PGIS-2-1), real mission names, and real
 * dose values, and nothing on screen said they were modelled. Everything on
 * screen said "measurement", so that is what a viewer read.
 *
 * The `title` carries provenance_note, so the derivation ("Modelled from
 * KNRA ... Table 3.1, n=1819, mean=140 nSv/h") is one hover away everywhere
 * the chip appears — the chip names the tier, the tooltip cites the source.
 *
 * Colours come from SOURCE_META (dataLog.types.ts), NOT from CSS vars: the
 * same palette drives MapLibre paint expressions, which cannot read vars.
 */
import { SOURCE_META, type DataSource } from "@/types/dataLog.types"

export interface SourceChipProps {
  source: DataSource
  /** provenance_note — the citation or derivation. Shown on hover. */
  note?: string
  /** Full label ("Modelled") instead of the 3-4 char code ("MOD"). */
  showLabel?: boolean
  className?: string
}

export function SourceChip({
  source,
  note,
  showLabel = false,
  className,
}: SourceChipProps) {
  // Defensive: an unrecognised tier degrades to the least authoritative
  // entry rather than throwing on an undefined lookup.
  const meta = SOURCE_META[source] ?? SOURCE_META.simulated
  return (
    <span
      title={note ? `${meta.label} — ${note}` : meta.label}
      className={
        "inline-flex items-center gap-1.5 font-mono text-[9px] tracking-[0.08em] " +
        "px-1.5 py-0.5 rounded border whitespace-nowrap align-middle " +
        (className ?? "")
      }
      style={{
        color: meta.color,
        borderColor: `${meta.color}55`,
        background: `${meta.color}15`,
      }}
    >
      <span
        className="w-[5px] h-[5px] rounded-full flex-none"
        style={{ background: meta.color }}
      />
      {showLabel ? meta.label : meta.short}
    </span>
  )
}
// ─── RANGER V3 END: source chip ───
