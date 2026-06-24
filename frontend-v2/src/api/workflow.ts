import { getPage, getOne, createOne, updateOne, deleteOne, type Page, type PageQuery } from './http'

// workflow-service: 8009
export interface WorkflowItem {
  id: string | number
  name: string
  status: 'draft' | 'active' | 'paused' | 'archived'
  steps?: number
  created_at?: string
}

export interface WorkflowCreate {
  name: string
  status?: WorkflowItem['status']
  steps?: number
}

const BASE = '/api/v1/workflows'

export async function listWorkflows(query: PageQuery = {}): Promise<Page<WorkflowItem>> {
  return getPage<WorkflowItem>(BASE, query)
}
export async function getWorkflow(id: string | number): Promise<WorkflowItem> {
  return getOne(`${BASE}/${id}`)
}
export async function createWorkflow(body: WorkflowCreate): Promise<WorkflowItem> {
  return createOne(BASE, body)
}
export async function updateWorkflow(id: string | number, body: Partial<WorkflowCreate>): Promise<WorkflowItem> {
  return updateOne(`${BASE}/${id}`, body)
}
export async function deleteWorkflow(id: string | number): Promise<void> {
  return deleteOne(`${BASE}/${id}`)
}
