import { defineStore } from 'pinia'
import axios, { type AxiosInstance, type InternalAxiosRequestConfig, type AxiosResponse, AxiosError } from 'axios'
import type { ApiError, LoginRequest, LoginResponse, RefreshResponse } from '@/types'

// Token storage keys
const ACCESS_TOKEN_KEY = 'imdf.auth.access_token'
const REFRESH_TOKEN_KEY = 'imdf.auth.refresh_token'
const USER_KEY = 'imdf.auth.user'

// Singleton axios instance used by every API call in the app
export const api: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
  timeout: 30_000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest'
  }
})

// Attach Authorization + CSRF token to every request
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY)
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`)
  }
  // Double-submit CSRF: read cookie written by backend middleware
  const csrfMatch = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/)
  if (csrfMatch && csrfMatch[1]) {
    config.headers.set('X-CSRF-Token', decodeURIComponent(csrfMatch[1]))
  }
  return config
})

// Track refresh state to avoid stampeding retries
let isRefreshing = false
let pendingQueue: Array<(token: string | null) => void> = []

function flushQueue(token: string | null) {
  pendingQueue.forEach((cb) => cb(token))
  pendingQueue = []
}

api.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError<ApiError>) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean }
    const status = error.response?.status

    if (status === 401 && original && !original._retry && !original.url?.includes('/auth/')) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          pendingQueue.push((token) => {
            if (token) {
              original.headers.set('Authorization', `Bearer ${token}`)
              original._retry = true
              resolve(api(original))
            } else {
              reject(error)
            }
          })
        })
      }
      original._retry = true
      isRefreshing = true
      try {
        const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
        if (!refreshToken) throw new Error('no refresh token')
        const { data } = await axios.post<RefreshResponse>(
          `${import.meta.env.VITE_API_BASE || ''}/api/auth/refresh`,
          { refresh_token: refreshToken },
          { withCredentials: true }
        )
        localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
        flushQueue(data.access_token)
        original.headers.set('Authorization', `Bearer ${data.access_token}`)
        return api(original)
      } catch (refreshErr) {
        flushQueue(null)
        // Hard logout — clear localStorage; route guard will redirect
        localStorage.removeItem(ACCESS_TOKEN_KEY)
        localStorage.removeItem(REFRESH_TOKEN_KEY)
        localStorage.removeItem(USER_KEY)
        return Promise.reject(refreshErr)
      } finally {
        isRefreshing = false
      }
    }
    return Promise.reject(error)
  }
)

// Pinia store — exposes api + token mutators + login/logout flows
export const useApiStore = defineStore('api', {
  state: () => ({
    baseURL: import.meta.env.VITE_API_BASE || '',
    ready: true
  }),
  actions: {
    async login(req: LoginRequest): Promise<LoginResponse> {
      const { data } = await api.post<LoginResponse>('/api/auth/login', req)
      if (data.access_token) localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
      if (data.refresh_token) localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token)
      if (data.user) localStorage.setItem(USER_KEY, JSON.stringify(data.user))
      return data
    },
    logout(): void {
      localStorage.removeItem(ACCESS_TOKEN_KEY)
      localStorage.removeItem(REFRESH_TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    },
    getAccessToken(): string | null {
      return localStorage.getItem(ACCESS_TOKEN_KEY)
    }
  }
})