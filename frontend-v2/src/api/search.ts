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
