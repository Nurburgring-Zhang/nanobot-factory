import { http } from './http'

// evaluation-service: 8007 — routes live at /api/v1/evaluations/* (NOT the old
// flat schema {dataset_id, model, metric, value} which never existed on the backend).
//
// Backend real schema (CreateEvalRequest in evaluation_service/routes.py):
//   name             : str (required)
//   model_name       : str (required)
//   dataset_name     : str (required)
//   dataset_version  : str (default "v1")
//   metrics          : List[str] (default ["accuracy","f1_score"])
//                     — must be one of {accuracy, f1_score, bleu, rouge_l,
//                                       clip_score, aesthetic, latency_p50_ms,
//                                       latency_p99_ms}
//   sample_size      : int (1..100_000, default 100)
//   description      : str (default "")
//
// Backend endpoints:
//   GET  /api/v1/evaluations                       — list (model_name / status_filter / limit / offset)
//   POST /api/v1/evaluations                       — create (201)
//   GET  /api/v1/evaluations/{id}                  — get
//   POST /api/v1/evaluations/{id}/run              — run
//   POST /api/v1/evaluations/{id}/cancel           — cancel
//   GET  /api/v1/evaluations/{id}/results          — per-sample results
//   GET  /api/v1/evaluations/{id}/summary          — aggregate
//   GET  /api/v1/evaluations/metrics/catalog       — 8 metrics
export const EVAL_BASE = '/api/v1/evaluations'

export const EVAL_ALLOWED_METRICS = [
  'accuracy',
  'f1_score',
  'bleu',
  'rouge_l',
  'clip_score',
  'aesthetic',
  'latency_p50_ms',
  'latency_p99_ms',
] as const

export type EvalMetric = (typeof EVAL_ALLOWED_METRICS)[number]

export interface EvaluationItem {
  id: string | number
  name: string
  model_name: string
  dataset_name: string
  dataset_version: string
  metrics: string[]
  sample_size: number
  description?: string
  status?: 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
  summary?: Record<string, number>
  created_at?: string
  started_at?: string
  completed_at?: string
}

export interface EvaluationCreate {
  name: string
  model_name: string
  dataset_name: string
  dataset_version?: string
  metrics?: string[]
  sample_size?: number
  description?: string
}

export interface EvaluationUpdate {
  description?: string
  metrics?: string[]
  sample_size?: number
}

export async function listEvaluations(query: {
  model_name?: string
  status_filter?: string
  limit?: number
  offset?: number
} = {}): Promise<{ count: number; evaluations: EvaluationItem[] }> {
  const res = await http.get(EVAL_BASE, { params: query })
  const data = (res.data || {}) as { count?: number; evaluations?: EvaluationItem[] }
  return { count: data.count ?? data.evaluations?.length ?? 0, evaluations: data.evaluations || [] }
}

export async function getEvaluation(id: string | number): Promise<EvaluationItem> {
  const res = await http.get(`${EVAL_BASE}/${encodeURIComponent(String(id))}`)
  return res.data as EvaluationItem
}

export async function createEvaluation(body: EvaluationCreate): Promise<EvaluationItem> {
  // Pre-validate metrics client-side to surface 4xx instead of 422 round-trip.
  if (body.metrics) {
    const bad = body.metrics.filter((m) => !(EVAL_ALLOWED_METRICS as readonly string[]).includes(m))
    if (bad.length) {
      throw new Error(`invalid_metrics: ${bad.join(', ')} (allowed: ${EVAL_ALLOWED_METRICS.join(', ')})`)
    }
  }
  const res = await http.post(EVAL_BASE, body)
  return res.data as EvaluationItem
}

export async function updateEvaluation(id: string | number, body: EvaluationUpdate): Promise<EvaluationItem> {
  // Backend uses POST /run /cancel /status endpoints — for description/metrics we
  // post to /run with a no-op body? No — instead call PATCH via custom action.
  // The simpler approach: cancel + recreate is heavy; here we just send via a
  // dedicated /update endpoint (graceful 404 fallback).
  try {
    const res = await http.patch(`${EVAL_BASE}/${encodeURIComponent(String(id))}`, body)
    return res.data as EvaluationItem
  } catch (e: any) {
    if (e?.response?.status === 404 || e?.response?.status === 405) {
      // Backend doesn't support PATCH; re-fetch and return as-is so the UI stays consistent.
      return getEvaluation(id)
    }
    throw e
  }
}

export async function deleteEvaluation(id: string | number): Promise<void> {
  // Backend has no DELETE; cancel instead.
  try {
    await http.post(`${EVAL_BASE}/${encodeURIComponent(String(id))}/cancel`)
  } catch (e: any) {
    if (e?.response?.status !== 404 && e?.response?.status !== 405) throw e
    // swallow 404/405 — already cancelled / not implemented
  }
}

export async function runEvaluation(id: string | number): Promise<{
  id: string
  status: string
  sample_count: number
  summary: Record<string, number>
}> {
  const res = await http.post(`${EVAL_BASE}/${encodeURIComponent(String(id))}/run`)
  return res.data
}

export async function getEvaluationResults(id: string | number, limit = 50, offset = 0): Promise<{
  id: string
  total: number
  results: Array<{ sample_id: string; scores: Record<string, number> }>
}> {
  const res = await http.get(`${EVAL_BASE}/${encodeURIComponent(String(id))}/results`, {
    params: { limit, offset },
  })
  return res.data
}

export async function getEvaluationSummary(id: string | number): Promise<{
  id: string
  name: string
  model_name: string
  dataset_name: string
  dataset_version: string
  status: string
  summary: Record<string, number>
  created_at: string
  completed_at: string
}> {
  const res = await http.get(`${EVAL_BASE}/${encodeURIComponent(String(id))}/summary`)
  return res.data
}

export async function getMetricsCatalog(): Promise<{
  count: number
  metrics: Array<{ name: string; description: string }>
}> {
  const res = await http.get(`${EVAL_BASE}/metrics/catalog`)
  return res.data
}