import { http } from './http'

// Engines = the 23-agent registry from backend/services/agent_service/agents.py
// plus a thin /api/v1/engines alias on backend/services/asset_service/iteration/routes.py.
// We use the agent_service endpoints (the canonical 23-agent catalogue).

export interface EngineType {
  /** agent slug, e.g. "llm_chat", "image_annotation" */
  id: string
  /** human-readable name */
  name: string
  description: string
  default_mode: 'full_auto' | 'semi_auto' | 'manual'
  default_priority: number
  /** downstream microservice this engine routes to, e.g. "annotation_service" */
  downstream_service: string
  capabilities: string[]
}

export interface EngineTypesResponse {
  count: number
  types: string[]
}

export interface EngineSummaryResponse {
  count: number
  agents: EngineType[]
}

export interface EngineDetail extends Omit<EngineType, 'default_mode'> {
  default_mode: string
  max_retries: number
  timeout_seconds: number
}

const AGENT_BASE = '/api/v1/agents'

export async function listEngineTypes(): Promise<EngineTypesResponse> {
  return (await http.get(`${AGENT_BASE}/types`)).data
}

export async function listEngines(): Promise<EngineSummaryResponse> {
  return (await http.get(AGENT_BASE)).data
}

export async function getEngine(agentType: string): Promise<EngineDetail> {
  return (await http.get(`${AGENT_BASE}/${agentType}`)).data
}

export interface RunAgentBody {
  payload?: Record<string, unknown>
  mode?: 'full_auto' | 'semi_auto' | 'manual'
  priority?: number
  submitted_by?: string
}

export async function runEngine(agentType: string, body: RunAgentBody): Promise<{
  task: { task_id: string; agent_type: string; status: string }
  result?: Record<string, unknown>
}> {
  return (await http.post(`${AGENT_BASE}/${agentType}/run`, body)).data
}

export async function getEngineTask(taskId: string): Promise<Record<string, unknown>> {
  return (await http.get(`/api/v1/agent_tasks/${taskId}`)).data
}

export async function cancelEngineTask(taskId: string): Promise<Record<string, unknown>> {
  return (await http.post(`/api/v1/agent_tasks/${taskId}/cancel`)).data
}

export async function retryEngineTask(taskId: string): Promise<Record<string, unknown>> {
  return (await http.post(`/api/v1/agent_tasks/${taskId}/retry`)).data
}