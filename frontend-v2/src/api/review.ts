import { http } from './http'

// Review queue endpoints live in:
//   backend/imdf/api/quality_v2_routes.py (router prefix=/api/quality/v2)
//
//   POST /api/quality/v2/review/submit
//   POST /api/quality/v2/review/process     (decision: approve / reject / return / partial_pass)
//   GET  /api/quality/v2/review/queue-stats
//   GET  /api/quality/v2/review/efficiency
//   POST /api/quality/v2/review/reviewer-agreement
//   POST /api/quality/v2/review/llm-flag        (LLM-assisted suspicious marker)
//   POST /api/quality/v2/cleaning/golden-validate (gold-set marker)
//
// Annotation review *list* (pending annotations to review) still lives at
// /api/v1/annotations (annotation_service), so we keep the legacy helper.

const QV2 = '/api/quality/v2'
const LEGACY_ANNOTATIONS = '/api/v1/annotations'

export type ReviewDecision = 'approve' | 'reject' | 'return' | 'partial_pass'

export interface ReviewQueueItem {
  item_id: string
  stage: 'initial' | 'secondary' | 'final'
  priority: number
  asset_id?: string
  asset_url?: string
  submitted_by?: string
  submitted_at?: string
  deadline?: string
  status?: 'pending' | 'in_review' | 'returned' | 'approved' | 'rejected'
  // P5-R1-T5 quick wins: AI suspicion + gold markers
  ai_suspicion?: {
    flagged: boolean
    suspicion_score?: number
    reason?: string
    criteria?: string
  }
  gold_match?: {
    matched: boolean
    accuracy?: number
    expected_label?: string
    given_label?: string
  }
}

export interface ReviewQueueStats {
  total_in_queue?: number
  pending: number
  in_review?: number
  completed_today?: number
  returned: number
  backlog_pressure?: number
  avg_review_seconds?: number
  by_stage?: Record<string, number | Record<string, number>>
  by_priority?: Record<string, number>
  by_reviewer?: Record<string, number>
}

export async function getReviewQueueStats(params: Record<string, unknown> = {}): Promise<{
  success: boolean
  stats: ReviewQueueStats
}> {
  const res = await http.get(`${QV2}/review/queue-stats`, { params })
  // Backend wraps: { success, stats, limit, offset, range, granularity, dimension }
  const data = (res.data || {}) as { success?: boolean; stats?: ReviewQueueStats }
  return { success: data.success !== false, stats: data.stats || { pending: 0, returned: 0 } }
}

export async function getReviewEfficiency(
  reviewerId?: string,
  params: Record<string, unknown> = {},
): Promise<{
  success: boolean
  report: {
    reviewers: Array<{ id: string; reviewed: number; avg_seconds: number; agreement: number }>
    total_completed: number
    avg_agreement: number
    reviewer_stats?: Record<string, unknown>
  }
}> {
  const res = await http.get(`${QV2}/review/efficiency`, {
    params: reviewerId ? { reviewer_id: reviewerId, ...params } : params,
  })
  const data = (res.data || {}) as { success?: boolean; report?: any }
  return {
    success: data.success !== false,
    report: data.report || { reviewers: [], total_completed: 0, avg_agreement: 0 },
  }
}

export async function submitForReview(body: {
  item: Record<string, unknown>
  priority: number
  reviewer_id?: string
}): Promise<{ success: boolean; result: any }> {
  const res = await http.post(`${QV2}/review/submit`, body)
  const data = (res.data || {}) as { success?: boolean; result?: any }
  return { success: data.success !== false, result: data.result }
}

export async function processReview(body: {
  item_id: string
  reviewer_id: string
  decision: ReviewDecision
  comments?: string
  decision_data?: Record<string, unknown>
}): Promise<{ success: boolean; result: any }> {
  const res = await http.post(`${QV2}/review/process`, body)
  const data = (res.data || {}) as { success?: boolean; result?: any }
  return { success: data.success !== false, result: data.result }
}

// ── AI 标记可疑度 (LLM-flag) ─────────────────────────────────────────────────
export interface LLMFlagRequest {
  annotations: Array<Record<string, unknown>>
  criteria?: string[]
}

export async function llmFlagSuspicious(req: LLMFlagRequest): Promise<{
  success: boolean
  result: {
    total_checked: number
    flagged_count: number
    flag_rate: number
    suspicious: Array<{
      annotation: Record<string, unknown>
      suspicion_score: number
      reason: string
      criteria_violated: string[]
    }>
  }
}> {
  const res = await http.post(`${QV2}/review/llm-flag`, req)
  const data = (res.data || {}) as { success?: boolean; result?: any }
  return {
    success: data.success !== false,
    result: data.result || { total_checked: 0, flagged_count: 0, flag_rate: 0, suspicious: [] },
  }
}

// ── 黄金题校验 ──────────────────────────────────────────────────────────────
export interface GoldValidateRequest {
  annotations: Array<{ id: string; label: string; [k: string]: unknown }>
}

export async function validateAgainstGold(req: GoldValidateRequest): Promise<{
  success: boolean
  result: {
    matches: Array<{ id: string; matched: boolean; accuracy: number; expected?: string; given?: string }>
    summary: { total: number; matched: number; accuracy: number }
  }
}> {
  const res = await http.post(`${QV2}/cleaning/golden-validate`, {
    filepaths: req.annotations.map((a) => String(a.id)),
    golden_pairs: req.annotations.map((a) => ({
      file_a: String(a.id),
      file_b: String(a.id),
      should_dedup: String(a.label || '').toLowerCase() === 'true',
    })),
  })
  // Reshape to client-friendly contract
  const data = (res.data || {}) as { success?: boolean; result?: any }
  const result = data.result || {}
  const matched = Array.isArray(result.matched) ? result.matched : []
  const summary = result.summary || { total: 0, matched: 0, accuracy: 0 }
  return {
    success: data.success !== false,
    result: { matches: matched, summary },
  }
}

// ── Legacy annotation list (annotation_service) ─────────────────────────────
export interface AnnotationSummary {
  id: string | number
  asset_id: string | number
  label: string
  annotator?: string
  status: 'pending' | 'approved' | 'rejected'
  created_at?: string
  task_id?: string
  operator?: string
  confidence?: number
}

export async function listReviewAnnotations(params: { status?: string; limit?: number; task_id?: string } = {}): Promise<{
  items: AnnotationSummary[]
  total: number
}> {
  const res = await http.get(LEGACY_ANNOTATIONS, { params })
  // annotation_service returns a raw List; coerce to { items, total }
  const data = res.data
  if (Array.isArray(data)) return { items: data as AnnotationSummary[], total: data.length }
  return {
    items: (data?.items || []) as AnnotationSummary[],
    total: data?.total ?? (data?.items?.length || 0),
  }
}