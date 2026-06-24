import { getPage, getOne, createOne, updateOne, deleteOne, type Page, type PageQuery } from './http'

// evaluation-service: 8007
export interface EvaluationItem {
  id: string | number
  dataset_id: string | number
  model: string
  metric: string
  value: number
  created_at?: string
}

export interface EvaluationCreate {
  dataset_id: string
  model: string
  metric: string
  value: number
}

const BASE = '/api/v1/evaluations'

export async function listEvaluations(query: PageQuery = {}): Promise<Page<EvaluationItem>> {
  return getPage<EvaluationItem>(BASE, query)
}
export async function getEvaluation(id: string | number): Promise<EvaluationItem> {
  return getOne(`${BASE}/${id}`)
}
export async function createEvaluation(body: EvaluationCreate): Promise<EvaluationItem> {
  return createOne(BASE, body)
}
export async function updateEvaluation(id: string | number, body: Partial<EvaluationCreate>): Promise<EvaluationItem> {
  return updateOne(`${BASE}/${id}`, body)
}
export async function deleteEvaluation(id: string | number): Promise<void> {
  return deleteOne(`${BASE}/${id}`)
}
