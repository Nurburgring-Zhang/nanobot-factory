import { http } from './http'

// Settings = local-storage backed UI preferences plus a thin backend hook for
// persisting user-level preferences to user_service.
// Most "settings" actions are client-side (theme / locale / token copy /
// refresh interval) — only JWT rotation + API base URL hit the backend.

export interface UserPreferences {
  theme: 'light' | 'dark' | 'auto'
  primaryColor: string
  locale: 'zh-CN' | 'en-US'
  pageSize: number
  refreshSeconds: number
  showTooltips: boolean
  compactTables: boolean
  defaultLanding: string
}

export interface JwtConfig {
  accessTtlMinutes: number
  refreshTtlDays: number
  algorithm: string
  rotateEnabled: boolean
  autoRefreshBuffer: number
}

export interface ApiEndpointConfig {
  apiBase: string
  gatewayBase: string
  timeoutMs: number
}

export interface SystemInfo {
  version: string
  build: string
  env: string
  startedAt: string
  services: { name: string; status: string }[]
}

const USER_BASE = '/api/v1/users'
const PREF_KEY = 'imdf.user.preferences'
const JWT_KEY = 'imdf.jwt.config'

export function loadPreferences(): UserPreferences {
  try {
    const raw = localStorage.getItem(PREF_KEY)
    if (raw) return JSON.parse(raw) as UserPreferences
  } catch {
    /* ignore */
  }
  return {
    theme: 'light',
    primaryColor: '#2080f0',
    locale: 'zh-CN',
    pageSize: 20,
    refreshSeconds: 30,
    showTooltips: true,
    compactTables: false,
    defaultLanding: '/',
  }
}

export function savePreferences(p: UserPreferences): void {
  localStorage.setItem(PREF_KEY, JSON.stringify(p))
}

export function loadJwtConfig(): JwtConfig {
  try {
    const raw = localStorage.getItem(JWT_KEY)
    if (raw) return JSON.parse(raw) as JwtConfig
  } catch {
    /* ignore */
  }
  return {
    accessTtlMinutes: 30,
    refreshTtlDays: 14,
    algorithm: 'HS256',
    rotateEnabled: true,
    autoRefreshBuffer: 60,
  }
}

export function saveJwtConfig(c: JwtConfig): void {
  localStorage.setItem(JWT_KEY, JSON.stringify(c))
}

/** Build an inspection report on the current JWT — used by the "JWT 切换" card. */
export function inspectToken(): {
  raw: string
  header: Record<string, unknown>
  payload: Record<string, unknown>
  expiresAt?: string
  isExpired: boolean
} | null {
  const token = localStorage.getItem('imdf.auth.access_token')
  if (!token) return null
  const parts = token.split('.')
  if (parts.length !== 3) return null
  try {
    const header = JSON.parse(atob(parts[0]))
    const payload = JSON.parse(atob(parts[1]))
    const exp = typeof payload.exp === 'number' ? payload.exp * 1000 : undefined
    return {
      raw: token,
      header,
      payload,
      expiresAt: exp ? new Date(exp).toISOString() : undefined,
      isExpired: exp ? exp < Date.now() : false,
    }
  } catch {
    return { raw: token, header: {}, payload: {}, isExpired: true }
  }
}

export async function fetchSystemInfo(): Promise<SystemInfo> {
  // user_service is the canonical /api root; fall back to default if missing.
  try {
    const res = await http.get('/')
    const data = (res.data ?? {}) as Record<string, unknown>
    return {
      version: String(data.version ?? '0.0.0'),
      build: String(data.build ?? 'dev'),
      env: String(data.env ?? import.meta.env.MODE ?? 'development'),
      startedAt: new Date().toISOString(),
      services: Array.isArray(data.services) ? (data.services as any) : [],
    }
  } catch {
    return {
      version: '0.0.0',
      build: 'dev',
      env: import.meta.env.MODE ?? 'development',
      startedAt: new Date().toISOString(),
      services: [],
    }
  }
}

export async function fetchCurrentUser(): Promise<{ username: string; role: string; email?: string } | null> {
  try {
    const res = await http.get('/api/auth/me')
    return (res.data ?? null) as any
  } catch {
    return null
  }
}

export async function listRoles(): Promise<{ roles: Array<{ id: string; label: string; permissions: string[] }> }> {
  return (await http.get(`${USER_BASE}/../roles`)).data
}