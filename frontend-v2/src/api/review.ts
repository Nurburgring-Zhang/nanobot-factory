import { http } from './http'

// review endpoints live in backend/imdf/api/quality_v2_routes.py at /api/v1/review/*
// and backend/services/annotation_service/routes.py for legacy /api/v1/annotations.

const BASE = '/api/v1/review'

export interface ReviewQueueItem {
  item_id: string
  stage: 'initial' | 'secondary' | 'final'
  priority: number
  asset_id?: string
  asset_url?: string
  submitted_by?: string
  submitted_at?: string
  deadline?: string
  status?: 'pending' | 'in_review' | 'returned'
}

export interface ReviewQueueStats {
  pending: number
  in_review: number
  completed_today: number
  returned: number
  avg_review_seconds?: number
  by_stage?: Record<string, number>
  by_reviewer?: Record<string, number>
}

export async function getReviewQueueStats(): Promise<{
  success: boolean
  stats: ReviewQueueStats
}> {
  return (await http.get(`${BASE}/queue-stats`)).data
}

export async function getReviewEfficiency(reviewerId?: string): Promise<{
  success: boolean
  report: {
    reviewers: Array<{ id: string; reviewed: number; avg_seconds: number; agreement: number }>
    total_completed: number
    avg_agreement: number
  }
}> {
  return (await http.get(`${BASE}/efficiency`, { params: reviewerId ? { reviewer_id: reviewerId } : {} })).data
}

export async function submitForReview(body: {
  item: Record<string, unknown>
  priority: number
  reviewer_id?: string
}): Promise<{ success: boolean; result: any }> {
  return (await http.post(`${BASE}/submit`, body)).data
}

export async function processReview(body: {
  item_id: string
  reviewer_id: string
  decision: 'approve' | 'reject' | 'return'
  comments?: string
  decision_data?: Record<string, unknown>
}): Promise<{ success: boolean; result: any }> {
  return (await http.post(`${BASE}/process`, body)).data
}

// ── Legacy annotation review (kept for transition) ─────────────────────────
export interface AnnotationSummary {
  id: string | number
  asset_id: string | number
  label: string
  annotator?: string
  status: 'pending' | 'approved' | 'rejected'
  created_at?: string
}

export async function listReviewAnnotations(params: { status?: string; limit?: number } = {}): Promise<{
  items: AnnotationSummary[]
  total: number
}> {
  return (await http.get('/api/v1/annotations', { params })).data
}