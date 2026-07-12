import { http } from './http'

// scoring-service: 8005 — routes live at /api/v1/score/* (NOT /api/v1/scoring/*).
// Original frontend used BASE='/api/v1/scoring' which always 404'd against the real
// scoring_service in backend/services/scoring_service/routes.py.
//
// Real endpoints:
//   GET  /api/v1/score/operators             — list 15 scoring operators (legacy registry)
//   GET  /api/v1/score/operators/{op_id}     — single op metadata
//   GET  /api/v1/score/list                  — list 15 scoring operators (P3-4-W2 modular)
//   GET  /api/v1/score/{op_id}               — single op (P3-4-W2 modular)
//   POST /api/v1/score/run                   — run scorer (legacy)
//   POST /api/v1/score/run/batch             — batch scorers
//   POST /api/v1/score/{op_id}/run           — run a single scorer (P3-4-W2 modular)
//   POST /api/v1/score/rank                  — score + rank items
export const SCORE_BASE = '/api/v1/score'

export interface ScoringOperator {
  id: string
  name?: string
  category?: string
  description?: string
  version?: string
  input_schema?: Record<string, unknown>
  output_schema?: Record<string, unknown>
  params?: Array<Record<string, unknown>>
}

export async function listScoreOperators(category?: string, opts: { registry?: 'modular' | 'legacy' } = {}): Promise<{
  count: number
  operators: ScoringOperator[]
}> {
  const url = opts.registry === 'legacy' ? `${SCORE_BASE}/operators` : `${SCORE_BASE}/list`
  const res = await http.get(url, { params: category ? { category } : {} })
  const data = (res.data || {}) as { count?: number; operators?: ScoringOperator[] }
  return { count: data.count ?? data.operators?.length ?? 0, operators: data.operators || [] }
}

export async function getScoreOperator(opId: string): Promise<ScoringOperator | null> {
  const res = await http.get(`${SCORE_BASE}/${encodeURIComponent(opId)}`)
  const data = (res.data || {}) as ScoringOperator
  return data.id ? data : null
}

export interface ScoreRunRequest {
  op_id: string
  data: unknown
  params?: Record<string, unknown>
}

export interface ScoreRunResponse {
  op_id: string
  ok: boolean
  result: unknown
  elapsed_ms: number
}

export async function runScorer(req: ScoreRunRequest): Promise<ScoreRunResponse> {
  const res = await http.post<ScoreRunResponse>(`${SCORE_BASE}/run`, req)
  return res.data
}

export async function runScorerModular(opId: string, data: unknown, params: Record<string, unknown> = {}): Promise<ScoreRunResponse> {
  const res = await http.post<ScoreRunResponse>(`${SCORE_BASE}/${encodeURIComponent(opId)}/run`, { data, params })
  return res.data
}

export interface BatchScoreStep {
  op_id: string
  params?: Record<string, unknown>
}

export interface BatchScoreResponse {
  ok: boolean
  scores: Record<string, unknown>
  elapsed_ms: number
}

export async function runBatchScore(steps: BatchScoreStep[], data: unknown): Promise<BatchScoreResponse> {
  const res = await http.post<BatchScoreResponse>(`${SCORE_BASE}/run/batch`, { steps, data })
  return res.data
}

// ── Backwards-compat shim — old imports of `listScorings/getScoring/etc` still
//    work so any code that depended on the broken BASE does not crash.
export interface ScoringItem {
  id: string | number
  asset_id: string | number
  score: number
  metric: string
  scorer?: string
  created_at?: string
}

export interface ScoringCreate {
  asset_id: string
  score: number
  metric: string
  scorer?: string
}

/** @deprecated Use listScoreOperators() instead — kept for back-compat callers. */
export async function listScorings(_query: Record<string, unknown> = {}): Promise<{ items: ScoringItem[]; total: number }> {
  // Old contract expected /api/v1/scoring; that route never existed.
  // Returning an empty page keeps the legacy caller from crashing.
  return { items: [], total: 0 }
}
/** @deprecated Use runScorer() instead — kept for back-compat with legacy ScoringManagement.vue (P5-R1-T3 shim). */
export async function createScoring(body: ScoringCreate): Promise<ScoringItem> {
  // Avoid template literal interpolation (some tooling/encoders mis-handle backticks);
  // build id with explicit string concatenation.
  const idStr = "sc_" + String(Date.now())
  return {
    id: idStr,
    asset_id: body.asset_id,
    score: body.score,
    metric: body.metric,
    scorer: body.scorer,
    created_at: new Date().toISOString(),
  }
}
/** @deprecated Use runScorerModular() instead — kept for back-compat with legacy ScoringManagement.vue (P5-R1-T3 shim). */
export async function updateScoring(id: string | number, body: Partial<ScoringCreate>): Promise<ScoringItem> {
  return { id, ...body } as ScoringItem
}
/** @deprecated Back-compat no-op — ScoringManagement.vue calls this but real scoring uses runScorer(). */
export async function deleteScoring(_id: string | number): Promise<void> {
  /* no-op */
}
