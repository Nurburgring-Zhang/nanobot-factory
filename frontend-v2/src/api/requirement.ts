/**
 * Requirement Center API Client — 需求中心 (P5-R1-T2)
 *
 * 9 个核心函数:
 *   1. listRequirements        列表 (分页 + 过滤)
 *   2. getRequirement          单个需求详情
 *   3. createRequirement       创建需求 (含 project_id 关联)
 *   4. updateRequirementMeta   更新需求关联元数据 (project/pack/qc/delivery/due/owner)
 *   5. decomposePreview        预览拆解 (不真拆)
 *   6. decomposeRequirement    真实拆解
 *   7. reassignTasks           重派任务 (按 strategy)
 *   8. getRequirementStats     需求统计
 *   9. closeRequirement        关闭需求
 */
import { http } from './http'

// 与后端 Pydantic Literal 对齐 (允许值集合)
export type RequirementType = 'general' | 'feature' | 'bug' | 'improvement'
export type RequirementPriority = 'low' | 'medium' | 'high' | 'critical'
export type RequirementStatus =
  | 'draft' | 'open' | 'in_progress' | 'review' | 'done' | 'closed'
export type QCStatus = 'not_started' | 'in_progress' | 'passed' | 'failed'
export type ReassignStrategy = 'by_skill' | 'by_workload' | 'random' | 'hybrid'

/** 单条需求 */
export interface RequirementItem {
  id: string
  title: string
  type: string  // engine 层 type (data_annotation/data_collection/...)
  status: RequirementStatus
  priority: string  // engine 层 priority (P0..P3)
  description?: string
  acceptance_criteria?: string
  tags?: string[]
  created_by?: string
  created_at?: string
  updated_at?: string
  closed_at?: string
  // P5-R1-T2 新增: 与 ProjectCenter / Pack / QC / Delivery 关联
  project_id?: string | null
  pack_id?: string | null
  qc_status?: QCStatus | null
  delivery_id?: string | null
  due_date?: string
  owner?: string
}

/** 创建需求 body */
export interface RequirementCreate {
  title: string
  type?: RequirementType
  priority?: RequirementPriority
  description?: string
  acceptance_criteria?: string
  tags?: string[]
  project_id?: string
  pack_id?: string
  qc_status?: QCStatus
  delivery_id?: string
  due_date?: string
  owner?: string
}

/** 更新需求关联元数据 body */
export interface RequirementMetaUpdate {
  project_id?: string | null
  pack_id?: string | null
  qc_status?: QCStatus
  delivery_id?: string | null
  due_date?: string | null
  owner?: string | null
}

/** 列表查询参数 */
export interface RequirementListQuery {
  project_id?: string
  status?: RequirementStatus
  type?: string
  priority?: string
  keyword?: string
  page?: number
  page_size?: number
}

/** 列表响应 */
export interface RequirementListResponse {
  items: RequirementItem[]
  total: number
  page: number
  page_size: number
}

/** 拆解预览 */
export interface DecomposePreviewTask {
  title: string
  estimated_hours: number
  acceptance_criteria: string
}

export interface DecomposePreview {
  requirement_id: string
  title: string
  type: string
  complexity: 'low' | 'medium' | 'high'
  estimated_hours: number
  task_count: number
  tasks: DecomposePreviewTask[]
}

/** 拆解结果 */
export interface DecomposeResult {
  requirement_id: string
  task_count: number
  tasks: any[]
}

/** 统计 */
export interface RequirementStats {
  requirement: RequirementItem
  tasks_count: number
  approved_count: number
  rejected_count: number
  in_progress_count: number
  pending_count: number
  submitted_count: number
  blocked_count: number
  packs_count: number
  progress: number
  status_flow: string[]
  current_step: number
  assignee_breakdown: Record<string, number>
  task_tree: Array<{
    id: string
    title: string
    status: string
    assignee: string
    priority: string
    estimated_hours: number
    actual_hours: number
  }>
  qc_status: string
}

/** 重派 body */
export interface ReassignBody {
  strategy: ReassignStrategy
  skill_requirements?: string[]
}

const BASE = '/api/requirements'

// ─────────────────────────────────────────────────────────────────
// 9 函数实现
// ─────────────────────────────────────────────────────────────────

/**
 * 1. 列表 (分页 + 过滤) — 与 ProjectCenter 通过 project_id 关联
 */
export async function listRequirements(
  query: RequirementListQuery = {}
): Promise<RequirementListResponse> {
  const params: Record<string, string | number> = {}
  if (query.project_id) params.project_id = query.project_id
  if (query.status) params.status = query.status
  if (query.type) params.type = query.type
  if (query.priority) params.priority = query.priority
  if (query.keyword) params.keyword = query.keyword
  params.page = query.page ?? 1
  params.page_size = query.page_size ?? 20
  const res = await http.get<{
    success: boolean
    data: { items: RequirementItem[]; total: number }
    page: number
    page_size: number
  }>(BASE + '/', { params })
  const data = res.data?.data ?? { items: [], total: 0 }
  return {
    items: data.items ?? [],
    total: data.total ?? 0,
    page: res.data?.page ?? 1,
    page_size: res.data?.page_size ?? 20,
  }
}

/**
 * 2. 单个需求详情 — 走 stats 接口拿到完整结构
 */
export async function getRequirement(reqId: string): Promise<RequirementStats> {
  const res = await http.get<{ success: boolean; data: RequirementStats }>(
    `${BASE}/${encodeURIComponent(reqId)}/stats`
  )
  return res.data.data
}

/**
 * 3. 创建需求 — 支持 project_id 关联
 */
export async function createRequirement(body: RequirementCreate): Promise<RequirementItem> {
  const res = await http.post<{ success: boolean; data: RequirementItem }>(
    `${BASE}/create`,
    body
  )
  return res.data.data
}

/**
 * 4. 更新需求关联元数据
 */
export async function updateRequirementMeta(
  reqId: string,
  body: RequirementMetaUpdate
): Promise<RequirementItem> {
  const res = await http.put<{ success: boolean; data: RequirementItem }>(
    `${BASE}/${encodeURIComponent(reqId)}/meta`,
    body
  )
  return res.data.data
}

/**
 * 5. 拆解预览 (不真拆)
 */
export async function decomposePreview(reqId: string): Promise<DecomposePreview> {
  const res = await http.get<{ success: boolean; data: DecomposePreview }>(
    `${BASE}/${encodeURIComponent(reqId)}/decompose-preview`
  )
  return res.data.data
}

/**
 * 6. 真实拆解 (创建子任务)
 */
export async function decomposeRequirement(reqId: string): Promise<DecomposeResult> {
  const res = await http.post<{ success: boolean; data: DecomposeResult }>(
    `${BASE}/${encodeURIComponent(reqId)}/decompose`,
    {}
  )
  return res.data.data
}

/**
 * 7. 重派任务 (按 strategy)
 */
export async function reassignTasks(
  reqId: string,
  body: ReassignBody
): Promise<{ requirement_id: string; strategy: ReassignStrategy; reassigned_count: number }> {
  const res = await http.post<{
    success: boolean
    data: { requirement_id: string; strategy: ReassignStrategy; reassigned_count: number }
  }>(`${BASE}/${encodeURIComponent(reqId)}/reassign`, body)
  return res.data.data
}

/**
 * 8. 需求统计 (含 tasks_count / packs_count / progress%)
 */
export async function getRequirementStats(reqId: string): Promise<RequirementStats> {
  const res = await http.get<{ success: boolean; data: RequirementStats }>(
    `${BASE}/${encodeURIComponent(reqId)}/stats`
  )
  return res.data.data
}

/**
 * 9. 关闭需求
 */
export async function closeRequirement(
  reqId: string,
  reason?: string
): Promise<{ status: string; requirement_id: string; reason?: string }> {
  const res = await http.post<{
    success: boolean
    data: { status: string; requirement_id: string; reason?: string }
  }>(`${BASE}/close`, { requirement_id: reqId, reason })
  return res.data.data
}