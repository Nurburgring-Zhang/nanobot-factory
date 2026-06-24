import { getPage, getOne, createOne, updateOne, deleteOne, type Page, type PageQuery } from './http'

// notification-service: 8010
export interface NotificationItem {
  id: string | number
  title: string
  body?: string
  level: 'info' | 'warning' | 'error' | 'success'
  read?: boolean
  created_at?: string
}

export interface NotificationCreate {
  title: string
  body?: string
  level: NotificationItem['level']
}

const BASE = '/api/v1/notifications'

export async function listNotifications(query: PageQuery = {}): Promise<Page<NotificationItem>> {
  return getPage<NotificationItem>(BASE, query)
}
export async function getNotification(id: string | number): Promise<NotificationItem> {
  return getOne(`${BASE}/${id}`)
}
export async function createNotification(body: NotificationCreate): Promise<NotificationItem> {
  return createOne(BASE, body)
}
export async function updateNotification(id: string | number, body: Partial<NotificationCreate & { read?: boolean }>): Promise<NotificationItem> {
  return updateOne(`${BASE}/${id}`, body)
}
export async function deleteNotification(id: string | number): Promise<void> {
  return deleteOne(`${BASE}/${id}`)
}
