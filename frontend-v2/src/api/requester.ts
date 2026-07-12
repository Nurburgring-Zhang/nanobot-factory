import { http } from './http'

// /api/v1/requester/* — Requester acceptance endpoints (backend/imdf/api/requester_routes.py)

const BASE = '/api/v1/requester'

export type AcceptanceStatus = 'pending' | 'accepted' | 'rejected' | 'needs_revision'

export interface AcceptanceRecord {
  id: string
  delivery_id: string
  requester_id: string
  status: AcceptanceStatus
  comments: string
  sampled_assets: string[]
  accepted_assets: string[]
  rejected_assets: string[]
  issues: Array<Record<string, string>>
  sampled_count: number
  accepted_count: number
  rejected_count: number
  metadata: Record<string, string>
  created_at: string
  updated_at: string
  acceptance_rate: number
}

export interface AcceptanceStats {
  acceptance_id: string
  delivery_id: string
  requester_id: string
  status: AcceptanceStatus
  sampled_count: number
  accepted_count: number
  rejected_count: number
  acceptance_rate: number
  rejection_rate: number
  issue_count: number
  created_at: string
  updated_at: string
}

export interface AcceptanceEnvelope<T> {
  success: boolean
  data: T
  error: string | null
  message: string
}

export async function listPending(requesterId: string): Promise<AcceptanceEnvelope<{ items: AcceptanceRecord[]; total: number }>> {
  return (await http.get(`${BASE}/pending`, { params: { requester_id: requesterId } })).data
}

export async function listAcceptances(params: {
  requester_id: string
  status?: AcceptanceStatus
}): Promise<AcceptanceEnvelope<{ items: AcceptanceRecord[]; total: number }>> {
  return (await http.get(`${BASE}/acceptances`, { params })).data
}

export async function createAcceptance(body: {
  delivery_id: string
  requester_id: string
  sample_rate?: number
  metadata?: Record<string, string>
  seed?: number
}): Promise<AcceptanceEnvelope<AcceptanceRecord>> {
  return (await http.post(`${BASE}/acceptances`, body)).data
}

export async function getAcceptance(acceptanceId: string): Promise<AcceptanceEnvelope<AcceptanceRecord>> {
  return (await http.get(`${BASE}/acceptances/${acceptanceId}`)).data
}

export async function getAcceptanceStats(acceptanceId: string): Promise<AcceptanceEnvelope<AcceptanceStats>> {
  return (await http.get(`${BASE}/acceptances/${acceptanceId}/stats`)).data
}

export async function submitAcceptance(
  acceptanceId: string,
  body: {
    status: 'accepted' | 'rejected' | 'needs_revision'
    comments?: string
    accepted_assets?: string[]
    rejected_assets?: string[]
    issues?: Array<Record<string, string>>
  }
): Promise<AcceptanceEnvelope<AcceptanceRecord>> {
  return (await http.post(`${BASE}/acceptances/${acceptanceId}/submit`, body)).data
}

export async function requestRevision(
  acceptanceId: string,
  body: { reason: string; issues?: Array<Record<string, string>> }
): Promise<AcceptanceEnvelope<AcceptanceRecord>> {
  return (await http.post(`${BASE}/acceptances/${acceptanceId}/request-revision`, body)).data
}