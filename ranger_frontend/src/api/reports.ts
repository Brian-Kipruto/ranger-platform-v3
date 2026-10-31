// ─── RANGER V3 START: 16-report-download ───
/**
 * Compliance report API (F16 / 7c). Tenancy, permission and file integrity
 * are enforced server-side; nothing here is a security boundary.
 */
import axios from "axios"
import { api } from "./client"
import type { Mission } from "../types/mission.types"
import type { Report, ReportFileKind } from "../types/report.types"
import type { Paginated } from "../types/satellite.types"

/** The org's reports, newest first. One page of 1000 (DRF's cap); `truncated`
 *  says so if there are more, so a count is never mistaken for a total. */
export async function listReports(): Promise<{ items: Report[]; count: number; truncated: boolean }> {
  const { data } = await api.get<Paginated<Report>>("/reports/", { params: { limit: 1000 } })
  return { items: data.results, count: data.count, truncated: data.count > data.results.length }
}

/** COMPLETED missions only: the server refuses anything else (409). */
export async function listReportableMissions(): Promise<Mission[]> {
  const { data } = await api.get<Paginated<Mission>>("/missions/", { params: { limit: 1000 } })
  return data.results.filter((m) => m.status === "COMPLETED")
}

/** Synchronous: resolves when the PDF exists. 403 without
 *  reports.generate_report, 404 for another org's mission, 409 if not COMPLETED. */
export async function generateReport(missionId: number): Promise<Report> {
  const { data } = await api.post<Report>("/reports/", { mission: missionId })
  return data
}

async function sha256Hex(buf: ArrayBuffer): Promise<string | null> {
  // crypto.subtle exists only in secure contexts (https, localhost). On a
  // plain-http LAN address it is undefined; the server has already verified
  // the bytes, so the client check is skipped rather than failing the save.
  if (!globalThis.crypto?.subtle) return null
  const digest = await crypto.subtle.digest("SHA-256", buf)
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("")
}

/** With responseType "arraybuffer" the server's JSON error arrives as bytes:
 *  decode it so the integrity / missing-file message reaches the user. */
function downloadErrorText(err: unknown): string {
  if (!axios.isAxiosError(err)) return String(err)
  const status = err.response?.status
  const raw = err.response?.data
  if (raw instanceof ArrayBuffer) {
    try {
      const body = JSON.parse(new TextDecoder().decode(raw)) as { detail?: string }
      if (body.detail) return `${status}: ${body.detail}`
    } catch {
      /* not JSON: fall through */
    }
  }
  return `${status ?? "network"}: ${err.message}`
}

/**
 * Download through the api instance (JWT attached) and save. The bytes are
 * hashed in the browser and compared with the hash recorded at generation;
 * a mismatch is thrown, never saved. Returns whether the browser verified.
 */
export async function downloadReportFile(report: Report, kind: ReportFileKind): Promise<{ verified: boolean }> {
  let response
  try {
    response = await api.get<ArrayBuffer>(`/reports/${report.id}/${kind}/`, {
      responseType: "arraybuffer",
      headers: { "Cache-Control": "no-cache" },
    })
  } catch (err) {
    throw new Error(downloadErrorText(err), { cause: err })
  }
  const expected = kind === "pdf" ? report.pdf_sha256 : report.csv_sha256
  const actual = await sha256Hex(response.data)
  if (actual !== null && actual !== expected) {
    throw new Error(`Downloaded ${kind.toUpperCase()} does not match its recorded hash. Not saved.`)
  }
  const disposition = String(response.headers["content-disposition"] ?? "")
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `report-${report.id}.${kind}`
  const blob = new Blob([response.data], { type: kind === "pdf" ? "application/pdf" : "text/csv" })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
  return { verified: actual !== null }
}
// ─── RANGER V3 END: 16-report-download ───
