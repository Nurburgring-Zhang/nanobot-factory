import { http } from './http'

// billing module — mounted at /api/v1/billing via backend/billing/routes.py.
// All endpoints accept user_id via query string (single-tenant in-memory store).

const BASE = '/api/v1/billing'

// ── Plans ──────────────────────────────────────────────────────────────────
export interface PlanItem {
  id: string
  name: string
  tier: string
  price_monthly: number
  price_yearly: number
  currency: string
  features: string[]
  limits: Record<string, number>
  recommended?: boolean
  description?: string
}

export async function listPlans(): Promise<{ plans: PlanItem[]; count: number }> {
  return (await http.get(`${BASE}/plans`)).data
}

export async function getPlan(planId: string): Promise<PlanItem> {
  return (await http.get(`${BASE}/plans/${planId}`)).data
}

export async function getCurrentPlan(userId: string): Promise<{
  user_id: string
  plan_id: string
  plan_name: string
  period: string
  status: string
  started_at: string
  renews_at: string
}> {
  return (await http.get(`${BASE}/plans/current/user`, { params: { user_id: userId } })).data
}

// ── Usage / Quotas ─────────────────────────────────────────────────────────
export interface UsageBucket {
  key: string
  label: string
  used: number
  quota: number
  unit: string
  cost: number
}

export async function getUserUsage(userId: string): Promise<{
  user_id: string
  period: string
  buckets: UsageBucket[]
  total_cost: number
}> {
  return (await http.get(`${BASE}/usage`, { params: { user_id: userId } })).data
}

export async function getUserQuotas(userId: string): Promise<{
  user_id: string
  quotas: Record<string, { used: number; limit: number; reset_at: string }>
}> {
  return (await http.get(`${BASE}/quotas`, { params: { user_id: userId } })).data
}

// ── Orders / Payment (entry points; not the focus of Billing.vue) ──────────
export async function listOrders(userId: string): Promise<{ orders: any[]; count: number }> {
  return (await http.get(`${BASE}/orders`, { params: { user_id: userId } })).data
}

export async function createOrder(body: {
  user_id: string
  plan_id: string
  period: 'monthly' | 'yearly'
  currency?: string
}): Promise<{ order_id: string; status: string }> {
  return (await http.post(`${BASE}/orders`, body)).data
}

export async function cancelOrder(orderId: string, reason = 'user_cancel'): Promise<any> {
  return (await http.post(`${BASE}/orders/${orderId}/cancel`, null, { params: { reason } })).data
}

// ── Subscription ───────────────────────────────────────────────────────────
export async function getSubscription(userId: string): Promise<any> {
  return (await http.get(`${BASE}/subscription/user/${userId}`)).data
}

export async function createSubscription(userId: string, planId: string, period = 'monthly'): Promise<any> {
  return (await http.post(
    `${BASE}/subscription/user/${userId}/create`,
    null,
    { params: { plan_id: planId, period } },
  )).data
}

export async function changePlan(userId: string, planId: string): Promise<any> {
  return (await http.post(`${BASE}/subscription/user/${userId}/change-plan`, { plan_id: planId })).data
}