// frontend-v2/src/api/lineage.ts
// P4-8-W2: data lineage graph API client (P4-4 lineage-service).
// Base path: /api/v1/lineage.
import { http } from './http'

export type LineageNodeKind = 'dataset' | 'table' | 'column' | 'job' | 'model'

export interface LineageNode {
  id: string
  label: string
  kind: LineageNodeKind
  layer: number                    // 0=root dataset ... deeper = column
  description?: string
  meta?: Record<string, unknown>
  size: number                     // number of rows / columns / etc
}

export interface LineageEdge {
  source: string
  target: string
  kind: 'derives_from' | 'transforms' | 'uses' | 'produces' | 'references'
  label?: string
  weight: number
}

export interface LineageGraph {
  nodes: LineageNode[]
  edges: LineageEdge[]
  root: string
  stats: { nodes: number; edges: number; max_depth: number }
}

export interface LineageImpact {
  upstream: LineageNode[]
  downstream: LineageNode[]
  affected_jobs: string[]
  estimated_blast_radius: number
}

export const lineageApi = {
  graph: (root: string, depth: number = 3) =>
    http.get<LineageGraph>('/api/v1/lineage/graph', { params: { root, depth } }).then(r => r.data),
  impact: (nodeId: string) =>
    http.get<LineageImpact>(`/api/v1/lineage/impact/${encodeURIComponent(nodeId)}`).then(r => r.data),
  search: (keyword: string) =>
    http.get<{ nodes: LineageNode[] }>('/api/v1/lineage/search', { params: { keyword } }).then(r => r.data.nodes),
  listDatasets: () =>
    http.get<{ datasets: LineageNode[] }>('/api/v1/lineage/datasets').then(r => r.data.datasets),
}
