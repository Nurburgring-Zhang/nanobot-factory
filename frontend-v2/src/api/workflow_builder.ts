// VDP-2026 R2 — Workflow builder client.
//
// Lets users compose the R1 capability modules into executable workflows.
// Workflows are directed graphs:
//   - nodes carry `capability_id` + `inputs`
//   - edges connect nodes
//   - the backend runner walks in topological order invoking capabilities
import { http } from './http'
import { fetchCatalogue } from './capabilities_v2'
import type { CapabilityItem } from './capabilities_v2'

// Re-export so callers that already use capability types don't have to import
// from a second module.
export type { CapabilityItem } from './capabilities_v2'

const BASE = '/api/v1/workflow_builder'

// ---------------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------------

export interface WorkflowNode {
  id: string
  capability_id: string
  inputs: Record<string, unknown>
  depends_on: string[]
  position: { x: number, y: number }
  label: string
}

export interface WorkflowEdge {
  source: string
  target: string
  kind: 'data' | 'control'
}

export interface Workflow {
  id: string
  name: string
  description: string
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
  tags: string[]
  project_id: string
  created_at: string
  updated_at: string
}

export interface WorkflowStepResult {
  node_id: string
  capability_id: string
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped'
  outputs: Record<string, unknown>
  error: string
  duration_ms: number
  started_at: string
  finished_at: string
}

export interface WorkflowRun {
  id: string
  workflow_id: string
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  steps: WorkflowStepResult[]
  final_outputs: Record<string, unknown>
  started_at: string
  finished_at: string
  actor: string
}

// ---------------------------------------------------------------------------
// Vue Flow adapters
// ---------------------------------------------------------------------------

// We use Vue Flow's id-based node/edge JSON. Our backend `WorkflowNode` /
// `WorkflowEdge` are compatible — the adapter is essentially the canonical
// shape plus a label / sourceHandle / targetHandle that Vue Flow wants.

export interface VFNode {
  id: string
  type?: string
  position: { x: number, y: number }
  data: {
    capability_id: string
    capability_name?: string
    capability_category?: string
    inputs: Record<string, unknown>
    depends_on: string[]
    label: string
  }
  label: string
}

export interface VFEdge {
  id: string
  source: string
  target: string
  sourceHandle?: string
  targetHandle?: string
  label?: string
  type?: string
  data?: Record<string, unknown>
}

export function nodesFromWorkflow(wf: Workflow, catalogue?: CapabilityItem[]): { nodes: VFNode[], edges: VFEdge[] } {
  const cat_by_id = new Map<string, CapabilityItem>()
  if (catalogue) for (const c of catalogue) cat_by_id.set(c.id, c)
  const nodes: VFNode[] = wf.nodes.map((n) => {
    const cap = cat_by_id.get(n.capability_id)
    return {
      id: n.id,
      type: 'default',
      position: { x: n.position?.x ?? 0, y: n.position?.y ?? 0 },
      data: {
        capability_id: n.capability_id,
        capability_name: cap?.name || n.label || n.capability_id,
        capability_category: cap?.category,
        inputs: n.inputs || {},
        depends_on: n.depends_on || [],
        label: n.label || cap?.name || n.capability_id,
      },
      label: n.label || cap?.name || n.capability_id,
    }
  })
  const edges: VFEdge[] = wf.edges.map((e, idx) => ({
    id: `e_${e.source}_${e.target}_${idx}`,
    source: e.source,
    target: e.target,
    type: 'smoothstep',
    data: { kind: e.kind },
  }))
  return { nodes, edges }
}

export function workflowFromNodes(nodes: VFNode[], edges: VFEdge[]): Partial<Workflow> {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      capability_id: n.data.capability_id,
      inputs: n.data.inputs || {},
      depends_on: n.data.depends_on || [],
      position: n.position,
      label: n.data.label,
    })),
    edges: edges.map((e) => ({
      source: e.source,
      target: e.target,
      kind: (e.data as { kind?: string })?.kind as 'data' | 'control' || 'data',
    })),
  }
}

// ---------------------------------------------------------------------------
// HTTP
// ---------------------------------------------------------------------------

export interface TemplatesResponse {
  total: number
  items: Workflow[]
}

export async function listTemplates(): Promise<TemplatesResponse> {
  return (await http.get(`${BASE}/templates`)).data
}

export async function reloadTemplates(): Promise<{ ok: boolean, loaded: number }> {
  return (await http.post(`${BASE}/templates/reload`)).data
}

export async function listWorkflows(
  project_id?: string,
  limit = 200,
): Promise<{ total: number, items: Workflow[] }> {
  return (await http.get(`${BASE}/workflows`, {
    params: { project_id, limit },
  })).data
}

export async function getWorkflow(id: string): Promise<Workflow> {
  return (await http.get(`${BASE}/workflows/${encodeURIComponent(id)}`)).data
}

export async function saveWorkflow(wf: Partial<Workflow> & { id?: string, name: string }): Promise<Workflow> {
  return (await http.post(`${BASE}/workflows`, wf)).data
}

export async function deleteWorkflow(id: string): Promise<{ ok: boolean, id: string }> {
  return (await http.delete(`${BASE}/workflows/${encodeURIComponent(id)}`)).data
}

export async function runWorkflow(
  id: string,
  actor = 'system',
  refs: Record<string, string> = {},
): Promise<WorkflowRun> {
  return (await http.post(`${BASE}/workflows/${encodeURIComponent(id)}/run`, { actor, refs })).data
}

export async function listRuns(workflow_id?: string, limit = 50): Promise<{ total: number, items: WorkflowRun[] }> {
  return (await http.get(`${BASE}/runs`, { params: { workflow_id, limit } })).data
}

export async function getRun(id: string): Promise<WorkflowRun> {
  return (await http.get(`${BASE}/runs/${encodeURIComponent(id)}`)).data
}

export async function wbHealth(): Promise<{ status: string, workflows_saved: number, starter_templates: number }> {
  return (await http.get(`${BASE}/health`)).data
}

export async function fetchCatalogueCached(): Promise<CapabilityItem[]> {
  const r = await fetchCatalogue()
  return r.items
}
