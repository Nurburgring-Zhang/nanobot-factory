// frontend-v2/src/api/multimodal.ts
// P4-7-W2: frontend API client for /api/v1/multimodal/* and /api/v1/agent/multimodal
import { http } from './http'

export type ModalKind = 'image' | 'video' | 'audio' | 'document' | 'text'

export interface MediaItem {
  kind?: ModalKind
  url?: string
  data_b64?: string
  text?: string
  mime?: string
  meta?: Record<string, unknown>
}

export type UnderstandingTask =
  | 'caption'
  | 'vqa'
  | 'classification'
  | 'relation'
  | 'sentiment'
  | 'ocr'
  | 'asr'
  | 'reasoning'

export interface UnderstandRequest {
  task: UnderstandingTask
  media: MediaItem[]
  query?: string
  params?: Record<string, unknown>
}

export interface UnderstandResponse {
  request_id: string
  task: UnderstandingTask
  text: string
  label?: string
  score?: number
  citations: Array<Record<string, unknown>>
  raw: Record<string, unknown>
  elapsed_ms: number
  model: string
}

export interface GenerateRequest {
  text: string
  target: 'image' | 'video' | 'audio' | 'text'
  ref_images?: MediaItem[]
  provider?: string
  params?: Record<string, unknown>
}

export interface GenerationCandidate {
  modality: string
  url: string
  mime: string
  seed?: number
  width?: number
  height?: number
  duration_sec?: number
  meta?: Record<string, unknown>
}

export interface GenerateResponse {
  request_id: string
  target: string
  candidates: GenerationCandidate[]
  provider: string
  elapsed_ms: number
}

export interface RagIndexRequest {
  media: MediaItem[]
}

export interface RagSearchRequest {
  query?: string
  media?: MediaItem
  top_k?: number
}

export interface AgentInvokeRequest {
  prompt: string
  media?: MediaItem[]
  session_id?: string
  save_to_memory?: boolean
}

export interface AgentToolCall {
  tool: string
  args: Record<string, unknown>
  result: Record<string, unknown>
}

export interface AgentInvokeResponse {
  request_id: string
  text: string
  tool_calls: AgentToolCall[]
  output_media: MediaItem[]
  memory_ids: string[]
  elapsed_ms: number
}

export const multimodalApi = {
  healthz: () => http.get<{ ok: boolean; service: string; providers: Array<{ name: string }> }>('/api/v1/multimodal/healthz'),

  understand: (req: UnderstandRequest) => http.post<UnderstandResponse>('/api/v1/multimodal/understand', req),
  understandBatch: (reqs: UnderstandRequest[]) => http.post<{ count: number; results: UnderstandResponse[] }>('/api/v1/multimodal/understand/batch', reqs),

  generate: (req: GenerateRequest) => http.post<GenerateResponse>('/api/v1/multimodal/generate', req),
  providers: () => http.get<{ providers: Array<{ name: string; supported: string[]; loaded: boolean }> }>('/api/v1/multimodal/providers'),

  ragIndex: (req: RagIndexRequest) => http.post<{ indexed: number; parsed: Array<Record<string, unknown>> }>('/api/v1/multimodal/rag/index', req),
  ragSearch: (req: RagSearchRequest) => http.post<{ hits: Array<Record<string, unknown>> }>('/api/v1/multimodal/rag/search', req),

  services: () => http.get<{ services: Array<{ service: string; capability: string; modalities: string[] }> }>('/api/v1/multimodal/services'),
  serviceSmoke: (name: string, payload: Record<string, unknown> = {}) => http.post<Record<string, unknown>>(`/api/v1/multimodal/services/${name}/smoke`, { payload }),

  agentTools: () => http.get<{ tools: Array<{ name: string; description: string }> }>('/api/v1/agent/multimodal/tools'),
  agentInvoke: (req: AgentInvokeRequest) => http.post<AgentInvokeResponse>('/api/v1/agent/multimodal', req),
}