// frontend-v2/src/api/obsidian.ts
// P4-8-W2: Obsidian-style knowledge graph + wiki API client (inspired by claude-obsidian).
// Base path: /api/v1/obsidian (P4-8-W1 obsidian submodule).
import { http } from './http'

export interface WikiPage {
  id: string                       // "page-<uuid>" / "tag-..." / "note-<slug>"
  title: string
  slug: string
  content_markdown: string
  tags: string[]
  outgoing_links: string[]         // titles or slugs
  backlinks: string[]
  created_at: string
  updated_at: string
  author: string
  word_count: number
  meta?: Record<string, unknown>
}

export interface WikiTag {
  name: string
  count: number
}

export interface GraphNode {
  id: string
  title: string
  group: 'page' | 'tag' | 'note'
  degree: number                   // num edges
  size: number                     // visual radius
  tags: string[]
  preview?: string                 // first 200 chars
}

export interface GraphEdge {
  source: string
  target: string
  kind: 'link' | 'tag' | 'backlink'
  weight: number
}

export interface GraphPayload {
  nodes: GraphNode[]
  edges: GraphEdge[]
  stats: { pages: number; tags: number; links: number; isolated: number }
}

export const obsidianApi = {
  // ----- Wiki CRUD -----
  listPages: (query: { tag?: string; keyword?: string; page?: number; page_size?: number } = {}) =>
    http.get<{ pages: WikiPage[]; total: number; page: number; page_size: number }>('/api/v1/obsidian/pages', { params: query }).then(r => r.data),
  getPage: (slug: string) => http.get<WikiPage>(`/api/v1/obsidian/pages/${slug}`).then(r => r.data),
  createPage: (body: { title: string; content_markdown?: string; tags?: string[] }) =>
    http.post<WikiPage>('/api/v1/obsidian/pages', body).then(r => r.data),
  updatePage: (slug: string, body: Partial<WikiPage>) => http.put<WikiPage>(`/api/v1/obsidian/pages/${slug}`, body).then(r => r.data),
  deletePage: (slug: string) => http.delete<{ deleted: boolean; slug: string }>(`/api/v1/obsidian/pages/${slug}`).then(r => r.data),

  // ----- Tags -----
  listTags: () => http.get<{ tags: WikiTag[] }>('/api/v1/obsidian/tags').then(r => r.data.tags),

  // ----- Search (full-text + fuzzy) -----
  search: (query: { keyword: string; limit?: number }) =>
    http.get<{ hits: Array<{ slug: string; title: string; snippet: string; score: number }> }>('/api/v1/obsidian/search', { params: query }).then(r => r.data.hits),

  // ----- Knowledge graph payload -----
  graph: () => http.get<GraphPayload>('/api/v1/obsidian/graph').then(r => r.data),
  graphSubset: (root: string, depth: number = 2) =>
    http.get<GraphPayload>(`/api/v1/obsidian/graph/subset`, { params: { root, depth } }).then(r => r.data),

  // ----- Autocomplete for [[link]] -----
  autocomplete: (prefix: string) =>
    http.get<{ candidates: Array<{ slug: string; title: string }> }>('/api/v1/obsidian/autocomplete', { params: { prefix } }).then(r => r.data.candidates),
}
