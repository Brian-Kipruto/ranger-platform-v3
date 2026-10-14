// ─── RANGER V3 START: dashboard LiveTelemetry ───
/**
 * LiveTelemetry — the right-column "LIVE TELEMETRY" panel (mockup ~297-320):
 * four mini stat tiles (radiation / PM2.5 / pressure / temp), each with a value
 * and an inline SVG sparkline. Driven by the selected robot.
 *
 * F13: driven by the live feed (liveTelemetrySpecs). Each value carries its
 * reading's own SourceChip; "—" where there is no current value, never an
 * invented one. The component just renders TelemetrySpec[].
 */
import { Panel } from "@/components/console/Panel"
import { MonoLabel } from "@/components/console/MonoLabel"
import { SourceChip } from "@/components/console/SourceChip"
import type { TelemetrySpec } from "@/components/dashboard/liveTelemetrySpecs"

/** Map a numeric series to an SVG polyline points string over a w×h viewbox. */
function sparkPoints(series: number[], w = 100, h = 16): string {
  if (series.length < 2) return "" // 13: one point would divide by zero
  const min = Math.min(...series)
  const max = Math.max(...series)
  const rng = max - min || 1
  return series
    .map((v, i) => {
      const x = (i / (series.length - 1)) * w
      const y = h - ((v - min) / rng) * h
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(" ")
}

interface LiveTelemetryProps {
  selectedId: string
  telemetry: TelemetrySpec[]
}

export function LiveTelemetry({ selectedId, telemetry }: LiveTelemetryProps) {
  return (
    <Panel
      title="LIVE TELEMETRY"
      right={<MonoLabel size="xs" tone="accent">{selectedId}</MonoLabel>}
    >
      <div className="p-[13px] grid grid-cols-2 gap-[11px]">
        {telemetry.map((t) => (
          <div
            key={t.label}
            title={t.note}
            className="bg-surface-3 border border-border-soft rounded-md px-[11px] py-[10px]"
          >
            <div className="flex items-center justify-between gap-1">
              <MonoLabel size="xs" tone="dim" tracking="0.1em">{t.label}</MonoLabel>
              {t.source ? (
                <SourceChip source={t.source} />
              ) : (
                <span
                  className="w-[6px] h-[6px] rounded-full"
                  style={{ background: t.color }}
                />
              )}
            </div>
            <div className="mt-[7px] flex items-baseline gap-1">
              <span className="font-mono text-[19px] font-medium" style={{ color: t.color }}>
                {t.value}
              </span>
              <span className="font-mono text-[10px] text-fg-faint">{t.unit}</span>
            </div>
            <svg
              viewBox="0 0 100 16"
              preserveAspectRatio="none"
              className="mt-[6px] w-full h-4 block"
            >
              <polyline
                points={sparkPoints(t.series)}
                fill="none"
                stroke={t.color}
                strokeWidth={1}
                opacity={0.7}
              />
            </svg>
          </div>
        ))}
      </div>
    </Panel>
  )
}
// ─── RANGER V3 END: dashboard LiveTelemetry ───