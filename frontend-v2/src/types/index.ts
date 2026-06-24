// Shared TypeScript types for the nanobot-factory frontend-v2 SPA.

export interface User {
  id: string
  username: string
  email?: string
  role: 'admin' | 'annotator' | 'reviewer' | 'engineer' | 'guest'
  created_at?: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  refresh_token?: string
  token_type?: string
  expires_in?: number
  user?: User
}

export interface RefreshResponse {
  access_token: string
  token_type?: string
  expires_in?: number
}

export interface ApiError {
  detail?: string
  message?: string
  code?: string | number
}

export interface StatsOverview {
  total_datasets: number
  total_tasks: number
  total_engines: number
  total_users: number
  active_workflows: number
  [k: string]: number | string | undefined
}

// 12 microservice modules — single source of truth for routing + sidebar
export const MODULES = [
  { path: '/',            name: 'dashboard',   title: '仪表盘',   icon: 'gauge' },
  { path: '/dataset',     name: 'dataset',     title: '数据集',   icon: 'database' },
  { path: '/annotation',  name: 'annotation',  title: '标注',     icon: 'edit' },
  { path: '/review',      name: 'review',      title: '审核',     icon: 'check' },
  { path: '/scoring',     name: 'scoring',     title: '评分',     icon: 'star' },
  { path: '/workflows',   name: 'workflows',   title: '工作流',   icon: 'flow' },
  { path: '/engines',     name: 'engines',     title: '引擎',     icon: 'cube' },
  { path: '/tasks',       name: 'tasks',       title: '任务',     icon: 'queue' },
  { path: '/users',       name: 'users',       title: '用户',     icon: 'people' },
  { path: '/billing',     name: 'billing',     title: '计费',     icon: 'card' },
  { path: '/monitoring',  name: 'monitoring',  title: '监控',     icon: 'pulse' },
  { path: '/settings',    name: 'settings',    title: '设置',     icon: 'gear' }
] as const

export type ModuleName = (typeof MODULES)[number]['name']