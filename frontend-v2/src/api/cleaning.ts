import { getPage, getOne, createOne, updateOne, deleteOne, type Page, type PageQuery } from './http'

// cleaning-service: 8004
export interface CleaningItem {
  id: string | number
  asset_id: string | number
  rule: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  result_count?: number
  created_at?: string
}

export interface CleaningCreate {
  asset_id: string
  rule: string
}

const BASE = '/api/v1/cleaning'

export async function listCleanings(query: PageQuery = {}): Promise<Page<CleaningItem>> {
  return getPage<CleaningItem>(BASE, query)
}
export async function getCleaning(id: string | number): Promise<CleaningItem> {
  return getOne(`${BASE}/${id}`)
}
export async function createCleaning(body: CleaningCreate): Promise<CleaningItem> {
  return createOne(BASE, body)
}
export async function updateCleaning(id: string | number, body: Partial<CleaningCreate & { status?: CleaningItem['status'] }>): Promise<CleaningItem> {
  return updateOne(`${BASE}/${id}`, body)
}
export async function deleteCleaning(id: string | number): Promise<void> {
  return deleteOne(`${BASE}/${id}`)
}
