import { getPage, getOne, createOne, updateOne, deleteOne, type Page, type PageQuery } from './http'

// user-service: 8001
export interface UserItem {
  id: string | number
  username: string
  email?: string
  role: 'admin' | 'annotator' | 'reviewer' | 'engineer' | 'guest'
  created_at?: string
}

export interface UserCreate {
  username: string
  email?: string
  role: UserItem['role']
  password: string
}

const BASE = '/api/v1/users'

export async function listUsers(query: PageQuery = {}): Promise<Page<UserItem>> {
  return getPage<UserItem>(BASE, query)
}
export async function getUser(id: string | number): Promise<UserItem> {
  return getOne(`${BASE}/${id}`)
}
export async function createUser(body: UserCreate): Promise<UserItem> {
  return createOne(BASE, body)
}
export async function updateUser(id: string | number, body: Partial<UserCreate>): Promise<UserItem> {
  return updateOne(`${BASE}/${id}`, body)
}
export async function deleteUser(id: string | number): Promise<void> {
  return deleteOne(`${BASE}/${id}`)
}
