// 智影 V5 — Frontend TypeScript API (Identity + Memory + Harness + Roles + MCP + Proactive + Monitor + Geo + Profile + Perf + Video + Brand + Data + Cron + Goals + Skills + MoA)
import type { AxiosInstance, AxiosResponse } from 'axios'

export interface V5Bot {
  bot_id: string
  name: string
  role: string
  description?: string
  team?: string
  status?: string
}

export interface V5MemoryItem {
  item_id: string
  layer: string
  title: string
  content: string
  source?: string
  created_at?: number
}

export interface V5Plan {
  plan_id: string
  steps_count: number
  steps: Array<{ step_id: string; type: string; title: string; description: string }>
}

export interface V5Role {
  role_id: string
  name: string
  department: string
  description?: string
}

export interface V5VideoProject {
  project_id: string
  status: string
  prompt?: string
}

export interface V5Goal {
  name: string
  result: string
  status: string
  sources?: string[]
  deliverables?: string[]
}

export interface V5Skill {
  name: string
  description: string
}

export interface V5McpTool {
  name: string
  description: string
}

export interface V5Platform {
  name: string
  value: string
  category: string
}

export interface V5Profile {
  user_id: string
  username: string
  display_name?: string
  identity?: string
  preferences?: string[]
}

export interface V5Stats {
  identity: any
  memory: any
  palace: any
  feedback: any
  roles: any
  mcp: any
  proactive: any
  data_gateway: any
  profile: any
  perf_cache: any
}

export class V5Client {
  constructor(private http: AxiosInstance) {}

  // ===== Health & Stats =====
  async health() {
    return (await this.http.get('/api/v5/health')).data
  }
  async stats(): Promise<V5Stats> {
    return (await this.http.get('/api/v5/stats')).data
  }

  // ===== Identity =====
  async registerBot(payload: { name: string; role: string; description?: string; team?: string; department?: string; tags?: string[] }): Promise<V5Bot> {
    return (await this.http.post('/api/v5/bots/register', payload)).data
  }
  async listBots(role?: string, team?: string): Promise<{ bots: V5Bot[]; count: number }> {
    return (await this.http.get('/api/v5/bots', { params: { role, team } })).data
  }
  async createChannel(payload: { name: string; channel_type?: string; description?: string }) {
    return (await this.http.post('/api/v5/channels', payload)).data
  }
  async createThread(payload: { title: string; channel_id?: string; creator_id?: string }) {
    return (await this.http.post('/api/v5/threads', payload)).data
  }
  async createMatter(payload: { title: string; description?: string; owner_id?: string; thread_id?: string }) {
    return (await this.http.post('/api/v5/matters', payload)).data
  }

  // ===== Memory =====
  async addRawMemory(title: string, content: string, source = '') {
    return (await this.http.post('/api/v5/memory/raw', { title, content, source })).data
  }
  async addInboxMemory(title: string, content: string) {
    return (await this.http.post('/api/v5/memory/inbox', { title, content })).data
  }
  async promoteToLongTerm(itemId: string) {
    return (await this.http.post(`/api/v5/memory/promote/${itemId}`)).data
  }
  async queryMemory(q: string, layers?: string[]): Promise<{ count: number; items: V5MemoryItem[] }> {
    return (await this.http.get('/api/v5/memory/query', { params: { q, layers: (layers || []).join(',') } })).data
  }
  async installPalace() {
    return (await this.http.post('/api/v5/palace/install')).data
  }
  async recordFeedback(targetId: string, type: string, comment = '') {
    return (await this.http.post('/api/v5/feedback', { target_id: targetId, feedback_type: type, comment })).data
  }

  // ===== Harness =====
  async planHarness(prompt: string): Promise<V5Plan> {
    return (await this.http.post('/api/v5/harness/plan', { prompt })).data
  }
  async runHarness(prompt: string, maxIterations = 3) {
    return (await this.http.post('/api/v5/harness/run', { prompt, max_iterations: maxIterations })).data
  }
  async harnessStats() {
    return (await this.http.get('/api/v5/harness/stats')).data
  }

  // ===== Skills =====
  async listSkills(): Promise<{ skills: V5Skill[]; count: number }> {
    return (await this.http.get('/api/v5/skills')).data
  }

  // ===== MoA =====
  async moaAsk(query: string) {
    return (await this.http.post('/api/v5/moa/ask', { query })).data
  }

  // ===== Cron + Goals =====
  async addCronJob(name: string, schedule: string, action: string) {
    return (await this.http.post('/api/v5/cron/jobs', { name, schedule, action })).data
  }
  async listCronJobs() {
    return (await this.http.get('/api/v5/cron/jobs')).data
  }
  async createGoal(payload: { name: string; result: string; sources?: string[]; constraints?: string[]; deliverables?: string[]; priority?: string }): Promise<V5Goal> {
    return (await this.http.post('/api/v5/goals', payload)).data
  }

  // ===== Video Harness =====
  async createVideoProject(prompt: string): Promise<V5VideoProject> {
    return (await this.http.post('/api/v5/video/projects', { prompt })).data
  }
  async listVideoProjects() {
    return (await this.http.get('/api/v5/video/projects')).data
  }

  // ===== Brand Research =====
  async researchBrand(brand: string) {
    return (await this.http.post('/api/v5/brand/research', { brand })).data
  }
  async findHooks(category = '') {
    return (await this.http.post('/api/v5/brand/hooks', { category })).data
  }

  // ===== Data Gateway =====
  async listPlatforms(): Promise<{ platforms: V5Platform[]; count: number }> {
    return (await this.http.get('/api/v5/data/platforms')).data
  }
  async searchData(keyword: string, platform = '') {
    return (await this.http.post('/api/v5/data/search', { keyword, platform })).data
  }

  // ===== Roles =====
  async listRoles(department?: string): Promise<{ roles: V5Role[]; count: number }> {
    return (await this.http.get('/api/v5/roles', { params: { department } })).data
  }
  async getRole(roleId: string): Promise<V5Role & { system_prompt: string }> {
    return (await this.http.get(`/api/v5/roles/${roleId}`)).data
  }
  async getRoleSystemPrompt(roleId: string): Promise<{ system_prompt: string }> {
    return (await this.http.get(`/api/v5/roles/${roleId}/system-prompt`)).data
  }

  // ===== MCP =====
  async listMcpTools(): Promise<{ tools: V5McpTool[]; count: number }> {
    return (await this.http.get('/api/v5/mcp/tools')).data
  }
  async mcpRpc(request: any) {
    return (await this.http.post('/api/v5/mcp/rpc', request)).data
  }

  // ===== Proactive =====
  async dailyReport(userId = 'default') {
    return (await this.http.post('/api/v5/proactive/daily-report', { user_id: userId })).data
  }

  // ===== Monitor =====
  async heartbeat(botId: string, status = 'working') {
    return (await this.http.post('/api/v5/monitor/heartbeat', { bot_id: botId, status })).data
  }

  // ===== Geo =====
  async terrariumDecode(r: number, g: number, b: number) {
    return (await this.http.post('/api/v5/geo/decode', { r, g, b })).data
  }
  async terrariumEncode(elevation: number) {
    return (await this.http.post('/api/v5/geo/encode', { elevation })).data
  }

  // ===== Profile =====
  async createUserProfile(payload: { user_id: string; username?: string; display_name?: string; identity?: string; role?: string; industry?: string }): Promise<V5Profile> {
    return (await this.http.post('/api/v5/profile/users', payload)).data
  }
  async getUserProfile(userId: string): Promise<V5Profile> {
    return (await this.http.get(`/api/v5/profile/users/${userId}`)).data
  }
  async getProfileMd(userId: string): Promise<{ md: string }> {
    return (await this.http.get(`/api/v5/profile/users/${userId}/profile-md`)).data
  }
  async getStyleMd(userId: string): Promise<{ md: string }> {
    return (await this.http.get(`/api/v5/profile/users/${userId}/style-md`)).data
  }
  async listAgentTemplates() {
    return (await this.http.get('/api/v5/profile/agent-templates')).data
  }

  // ===== Perf =====
  async cachePut(key: string, value: any, ttl = 3600) {
    return (await this.http.post('/api/v5/perf/cache/put', { key, value, ttl })).data
  }
  async cacheGet(key: string) {
    return (await this.http.get('/api/v5/perf/cache/get', { params: { key } })).data
  }
  async cacheInvalidate(key: string) {
    return (await this.http.delete(`/api/v5/perf/cache/${key}`)).data
  }
  async cacheStats() {
    return (await this.http.get('/api/v5/perf/cache/stats')).data
  }
  async compressMessages(messages: any[]) {
    return (await this.http.post('/api/v5/perf/compress', { messages })).data
  }
}

let _v5: V5Client | null = null
export function getV5Client(http: AxiosInstance): V5Client {
  if (!_v5) _v5 = new V5Client(http)
  return _v5
}
