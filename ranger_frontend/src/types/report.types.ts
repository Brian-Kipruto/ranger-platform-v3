// ─── RANGER V3 START: 16-report-download ───
/** Compliance reports (F16 / 7c). Mirrors reports/serializers.py.
 *  File paths are never sent: downloads go through /reports/<id>/<kind>/. */
import type { DataSource } from "./dataLog.types"

export interface Report {
  id: number
  mission: number
  mission_name: string
  robot_id_str: string
  generated_at: string
  generated_by: string | null
  format_version: string
  row_count: number
  weakest_source: DataSource
  pdf_sha256: string
  csv_sha256: string
  has_csv: boolean
  registry_version: string | null
}

export type ReportFileKind = "pdf" | "csv"
// ─── RANGER V3 END: 16-report-download ───
