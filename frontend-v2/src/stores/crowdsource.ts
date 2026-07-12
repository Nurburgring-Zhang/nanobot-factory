import { defineStore } from 'pinia'

/**
 * Crowdsource admin store (V5 §13.4 / Chapter 17).
 *
 * Mock-backed by deterministic seed data so the admin panel renders
 * without a backend dependency. Real wiring is staged for P19 v5.7 to
 * call `imdf/business/crowdsource.py`.
 */

export interface CrowdsourceTask {
  id: string
  title: string
  status: 'pending' | 'in_progress' | 'completed' | 'paused'
  workers_count: number
  payment: number
  deadline: string   // ISO date
}

export interface Worker {
  id: string
  name: string
  completed_tasks: number
  quality_score: number   // 0–100
  earnings: number        // USD
}

export interface Payment {
  id: string
  worker_id: string
  worker_name: string
  amount: number
  status: 'pending' | 'processed' | 'failed'
  scheduled_for: string   // ISO date
}

interface CrowdsourceState {
  tasks: CrowdsourceTask[]
  workers: Worker[]
  payments: Payment[]
  loading: boolean
  error: string | null
  loaded: boolean
}

// Deterministic seed data — same across reloads so tests can assert on it.
const SEED_TASKS: CrowdsourceTask[] = [
  { id: 'T-1001', title: 'Image classification — kitchen scenes', status: 'in_progress', workers_count: 12, payment: 480, deadline: '2026-07-15' },
  { id: 'T-1002', title: 'Sentiment labeling — product reviews', status: 'pending',     workers_count: 0,  payment: 220, deadline: '2026-07-22' },
  { id: 'T-1003', title: 'Bounding box — urban driving frames', status: 'completed',   workers_count: 18, payment: 980, deadline: '2026-06-30' },
  { id: 'T-1004', title: 'OCR transcription — handwritten notes', status: 'paused',    workers_count: 4,  payment: 360, deadline: '2026-08-01' },
  { id: 'T-1005', title: 'Toxicity annotation — chat logs', status: 'in_progress',     workers_count: 7,  payment: 150, deadline: '2026-07-20' },
]

const SEED_WORKERS: Worker[] = [
  { id: 'W-001', name: 'Alice Chen',     completed_tasks: 142, quality_score: 96.5, earnings: 1280.5 },
  { id: 'W-002', name: 'Bob Singh',      completed_tasks: 87,  quality_score: 91.0, earnings: 760.0 },
  { id: 'W-003', name: 'Carmen Diaz',    completed_tasks: 201, quality_score: 88.5, earnings: 1830.25 },
  { id: 'W-004', name: 'Dao Wei',        completed_tasks: 45,  quality_score: 99.0, earnings: 410.75 },
  { id: 'W-005', name: 'Esha Patel',     completed_tasks: 67,  quality_score: 84.0, earnings: 595.0 },
  { id: 'W-006', name: 'Felix Tanaka',   completed_tasks: 23,  quality_score: 72.5, earnings: 195.0 },
]

const SEED_PAYMENTS: Payment[] = [
  { id: 'P-2001', worker_id: 'W-001', worker_name: 'Alice Chen',   amount: 480.0,  status: 'processed', scheduled_for: '2026-07-10' },
  { id: 'P-2002', worker_id: 'W-002', worker_name: 'Bob Singh',    amount: 220.0,  status: 'pending',   scheduled_for: '2026-07-12' },
  { id: 'P-2003', worker_id: 'W-003', worker_name: 'Carmen Diaz',  amount: 980.0,  status: 'processed', scheduled_for: '2026-07-05' },
  { id: 'P-2004', worker_id: 'W-004', worker_name: 'Dao Wei',      amount: 360.0,  status: 'pending',   scheduled_for: '2026-07-15' },
  { id: 'P-2005', worker_id: 'W-005', worker_name: 'Esha Patel',   amount: 150.0,  status: 'failed',    scheduled_for: '2026-07-08' },
]

export const useCrowdsourceStore = defineStore('crowdsource', {
  state: (): CrowdsourceState => ({
    tasks: [],
    workers: [],
    payments: [],
    loading: false,
    error: null,
    loaded: false,
  }),

  getters: {
    completedTasksCount: (s) => s.tasks.filter(t => t.status === 'completed').length,
    pendingPaymentsCount: (s) => s.payments.filter(p => p.status === 'pending').length,
    activeWorkersCount: (s) => s.workers.filter(w => w.completed_tasks > 0).length,
  },

  actions: {
    async loadAll(): Promise<void> {
      this.loading = true
      this.error = null
      try {
        // Simulate async — in real wiring this would be 3 parallel axios calls.
        await new Promise((r) => setTimeout(r, 50))
        this.tasks = [...SEED_TASKS]
        this.workers = [...SEED_WORKERS]
        this.payments = [...SEED_PAYMENTS]
        this.loaded = true
      } catch (e: unknown) {
        this.error = e instanceof Error ? e.message : String(e)
      } finally {
        this.loading = false
      }
    },

    selectTask(id: string): CrowdsourceTask | null {
      return this.tasks.find(t => t.id === id) ?? null
    },

    selectWorker(id: string): Worker | null {
      return this.workers.find(w => w.id === id) ?? null
    },
  },
})
