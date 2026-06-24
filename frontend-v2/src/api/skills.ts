// frontend-v2/src/api/skills.ts
// P4-8-W2: Skill marketplace + orchestrator API client.
// Base path: /api/v1/skills (P4-8-W1 backend module).
import { http, getPage, type Page, type PageQuery } from './http'

// ---------- 10 official Skill catalog (mirrors backend builtin registry) ----------
export type SkillCategory =
  | 'content' | 'media' | 'language' | 'research' | 'production'
  | 'video' | 'writing' | 'youtube' | 'story' | 'marketing'

export interface Skill {
  id: string                       // "ppt" / "social-card" / "deep-research" ...
  name: string
  description: string
  category: SkillCategory
  version: string
  author: string
  downloads: number
  rating: number                   // 0-5
  tags: string[]
  inputs: Array<{ name: string; type: string; required: boolean; description?: string }>
  outputs: Array<{ name: string; type: string; description?: string }>
  dependencies: string[]           // other skill ids
  icon: string                     // emoji icon
  installed?: boolean
  installed_version?: string | null
}

export interface SkillComment {
  id: string
  skill_id: string
  user: string
  rating: number
  text: string
  created_at: string
}

export interface SkillExecutionResult {
  execution_id: string
  skill_id: string
  status: 'pending' | 'running' | 'succeeded' | 'failed'
  output: Record<string, unknown>
  logs: string[]
  artifacts: Array<{ name: string; url: string; mime: string }>
  elapsed_ms: number
}

export interface SkillPipeline {
  id: string
  name: string
  description: string
  nodes: Array<{ id: string; skill_id: string; position: { x: number; y: number }; config?: Record<string, unknown> }>
  edges: Array<{ source: string; target: string; source_output?: string; target_input?: string }>
  exec_mode: 'sequential' | 'parallel'
  owner: string
  created_at?: string
  updated_at?: string
}

export const skillsApi = {
  // ----- Marketplace -----
  list: (query: PageQuery & { category?: string; sort?: 'downloads' | 'rating' | 'latest'; installed_only?: boolean } = {}) =>
    getPage<Skill>('/api/v1/skills', query),
  listAll: () => http.get<{ skills: Skill[]; total: number }>('/api/v1/skills/all').then(r => r.data),
  detail: (id: string) => http.get<Skill>(`/api/v1/skills/${id}`).then(r => r.data),
  comments: (id: string) => http.get<{ comments: SkillComment[] }>(`/api/v1/skills/${id}/comments`).then(r => r.data.comments),
  install: (id: string, version?: string) => http.post<{ installed: boolean; skill_id: string; version: string }>('/api/v1/skills/install', { id, version }).then(r => r.data),
  uninstall: (id: string) => http.post<{ uninstalled: boolean; skill_id: string }>('/api/v1/skills/uninstall', { id }).then(r => r.data),
  installed: () => http.get<{ skills: Skill[] }>('/api/v1/skills/installed').then(r => r.data.skills),
  // ----- Execution -----
  execute: (id: string, inputs: Record<string, unknown>) =>
    http.post<SkillExecutionResult>('/api/v1/skills/execute', { skill_id: id, inputs }).then(r => r.data),
  executionStatus: (executionId: string) =>
    http.get<SkillExecutionResult>(`/api/v1/skills/executions/${executionId}`).then(r => r.data),
  // ----- Orchestrator / Pipeline -----
  listPipelines: () => http.get<{ pipelines: SkillPipeline[] }>('/api/v1/skills/pipelines').then(r => r.data.pipelines),
  getPipeline: (id: string) => http.get<SkillPipeline>(`/api/v1/skills/pipelines/${id}`).then(r => r.data),
  savePipeline: (pipeline: SkillPipeline) => http.post<SkillPipeline>('/api/v1/skills/pipelines', pipeline).then(r => r.data),
  deletePipeline: (id: string) => http.delete<{ deleted: boolean }>(`/api/v1/skills/pipelines/${id}`).then(r => r.data),
  runPipeline: (id: string, inputs: Record<string, unknown> = {}) =>
    http.post<{ run_id: string; status: string }>(`/api/v1/skills/pipelines/${id}/run`, { inputs }).then(r => r.data),
  pipelineStatus: (runId: string) =>
    http.get<SkillExecutionResult & { pipeline_id: string; step_count: number }>(`/api/v1/skills/pipelines/runs/${runId}`).then(r => r.data),
}

export type { Page }
