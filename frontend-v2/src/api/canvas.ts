import { getOne, createOne, updateOne, deleteOne } from './http'

// canvas — FastAPI monolith endpoint, NOT a microservice.
// Routes: GET/PUT/DELETE /api/canvas/{id}, POST /api/canvas/{id}/nodes, etc.
export interface CanvasNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: Record<string, unknown>
}

export interface CanvasEdge {
  id: string
  source: string
  target: string
  label?: string
}

export interface CanvasDoc {
  id: string
  name: string
  nodes: CanvasNode[]
  edges: CanvasEdge[]
  version: number
  updated_at?: string
}

export async function getCanvas(id: string): Promise<CanvasDoc> {
  return getOne<CanvasDoc>(`/api/canvas/${encodeURIComponent(id)}`)
}

export async function createCanvas(body: { name: string }): Promise<CanvasDoc> {
  return createOne<CanvasDoc>('/api/canvas', body)
}

export async function saveCanvas(id: string, body: Partial<CanvasDoc>): Promise<CanvasDoc> {
  return updateOne<CanvasDoc>(`/api/canvas/${encodeURIComponent(id)}`, body)
}

export async function deleteCanvas(id: string): Promise<void> {
  return deleteOne(`/api/canvas/${encodeURIComponent(id)}`)
}
