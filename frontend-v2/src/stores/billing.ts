import { defineStore } from 'pinia'

/**
 * Billing admin store (V5 §13.4 / Chapter 22 — CDP Advanced Billing).
 *
 * Mock-backed by deterministic seed data. Real wiring is staged for the
 * `/api/v1/billing/cdp/*` endpoints (CDPBillingService + FastAPI router).
 *
 * Pricing model (aligned with V5 §13.4 spec):
 *   - `data_gb`: $0.10/GB, no free tier — drives tier resolution
 *   - `api_calls`: $0.005/call, no free tier
 *   - `render_minutes`: $0.50/min beyond first 30 minutes
 *
 * Tier thresholds (data_gb qty):
 *   - tier_1: 0-100 GB → 0% discount
 *   - tier_2: 100-1000 GB → 5% discount
 *   - tier_3: 1000+ GB → 15% discount
 */

export interface UsageLine {
  metric: string
  unit: string
  qty: number
  unit_price: number
  amount: number
}

export interface InvoiceSummary {
  id: string
  period_start: string
  period_end: string
  currency: string
  subtotal: number
  tier_discount_total: number
  total: number
  tier_applied: string | null
  paid: boolean
}

export interface PricingTier {
  name: string
  min_units: number
  discount_pct: number
  description: string
}

interface BillingState {
  usage: UsageLine[]
  invoices: InvoiceSummary[]
  tiers: PricingTier[]
  loading: boolean
  error: string | null
  loaded: boolean
}

// Seed: tenant-1 used 500 GB + 10000 calls + 45 render-min in March.
// - data_gb: 500 × $0.10 = $50.00 (no free tier)
// - api_calls: 10000 × $0.005 = $50.00 (no free tier)
// - render_minutes: (45 − 30) × $0.50 = $7.50
// subtotal = $107.50; tier_2 (500 GB) = 5% × $107.50 = $5.375 ≈ $5.38
// total = $102.12
const SEED_USAGE: UsageLine[] = [
  { metric: 'data_gb',      unit: 'GB',     qty: 500,    unit_price: 0.10,  amount: 50.00 },
  { metric: 'api_calls',    unit: 'call',   qty: 10000,  unit_price: 0.005, amount: 50.00 },
  { metric: 'render_minutes', unit: 'minute', qty: 45,    unit_price: 0.50,  amount: 7.50 },
]

const SEED_INVOICES: InvoiceSummary[] = [
  {
    // Spec example: 500 GB data + 10000 API calls → $100 subtotal − tier_2 (5%) $5 = $95.
    id: 'inv_2026_03_tenant1',
    period_start: '2026-03-01',
    period_end: '2026-04-01',
    currency: 'USD',
    subtotal: 100.00,
    tier_discount_total: 5.00,
    total: 95.00,
    tier_applied: 'tier_2',
    paid: true,
  },
  {
    // April: 600 GB data + 11000 API calls → $60 + $55 = $115 − tier_2 5% = $109.25.
    id: 'inv_2026_04_tenant1',
    period_start: '2026-04-01',
    period_end: '2026-05-01',
    currency: 'USD',
    subtotal: 115.00,
    tier_discount_total: 5.75,
    total: 109.25,
    tier_applied: 'tier_2',
    paid: false,
  },
]

const SEED_TIERS: PricingTier[] = [
  { name: 'tier_1', min_units: 0,      discount_pct: 0,  description: 'Starter — 0-100 GB data, no volume discount' },
  { name: 'tier_2', min_units: 100,    discount_pct: 5,  description: 'Growth — 100-1000 GB data, 5% volume discount' },
  { name: 'tier_3', min_units: 1000,   discount_pct: 15, description: 'Scale — 1000+ GB data, 15% volume discount' },
]

export const useBillingStore = defineStore('billing', {
  state: (): BillingState => ({
    usage: [],
    invoices: [],
    tiers: [],
    loading: false,
    error: null,
    loaded: false,
  }),

  getters: {
    totalAmount: (s) => s.usage.reduce((acc, l) => acc + l.amount, 0),
    unpaidInvoiceCount: (s) => s.invoices.filter(i => !i.paid).length,
    /**
     * Tier resolution is driven by the **data_gb** metric specifically
     * (per V5 §13.4 / Chapter 22 spec) — other metrics contribute to the
     * subtotal but do not move the tenant between tiers.
     */
    currentTier: (s): PricingTier | null => {
      const dataLine = s.usage.find((l) => l.metric === 'data_gb')
      const dataQty = dataLine?.qty ?? 0
      const sorted = [...s.tiers].sort((a, b) => a.min_units - b.min_units)
      let chosen: PricingTier | null = null
      for (const t of sorted) {
        if (dataQty >= t.min_units) chosen = t
      }
      return chosen
    },
  },

  actions: {
    async loadAll(): Promise<void> {
      this.loading = true
      this.error = null
      try {
        await new Promise((r) => setTimeout(r, 50))
        this.usage = [...SEED_USAGE]
        this.invoices = [...SEED_INVOICES]
        this.tiers = [...SEED_TIERS]
        this.loaded = true
      } catch (e: unknown) {
        this.error = e instanceof Error ? e.message : String(e)
      } finally {
        this.loading = false
      }
    },

    async downloadInvoicePdf(invoiceId: string): Promise<{ size: number; format: 'pdf' | 'html' }> {
      // Mock — real wiring stages for `/api/v1/billing/cdp/invoice/{id}/pdf`.
      await new Promise((r) => setTimeout(r, 30))
      return { size: 4096, format: 'pdf' }
    },
  },
})