import { getPage, getOne, createOne, updateOne, deleteOne, type Page, type PageQuery } from './http'

// annotation-service: 8003
export interface AnnotationItem {
  id: string | number
  asset_id: string | number
  label: string
  annotator?: string
  status: 'pending' | 'approved' | 'rejected'
  created_at?: string
}

export interface AnnotationCreate {
  asset_id: string
  label: string
  annotator?: string
  status?: AnnotationItem['status']
}

const BASE = '/api/v1/annotations'

export async function listAnnotations(query: PageQuery = {}): Promise<Page<AnnotationItem>> {
  return getPage<AnnotationItem>(BASE, query)
}
export async function getAnnotation(id: string | number): Promise<AnnotationItem> {
  return getOne(`${BASE}/${id}`)
}
export async function createAnnotation(body: AnnotationCreate): Promise<AnnotationItem> {
  return createOne(BASE, body)
}
export async function updateAnnotation(id: string | number, body: Partial<AnnotationCreate>): Promise<AnnotationItem> {
  return updateOne(`${BASE}/${id}`, body)
}
export async function deleteAnnotation(id: string | number): Promise<void> {
  return deleteOne(`${BASE}/${id}`)
}
