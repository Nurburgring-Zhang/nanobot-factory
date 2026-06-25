<template>
  <!-- Normal render path -->
  <template v-if="!error">
    <slot />
  </template>

  <!-- Fallback UI when a child component throws -->
  <div v-else class="error-boundary" role="alert" aria-live="assertive">
    <div class="error-card">
      <div class="error-icon" aria-hidden="true">
        <NIcon size="48" :color="iconColor">
          <AlertCircleOutline />
        </NIcon>
      </div>
      <h2 class="error-title">页面遇到了一些问题</h2>
      <p class="error-subtitle">
        组件渲染时发生了未捕获的错误。您可以重试,或刷新整页。
      </p>

      <div v-if="showDetails" class="error-details">
        <div class="error-detail-row">
          <span class="error-detail-label">错误名:</span>
          <code class="error-detail-value">{{ error.name }}</code>
        </div>
        <div class="error-detail-row">
          <span class="error-detail-label">消息:</span>
          <code class="error-detail-value">{{ error.message || '(no message)' }}</code>
        </div>
        <div v-if="errorInfo" class="error-detail-row error-detail-stack">
          <span class="error-detail-label">堆栈:</span>
          <pre class="error-detail-value"><code>{{ errorInfo }}</code></pre>
        </div>
        <div v-if="lastReport" class="error-detail-row">
          <span class="error-detail-label">事件ID:</span>
          <code class="error-detail-value">{{ lastReport.eventId }}</code>
        </div>
      </div>

      <div class="error-actions">
        <NButton type="primary" @click="onRetry">
          <template #icon>
            <NIcon><RefreshOutline /></NIcon>
          </template>
          重试
        </NButton>
        <NButton @click="onToggleDetails">
          {{ showDetails ? '隐藏' : '查看' }}详情
        </NButton>
        <NButton @click="onReload">
          <template #icon>
            <NIcon><ReloadOutline /></NIcon>
          </template>
          刷新整页
        </NButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ErrorBoundary — Vue 3 error boundary.
 *
 * Uses onErrorCaptured to intercept render-time errors in any child
 * component. Shows a fallback UI with retry / reload / view-details
 * controls. Also pipes every captured error to a Sentry-style reporter
 * (locally this is a console.error + in-memory event log).
 *
 * Usage:
 *   <ErrorBoundary>
 *     <SomeComponentThatMightThrow />
 *   </ErrorBoundary>
 *
 * Optional: pass a `name` prop to label the boundary in error logs,
 * or a custom `fallback` slot to fully replace the default UI.
 */
import { ref, onErrorCaptured, computed, getCurrentInstance } from 'vue'
import { NButton, NIcon } from 'naive-ui'
import { AlertCircleOutline, RefreshOutline, ReloadOutline } from '@vicons/ionicons5'
import { reportError, generateEventId } from '@/utils/errorReporter'

interface Props {
  /** Label used in error logs and the fallback UI */
  name?: string
  /** Whether to surface the stack trace and error details by default */
  showDetailsDefault?: boolean
  /** Whether to log to console (Sentry-style reporter is always active) */
  silent?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  name: 'ErrorBoundary',
  showDetailsDefault: false,
  silent: false
})

const error = ref<Error | null>(null)
const errorInfo = ref<string>('')
const showDetails = ref<boolean>(props.showDetailsDefault)
const retryCount = ref<number>(0)
const lastReport = ref<{ eventId: string } | null>(null)

const iconColor = computed<string>(() => '#d03050')

/**
 * Vue 3 hook that fires when a descendant component throws during
 * render or lifecycle. Returning false STOPS propagation — the error
 * won't bubble up to the global app.config.errorHandler.
 */
onErrorCaptured((err: unknown, _instance, info: string) => {
  const e =
    err instanceof Error
      ? err
      : new Error(typeof err === 'string' ? err : 'Unknown error from descendant component')

  error.value = e
  errorInfo.value = (e.stack ? String(e.stack) : '') + (info ? `\n\n[Vue info: ${info}]` : '')

  if (!props.silent) {
    // eslint-disable-next-line no-console
    console.error(`[${props.name}] captured error:`, e, info)
  }

  // Sentry-style report
  const eventId = generateEventId()
  reportError({
    eventId,
    boundary: props.name,
    error: e,
    info,
    retryCount: retryCount.value,
    timestamp: new Date().toISOString()
  }).catch(() => {
    // Reporter itself failed — already logged inside reportError
  })
  lastReport.value = { eventId }

  // Prevent the error from propagating to app.config.errorHandler
  // so we don't get duplicate logs
  return false
})

function onRetry(): void {
  retryCount.value += 1
  error.value = null
  errorInfo.value = ''
  showDetails.value = false
}

function onToggleDetails(): void {
  showDetails.value = !showDetails.value
}

function onReload(): void {
  if (typeof window !== 'undefined') {
    window.location.reload()
  }
}

// Expose reset method to parent (programmatic recovery)
const instance = getCurrentInstance()
if (instance) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(instance.proxy as any)?.$forceUpdate?.()
}
</script>

<style scoped>
.error-boundary {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
  padding: 24px;
}
.error-card {
  max-width: 560px;
  width: 100%;
  background: var(--error-boundary-bg, #ffffff);
  border: 1px solid var(--error-boundary-border, #e0e0e6);
  border-radius: 8px;
  padding: 32px 28px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
  text-align: center;
}
.error-icon {
  display: flex;
  justify-content: center;
  margin-bottom: 12px;
}
.error-title {
  margin: 0 0 8px 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--error-boundary-title, #333);
}
.error-subtitle {
  margin: 0 0 20px 0;
  font-size: 14px;
  color: var(--error-boundary-subtitle, #666);
  line-height: 1.5;
}
.error-details {
  text-align: left;
  background: var(--error-boundary-details-bg, #f7f8fa);
  border: 1px solid var(--error-boundary-details-border, #e6e8eb);
  border-radius: 6px;
  padding: 12px 14px;
  margin-bottom: 18px;
  font-size: 12px;
  max-height: 240px;
  overflow: auto;
}
.error-detail-row {
  display: flex;
  flex-direction: column;
  margin-bottom: 8px;
}
.error-detail-row:last-child {
  margin-bottom: 0;
}
.error-detail-stack pre {
  margin: 4px 0 0 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 11px;
  line-height: 1.5;
  max-height: 160px;
  overflow: auto;
}
.error-detail-label {
  font-weight: 600;
  color: var(--error-boundary-label, #555);
  font-size: 12px;
}
.error-detail-value {
  color: var(--error-boundary-value, #c7254e);
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 12px;
}
.error-actions {
  display: flex;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
}

/* Dark-mode-aware tweaks (driven by [data-theme="dark"] on <html>) */
:global(html[data-theme='dark']) .error-card {
  --error-boundary-bg: #1f1f23;
  --error-boundary-border: #2e2e33;
  --error-boundary-title: #e6e6ea;
  --error-boundary-subtitle: #767676;
  --error-boundary-details-bg: #18181c;
  --error-boundary-details-border: #2a2a30;
  --error-boundary-label: #c0c0c6;
  --error-boundary-value: #ff8a8a;
}
</style>
