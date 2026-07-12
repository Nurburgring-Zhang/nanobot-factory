import { getPage, getOne, createOne, updateOne, deleteOne, http, type Page, type PageQuery } from './http'

// ==================== Type Definitions ====================

export type PackType = 'data_pack' | 'task_pack'
export type PackSource = 'upload' | 'collection' | 'transfer' | 'generation'
export type PackStatus = 'created' | 'ready' | 'in_annotation' | 'annotated' | 'reviewed' | 'qc_passed' | 'delivered'
export type TaskType = 'annotation' | 'cleaning' | 'scoring' | 'review' | 'augmentation' | 'evaluation'

export interface PackItem {
  id: string
  name: string
  type: PackType
  has_data: boolean
  source: PackSource
  status: PackStatus
  requirement_id: string
  project_id: string
  asset_count: number
  dataset_id: string
  task_type: string
  metadata: Record<string, any>
  route_history: Array<{
    action: string
    [k: string]: any
    at?: string
  }>
  created_at: string
  updated_at: string
}

export interface PackCreate {
  name: string
  type: PackType
  has_data?: boolean
  source?: PackSource
  requirement_id?: string
  project_id?: string
  asset_ids?: string[]
  asset_type?: string
  task_type?: TaskType
  asset_count?: number
  metadata?: Record<string, any>
}

export interface PackUpdate {
  name?: string
  status?: PackStatus
  metadata?: Record<string, any>
  asset_count?: number
}

export interface PackTransition {
  new_status: PackStatus
  reason?: string
}

export interface PackLinkDataset {
  dataset_id: string
}

export interface PackStats {
  pack_id: string
  name: string
  type: PackType
  status: PackStatus
  progress_pct: number
  completion_rate: number
  asset_count: number
  has_data: boolean
  linked_dataset: string | null
  route_count: number
  created_at: string
  updated_at: string
}

export interface PackRouteResult {
  pack_id: string
  target_module: 'annotation' | 'collection'
  target_endpoint: string
  reason: string
  estimated_steps: string[]
  routed_at: string
}

// ==================== API Functions ====================

const BASE = '/api/v1/packs'

export async function listPacks(query: PageQuery & {
  requirement_id?: string
  project_id?: string
  type?: PackType
  status?: PackStatus
  keyword?: string
} = {}): Promise<Page<PackItem>> {
  return getPage<PackItem>(BASE, query)
}

export async function getPack(id: string): Promise<PackItem> {
  const res = await http.get<{ success: boolean; data: PackItem }>(`${BASE}/${id}`)
  return res.data.data
}

export async function createPack(body: PackCreate): Promise<PackItem> {
  const res = await http.post<{ success: boolean; data: PackItem }>(BASE, body)
  return res.data.data
}

export async function updatePack(id: string, body: PackUpdate): Promise<PackItem> {
  const res = await http.put<{ success: boolean; data: PackItem }>(`${BASE}/${id}`, body)
  return res.data.data
}

export async function deletePack(id: string): Promise<void> {
  await deleteOne(`${BASE}/${id}`)
}

export async function routePack(id: string): Promise<PackRouteResult> {
  const res = await http.post<{ success: boolean; data: PackRouteResult }>(`${BASE}/${id}/route`)
  return res.data.data
}

export async function linkPackToDataset(id: string, dataset_id: string): Promise<PackItem> {
  const res = await http.post<{ success: boolean; data: PackItem }>(
    `${BASE}/${id}/link-dataset`,
    { dataset_id },
  )
  return res.data.data
}

export async function getPackStats(id: string): Promise<PackStats> {
  const res = await http.get<{ success: boolean; data: PackStats }>(`${BASE}/${id}/stats`)
  return res.data.data
}

export async function transitionPack(id: string, body: PackTransition): Promise<PackItem> {
  const res = await http.post<{ success: boolean; data: PackItem }>(
    `${BASE}/${id}/transition`,
    body,
  )
  return res.data.data
}

// ==================== Constants ====================

export const PACK_TYPE_OPTIONS: Array<{ label: string; value: PackType }> = [
  { label: '数据包', value: 'data_pack' },
  { label: '任务包', value: 'task_pack' },
]

export const PACK_STATUS_OPTIONS: Array<{ label: string; value: PackStatus }> = [
  { label: '已创建', value: 'created' },
  { label: '就绪', value: 'ready' },
  { label: '标注中', value: 'in_annotation' },
  { label: '已标注', value: 'annotated' },
  { label: '已审核', value: 'reviewed' },
  { label: '质检通过', value: 'qc_passed' },
  { label: '已交付', value: 'delivered' },
]

export const PACK_STATUS_PROGRESS: Record<PackStatus, number> = {
  created: 0,
  ready: 10,
  in_annotation: 30,
  annotated: 55,
  reviewed: 75,
  qc_passed: 90,
  delivered: 100,
}

export const PACK_SOURCE_OPTIONS: Array<{ label: string; value: PackSource }> = [
  { label: '上传', value: 'upload' },
  { label: '采集', value: 'collection' },
  { label: '传输', value: 'transfer' },
  { label: '生成', value: 'generation' },
]

export const TASK_TYPE_OPTIONS: Array<{ label: string; value: TaskType }> = [
  { label: '标注', value: 'annotation' },
  { label: '清洗', value: 'cleaning' },
  { label: '评分', value: 'scoring' },
  { label: '审核', value: 'review' },
  { label: '增强', value: 'augmentation' },
  { label: '评测', value: 'evaluation' },
]