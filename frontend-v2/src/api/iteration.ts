// P4-5-W2: iteration API client (sessions + multi-agent + consistency).
import { http } from './http'

// ── Sessions ──────────────────────────────────────────────────────────────
export interface PromptVersion {
  version_id: string
  parent_version_id: string | null
  text: string
  params: Record<string, unknown>
  created_at: string
  note?: string | null
}

export interface IterativeSession {
  session_id: string
  owner_id: string
  project_id: string
  modality: string
  title: string
  state: 'draft' | 'review' | 'final' | 'discarded'
  best_variant_id?: string | null
  prompt_versions: PromptVersion[]
  assets?: AssetRow[]
  feedback?: FeedbackRow[]
  ab_tests?: ABRow[]
  created_at?: string
  updated_at?: string
}

export interface AssetRow {
  asset_id: string
  session_id: string
  prompt_version_id: string
  modality: string
  url: string
  seed: number
  metrics: Record<string, unknown>
  created_at: string
}

export interface FeedbackRow {
  feedback_id: string
  session_id: string
  asset_id: string | null
  rating: number
  text: string | null
  created_at: string
}

export interface ABRow {
  ab_id: string
  session_id: string
  parent_prompt_version_id: string
  variants: PromptVersion[]
  scores: Record<string, number>
  winner_variant_id?: string | null
  status: 'running' | 'decided'
  created_at: string
}

const BASE = '/api/v1/assets/sessions'

export async function listSessions(params: { owner_id?: string; project_id?: string; state?: string; limit?: number; offset?: number } = {}) {
  const res = await http.get<{ items: IterativeSession[]; count: number }>(BASE, { params })
  return res.data
}

export async function getSession(id: string) {
  const res = await http.get<IterativeSession>(`${BASE}/${id}`)
  return res.data
}

export async function createSession(body: { owner_id: string; project_id: string; modality: string; initial_prompt: string; params?: Record<string, unknown>; title?: string }) {
  const res = await http.post<IterativeSession>(BASE, body)
  return res.data
}

export async function iterateSession(id: string, body: { text: string; parent_version_id?: string; params?: Record<string, unknown>; note?: string }) {
  const res = await http.post<{ prompt_version: PromptVersion; session: IterativeSession }>(`${BASE}/${id}/iterate`, body)
  return res.data
}

export async function addFeedback(id: string, body: { rating: number; text?: string; asset_id?: string }) {
  const res = await http.post<FeedbackRow>(`${BASE}/${id}/feedback`, body)
  return res.data
}

export async function startAB(id: string, body: { parent_prompt_version_id: string; variants: { text: string; params?: Record<string, unknown>; note?: string }[] }) {
  const res = await http.post<ABRow>(`${BASE}/${id}/ab_test`, body)
  return res.data
}

export async function scoreAB(sid: string, abId: string, body: { scores: Record<string, number> }) {
  const res = await http.post<ABRow>(`${BASE}/${sid}/ab_test/${abId}/score`, body)
  return res.data
}

export async function pickBest(sid: string, abId: string) {
  const res = await http.post<ABRow>(`${BASE}/${sid}/ab_test/${abId}/best`)
  return res.data
}

export async function finalizeSession(id: string) {
  const res = await http.patch<IterativeSession>(`${BASE}/${id}`, { action: 'finalize' })
  return res.data
}

export async function discardSession(id: string) {
  const res = await http.patch<IterativeSession>(`${BASE}/${id}`, { action: 'discard' })
  return res.data
}

export async function deleteSession(id: string) {
  await http.delete(`${BASE}/${id}`)
}

// ── Multi-Agent ───────────────────────────────────────────────────────────
export interface AgentInfo {
  role: string
  name: string
  description: string
  capabilities: string[]
}

export interface OrchestratorReport {
  run_id: string
  started_at: string
  finished_at: string
  ok: boolean
  agent_results: { role: string; status: string; produced: number; error?: string }[]
  asset_pool: { asset_id: string; shot_id?: string; modality: string; url: string; seed?: number }[]
  qa_scores: Record<string, number>
  storyboard: { scenes: { scene_id: string; title: string; shots: { shot_id: string; prompt: string }[] }[] }
  character_state: Record<string, { shots: string[]; reference_url: string }>
  events: { role: string; kind: string; payload: Record<string, unknown>; created_at: string }[]
}

export async function listAgents() {
  const res = await http.get<{ items: AgentInfo[]; count: number }>('/api/v1/assets/agents')
  return res.data
}

export async function multiGenerate(body: { brief: Record<string, unknown>; character_pool?: Record<string, unknown>; scenes?: unknown[]; parallel?: boolean }) {
  const res = await http.post<OrchestratorReport>('/api/v1/assets/multi_generate', body)
  return res.data
}

export async function listRuns(limit = 20) {
  const res = await http.get<{ items: { run_id: string; started_at: string; finished_at: string; ok: boolean; asset_count: number; agent_results: { role: string; status: string }[] }[]; count: number }>('/api/v1/assets/multi_generate/runs', { params: { limit } })
  return res.data
}

export async function getRun(runId: string) {
  const res = await http.get<OrchestratorReport>(`/api/v1/assets/multi_generate/runs/${runId}`)
  return res.data
}

// ── Consistency ───────────────────────────────────────────────────────────
export interface IterationRound {
  round_no: number
  started_at: string
  finished_at: string
  regenerated_shots: string[]
  before_scores: Record<string, number>
  after_scores: Record<string, number>
  delta: number
  fallback_used: boolean
  note?: string | null
}

export interface ConsistencyReport {
  project_id: string
  started_at: string
  finished_at: string
  config: Record<string, unknown>
  rounds: IterationRound[]
  initial_avg_score: number
  final_avg_score: number
  delta: number
  fallback_used_count: number
  asset_count: number
  passed: boolean
}

export async function consistencyRun(body: { project_id: string; brief: Record<string, unknown>; config?: Record<string, unknown>; character_pool?: Record<string, unknown> }) {
  const res = await http.post<ConsistencyReport>('/api/v1/assets/consistency/run', body)
  return res.data
}

export async function listConsistencyReports(projectId?: string) {
  const res = await http.get<{ items: ConsistencyReport[]; count: number }>('/api/v1/assets/consistency/report', { params: { project_id: projectId } })
  return res.data
}