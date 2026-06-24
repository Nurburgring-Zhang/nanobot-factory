import { defineStore } from 'pinia'
import { useApiStore } from './api'
import type { LoginRequest, User } from '@/types'

interface AuthState {
  token: string | null
  refreshToken: string | null
  user: User | null
  loading: boolean
  lastError: string | null
}

const ACCESS_TOKEN_KEY = 'imdf.auth.access_token'
const REFRESH_TOKEN_KEY = 'imdf.auth.refresh_token'
const USER_KEY = 'imdf.auth.user'

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    token: null,
    refreshToken: null,
    user: null,
    loading: false,
    lastError: null
  }),

  getters: {
    isAuthenticated: (state) => !!state.token,
    role: (state) => state.user?.role ?? 'guest'
  },

  actions: {
    // Called once at boot from main.ts before the router runs its first navigation
    restoreFromStorage(): void {
      try {
        this.token = localStorage.getItem(ACCESS_TOKEN_KEY)
        this.refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
        const raw = localStorage.getItem(USER_KEY)
        this.user = raw ? (JSON.parse(raw) as User) : null
      } catch {
        // ignore — corrupted storage; treat as logged out
        this.token = null
        this.refreshToken = null
        this.user = null
      }
    },

    async login(req: LoginRequest): Promise<User | null> {
      this.loading = true
      this.lastError = null
      try {
        const apiStore = useApiStore()
        const res = await apiStore.login(req)
        this.token = res.access_token
        this.refreshToken = res.refresh_token ?? null
        this.user = res.user ?? null
        return this.user
      } catch (err: unknown) {
        const message =
          err && typeof err === 'object' && 'response' in err
            ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : null
        this.lastError = message || 'login failed'
        return null
      } finally {
        this.loading = false
      }
    },

    logout(): void {
      const apiStore = useApiStore()
      apiStore.logout()
      this.token = null
      this.refreshToken = null
      this.user = null
    }
  }
})