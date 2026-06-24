// P4-6-W2: workflow-service v2 API client (dag_v2 + director + operator marketplace).
//
// Base path: /api/v1/workflow (singular) to mirror the existing
// /api/v1/workflow/templates / /api/v1/workflow/editor surfaces.
import { http } from './http'

// ---------- DAG definition ----------
export type NodeType =
  | 'input' | 'transform' | 'condition' | 'loop'
  | 'parallel' | 'sub_workflow' | 'output'
export type EdgeType = 'data' | 'control' | 'error' | 'retry'
export type ExecMode = 'sequential' | 'parallel' | 'fan_out_fan_in' | 'map_reduce'
export type ErrorPolicy = 'retry' | 'fallback' | 'skip' | 'escalate'
export type NodeStatus =
  | 'pending' | 'ready' | 'running' | 'succeeded' | 'failed'
  | 'skipped' | 'cancelled' | 'retried'
export type RunStatus =
  | 'pending' | 'running' | 'succeeded' | 'failed' | 'partial' | 'cancelled'

export interface DAGNode {
  id: string
  name: string
  node_type: NodeType
  operator_id?: string | null
  config: Record<string, unknown>
  inputs: string[]
  retry_max: number
  timeout_seconds: number
  error_policy: ErrorPolicy
  fallback_node_id?: string | null
  position: [number, number]
  description?: string
}

export interface DAGEdge {
  source: string
  target: string
  edge_type: EdgeType
  source_handle?: string
  target_handle?: string
  condition?: string | null
}

export interface DAGDefinition {
  id: string
  name: string
  description: string
  nodes: DAGNode[]
  edges: DAGEdge[]
  exec_mode: ExecMode
  version: number
  owner: string
  tags: string[]
  node_count: number
  edge_count: number
  created_at?: string
  updated_at?: string
}

export interface RunStepState {
  node_id: string
  status: NodeStatus
  attempt: number
  started_at?: string
  finished_at?: string
  error?: string
  output: Record<string, unknown>
  log: string[]
}

export interface WorkflowRun {
  run_id: string
  workflow_id: string
  status: RunStatus
  exec_mode: ExecMode
  started_at?: string
  finished_at?: string
  inputs: Record<string, unknown>
  steps: Record<string, RunStepState>
  log: string[]
  trigger: string
  progress: number
}

// ---------- Visual (Vue Flow) JSON ----------
export interface FlowNode {
  id: string
  type: string
  position: { x: number, y: number }
  data: Record<string, unknown>
  label: string
  width: number
  height: number
}
export interface FlowEdge {
  id: string
  source: string
  target: string
  sourceHandle: string
  targetHandle: string
  label: string
  type: string
  data: Record<string, unknown>
}
export interface FlowPayload {
  workflowId: string
  version: number
  direction: 'LR' | 'TB'
  nodes: FlowNode[]
  edges: FlowEdge[]
  meta: Record<string, unknown>
}

// ---------- Operator marketplace ----------
export interface OperatorVersion {
  version: string
  released_at: string
  changelog: string
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
  deprecated: boolean
  replaces: string | null
}
export interface OperatorItem {
  id: string
  name: string
  category: string
  description: string
  icon: string
  color: string
  tags: string[]
  capabilities: string[]
  latest: string
  owner: string
  version_count: number
  versions: OperatorVersion[]
}
export interface OperatorSchema {
  id: string
  name: string
  category: string
  version: string
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
}
export interface OperatorSummary {
  total: number
  per_category: Record<string, number>
  categories: string[]
}

// ---------- Director studio ----------
export interface Shot {
  shot_id: string
  index: number
  title: string
  description: string
  duration_seconds: number
  visual_prompt: string
  voiceover: string
  camera: string
  mood: string
}
export interface VisualAsset {
  shot_id: string
  kind: 'image' | 'video' | 'voice' | 'music'
  uri: string
  prompt: string
  metadata: Record<string, unknown>
}
export type DirectorState =
  | 'pending' | 'running' | 'paused'
  | 'succeeded' | 'failed' | 'cancelled'
export interface DirectorSession {
  session_id: string
  brief: string
  state: DirectorState
  story_state: DirectorState
  visual_state: DirectorState
  assembly_state: DirectorState
  shots: Shot[]
  assets: VisualAsset[]
  final_cut_uri: string
  log: string[]
  created_at: string
  updated_at: string
  user_overrides: Record<string, unknown>
}

// =====================================================================
// API calls
// =====================================================================

const BASE = '/api/v1/workflow'

// DAG CRUD -------------------------------------------------------------
export async function listDAGs(): Promise<{ total: number, items: DAGDefinition[] }> {
  return (await http.get(`${BASE}/dag`)).data
}
export async function getDAG(id: string): Promise<DAGDefinition> {
  return (await http.get(`${BASE}/dag/${id}`)).data
}
export async function createDAG(body: Partial<DAGDefinition>): Promise<DAGDefinition> {
  return (await http.post(`${BASE}/dag`, body)).data
}
export async function updateDAG(id: string, body: Partial<DAGDefinition>): Promise<DAGDefinition> {
  return (await http.put(`${BASE}/dag/${id}`, body)).data
}
export async function deleteDAG(id: string): Promise<void> {
  await http.delete(`${BASE}/dag/${id}`)
}
export async function getDAGVisual(id: string, direction: 'LR' | 'TB' = 'LR'): Promise<FlowPayload> {
  return (await http.get(`${BASE}/dag/${id}/visual`, { params: { direction } })).data
}
export async function recomputeLayout(id: string,
                                       engine = 'dagre',
                                       direction: 'LR' | 'TB' = 'LR',
                                       persist = true): Promise<Record<string, unknown>> {
  return (await http.post(`${BASE}/dag/${id}/layout?engine=${engine}&direction=${direction}&persist=${persist}`)).data
}
export async function importFlow(payload: FlowPayload): Promise<DAGDefinition> {
  return (await http.post(`${BASE}/dag/import-flow`, { payload })).data
}
export async function listLayoutEngines(): Promise<{ engines: string[] }> {
  return (await http.get(`${BASE}/layout-engines`)).data
}

// Runs -----------------------------------------------------------------
export async function runDAG(id: string,
                              inputs: Record<string, unknown> = {},
                              trigger = 'manual',
                              sync = true): Promise<WorkflowRun> {
  return (await http.post(`${BASE}/dag/${id}/run`,
    { inputs, trigger, sync })).data
}
export async function listRuns(workflowId?: string): Promise<{ total: number, items: WorkflowRun[] }> {
  return (await http.get(`${BASE}/dag/runs`, { params: workflowId ? { dag_id: workflowId } : {} })).data
}
export async function getRun(runId: string): Promise<WorkflowRun> {
  return (await http.get(`${BASE}/dag/runs/${runId}`)).data
}
export async function cancelRun(runId: string): Promise<{ success: boolean }> {
  return (await http.post(`${BASE}/dag/runs/${runId}/cancel`)).data
}

// Operator marketplace -------------------------------------------------
export async function listOperators(q = '', category?: string): Promise<{ total: number, items: OperatorItem[] }> {
  return (await http.get(`${BASE}/operators`, { params: { q, category } })).data
}
export async function operatorSummary(): Promise<OperatorSummary> {
  return (await http.get(`${BASE}/operators/summary`)).data
}
export async function operatorCategories(): Promise<{ categories: string[], items: { name: string, count: number }[] }> {
  return (await http.get(`${BASE}/operators/categories`)).data
}
export async function operatorSchema(id: string): Promise<OperatorSchema> {
  return (await http.get(`${BASE}/operators/${id}/schema`)).data
}

// Director studio ------------------------------------------------------
export async function directorRun(brief: string, shotCount?: number): Promise<DirectorSession> {
  return (await http.post(`${BASE}/director/run`, { brief, shot_count: shotCount })).data
}
export async function createDirectorSession(brief: string, shotCount?: number): Promise<DirectorSession> {
  return (await http.post(`${BASE}/director/session`, { brief, shot_count: shotCount })).data
}
export async function getDirectorSession(id: string): Promise<DirectorSession> {
  return (await http.get(`${BASE}/director/session/${id}`)).data
}
export async function runDirectorStory(id: string): Promise<DirectorSession> {
  return (await http.post(`${BASE}/director/session/${id}/story`)).data
}
export async function runDirectorVisual(id: string): Promise<DirectorSession> {
  return (await http.post(`${BASE}/director/session/${id}/visual`)).data
}
export async function runDirectorAssembly(id: string): Promise<DirectorSession> {
  return (await http.post(`${BASE}/director/session/${id}/assemble`)).data
}
export async function overrideDirectorShots(id: string, shots: Shot[]): Promise<DirectorSession> {
  return (await http.put(`${BASE}/director/session/${id}/shots`, { shots })).data
}

// Stats ----------------------------------------------------------------
export async function dagStats(): Promise<Record<string, unknown>> {
  return (await http.get(`${BASE}/dag-stats/summary`)).data
}
