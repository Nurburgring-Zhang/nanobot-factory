import { getPage, getOne, createOne, updateOne, deleteOne, type Page, type PageQuery } from './http'

// scoring-service: 8005
export interface ScoringItem {
  id: string | number
  asset_id: string | number
  score: number
  metric: string
  scorer?: string
  created_at?: string
}

export interface ScoringCreate {
  asset_id: string
  score: number
  metric: string
  scorer?: string
}

const BASE = '/api/v1/scoring'

export async function listScorings(query: PageQuery = {}): Promise<Page<ScoringItem>> {
  return getPage<ScoringItem>(BASE, query)
}
export async function getScoring(id: string | number): Promise<ScoringItem> {
  return getOne(`${BASE}/${id}`)
}
export async function createScoring(body: ScoringCreate): Promise<ScoringItem> {
  return createOne(BASE, body)
}
export async function updateScoring(id: string | number, body: Partial<ScoringCreate>): Promise<ScoringItem> {
  return updateOne(`${BASE}/${id}`, body)
}
export async function deleteScoring(id: string | number): Promise<void> {
  return deleteOne(`${BASE}/${id}`)
}
