import { http } from './http'

// Tasks = union of:
//   1. annotation_service tasks   → /api/v1/tasks          (DB-backed)
//   2. agent_service agent_tasks → /api/v1/agent_tasks    (in-memory store)
//   3. workflow_service runs     → /api/v1/workflows/runs (in-memory DAG runtime)
// The Tasks.vue page merges all three into one tabbed view so users see
// the full queue at a glance.

export type TaskStatus = 'open' | 'in_progress' | 'completed' | 'failed' | 'pending' | 'running' | 'cancelled'
export type TaskSource = 'annotation' | 'agent' | 'workflow'

export interface AnnotationTask {
  id: string
  name: string
  type: string
  status: string
  assignee?: string
  asset_ids: string[]
  metadata?: Record<string, unknown>
  created_at: string
}

export interface AgentTask {
  task_id: string
  agent_type: string
  status: string
  mode: string
  priority: number
  submitted_by?: string
  created_at: string
  started_at?: string
  finished_at?: string
  error?: string
}

export interface WorkflowRun {
  run_id: string
  workflow_id: string
  status: string
  trigger: string
  started_at: string
  finished_at?: string
  progress?: number
  error?: string
}

export interface UnifiedTask {
  [key: string]: unknown
  source: TaskSource
  id: string
  name: string
  type: string
  status: TaskStatus
  owner?: string
  created_at: string
  finished_at?: string
  raw: AnnotationTask | AgentTask | WorkflowRun
}

const ANNOTATION_BASE = '/api/v1/tasks'
const AGENT_BASE = '/api/v1/agent_tasks'
const WORKFLOW_BASE = '/api/v1/workflows/runs'

export async function listAnnotationTasks(params: { status_filter?: string; limit?: number } = {}): Promise<AnnotationTask[]> {
  return (await http.get(ANNOTATION_BASE, { params })).data
}

export async function listAgentTasks(params: { status?: string; agent_type?: string; limit?: number } = {}): Promise<{
  count: number
  tasks: AgentTask[]
}> {
  return (await http.get(AGENT_BASE, { params })).data
}

export async function listWorkflowRuns(params: { workflow_id?: string; limit?: number } = {}): Promise<{
  total: number
  items: WorkflowRun[]
}> {
  return (await http.get(WORKFLOW_BASE, { params })).data
}

export async function getAgentTaskStats(): Promise<Record<string, number>> {
  return (await http.get(`${AGENT_BASE}/stats`)).data
}

export async function cancelAgentTask(taskId: string): Promise<AgentTask> {
  return (await http.post(`${AGENT_BASE}/${taskId}/cancel`)).data
}

export async function retryAgentTask(taskId: string): Promise<AgentTask> {
  return (await http.post(`${AGENT_BASE}/${taskId}/retry`)).data
}

export async function cancelWorkflowRun(runId: string): Promise<{ success: boolean; run_id: string }> {
  return (await http.post(`${WORKFLOW_BASE}/${runId}/cancel`)).data
}

export async function createAnnotationTask(body: Partial<AnnotationTask>): Promise<{ success: boolean; id: string; name: string }> {
  return (await http.post(ANNOTATION_BASE, body)).data
}

/** Map diverse status strings into the 5-slot badge enum. */
export function normalizeStatus(s: string): TaskStatus {
  const k = (s || '').toLowerCase()
  if (['completed', 'succeeded', 'done', 'success'].includes(k)) return 'completed'
  if (['failed', 'error'].includes(k)) return 'failed'
  if (['cancelled', 'canceled'].includes(k)) return 'cancelled'
  if (['running', 'in_progress', 'processing'].includes(k)) return 'running'
  return 'pending'
}