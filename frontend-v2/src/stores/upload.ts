import { defineStore } from 'pinia'

/**
 * Pinia store: upload
 *
 * Tracks drag-and-drop / pick-and-upload jobs across the SPA. Each
 * `UploadJob` represents one file (or one directory) being uploaded
 * with progress, status, retry counter and an optional error.
 *
 * The store does NOT make HTTP calls itself — `DragUpload.vue` calls
 * `enqueue` to register a job, then drives `XHR.send` to update
 * progress / status. This separation keeps the component testable
 * (you can swap XHR for fetch / axios / a mock transport) and lets
 * other views subscribe to upload state without coupling.
 *
 * Persistence:
 *   Only the *config* (maxConcurrent / retryLimit / chunkSize) is
 *   persisted to localStorage. Live jobs are intentionally NOT
 *   persisted across reloads — users expect an upload queue reset
 *   on a new session.
 */

export type UploadStatus = 'pending' | 'uploading' | 'success' | 'error' | 'cancelled'

export interface UploadJob {
  id: string
  name: string
  size: number
  uploadedBytes: number
  status: UploadStatus
  progress: number
  error?: string
  retries: number
  /** Optional target URL override. If omitted, the upload component
   *  resolves an endpoint from `target` + a stable id. */
  target?: string
  /** Logical target bucket — lets views filter their own jobs out of
   *  the global list. Values: 'dataset' | 'asset' | 'generic' */
  bucket: 'dataset' | 'asset' | 'generic'
  /** When true, indicates the job was a directory upload (we don't
   *  recurse the filesystem on the web — we only carry the root name
   *  for UI; real FS traversal would happen server-side). */
  isDirectory: boolean
  startedAt: number
  finishedAt?: number
  /** Optional FormData/File ref so cancellation can call xhr.abort() */
  controller?: XMLHttpRequest
}

interface UploadState {
  jobs: UploadJob[]
  /** Max parallel uploads; configurable from DragUpload.vue */
  maxConcurrent: number
  /** Max retries per job before marking failed. */
  retryLimit: number
  /** Optional chunk size for future chunked uploads. */
  chunkSize: number
}

const STORAGE_KEY = 'vdp.upload.config.v1'

interface PersistedConfig {
  maxConcurrent: number
  retryLimit: number
  chunkSize: number
}

function loadConfig(): PersistedConfig {
  if (typeof localStorage === 'undefined') {
    return { maxConcurrent: 3, retryLimit: 2, chunkSize: 0 }
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { maxConcurrent: 3, retryLimit: 2, chunkSize: 0 }
    const parsed = JSON.parse(raw) as Partial<PersistedConfig>
    return {
      maxConcurrent: typeof parsed.maxConcurrent === 'number' && parsed.maxConcurrent > 0
        ? parsed.maxConcurrent : 3,
      retryLimit: typeof parsed.retryLimit === 'number' && parsed.retryLimit >= 0
        ? parsed.retryLimit : 2,
      chunkSize: typeof parsed.chunkSize === 'number' && parsed.chunkSize >= 0
        ? parsed.chunkSize : 0,
    }
  } catch {
    return { maxConcurrent: 3, retryLimit: 2, chunkSize: 0 }
  }
}

function persistConfig(cfg: PersistedConfig): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg))
  } catch {
    /* quota / private mode — silently ignore */
  }
}

function makeId(): string {
  // Browser-grade unique id without crypto.randomUUID dependency
  return `up-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

export const useUploadStore = defineStore('upload', {
  state: (): UploadState => ({
    jobs: [],
    ...loadConfig(),
  }),

  getters: {
    activeCount: (state): number =>
      state.jobs.filter((j) => j.status === 'uploading' || j.status === 'pending').length,
    successCount: (state): number =>
      state.jobs.filter((j) => j.status === 'success').length,
    errorCount: (state): number =>
      state.jobs.filter((j) => j.status === 'error').length,
    totalBytes: (state): number =>
      state.jobs.reduce((acc, j) => acc + (j.size || 0), 0),
    uploadedBytes: (state): number =>
      state.jobs.reduce((acc, j) => acc + (j.uploadedBytes || 0), 0),
    /** Aggregated progress in [0, 1]. */
    progress: (state): number => {
      const total = state.jobs.reduce((acc, j) => acc + (j.size || 0), 0)
      if (total === 0) return 0
      const uploaded = state.jobs.reduce((acc, j) => acc + (j.uploadedBytes || 0), 0)
      return Math.min(1, uploaded / total)
    },
    /** Per-bucket filtered views. */
    datasetJobs: (state) => state.jobs.filter((j) => j.bucket === 'dataset'),
    assetJobs: (state) => state.jobs.filter((j) => j.bucket === 'asset'),
    /** Recently-finished (success or error) jobs, newest first. */
    recent: (state) => {
      return [...state.jobs]
        .filter((j) => j.status === 'success' || j.status === 'error')
        .sort((a, b) => (b.finishedAt || 0) - (a.finishedAt || 0))
        .slice(0, 20)
    },
  },

  actions: {
    enqueue(input: {
      name: string
      size: number
      bucket?: UploadJob['bucket']
      target?: string
      isDirectory?: boolean
      controller?: XMLHttpRequest
    }): UploadJob {
      const job: UploadJob = {
        id: makeId(),
        name: input.name,
        size: input.size,
        uploadedBytes: 0,
        status: 'pending',
        progress: 0,
        retries: 0,
        target: input.target,
        bucket: input.bucket ?? 'generic',
        isDirectory: !!input.isDirectory,
        startedAt: Date.now(),
        controller: input.controller,
      }
      this.jobs.unshift(job)
      // Trim history: keep at most 200 jobs to avoid unbounded growth
      if (this.jobs.length > 200) {
        this.jobs = this.jobs.slice(0, 200)
      }
      return job
    },

    updateProgress(id: string, uploadedBytes: number): void {
      const job = this.jobs.find((j) => j.id === id)
      if (!job) return
      job.uploadedBytes = uploadedBytes
      job.progress = job.size > 0 ? Math.min(1, uploadedBytes / job.size) : 0
      if (job.status === 'pending' && uploadedBytes > 0) {
        job.status = 'uploading'
      }
    },

    markSuccess(id: string): void {
      const job = this.jobs.find((j) => j.id === id)
      if (!job) return
      job.status = 'success'
      job.progress = 1
      job.uploadedBytes = job.size
      job.finishedAt = Date.now()
      job.controller = undefined
    },

    markError(id: string, error: string): void {
      const job = this.jobs.find((j) => j.id === id)
      if (!job) return
      job.status = 'error'
      job.error = error
      job.finishedAt = Date.now()
      job.controller = undefined
    },

    markCancelled(id: string): void {
      const job = this.jobs.find((j) => j.id === id)
      if (!job) return
      job.status = 'cancelled'
      job.finishedAt = Date.now()
      // Caller is expected to have already called controller?.abort()
      job.controller = undefined
    },

    /** Increment retry counter; transitions job back to pending so the
     *  caller can restart the underlying transport. */
    retry(id: string): boolean {
      const job = this.jobs.find((j) => j.id === id)
      if (!job) return false
      if (job.retries >= this.retryLimit) return false
      job.retries += 1
      job.status = 'pending'
      job.uploadedBytes = 0
      job.progress = 0
      job.error = undefined
      job.finishedAt = undefined
      return true
    },

    remove(id: string): void {
      const idx = this.jobs.findIndex((j) => j.id === id)
      if (idx >= 0) {
        const job = this.jobs[idx]
        if (job.controller && job.status === 'uploading') {
          try { job.controller.abort() } catch { /* ignore */ }
        }
        this.jobs.splice(idx, 1)
      }
    },

    clearFinished(): void {
      this.jobs = this.jobs.filter(
        (j) => j.status === 'pending' || j.status === 'uploading'
      )
    },

    setMaxConcurrent(n: number): void {
      this.maxConcurrent = Math.max(1, Math.min(10, Math.floor(n)))
      persistConfig({ maxConcurrent: this.maxConcurrent, retryLimit: this.retryLimit, chunkSize: this.chunkSize })
    },

    setRetryLimit(n: number): void {
      this.retryLimit = Math.max(0, Math.min(10, Math.floor(n)))
      persistConfig({ maxConcurrent: this.maxConcurrent, retryLimit: this.retryLimit, chunkSize: this.chunkSize })
    },
  },
})