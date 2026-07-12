// VDP-2026 R1 — Platform Capability Module Registry v2 (client)
//
// 47 capabilities across 17 categories. The Capability Registry UI lets
// engineers browse the catalogue, inspect input/output schemas, and invoke
// any capability through one stable HTTP surface.
import { http } from './http'

// --- domain types ---------------------------------------------------------
export const CAPABILITY_CATEGORIES = [
  'project',
  'requirement',
  'dataset',
  'pack',
  'collection',
  'annotation',
  'review',
  'qc',
  'acceptance',
  'delivery',
  'scoring',
  'tagging',
  'cleaning',
  'classification',
  'search',
  'evaluation',
  'export',
] as const
export type CapabilityCategory = typeof CAPABILITY_CATEGORIES[number]

export interface CapabilitySchema {
  type?: string
  required?: string[]
  properties?: Record<string, {
    type?: string
    description?: string
    enum?: string[]
    min?: number
    max?: number
    min_length?: number
    max_length?: number
    min_items?: number
    max_items?: number
    items?: { type?: string }
    default?: unknown
  }>
}

export interface CapabilityItem {
  id: string
  name: string
  category: CapabilityCategory
  description: string
  inputs_schema: CapabilitySchema
  outputs_schema: CapabilitySchema
  tags: string[]
  owner: string
  version: string
  rate_limit_per_min: number | null
  cost_unit: string
  emits_domain_event: boolean
  domain_event_subject: string | null
}

export interface CatalogueResponse {
  total: number
  categories: Record<string, number>
  items: CapabilityItem[]
}

export interface CategoryResponse {
  categories: string[]
}

export interface CapabilityListResponse {
  total: number
  items: CapabilityItem[]
}

export interface InvocationRequest {
  capability_id: string
  inputs: Record<string, unknown>
  actor?: string
  refs?: {
    project_id?: string
    requirement_id?: string
    dataset_id?: string
    pack_id?: string
    delivery_id?: string
  }
}

export interface InvocationResult {
  capability_id: string
  status: 'success' | 'error' | 'partial'
  outputs: Record<string, unknown>
  error: string
  duration_ms: number
  invocation_id: string
  emitted_event: string | null
}

export interface InvocationRecord {
  id: string
  capability_id: string
  inputs_json: string
  outputs_json: string
  status: string
  error: string
  actor: string
  duration_ms: number
  ref_project_id: string
  ref_requirement_id: string
  ref_dataset_id: string
  ref_pack_id: string
  ref_delivery_id: string
  created_at: string
}

// --- HTTP helpers ---------------------------------------------------------
const BASE = '/api/v1/capabilities_v2'

export async function fetchCatalogue(): Promise<CatalogueResponse> {
  return (await http.get(`${BASE}/catalogue`)).data
}

export async function fetchCategories(): Promise<CategoryResponse> {
  return (await http.get(`${BASE}/categories`)).data
}

export async function listCapabilities(
  category?: CapabilityCategory,
  q?: string,
): Promise<CapabilityListResponse> {
  const params: Record<string, string> = {}
  if (category) params.category = category
  if (q) params.q = q
  return (await http.get(`${BASE}/capabilities`, { params })).data
}

export async function describeCapability(id: string): Promise<CapabilityItem> {
  return (await http.get(`${BASE}/capabilities/${encodeURIComponent(id)}`)).data
}

export async function invokeCapability(req: InvocationRequest): Promise<InvocationResult> {
  return (await http.post(`${BASE}/invoke`, req)).data
}

export async function listInvocations(
  cap_id?: string,
  project_id?: string,
  limit = 100,
): Promise<{ total: number, items: InvocationRecord[] }> {
  return (await http.get(`${BASE}/invocations`, {
    params: { cap_id, project_id, limit },
  })).data
}

export async function health(): Promise<{ status: string, capabilities_registered: number, categories: string[] }> {
  return (await http.get(`${BASE}/health`)).data
}
