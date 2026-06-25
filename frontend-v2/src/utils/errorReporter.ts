/**
 * errorReporter — Sentry-style local error pipeline.
 *
 * For now this is a thin wrapper that:
 *   1. Logs every captured error to the console with a stable event ID
 *   2. Keeps an in-memory ring buffer of recent events (visible via window.__lastErrorEvents__)
 *   3. Forwards to a Sentry DSN if VITE_SENTRY_DSN is set (no-op when missing)
 *
 * The contract is intentionally narrow: it accepts a plain object, never
 * throws, and resolves with the assigned eventId. Components can await it
 * if they want, but the typical call is fire-and-forget.
 */

export interface ErrorReport {
  eventId: string
  boundary: string
  error: Error
  info?: string
  retryCount?: number
  timestamp: string
  userId?: string
  url?: string
  userAgent?: string
}

const RECENT_LIMIT = 50
const recentEvents: ErrorReport[] = []

function pushRecent(report: ErrorReport): void {
  recentEvents.push(report)
  if (recentEvents.length > RECENT_LIMIT) {
    recentEvents.shift()
  }
  // Expose to window for debugging / e2e introspection
  if (typeof window !== 'undefined') {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(window as any).__lastErrorEvents__ = recentEvents
  }
}

export function generateEventId(): string {
  // 16-char base36 random, e.g. 'k2j4f9a1b8c0d3e7'
  const arr = new Uint8Array(8)
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    crypto.getRandomValues(arr)
  } else {
    for (let i = 0; i < arr.length; i += 1) {
      arr[i] = Math.floor(Math.random() * 256)
    }
  }
  return Array.from(arr, (b) => b.toString(16).padStart(2, '0')).join('')
}

function enrichReport(input: Omit<ErrorReport, 'userId' | 'url' | 'userAgent'>): ErrorReport {
  let userId: string | undefined
  if (typeof localStorage !== 'undefined') {
    try {
      const raw = localStorage.getItem('imdf.auth.user')
      if (raw) {
        const parsed = JSON.parse(raw) as { id?: string | number }
        if (parsed && parsed.id !== undefined) {
          userId = String(parsed.id)
        }
      }
    } catch {
      // ignore
    }
  }
  return {
    ...input,
    userId,
    url: typeof location !== 'undefined' ? location.href : undefined,
    userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined
  }
}

export async function reportError(input: Omit<ErrorReport, 'userId' | 'url' | 'userAgent'>): Promise<string> {
  try {
    const full = enrichReport(input)
    pushRecent(full)

    // eslint-disable-next-line no-console
    console.error('[errorReporter]', full.eventId, full.boundary, full.error, full.info)

    const dsn = import.meta.env.VITE_SENTRY_DSN
    if (dsn && typeof fetch === 'function') {
      // Real Sentry envelope would go here. Stub: just log intent.
      // eslint-disable-next-line no-console
      console.info('[errorReporter] would forward to Sentry DSN', dsn, full.eventId)
    }

    return full.eventId
  } catch (innerErr) {
    // Last-resort fallback — never throw from the reporter
    // eslint-disable-next-line no-console
    console.error('[errorReporter] internal failure', innerErr)
    return input.eventId
  }
}

export function getRecentEvents(): ReadonlyArray<ErrorReport> {
  return recentEvents
}

export function clearRecentEvents(): void {
  recentEvents.length = 0
  if (typeof window !== 'undefined') {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(window as any).__lastErrorEvents__ = recentEvents
  }
}
