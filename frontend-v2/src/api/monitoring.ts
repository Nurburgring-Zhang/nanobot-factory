import { http } from './http'

// Monitoring surfaces Prometheus /metrics and /healthz from backend/routes/health.py
// plus service-level /healthz on each microservice.

export interface MetricSample {
  name: string
  labels: Record<string, string>
  value: number
}

export interface PrometheusPayload {
  raw: string
  samples: MetricSample[]
  /** parsed summary — convenient previews for the dashboard */
  summary: {
    processCount?: number
    memoryRssBytes?: number
    memoryVmsBytes?: number
    cpuSeconds?: number
    openFds?: number
    threads?: number
    perService?: Record<string, { status: 'ok' | 'down' | 'unknown'; latencyMs?: number }>
  }
  fetchedAt: string
}

export interface ServiceHealth {
  name: string
  baseUrl: string
  status: 'ok' | 'down' | 'unknown'
  latencyMs?: number
  version?: string
  detail?: Record<string, unknown>
}

// In production we hit /metrics + /healthz on a configurable origin.
// For dev / docker-compose the gateway runs at 18080.
const GATEWAY = '/api'

/** Parse a Prometheus exposition payload into typed samples. */
export function parsePrometheus(text: string): { samples: MetricSample[]; summary: PrometheusPayload['summary'] } {
  const samples: MetricSample[] = []
  const summary: PrometheusPayload['summary'] = {}
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    // metric_name{label="value",...}  number [timestamp]
    const m = line.match(/^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([0-9eE.+\-]+)(?:\s+\d+)?$/)
    if (!m) continue
    const name = m[1]
    const labels: Record<string, string> = {}
    const labelBlock = m[2]
    if (labelBlock) {
      const inner = labelBlock.slice(1, -1)
      // split on commas not inside quotes
      const parts: string[] = []
      let depth = 0
      let buf = ''
      let inQuote = false
      for (let i = 0; i < inner.length; i++) {
        const c = inner[i]
        if (c === '"' && inner[i - 1] !== '\\') inQuote = !inQuote
        if (!inQuote && c === ',' && depth === 0) {
          parts.push(buf); buf = ''
        } else {
          buf += c
        }
      }
      if (buf) parts.push(buf)
      for (const p of parts) {
        const eq = p.indexOf('=')
        if (eq < 0) continue
        const k = p.slice(0, eq).trim()
        let v = p.slice(eq + 1).trim()
        if (v.startsWith('"') && v.endsWith('"')) v = v.slice(1, -1)
        labels[k] = v
      }
    }
    const value = parseFloat(m[3])
    if (!Number.isFinite(value)) continue
    samples.push({ name, labels, value })
    switch (name) {
      case 'process_count':
      case 'processes_total':
        summary.processCount = (summary.processCount ?? 0) + value
        break
      case 'process_resident_memory_bytes':
      case 'process_memory_rss_bytes':
        summary.memoryRssBytes = (summary.memoryRssBytes ?? 0) + value
        break
      case 'process_virtual_memory_bytes':
      case 'process_memory_vms_bytes':
        summary.memoryVmsBytes = (summary.memoryVmsBytes ?? 0) + value
        break
      case 'process_cpu_seconds_total':
        summary.cpuSeconds = (summary.cpuSeconds ?? 0) + value
        break
      case 'process_open_fds':
        summary.openFds = (summary.openFds ?? 0) + value
        break
      case 'process_threads':
        summary.threads = (summary.threads ?? 0) + value
        break
    }
  }
  return { samples, summary }
}

export async function fetchMetrics(): Promise<PrometheusPayload> {
  const t0 = performance.now()
  // try Prometheus exposition format first
  try {
    const res = await http.get<string>(`${GATEWAY}/metrics`, { responseType: 'text', transformResponse: [(d) => d] })
    const text = typeof res.data === 'string' ? res.data : JSON.stringify(res.data)
    const { samples, summary } = parsePrometheus(text)
    return { raw: text, samples, summary, fetchedAt: new Date().toISOString() }
  } catch {
    // fall back to JSON summary
    try {
      const json = (await http.get(`${GATEWAY}/metrics/json`)).data as Record<string, unknown>
      const text = JSON.stringify(json, null, 2)
      return { raw: text, samples: [], summary: json as any, fetchedAt: new Date().toISOString() }
    } catch {
      void t0
      return { raw: '', samples: [], summary: {}, fetchedAt: new Date().toISOString() }
    }
  }
}

export async function fetchHealth(services: ServiceHealth[]): Promise<ServiceHealth[]> {
  return Promise.all(services.map(async (svc) => {
    const t0 = performance.now()
    try {
      const res = await http.get(`${svc.baseUrl}/healthz`, { timeout: 5000 })
      const latency = Math.round(performance.now() - t0)
      return {
        ...svc,
        status: 'ok',
        latencyMs: latency,
        detail: typeof res.data === 'object' ? res.data : { raw: res.data },
      }
    } catch (e) {
      return { ...svc, status: 'down', latencyMs: Math.round(performance.now() - t0), detail: { error: (e as Error).message } }
    }
  }))
}

/** Default service roster — matches backend compose / k8s deployment. */
export const DEFAULT_SERVICES: ServiceHealth[] = [
  { name: 'API Gateway', baseUrl: '', status: 'unknown' },
  { name: 'agent-service', baseUrl: '', status: 'unknown' },
  { name: 'annotation-service', baseUrl: '', status: 'unknown' },
  { name: 'asset-service', baseUrl: '', status: 'unknown' },
  { name: 'cleaning-service', baseUrl: '', status: 'unknown' },
  { name: 'collection-service', baseUrl: '', status: 'unknown' },
  { name: 'dataset-service', baseUrl: '', status: 'unknown' },
  { name: 'evaluation-service', baseUrl: '', status: 'unknown' },
  { name: 'notification-service', baseUrl: '', status: 'unknown' },
  { name: 'scoring-service', baseUrl: '', status: 'unknown' },
  { name: 'search-service', baseUrl: '', status: 'unknown' },
  { name: 'user-service', baseUrl: '', status: 'unknown' },
  { name: 'workflow-service', baseUrl: '', status: 'unknown' },
]