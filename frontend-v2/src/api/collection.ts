import { http } from './http'

// ==================== Type Definitions ====================

export type SourceType = 'rss' | 'crawler' | 'api' | 'import'
export type JobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface RssFeed {
  id: string
  name: string
  url: string
  status: string
  item_count: number
  created_at: string
  last_refreshed?: string | null
}

export interface CrawlerJob {
  id: string
  name: string
  url: string
  selectors?: Record<string, string>
  max_pages?: number
  delay?: number
  output_format?: string
  user_agent?: string
  status: string
  created_at: string
  items_collected: number
  source_type?: 'crawler'
}

export interface ApiConfig {
  id: string
  name: string
  endpoint: string
  method: string
  pagination?: string
  page_size?: number
  max_pages?: number
  headers?: Record<string, string>
  data_path?: string
  created_at: string
  source_type?: 'api'
}

export interface ImportItem {
  id?: string
  name?: string
  source?: string
  format?: string
  status?: string
  items_collected?: number
  created_at?: string
  type?: string
}

export interface Backup {
  id: string
  filename: string
  size: number
  created_at: string
  status: string
  item_count: number
}

export interface CollectionSources {
  rss: RssFeed[]
  crawler: CrawlerJob[]
  api: ApiConfig[]
  import: ImportItem[]
}

// ==================== Sources ====================

const BASE = '/api/v1/collection'

export async function listSources(type?: SourceType): Promise<CollectionSources> {
  const res = await http.get<{ success: boolean; data: CollectionSources }>(
    `${BASE}/sources`,
    { params: type ? { type } : {} },
  )
  return res.data.data
}

// ==================== RSS ====================

export async function createRss(body: {
  name: string
  url: string
  category?: string
  refresh_interval_minutes?: number
}): Promise<RssFeed> {
  const res = await http.post<{ success: boolean; data: RssFeed }>(
    `${BASE}/sources/rss`, body,
  )
  return res.data.data
}

export async function refreshRss(feed_id: string): Promise<RssFeed> {
  const res = await http.post<{ success: boolean; data: RssFeed; message: string }>(
    `${BASE}/sources/rss/${feed_id}/refresh`, {},
  )
  return res.data.data
}

export async function refreshAllRss(): Promise<any> {
  const res = await http.post(`${BASE}/sources/rss/refresh-all`, {})
  return res.data.data
}

export async function deleteRss(feed_id: string): Promise<void> {
  await http.delete(`${BASE}/sources/rss/${feed_id}`)
}

// ==================== Crawler ====================

export async function createCrawler(body: {
  name: string
  url: string
  selectors?: Record<string, string>
  max_pages?: number
  delay?: number
  output_format?: string
  user_agent?: string
}): Promise<CrawlerJob> {
  const res = await http.post<{ success: boolean; data: CrawlerJob }>(
    `${BASE}/sources/crawler`, body,
  )
  return res.data.data
}

export async function getCrawler(job_id: string): Promise<CrawlerJob> {
  const res = await http.get<{ success: boolean; data: CrawlerJob }>(
    `${BASE}/sources/crawler/${job_id}`,
  )
  return res.data.data
}

// ==================== API ====================

export async function createApiConfig(body: {
  name: string
  endpoint: string
  method?: string
  pagination?: string
  page_size?: number
  max_pages?: number
  headers?: Record<string, string>
  data_path?: string
  schedule_cron?: string
}): Promise<ApiConfig> {
  const res = await http.post<{ success: boolean; data: ApiConfig }>(
    `${BASE}/sources/api`, body,
  )
  return res.data.data
}

// ==================== Jobs ====================

export interface JobItem {
  id: string
  name?: string
  url?: string
  endpoint?: string
  source_type: SourceType
  status: string
  items_collected?: number
  item_count?: number
  created_at?: string
  last_refreshed?: string
  [k: string]: any
}

export async function listJobs(query: {
  status?: JobStatus
  source_type?: SourceType
  limit?: number
} = {}): Promise<{ jobs: JobItem[]; total: number }> {
  const res = await http.get<{ success: boolean; data: { jobs: JobItem[]; total: number } }>(
    `${BASE}/jobs`, { params: query },
  )
  return res.data.data
}

export async function getJob(job_id: string): Promise<JobItem> {
  const res = await http.get<{ success: boolean; data: JobItem }>(`${BASE}/jobs/${job_id}`)
  return res.data.data
}

export async function cancelJob(job_id: string): Promise<any> {
  const res = await http.post(`${BASE}/jobs/${job_id}/cancel`, {})
  return res.data
}

export async function getJobItems(job_id: string, page = 1, page_size = 20): Promise<{
  items: any[]
  total: number
  page: number
  page_size: number
}> {
  const res = await http.get(`${BASE}/jobs/${job_id}/items`, {
    params: { page, page_size },
  })
  return res.data.data
}

export async function jobToDataset(job_id: string): Promise<{
  dataset_name: string
  version: string
  items_collected: number
  source_type: string
  warning?: string
}> {
  const res = await http.post(`${BASE}/jobs/${job_id}/to-dataset`, {})
  return res.data.data
}

// ==================== Backups ====================

export async function listBackups(): Promise<Backup[]> {
  const res = await http.get<{ success: boolean; data: Backup[] }>(`${BASE}/backups`)
  return res.data.data
}

export async function createBackup(): Promise<Backup> {
  const res = await http.post<{ success: boolean; data: Backup }>(`${BASE}/backups`, {})
  return res.data.data
}

export async function restoreBackup(backup_id: string): Promise<any> {
  const res = await http.post(`${BASE}/backups/${backup_id}/restore`, {})
  return res.data
}

export async function deleteBackup(backup_id: string): Promise<any> {
  const res = await http.delete(`${BASE}/backups/${backup_id}`)
  return res.data
}

// ==================== Constants ====================

export const SOURCE_TYPE_OPTIONS: Array<{ label: string; value: SourceType }> = [
  { label: 'RSS 订阅', value: 'rss' },
  { label: '爬虫', value: 'crawler' },
  { label: 'API 拉取', value: 'api' },
  { label: '文件导入', value: 'import' },
]

export const JOB_STATUS_OPTIONS: Array<{ label: string; value: JobStatus }> = [
  { label: '待处理', value: 'pending' },
  { label: '运行中', value: 'running' },
  { label: '已完成', value: 'completed' },
  { label: '失败', value: 'failed' },
  { label: '已取消', value: 'cancelled' },
]