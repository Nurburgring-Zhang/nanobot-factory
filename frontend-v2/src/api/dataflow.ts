// VDP-2026 R1 — Data flow tracker client.
//
// The tracker reconstructs a project/requirement/dataset/pack/delivery flow
// from the 8-stage canonical pipeline:
//
//   project → requirement → dataset → pack → annotation → review → qc
//                                                                  ↓
//                                                          acceptance → delivery
//
// The frontend consumes the snapshot endpoint to render an ECharts sankey or
// per-stage progress bar.
import { http } from './http'

const BASE = '/api/v1/dataflow'

export interface FlowStageMeta {
  stage: string
  label: string
  color: string
}

export interface FlowStageNode extends FlowStageMeta {
  event_count: number
  last_event_at: string
  last_payload: Record<string, unknown>
}

export interface FlowTimelineEvent {
  id: number
  subject: string
  stage: string
  actor: string
  created_at: string
  project_id: string
  pack_id: string
  delivery_id: string
}

export interface FlowSnapshot {
  project_id: string | null
  requirement_id: string | null
  dataset_id: string | null
  pack_id: string | null
  delivery_id: string | null
  stages: FlowStageNode[]
  timeline: FlowTimelineEvent[]
  generated_at: string
  total_events: number
}

export interface StagesResponse {
  stages: (FlowStageMeta & { event_count: number })[]
  total_events: number
}

export async function fetchStages(): Promise<StagesResponse> {
  return (await http.get(`${BASE}/stages`)).data
}

export interface EventsResponse {
  total: number
  items: Array<{
    id: number
    subject: string
    payload: Record<string, unknown>
    actor: string
    project_id: string
    requirement_id: string
    dataset_id: string
    pack_id: string
    delivery_id: string
    created_at: string
  }>
}

export async function fetchEvents(project_id?: string, limit = 200): Promise<EventsResponse> {
  return (await http.get(`${BASE}/events`, {
    params: { project_id, limit },
  })).data
}

export interface SnapshotQuery {
  project_id?: string
  requirement_id?: string
  dataset_id?: string
  pack_id?: string
  delivery_id?: string
}

export async function fetchSnapshot(q: SnapshotQuery): Promise<FlowSnapshot> {
  const params: Record<string, string> = {}
  Object.entries(q).forEach(([k, v]) => {
    if (v) params[k] = String(v)
  })
  return (await http.get(`${BASE}/snapshot`, { params })).data
}

export interface SubjectMap {
  subject_to_stage: Record<string, string>
  stages: FlowStageMeta[]
}

export async function fetchSubjectMap(): Promise<SubjectMap> {
  return (await http.get(`${BASE}/subjects`)).data
}

export async function dataflowHealth(): Promise<{ status: string, events_recent: number }> {
  return (await http.get(`${BASE}/health`)).data
}
