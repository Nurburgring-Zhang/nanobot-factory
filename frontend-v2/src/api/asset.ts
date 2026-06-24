import { getPage, getOne, createOne, updateOne, deleteOne, type Page, type PageQuery } from './http'

// asset-service: 8002
export interface AssetItem {
  id: string | number
  name: string
  type: 'image' | 'video' | 'audio' | 'text'
  url?: string
  size?: number
  created_at?: string
}

export interface AssetCreate {
  name: string
  type: AssetItem['type']
  url?: string
  size?: number
}

const BASE = '/api/v1/assets'

export async function listAssets(query: PageQuery = {}): Promise<Page<AssetItem>> {
  return getPage<AssetItem>(BASE, query)
}
export async function getAsset(id: string | number): Promise<AssetItem> {
  return getOne(`${BASE}/${id}`)
}
export async function createAsset(body: AssetCreate): Promise<AssetItem> {
  return createOne(BASE, body)
}
export async function updateAsset(id: string | number, body: Partial<AssetCreate>): Promise<AssetItem> {
  return updateOne(`${BASE}/${id}`, body)
}
export async function deleteAsset(id: string | number): Promise<void> {
  return deleteOne(`${BASE}/${id}`)
}
