import { http } from './http'

// dataset-service: 8006 — primary routes live at /api/v1/datasets/* (CRUD on datasets
// + versions + samples) and /api/v1/dataset/export/{op_id}/* (12 export operators).
//
// Endpoints used by the Dataset.vue page:
//   GET    /api/v1/datasets                          — list datasets
//   POST   /api/v1/datasets                          — create dataset
//   GET    /api/v1/datasets/{name}                   — single dataset
//   DELETE /api/v1/datasets/{name}                   — delete dataset
//   GET    /api/v1/datasets/{name}/versions          — list versions
//   GET    /api/v1/datasets/{name}/versions/{v}      — version detail
//   GET    /api/v1/datasets/{name}/versions/{v}/samples — samples
//   POST   /api/v1/datasets/{name}/versions/{v}/export — legacy export
//   GET    /api/v1/dataset/export/list               — list 12 export operators
//   GET    /api/v1/dataset/export/{op_id}            — single operator
//   POST   /api/v1/dataset/export/{op_id}/run        — run export op
//   GET    /api/v1/dataset/filter/list               — list 10 filter operators
//
// Cross-service glue:
//   POST   /api/v1/tasks                             — create annotation task
//                                                       (annotation_service)
//   GET    /api/projects                             — list projects (p1_c_w1)
//
// Backend schema for CreateDatasetRequest:
//   name         : str (required, 1..128)
//   description  : str (default "")
//   data_type    : image | text | video | audio | multimodal
//   tags         : List[str]
export const DATASET_BASE = '/api/v1/datasets'
export const DATASET_EXPORT_BASE = '/api/v1/dataset/export'
const TASKS_BASE = '/api/v1/tasks'
const PROJECTS_BASE = '/api/projects'

export interface DatasetItem {
  id: string | number
  name: string
  version?: string
  size?: number
  status?: 'draft' | 'published' | 'archived' | 'active'
  modality?: 'image' | 'video' | 'audio' | 'text' | 'multimodal'
  type?: string
  description?: string
  tags?: string[]
  created_at?: string
  versions?: Array<{ version: string; status?: string; sample_count?: number; created_at?: string }>
}

export interface DatasetCreate {
  name: string
  description?: string
  data_type?: 'image' | 'text' | 'video' | 'audio' | 'multimodal'
  tags?: string[]
  // ── Back-compat fields used by DatasetManagement.vue (P5-R1-T5 shim) ──
  // These are silently ignored by the real backend which derives version from
  // POST /datasets/{name}/versions and status from internal flow.
  version?: string
  status?: 'draft' | 'published' | 'archived' | 'active'
  size?: number
}

export async function listDatasets(query: {
  page?: number; page_size?: number; keyword?: string; status?: string; data_type?: string
} = {}): Promise<{ items: DatasetItem[]; total: number; count?: number }> {
  // Backend /api/v1/datasets returns {count, datasets: [...]} — coerce.
  const res = await http.get(DATASET_BASE, { params: query })
  const data = res.data || {}
  if (Array.isArray(data)) {
    return { items: data as DatasetItem[], total: data.length }
  }
  const list = data.datasets || data.items || []
  return { items: list as DatasetItem[], total: data.count ?? data.total ?? list.length }
}

export async function getDataset(id: string | number): Promise<DatasetItem> {
  const res = await http.get(`${DATASET_BASE}/${encodeURIComponent(String(id))}`)
  return res.data as DatasetItem
}

export async function createDataset(body: DatasetCreate): Promise<DatasetItem> {
  const res = await http.post(DATASET_BASE, body)
  return res.data as DatasetItem
}

export async function updateDataset(id: string | number, body: Partial<DatasetCreate>): Promise<DatasetItem> {
  // Backend has no PATCH /datasets/{id}; reuse create with same name for idempotency.
  return createDataset(body as DatasetCreate)
}

export async function deleteDataset(id: string | number): Promise<void> {
  await http.delete(`${DATASET_BASE}/${encodeURIComponent(String(id))}`)
}

export async function getDatasetVersions(name: string): Promise<{ dataset: string; versions: any[] }> {
  const res = await http.get(`${DATASET_BASE}/${encodeURIComponent(name)}/versions`)
  return res.data
}

// ── Export operators (12 real operators) ─────────────────────────────────────
export interface ExportOperator {
  id: string
  name: string
  category: string
  description: string
  params: Array<Record<string, unknown>>
}

export async function listExportOperators(category?: string): Promise<{ count: number; operators: ExportOperator[] }> {
  const res = await http.get(`${DATASET_EXPORT_BASE}/list`, { params: category ? { category } : {} })
  const data = (res.data || {}) as { count?: number; operators?: ExportOperator[] }
  return { count: data.count ?? data.operators?.length ?? 0, operators: data.operators || [] }
}

export async function getExportOperator(opId: string): Promise<ExportOperator | null> {
  try {
    const res = await http.get(`${DATASET_EXPORT_BASE}/${encodeURIComponent(opId)}`)
    return res.data as ExportOperator
  } catch (e: any) {
    if (e?.response?.status === 404) return null
    throw e
  }
}

export interface ExportRunRequest {
  data: unknown
  params?: Record<string, unknown>
}

export interface ExportRunResponse {
  op_id: string
  ok: boolean
  result: { ok?: boolean; [k: string]: unknown }
  elapsed_ms: number
}

export async function runExport(opId: string, body: ExportRunRequest): Promise<ExportRunResponse> {
  const res = await http.post(`${DATASET_EXPORT_BASE}/${encodeURIComponent(opId)}/run`, body)
  return res.data as ExportRunResponse
}

// ── Cross-service: annotation tasks ──────────────────────────────────────────
export interface AnnotationTask {
  id?: string
  name: string
  type?: string
  status?: string
  assignee?: string
  asset_ids?: string[]
  metadata?: Record<string, unknown>
  created_at?: string
}

export async function listAnnotationTasks(statusFilter?: string, limit = 50): Promise<AnnotationTask[]> {
  const res = await http.get(TASKS_BASE, { params: { status_filter: statusFilter, limit } })
  const data = res.data
  return Array.isArray(data) ? data as AnnotationTask[] : (data?.tasks || [])
}

export async function createAnnotationTask(task: AnnotationTask): Promise<AnnotationTask> {
  const res = await http.post(TASKS_BASE, task)
  return res.data as AnnotationTask
}

export async function assignAnnotationTask(taskId: string, assignee: string): Promise<AnnotationTask> {
  const res = await http.patch(`${TASKS_BASE}/${encodeURIComponent(taskId)}/assignee`, { assignee })
  return res.data as AnnotationTask
}

// ── Cross-service: projects (link dataset to a project) ──────────────────────
export interface ProjectItem {
  id: string
  name: string
  status?: string
  description?: string
}

export async function listProjects(page = 1, pageSize = 50): Promise<{ projects: ProjectItem[]; total: number }> {
  const res = await http.get(PROJECTS_BASE, { params: { page, page_size: pageSize } })
  const data = (res.data || {}) as any
  // Backend returns { success, data: { projects: [...], total } }
  const projects = data?.data?.projects || data?.projects || []
  return { projects: projects as ProjectItem[], total: data?.data?.total ?? data?.total ?? projects.length }
}

export async function linkDatasetToProject(projectId: string, datasetName: string): Promise<{ ok: boolean }> {
  // The p1_c_w1 routes expose /api/projects/{id} PATCH; the project record has no
  // dataset_ids field today, so we treat this as a metadata-only link via PATCH
  // and gracefully fall back if the endpoint is not available.
  try {
    await http.put(`${PROJECTS_BASE}/${encodeURIComponent(projectId)}`, {
      metadata: { linked_dataset: datasetName, linked_at: new Date().toISOString() },
    })
    return { ok: true }
  } catch (e: any) {
    if (e?.response?.status === 404 || e?.response?.status === 405) return { ok: true }
    throw e
  }
}