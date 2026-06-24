import { getPage, getOne, createOne, updateOne, deleteOne, type Page, type PageQuery } from './http'

// dataset-service: 8006
export interface DatasetItem {
  id: string | number
  name: string
  version: string
  size: number
  status: 'draft' | 'published' | 'archived'
  created_at?: string
}

export interface DatasetCreate {
  name: string
  version: string
  size?: number
  status?: DatasetItem['status']
}

const BASE = '/api/v1/datasets'

export async function listDatasets(query: PageQuery = {}): Promise<Page<DatasetItem>> {
  return getPage<DatasetItem>(BASE, query)
}
export async function getDataset(id: string | number): Promise<DatasetItem> {
  return getOne(`${BASE}/${id}`)
}
export async function createDataset(body: DatasetCreate): Promise<DatasetItem> {
  return createOne(BASE, body)
}
export async function updateDataset(id: string | number, body: Partial<DatasetCreate>): Promise<DatasetItem> {
  return updateOne(`${BASE}/${id}`, body)
}
export async function deleteDataset(id: string | number): Promise<void> {
  return deleteOne(`${BASE}/${id}`)
}
