import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import { useThemeStore } from './stores/theme'
import { useLocaleStore } from './stores/locale'
import { reportError, generateEventId } from './utils/errorReporter'
import { i18n } from './locales'

// Global a11y + WCAG styles (focus-visible, skip-link, high-contrast tokens)
import './styles/a11y.css'

// Global RTL stylesheet — activated by `<html dir="rtl">` set automatically
// when locale is ar-SA. See setLocale() in `@/locales/index.ts`.
import './styles/rtl.css'

// Create app + plugins
const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(i18n)

// Restore auth + theme + locale from localStorage BEFORE first navigation so
// route guards and the initial paint see the correct state.
const auth = useAuthStore()
auth.restoreFromStorage()

const themeStore = useThemeStore()
themeStore.restoreFromStorage()
const unbindSystem = themeStore.bindSystemListener()
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    unbindSystem()
  })
}

// Locale bootstrap — picks up localStorage / navigator.language and applies
// the right <html lang> attribute for assistive tech.
const localeStore = useLocaleStore()
localeStore.restoreFromStorage()

// Global error handlers — backstop for errors that escape the
// <ErrorBoundary> tree (async work, setTimeout, event handlers, etc.)

/**
 * Synchronous render/lifecycle errors. By the time we get here the
 * ErrorBoundary in App.vue has already had a chance to capture; this
 * handler logs anything that bubbled past it.
 */
app.config.errorHandler = (err, _instance, info) => {
  const e =
    err instanceof Error
      ? err
      : new Error(typeof err === 'string' ? err : 'Unknown app error')
  // eslint-disable-next-line no-console
  console.error('[app.config.errorHandler]', info, e)
  const eventId = generateEventId()
  void reportError({
    eventId,
    boundary: 'app.config.errorHandler',
    error: e,
    info,
    timestamp: new Date().toISOString()
  })
}

/**
 * Unhandled promise rejections — log + report. We don't surface these
 * to the user directly (avoid a 5-flash of toasts on hydration issues)
 * but we keep them in the in-memory event log so /monitoring or
 * support tooling can introspect via window.__lastErrorEvents__.
 */
if (typeof window !== 'undefined') {
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason
    const e =
      reason instanceof Error
        ? reason
        : new Error(
            typeof reason === 'string'
              ? reason
              : `Unhandled rejection: ${String(reason)}`
          )
    // eslint-disable-next-line no-console
    console.error('[unhandledrejection]', e)
    const eventId = generateEventId()
    void reportError({
      eventId,
      boundary: 'window.unhandledrejection',
      error: e,
      info: 'async',
      timestamp: new Date().toISOString()
    })
  })
}

// Mount
app.mount('#app')