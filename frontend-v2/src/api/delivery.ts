import { http } from './http'

// /api/delivery/* — Delivery workflow endpoints (backend/imdf/api/delivery_routes.py)

const BASE = '/api/delivery'

export type DeliveryStatus =
  | 'draft' | 'submitted' | 'in_review' | 'approved' | 'rejected'
  | 'delivered' | 'shared' | 'archived' | 'pending'

export interface DeliveryItem {
  id: string
  name: string
  format: string
  dataset_version: string
  status: DeliveryStatus
  reviewer: string
  comments: string
}

export interface TimelineEvent {
  id: number
  delivery_id: string
  event_type: string
  actor: string
  payload: Record<string, unknown>
  timestamp: string
}

export interface FinalizeShareResult {
  delivery_id: string
  internal_id?: number
  snapshot_id: string
  share_token: string
  share_url: string
  expires_at: string
  expires_in_hours: number
  max_downloads: number
  has_password: boolean
  status: string
  events: Array<Record<string, unknown>>
  owner_id: string
  created_at: string
}

export interface DeliveryEnvelope<T> {
  success: boolean
  data: T
  error: string | null
  message: string
}

export async function listDeliveries(params: {
  limit?: number
  offset?: number
  q?: string
} = {}): Promise<DeliveryEnvelope<{ deliveries: DeliveryItem[]; total: number }>> {
  return (await http.get(`${BASE}/`, { params })).data
}

export async function createDelivery(body: {
  name: string
  format?: 'json' | 'csv' | 'parquet' | 'coco' | 'voc' | 'yolo'
  items?: string[]
}): Promise<DeliveryEnvelope<{ delivery_id: string }>> {
  return (await http.post(`${BASE}/create`, body)).data
}

export async function listPendingForRequester(requesterId: string): Promise<DeliveryEnvelope<{ items: unknown[]; total: number }>> {
  return (await http.get(`${BASE}/pending-requester`, { params: { requester_id: requesterId } })).data
}

export async function requesterAccept(params: {
  delivery_id: string
  requester_id: string
  comments?: string
  sample_rate?: number
}): Promise<DeliveryEnvelope<unknown>> {
  return (await http.post(`${BASE}/${params.delivery_id}/requester-accept`, null, { params: {
    requester_id: params.requester_id,
    comments: params.comments || '',
    sample_rate: params.sample_rate ?? 0.05,
  } })).data
}

export async function requesterReject(params: {
  delivery_id: string
  requester_id: string
  comments?: string
  sample_rate?: number
}): Promise<DeliveryEnvelope<unknown>> {
  return (await http.post(`${BASE}/${params.delivery_id}/requester-reject`, null, { params: {
    requester_id: params.requester_id,
    comments: params.comments || '',
    sample_rate: params.sample_rate ?? 0.05,
  } })).data
}

export async function getDeliveryTimeline(deliveryId: string): Promise<DeliveryEnvelope<{ delivery_id: string; events: TimelineEvent[]; total: number }>> {
  return (await http.get(`${BASE}/${deliveryId}/timeline`)).data
}

export async function finalizeAndShare(params: {
  delivery_id: string
  owner_id?: string
  expiry_hours?: number
  max_downloads?: number
  password?: string
  note?: string
}): Promise<DeliveryEnvelope<FinalizeShareResult>> {
  return (await http.post(`${BASE}/${params.delivery_id}/finalize-and-share`, null, { params: {
    owner_id: params.owner_id || 'system',
    expiry_hours: params.expiry_hours ?? 72,
    max_downloads: params.max_downloads ?? 0,
    password: params.password || '',
    note: params.note || '',
  } })).data
}

export async function compareDeliveries(a: string, b: string): Promise<DeliveryEnvelope<unknown>> {
  return (await http.get(`${BASE}/compare/${a}/${b}`)).data
}