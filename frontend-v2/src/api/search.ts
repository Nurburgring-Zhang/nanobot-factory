import { getOne, type Page } from './http'

// search-service: 8011 — read-only search across assets/datasets/annotations
export interface SearchHit {
  id: string | number
  type: 'asset' | 'dataset' | 'annotation' | 'workflow'
  title: string
  snippet?: string
  score?: number
}

export interface SearchQuery {
  q: string
  type?: SearchHit['type']
  page?: number
  page_size?: number
}

export async function searchAll(query: SearchQuery): Promise<Page<SearchHit>> {
  const { q, type, page = 1, page_size = 20 } = query
  const params: Record<string, unknown> = { q, page, page_size }
  if (type) params.type = type
  const res = await import('./http').then(({ http }) =>
    http.get<Page<SearchHit>>('/api/v1/search', { params })
  )
  return res.data
}

export async function searchByType(type: SearchHit['type'], q: string): Promise<SearchHit[]> {
  const res = await import('./http').then(({ http }) =>
    http.get<SearchHit[]>(`/api/v1/search/${type}`, { params: { q } })
  )
  return res.data
}

export async function getSearchSuggestion(prefix: string): Promise<string[]> {
  return getOne<string[]>(`/api/v1/search/suggest?q=${encodeURIComponent(prefix)}`)
}

// ============================================================================
// P17-D3: Global cross-domain search (/api/v1/search/global)
// ============================================================================
//
// Aggregates hits across dataset / project / user / asset / agent / workflow in
// a single round-trip. Used by the GlobalSearch palette (Ctrl+K).

export type GlobalDomain = 'dataset' | 'project' | 'user' | 'asset' | 'agent' | 'workflow'

export interface GlobalHit {
  domain: GlobalDomain
  domain_title: string
  id: string | number
  title: string
  snippet?: string
  score: number
  url?: string
}

export interface GlobalSearchResponse {
  query: string
  top_k: number
  total: number
  counts: Partial<Record<GlobalDomain, number>>
  hits: GlobalHit[]
  elapsed_ms?: number
}

export interface GlobalSearchQuery {
  q: string
  top_k?: number
  domains?: GlobalDomain[]
}

/**
 * Cross-domain search.
 *
 * Maps cleanly to backend endpoint:
 *   GET /api/v1/search/global?q=<query>&top_k=<n>&domains=<csv>
 *
 * Returns the raw response so callers can group / paginate as they wish.
 */
export async function searchGlobal(query: GlobalSearchQuery): Promise<GlobalSearchResponse> {
  const q = (query.q || '').trim()
  if (!q) {
    return { query: '', top_k: query.top_k ?? 3, total: 0, counts: {}, hits: [] }
  }
  const topK = Math.max(1, Math.min(10, query.top_k ?? 3))
  const params: Record<string, unknown> = { q, top_k: topK }
  if (query.domains && query.domains.length > 0) {
    params.domains = query.domains.join(',')
  }
  return getOne<GlobalSearchResponse>('/api/v1/search/global', { params })
}
