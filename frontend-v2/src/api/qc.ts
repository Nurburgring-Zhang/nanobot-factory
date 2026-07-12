import { http } from './http'

// /api/v1/qc/* — Internal QC endpoints (backend/imdf/api/qc_routes.py)

const BASE = '/api/v1/qc'

export type QCMode = 'full' | 'sample' | 'aql' | 'stratified'
export type QCResult = 'passed' | 'failed'
export type IssueType = 'label' | 'geometry' | 'completeness' | 'format'
export type Severity = 'critical' | 'major' | 'minor'

export interface QCIssue {
  id: string
  qc_id: string
  asset_id: string
  type: IssueType
  severity: Severity
  description: string
  suggested_action: string
}

export interface QCRecord {
  id: string
  dataset_id: string
  project_id: string
  requirement_id: string
  pack_id: string
  mode: QCMode
  sample_rate: number
  sample_size: number
  total_assets: number
  result: QCResult
  issue_count: number
  issues?: QCIssue[]
  issue_summary?: { by_severity: Record<string, number>; by_type: Record<string, number> }
  qcer_id: string
  notes: string
  created_at: string
  updated_at: string
}

export interface QCStats {
  qc_id: string
  dataset_id: string
  mode: QCMode
  result: QCResult
  sample_size: number
  total_assets: number
  issue_count: number
  defect_rate: number
  pass_rate: number
  by_severity: Record<Severity, number>
  by_type: Record<IssueType, number>
  qcer_id: string
  created_at: string
}

export interface QCPageResp {
  items: QCRecord[]
  total: number
  page: number
  page_size: number
}

export interface QCEnvelope<T> {
  success: boolean
  data: T
  error: string | null
  message: string
}

export async function listQCRecords(params: {
  dataset_id?: string
  project_id?: string
  result?: QCResult
  page?: number
  page_size?: number
} = {}): Promise<QCPageResp> {
  return (await http.get(`${BASE}/records`, { params })).data
}

export async function runFullCheck(body: {
  dataset_id: string
  qcer_id?: string
  project_id?: string
  requirement_id?: string
  pack_id?: string
  severity_bias?: number
  notes?: string
}): Promise<QCEnvelope<QCRecord>> {
  return (await http.post(`${BASE}/full`, body)).data
}

export async function runSampleCheck(body: {
  dataset_id: string
  sample_rate?: number
  qcer_id?: string
  project_id?: string
  requirement_id?: string
  pack_id?: string
  severity_bias?: number
  notes?: string
  seed?: number
}): Promise<QCEnvelope<QCRecord>> {
  return (await http.post(`${BASE}/sample`, body)).data
}

export async function runAQLCheck(body: {
  dataset_id: string
  aql_level?: number
  lot_size?: number
  qcer_id?: string
  project_id?: string
  requirement_id?: string
  pack_id?: string
  severity_bias?: number
  notes?: string
  seed?: number
}): Promise<QCEnvelope<QCRecord>> {
  return (await http.post(`${BASE}/aql`, body)).data
}

export async function runStratifiedCheck(body: {
  dataset_id: string
  sample_size?: number
  strata?: Record<string, Record<string, number>>
  qcer_id?: string
  project_id?: string
  requirement_id?: string
  pack_id?: string
  severity_bias?: number
  notes?: string
  seed?: number
}): Promise<QCEnvelope<QCRecord>> {
  return (await http.post(`${BASE}/stratified`, body)).data
}

export async function getQCRecord(qcId: string): Promise<QCEnvelope<QCRecord>> {
  return (await http.get(`${BASE}/${qcId}`)).data
}

export async function getQCStats(qcId: string): Promise<QCEnvelope<QCStats>> {
  return (await http.get(`${BASE}/${qcId}/stats`)).data
}

export async function exportQCReport(
  qcId: string,
  format: 'json' | 'csv' | 'pdf' = 'json'
): Promise<QCEnvelope<{ file_path: string; format: string; qc_id: string }>> {
  return (await http.get(`${BASE}/${qcId}/report`, { params: { format } })).data
}

export async function rerunQC(
  qcId: string,
  severity_bias = 0
): Promise<QCEnvelope<QCRecord>> {
  return (await http.post(`${BASE}/${qcId}/rerun`, { severity_bias })).data
}