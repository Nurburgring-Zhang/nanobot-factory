import { getPage, getOne, createOne, updateOne, deleteOne, http, type Page, type PageQuery } from './http'

// workflow-service: 8009
export interface WorkflowItem {
  id: string | number
  name: string
  status: 'draft' | 'active' | 'paused' | 'archived'
  steps?: number
  description?: string
  created_at?: string
  updated_at?: string
  last_run_at?: string
}

export interface WorkflowCreate {
  name: string
  status?: WorkflowItem['status']
  steps?: number
  description?: string
}

export interface WorkflowTemplate {
  id: string
  name: string
  description: string
  kind: 'system' | 'user'
}

export interface WorkflowRunResult {
  run_id: string
  workflow_id: string | number
  started_at: string
  status: 'queued' | 'running' | 'completed' | 'failed'
}

const BASE = '/api/v1/workflows'

export async function listWorkflows(query: PageQuery = {}): Promise<Page<WorkflowItem>> {
  return getPage<WorkflowItem>(BASE, query)
}
export async function getWorkflow(id: string | number): Promise<WorkflowItem> {
  return getOne(`${BASE}/${id}`)
}
export async function createWorkflow(body: WorkflowCreate): Promise<WorkflowItem> {
  return createOne(BASE, body)
}
export async function updateWorkflow(id: string | number, body: Partial<WorkflowCreate>): Promise<WorkflowItem> {
  return updateOne(`${BASE}/${id}`, body)
}
export async function deleteWorkflow(id: string | number): Promise<void> {
  return deleteOne(`${BASE}/${id}`)
}

// ── P22-P2-cleanup: lifecycle actions (run / pause / resume) ───────────
// These hit dedicated sub-resources of the workflow service. The
// service-side implementation lives in backend/imdf/api/workflow_routes.py;
// each route returns a WorkflowRunResult (run) or the updated WorkflowItem
// (pause/resume). Errors propagate as rejected Promises so the caller can
// use the same `try/catch` pattern as the other CRUD methods.
export async function runWorkflow(id: string | number): Promise<WorkflowRunResult> {
  const r = await http.post<WorkflowRunResult>(`${BASE}/${id}/run`)
  return r.data
}
export async function pauseWorkflow(id: string | number): Promise<WorkflowItem> {
  const r = await http.post<WorkflowItem>(`${BASE}/${id}/pause`)
  return r.data
}
export async function resumeWorkflow(id: string | number): Promise<WorkflowItem> {
  const r = await http.post<WorkflowItem>(`${BASE}/${id}/resume`)
  return r.data
}

// ── P22-P2-cleanup: template library ────────────────────────────────
// The workflow service ships with a catalogue of system templates and
// any user-saved templates. Returns the union; UI filters by ``kind``.
export async function listWorkflowTemplates(): Promise<WorkflowTemplate[]> {
  const r = await http.get<WorkflowTemplate[]>(`${BASE}/templates`)
  return r.data ?? []
}
