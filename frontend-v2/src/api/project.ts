/**
 * Project Center API client — P5-R1-T1
 *
 * 端点前缀: /api/v1/projects
 * - GET    /                          列表 (status/owner_id/keyword/priority/page/page_size)
 * - POST   /                          创建
 * - GET    /:id                       详情 (含 stats)
 * - PUT    /:id                       更新
 * - DELETE /:id                       删除
 * - POST   /:id/members               添成员
 * - DELETE /:id/members/:user_id      移除成员
 * - PATCH  /:id/status                状态机转换
 * - GET    /:id/stats                 统计
 * - GET    /:id/timeline              时间线
 */
import {
  getPage,
  getOne,
  createOne,
  updateOne,
  patchOne,
  deleteOne,
  http,
  type Page,
  type PageQuery
} from './http'

// ─────────────────────────────────────────────────────────────────────────────
// 类型定义
// ─────────────────────────────────────────────────────────────────────────────

export type ProjectStatus = 'planning' | 'active' | 'paused' | 'closed'
export type ProjectPriority = 'P0' | 'P1' | 'P2' | 'P3'
export type ProjectMemberRole = 'owner' | 'admin' | 'member' | 'viewer'

export interface Project {
  id: string
  name: string
  description: string
  status: ProjectStatus
  priority: ProjectPriority
  owner_id: string
  owner?: string // alias of owner_id (legacy p1_c_w1 兼容)
  members: string[]
  tags: string[]
  start_date: string
  due_date: string
  created_at: string
  updated_at: string
}

export interface ProjectCreate {
  name: string
  description?: string
  priority?: ProjectPriority
  tags?: string[]
  members?: string[]
  start_date?: string
  due_date?: string
  status?: ProjectStatus
}

export interface ProjectUpdate {
  name?: string
  description?: string
  priority?: ProjectPriority
  tags?: string[]
  members?: string[]
  start_date?: string
  due_date?: string
}

export interface ProjectMember {
  id: string
  project_id: string
  user_id: string
  role: ProjectMemberRole
  joined_at: string
}

export interface ProjectStats {
  project_id: string
  name: string
  status: ProjectStatus
  priority: ProjectPriority
  owner_id: string
  members_count: number
  requirements_count: number
  tasks_count: number
  datasets_count: number
  deliveries_count: number
  progress: number
  tags_count: number
  due_date: string
  created_at: string
  updated_at: string
}

export interface ProjectTimelineEvent {
  id: string
  project_id: string
  event_type: 'created' | 'updated' | 'status_changed' | 'member_added' | 'member_removed' | 'member_role_changed'
  actor: string
  ts: string
  payload: Record<string, unknown>
  message: string
}

export interface ProjectListQuery extends PageQuery {
  status?: ProjectStatus
  owner_id?: string
  priority?: ProjectPriority
}

// ─────────────────────────────────────────────────────────────────────────────
// 端点函数 (10 个, 与后端对齐)
// ─────────────────────────────────────────────────────────────────────────────

const BASE = '/api/v1/projects'

/** 列表 (返回 items/total + 分页元数据)。 */
export async function listProjects(query: ProjectListQuery = {}): Promise<Page<Project>> {
  return getPage<Project>(BASE, query)
}

/** 详情 (含 members + recent timeline)。 */
export async function getProject(id: string): Promise<Project & {
  members_detail?: ProjectMember[]
  recent_timeline?: ProjectTimelineEvent[]
}> {
  return getOne(`${BASE}/${id}`)
}

/** 创建。 */
export async function createProject(body: ProjectCreate): Promise<Project> {
  return createOne(BASE, body)
}

/** 更新 (任意字段)。 */
export async function updateProject(id: string, body: ProjectUpdate): Promise<Project> {
  return updateOne(`${BASE}/${id}`, body)
}

/** 删除。 */
export async function deleteProject(id: string): Promise<void> {
  return deleteOne(`${BASE}/${id}`)
}

/** 添加成员。 */
export async function addMember(
  id: string,
  user_id: string,
  role: ProjectMemberRole = 'member'
): Promise<Project> {
  return createOne(`${BASE}/${id}/members`, { user_id, role })
}

/** 移除成员 — 返回更新后的 Project (后端 PATCH 模式)。 */
export async function removeMember(id: string, user_id: string): Promise<Project> {
  const res = await http.delete<{ success: boolean; data: Project }>(
    `${BASE}/${id}/members/${user_id}`
  )
  return res.data.data
}

/** 状态机转换 (body: {status, reason})。 */
export async function updateStatus(
  id: string,
  status: ProjectStatus,
  reason: string = ''
): Promise<Project> {
  return patchOne(`${BASE}/${id}/status`, { status, reason })
}

/** 统计。 */
export async function getStats(id: string): Promise<ProjectStats> {
  const res = await http.get<{ success: boolean; data: ProjectStats }>(`${BASE}/${id}/stats`)
  return res.data.data
}

/** 时间线。 */
export async function getTimeline(id: string, limit: number = 100): Promise<{
  project_id: string
  events: ProjectTimelineEvent[]
  total: number
}> {
  const res = await http.get<{ success: boolean; data: any }>(`${BASE}/${id}/timeline`, {
    params: { limit }
  })
  return res.data.data
}