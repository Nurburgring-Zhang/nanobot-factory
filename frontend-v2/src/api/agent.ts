import { getPage, getOne, createOne, updateOne, deleteOne, type Page, type PageQuery } from './http'

// agent-service: 8008
export interface AgentItem {
  id: string | number
  name: string
  kind: string
  status: 'idle' | 'running' | 'stopped' | 'error'
  created_at?: string
}

export interface AgentCreate {
  name: string
  kind: string
  status?: AgentItem['status']
}

const BASE = '/api/v1/agents'

export async function listAgents(query: PageQuery = {}): Promise<Page<AgentItem>> {
  return getPage<AgentItem>(BASE, query)
}
export async function getAgent(id: string | number): Promise<AgentItem> {
  return getOne(`${BASE}/${id}`)
}
export async function createAgent(body: AgentCreate): Promise<AgentItem> {
  return createOne(BASE, body)
}
export async function updateAgent(id: string | number, body: Partial<AgentCreate>): Promise<AgentItem> {
  return updateOne(`${BASE}/${id}`, body)
}
export async function deleteAgent(id: string | number): Promise<void> {
  return deleteOne(`${BASE}/${id}`)
}
