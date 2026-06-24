import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'

const ACCESS_TOKEN_KEY = 'imdf.auth.access_token'

// Shared axios instance used by every business API client.
// Each domain module gets its own typed wrapper.
export const http: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest'
  }
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY)
  if (token && config.headers) {
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface PageQuery {
  page?: number
  page_size?: number
  keyword?: string
}

export async function getPage<T>(
  url: string,
  query: PageQuery = {},
  config?: AxiosRequestConfig
): Promise<Page<T>> {
  const res = await http.get<Page<T>>(url, {
    ...config,
    params: { page: 1, page_size: 20, ...query }
  })
  return res.data
}

export async function getOne<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const res = await http.get<T>(url, config)
  return res.data
}

export async function createOne<T>(url: string, body: unknown, config?: AxiosRequestConfig): Promise<T> {
  const res = await http.post<T>(url, body, config)
  return res.data
}

export async function updateOne<T>(url: string, body: unknown, config?: AxiosRequestConfig): Promise<T> {
  const res = await http.put<T>(url, body, config)
  return res.data
}

export async function patchOne<T>(url: string, body: unknown, config?: AxiosRequestConfig): Promise<T> {
  const res = await http.patch<T>(url, body, config)
  return res.data
}

export async function deleteOne(url: string, config?: AxiosRequestConfig): Promise<void> {
  await http.delete(url, config)
}
