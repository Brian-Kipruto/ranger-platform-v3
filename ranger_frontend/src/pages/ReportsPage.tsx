// ─── RANGER V3 START: 16-report-download ───
/**
 * Compliance Reports (F16 / 7c). Generate a report from a COMPLETED mission
 * and download any report the org has, as PDF or as the embedded CSV.
 *
 * The page is a view: tenancy, the generate permission and file integrity
 * are all enforced by the server. Generate is hidden without
 * reports.generate_report only so a reader is not offered a 403.
 */
import { useEffect, useMemo, useState } from "react"
import { MonoLabel } from "@/components/console/MonoLabel"
import { Panel } from "@/components/console/Panel"
import { SourceChip } from "@/components/console/SourceChip"
import { useAuthStore } from "@/stores/authStore"
import { errorLines } from "@/api/missions"
import {
  downloadReportFile,
  generateReport,
  listReportableMissions,
  listReports,
} from "@/api/reports"
import type { Mission } from "@/types/mission.types"
import type { Report, ReportFileKind } from "@/types/report.types"

type RowNote = { tone: "ok" | "alert"; text: string }

function shortHash(h: string) {
  return `${h.slice(0, 8)}…${h.slice(-4)}`
}

function when(iso: string) {
  return new Date(iso).toISOString().replace("T", " ").slice(0, 19) + " UTC"
}

export default function ReportsPage() {
  const canGenerate = useAuthStore((s) => !!s.user && s.hasPermission("reports.generate_report"))

  const [reports, setReports] = useState<Report[]>([])
  const [count, setCount] = useState(0)
  const [truncated, setTruncated] = useState(false)
  const [missions, setMissions] = useState<Mission[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [missionId, setMissionId] = useState<number | "">("")
  const [generating, setGenerating] = useState(false)
  const [genErrors, setGenErrors] = useState<string[]>([])
  const [busy, setBusy] = useState<string | null>(null)       // "<id>:<kind>"
  const [notes, setNotes] = useState<Record<number, RowNote>>({})

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [r, m] = await Promise.all([listReports(), listReportableMissions()])
        if (cancelled) return
        setReports(r.items)
        setCount(r.count)
        setTruncated(r.truncated)
        setMissions(m)
      } catch (err) {
        if (!cancelled) setLoadError(errorLines(err).join(" · "))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const reportCounts = useMemo(() => {
    const c = new Map<number, number>()
    for (const r of reports) c.set(r.mission, (c.get(r.mission) ?? 0) + 1)
    return c
  }, [reports])

  async function onGenerate() {
    if (missionId === "") return
    setGenerating(true)
    setGenErrors([])
    try {
      const report = await generateReport(missionId)
      setReports((prev) => [report, ...prev])
      setCount((c) => c + 1)
      setNotes((n) => ({ ...n, [report.id]: { tone: "ok", text: "GENERATED" } }))
    } catch (err) {
      setGenErrors(errorLines(err))
    } finally {
      setGenerating(false)
    }
  }

  async function onDownload(report: Report, kind: ReportFileKind) {
    setBusy(`${report.id}:${kind}`)
    try {
      const { verified } = await downloadReportFile(report, kind)
      setNotes((n) => ({
        ...n,
        [report.id]: {
          tone: "ok",
          text: verified
            ? `${kind.toUpperCase()} SAVED · SHA-256 VERIFIED IN BROWSER`
            : `${kind.toUpperCase()} SAVED · VERIFIED BY SERVER (BROWSER HASH UNAVAILABLE ON HTTP)`,
        },
      }))
    } catch (err) {
      setNotes((n) => ({ ...n, [report.id]: { tone: "alert", text: String((err as Error).message ?? err) } }))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="p-[18px] space-y-3">
      <MonoLabel size="xs" tone="dim" tracking="0.12em">
        {loading
          ? "LOADING REPORTS…"
          : loadError
            ? loadError.toUpperCase()
            : `${count} REPORT${count === 1 ? "" : "S"} · ${missions.length} COMPLETED MISSION${missions.length === 1 ? "" : "S"}`}
      </MonoLabel>

      {truncated ? (
        <div className="px-3 py-2 rounded-md border font-mono text-[10px]"
             style={{ color: "#f5a623", borderColor: "#f5a62355", background: "#f5a62312" }}>
          ⚠ SHOWING {reports.length} OF {count} REPORTS.
        </div>
      ) : null}

      {canGenerate ? (
        <Panel title="GENERATE REPORT">
          <div className="p-[13px] flex flex-wrap items-center gap-3">
            <select
              className="bg-surface-3 border border-border rounded-md px-2 py-1.5 font-mono text-[11px] text-fg min-w-[280px]"
              value={missionId}
              onChange={(e) => setMissionId(e.target.value === "" ? "" : Number(e.target.value))}
              disabled={generating || missions.length === 0}
            >
              <option value="">
                {missions.length === 0 ? "NO COMPLETED MISSIONS" : "SELECT A COMPLETED MISSION"}
              </option>
              {missions.map((m) => (
                <option key={m.id} value={m.id}>
                  #{m.id} · {m.name} · {m.robot_id_str}
                  {reportCounts.get(m.id) ? ` · ${reportCounts.get(m.id)} report(s)` : ""}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={onGenerate}
              disabled={missionId === "" || generating}
              className="px-3 py-1.5 rounded-md border font-mono text-[10px] tracking-[0.1em] disabled:opacity-40"
              style={{ borderColor: "var(--accent)", color: "var(--accent)" }}
            >
              {generating ? "GENERATING…" : "GENERATE PDF"}
            </button>
            <MonoLabel size="xs" tone="faint">
              Each run creates a new report; existing reports are never changed.
            </MonoLabel>
          </div>
          {genErrors.length ? (
            <div className="px-[13px] pb-[13px] font-mono text-[10px] text-alert space-y-0.5">
              {genErrors.map((l, i) => <div key={i}>✕ {l}</div>)}
            </div>
          ) : null}
        </Panel>
      ) : null}

      <Panel title="REPORTS" right={<MonoLabel size="xs" tone="faint">NEWEST FIRST</MonoLabel>}>
        {reports.length === 0 && !loading ? (
          <div className="p-[13px] font-mono text-[10px] text-fg-dim">
            NO REPORTS YET{canGenerate ? " · GENERATE ONE FROM A COMPLETED MISSION ABOVE" : ""}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full font-mono text-[10.5px]">
              <thead>
                <tr className="text-fg-dim text-left border-b border-border">
                  <th className="px-3 py-2 font-normal">#</th>
                  <th className="px-3 py-2 font-normal">MISSION</th>
                  <th className="px-3 py-2 font-normal">WEAKEST</th>
                  <th className="px-3 py-2 font-normal">GENERATED</th>
                  <th className="px-3 py-2 font-normal text-right">ROWS</th>
                  <th className="px-3 py-2 font-normal">PDF SHA-256</th>
                  <th className="px-3 py-2 font-normal">DOWNLOAD</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r) => (
                  <tr key={r.id} className="border-b border-border/60 align-top">
                    <td className="px-3 py-2 text-fg-dim">{r.id}</td>
                    <td className="px-3 py-2">
                      <div className="text-fg">{r.mission_name}</div>
                      <div className="text-fg-faint">#{r.mission} · {r.robot_id_str}</div>
                    </td>
                    <td className="px-3 py-2">
                      <SourceChip source={r.weakest_source} showLabel />
                    </td>
                    <td className="px-3 py-2 text-fg-soft">
                      <div>{when(r.generated_at)}</div>
                      <div className="text-fg-faint">
                        {r.generated_by ?? "—"} · fmt {r.format_version}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right text-fg-soft">{r.row_count.toLocaleString()}</td>
                    <td className="px-3 py-2 text-fg-faint" title={r.pdf_sha256}>{shortHash(r.pdf_sha256)}</td>
                    <td className="px-3 py-2">
                      <div className="flex gap-2">
                        {(["pdf", "csv"] as const).map((kind) => (
                          <button
                            key={kind}
                            type="button"
                            onClick={() => onDownload(r, kind)}
                            disabled={busy !== null || (kind === "csv" && !r.has_csv)}
                            title={kind === "csv" && !r.has_csv ? "Generated before CSV download existed. Generate a new report." : undefined}
                            className="px-2 py-1 rounded border border-border text-fg-soft hover:text-fg disabled:opacity-35"
                          >
                            {busy === `${r.id}:${kind}` ? "…" : kind.toUpperCase()}
                          </button>
                        ))}
                      </div>
                      {notes[r.id] ? (
                        <div className={`mt-1 text-[9px] max-w-[340px] whitespace-normal break-words leading-[1.5] ${notes[r.id].tone === "ok" ? "text-ok" : "text-alert"}`}>
                          {notes[r.id].text}
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
// ─── RANGER V3 END: 16-report-download ───
