// 智影 V4 — Intelligence API client (智能数据采集 + 全 Agent 驱动)
import { http } from './http'

export interface ChatResponse {
  session_id: string
  user_text: string
  intent: string
  action: string
  success: boolean
  response: string
  output?: any
  suggestions: string[]
  error?: string
  duration_ms: number
}

export interface ChatRequest {
  text: string
  session_id?: string | null
  user_id?: string
}

export interface CrawlRequest {
  url: string
  channel?: string
  max_pages?: number
  max_depth?: number
  strategy?: string
  compliance_mode?: string
}

export interface CrawlResponse {
  success: boolean
  url: string
  channel: string
  items: any[]
  total_crawled: number
  total_kept: number
  metrics: Record<string, any>
  error?: string
}

export interface SearchRequest {
  query: string
  provider?: string
  max_results?: number
}

export interface SessionInfo {
  session_id: string
  user_id: string
  started_at: number
  last_active: number
  history_count: number
  working_set_size: number
  status: string
}

const BASE = '/api/v1/intelligence'

export async function getOverview(): Promise<{
  name: string
  version: string
  modules: { crawler_channels: number; platform_agents: number; intent_actions: number }
  agents: string[]
}> {
  const r = await http.get(`${BASE}/`)
  return r.data
}

export async function getChannels(): Promise<{ success: boolean; channels: string[]; total: number }> {
  const r = await http.get(`${BASE}/channels`)
  return r.data
}

export async function getAgents(): Promise<{ success: boolean; agents: any[] }> {
  const r = await http.get(`${BASE}/agents`)
  return r.data
}

export async function getActions(): Promise<{ success: boolean; actions: string[]; total: number }> {
  const r = await http.get(`${BASE}/actions`)
  return r.data
}

export async function getStatus(): Promise<{ success: boolean; status: any }> {
  const r = await http.get(`${BASE}/status`)
  return r.data
}

export async function getHelp(): Promise<{ success: boolean; text: string }> {
  const r = await http.get(`${BASE}/help`)
  return r.data
}

export async function chat(req: ChatRequest): Promise<ChatResponse> {
  const r = await http.post<ChatResponse>(`${BASE}/chat`, req)
  return r.data
}

export async function chatText(text: string, sessionId?: string, userId = 'web-user'): Promise<ChatResponse> {
  const r = await http.get<ChatResponse>(`${BASE}/chat`, {
    params: { text, session_id: sessionId, user_id: userId }
  })
  return r.data
}

export async function crawl(req: CrawlRequest): Promise<CrawlResponse> {
  const r = await http.post<CrawlResponse>(`${BASE}/crawl`, req)
  return r.data
}

export async function search(req: SearchRequest): Promise<any> {
  const r = await http.post(`${BASE}/search`, req)
  return r.data
}

export async function listSessions(userId?: string): Promise<{ success: boolean; sessions: SessionInfo[] }> {
  const r = await http.get(`${BASE}/sessions`, { params: userId ? { user_id: userId } : {} })
  return r.data
}

export async function getSession(sessionId: string, historyLimit = 20): Promise<{
  success: boolean
  session: SessionInfo
  history: any[]
  last_intent: any
  variables: Record<string, any>
}> {
  const r = await http.get(`${BASE}/sessions/${sessionId}`, { params: { history_limit: historyLimit } })
  return r.data
}

export async function closeSession(sessionId: string): Promise<{ success: boolean; session_id: string; status: string }> {
  const r = await http.delete(`${BASE}/sessions/${sessionId}`)
  return r.data
}

export function getChatWebSocketURL(sessionId?: string, userId = 'web-user'): string {
  const base = (import.meta.env.VITE_WS_BASE || (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host)
  const params = new URLSearchParams()
  if (sessionId) params.append('session_id', sessionId)
  params.append('user_id', userId)
  return `${base}${BASE.replace(/^\/api/, '')}/ws/chat?${params.toString()}`
}
