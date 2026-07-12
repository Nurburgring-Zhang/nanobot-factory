import { http } from './http'
// P5-R1-T4 retry: 真引用项目已有 annotation_system 模块 (前端 TS mirror)
import {
  AnnotationType as AS_AnnotationType,
  ANNOTATION_SYSTEM_TO_WORKBENCH,
  toWorkbenchType,
  type Point,
  type BoundingBox,
  ALL_ANNOTATION_TYPES,
} from './annotation_system'
import type { AnnotationType as _UnusedAnnotationType } from './annotation_system' // ensures tree-shake keeps it

// ---------------------------------------------------------------------------
// AnnotationWorkbench API client (P5-R1-T4)
// ---------------------------------------------------------------------------

export type GeometryType = 'rect' | 'polygon' | 'point' | 'keypoint' | 'obb' | 'mask'

/**
 * P5-R1-T4 retry: re-export annotation_system types so consumers (Annotation.vue)
 * can do `import { GeometryType, AS_AnnotationType, ANNOTATION_SYSTEM_TO_WORKBENCH }`
 * from this single module. Demonstrates real use of annotation_system enum values
 * rather than just workbench-local schema.
 */
export {
  AS_AnnotationType,
  ANNOTATION_SYSTEM_TO_WORKBENCH,
  toWorkbenchType,
  ALL_ANNOTATION_TYPES,
}
export type TaskStatus =
  | 'pending'
  | 'in_progress'
  | 'submitted'
  | 'in_review'
  | 'approved'
  | 'rejected'
  | 'closed'
export type ReviewStage = 'draft' | 'self_check' | 'peer_review' | 'final_review' | 'done'

export interface RectGeometry {
  x: number
  y: number
  width: number
  height: number
}
export interface PointGeometry {
  x: number
  y: number
}
export interface PolygonGeometry {
  points: Array<[number, number]>
}
export interface KeypointGeometry {
  points: Array<[number, number]>
  labels?: string[]
}
export interface OBBGeometry {
  cx: number
  cy: number
  w: number
  h: number
  angle: number
}
export interface MaskGeometry {
  rle?: number[]
  bitmap_url?: string
  counts?: string
  size?: [number, number]
}
export type Geometry =
  | RectGeometry
  | PointGeometry
  | PolygonGeometry
  | KeypointGeometry
  | OBBGeometry
  | MaskGeometry

export interface WorkbenchTask {
  id: string
  task_id: string
  asset_id: string
  status: TaskStatus
  locked_by: string | null
  locked_at: number | null
  lock_remaining_seconds?: number | null
  progress: number
  assigned_to: string | null
  due_date: string | null
  priority: number
  quality_score: number | null
  created_at: string
  updated_at: string
}

export interface AnnotationRecord {
  id: string
  task_id: string
  asset_id: string
  geometry_type: GeometryType
  geometry: Geometry
  label: string
  attributes: Record<string, unknown>
  confidence: number
  occluded: boolean
  truncated: boolean
  annotator_id: string | null
  created_at: string
  updated_at: string
  review_stage: ReviewStage
  parent_annotation_id: string | null
}

export interface LockStatus {
  task_id: string
  exists: boolean
  locked: boolean
  locked_by: string | null
  locked_at_epoch: number | null
  lock_remaining_seconds: number
  status?: TaskStatus
}

export interface WorkbenchStats {
  annotator_id: string | null
  task_status_breakdown: Record<string, number>
  annotation_count: number
  generated_at: string
}

// ---------------------------------------------------------------------------
// Endpoint wrappers
// ---------------------------------------------------------------------------
const BASE = '/api/v1/workbench'

export async function pullTask(body: {
  annotator_id: string
  task_type?: string
}): Promise<{ task: WorkbenchTask }> {
  return (await http.post(`${BASE}/pull`, body)).data
}

export async function releaseTask(body: {
  task_id: string
  annotator_id: string
}): Promise<{ success: boolean; task_id: string; released_by: string }> {
  return (await http.post(`${BASE}/release`, body)).data
}

export async function heartbeat(body: {
  task_id: string
  annotator_id: string
}): Promise<{ success: boolean; task_id: string; annotator_id: string; ts: number }> {
  return (await http.post(`${BASE}/heartbeat`, body)).data
}

export async function saveAnnotation(body: {
  task_id: string
  asset_id: string
  geometry_type: GeometryType
  geometry: Geometry
  label: string
  attributes?: Record<string, unknown>
  annotator_id?: string
  confidence?: number
  occluded?: boolean
  truncated?: boolean
  annotation_id?: string
  parent_annotation_id?: string
  review_stage?: ReviewStage
}): Promise<{ annotation: AnnotationRecord }> {
  return (await http.post(`${BASE}/annotations`, body)).data
}

export async function bulkSaveAnnotations(body: {
  task_id: string
  annotator_id?: string
  annotations: Array<Partial<{
    asset_id: string
    geometry_type: GeometryType
    geometry: Geometry
    label: string
    attributes: Record<string, unknown>
    annotator_id: string
    confidence: number
    occluded: boolean
    truncated: boolean
    annotation_id: string
    parent_annotation_id: string
    review_stage: ReviewStage
  }>>
}): Promise<{ saved: number; annotations: AnnotationRecord[] }> {
  return (await http.post(`${BASE}/annotations/bulk`, body)).data
}

export async function submitTask(body: {
  task_id: string
  annotator_id: string
}): Promise<{
  task_id: string
  status: TaskStatus
  submitted_by: string
  annotation_count: number
  progress: number
  next_stage: string
  submitted_at: string
}> {
  return (await http.post(`${BASE}/submit`, body)).data
}

export async function listTaskAnnotations(task_id: string): Promise<{
  task_id: string
  count: number
  annotations: AnnotationRecord[]
}> {
  return (await http.get(`${BASE}/tasks/${encodeURIComponent(task_id)}/annotations`)).data
}

export async function getAnnotationHistory(
  annotation_id: string
): Promise<{
  annotation_id: string
  history: Array<{
    id: number
    annotation_id: string
    editor_id: string | null
    action: string
    payload: Record<string, unknown>
    created_at: string
  }>
  exists: boolean
}> {
  return (await http.get(`${BASE}/annotations/${encodeURIComponent(annotation_id)}/history`)).data
}

export async function getLockStatus(task_id: string): Promise<LockStatus> {
  return (await http.get(`${BASE}/tasks/${encodeURIComponent(task_id)}/lock`)).data
}

export async function getStats(annotator_id?: string): Promise<WorkbenchStats> {
  return (await http.get(`${BASE}/stats`, { params: annotator_id ? { annotator_id } : {} })).data
}

// (内部) 入队
export async function enqueueTask(body: {
  task_id: string
  asset_id: string
  priority?: number
  assigned_to?: string
  due_date?: string
}): Promise<{ task: WorkbenchTask }> {
  return (await http.post(`${BASE}/enqueue`, body)).data
}