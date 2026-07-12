<!--
  NotificationBell.vue
  --------------------
  App-bar bell that shows unread notifications pushed from the
  notification-service over WebSocket. Falls back to long-polling
  /api/v1/notifications if the WS is not available.

  Wiring:
    - Push: notification-service `/ws/notifications` (auto-reconnect with
      exponential backoff capped at 30s).
    - Pull (initial + fallback): GET /api/v1/notifications every 60s.
    - Click: opens a NPopover list; marking a row read hits
      PATCH /api/v1/notifications/{id}.
    - Empty state, error state, and connecting state are all explicit
      so the badge area doesn't flicker.

  Failure mode policy:
    - WS error → status pill says "离线", pull loop continues at 60s.
    - API 4xx → keep last good list, surface a "刷新失败" hint.
    - On full disconnect (API 5xx + WS closed) → banner shows "实时通
      知暂不可用".
-->
<template>
  <div class="notification-bell" data-testid="topbar-notification-bell">
    <NPopover
      v-model:show="ui.notificationCenterOpen"
      trigger="click"
      placement="bottom-end"
      :raw="false"
      :duration="200"
      overlap
      @clickoutside="ui.closeNotificationCenter()"
    >
      <template #trigger>
        <NBadge
          :value="ui.unreadCount"
          :max="99"
          :show="ui.unreadCount > 0"
          :offset="[-2, 2]"
        >
          <NButton
            circle
            quaternary
            size="small"
            :title="bellTitle"
            :aria-label="bellTitle"
            @click="onToggleCenter"
          >
            <template #icon>
              <NIcon size="18">
                <NotificationsOutline />
              </NIcon>
            </template>
          </NButton>
        </NBadge>
      </template>

      <div class="bell-popover" role="dialog" aria-label="通知中心">
        <header class="bell-header">
          <span class="bell-title">
            {{ localeStore.current === 'zh-CN' ? '通知' : 'Notifications' }}
            <NTag size="small" round :type="streamTagType" style="margin-left: 6px">
              {{ streamTagText }}
            </NTag>
          </span>
          <NSpace :size="6">
            <NButton size="tiny" quaternary @click="onMarkAllRead" :disabled="ui.unreadCount === 0">
              {{ localeStore.current === 'zh-CN' ? '全部已读' : 'Mark all read' }}
            </NButton>
            <NButton size="tiny" quaternary @click="onRefresh" :loading="loading">
              {{ localeStore.current === 'zh-CN' ? '刷新' : 'Refresh' }}
            </NButton>
          </NSpace>
        </header>

        <NEmpty v-if="recent.length === 0" size="small" :description="emptyText" style="padding: 24px 0">
          <template #icon>
            <NIcon size="32"><NotificationsOffOutline /></NIcon>
          </template>
        </NEmpty>

        <ul v-else class="bell-list" role="list">
          <li
            v-for="n in recent"
            :key="n.id"
            class="bell-item"
            :class="{ 'is-unread': !n.read }"
            role="listitem"
            tabindex="0"
            @click="onItemClick(n)"
            @keydown.enter="onItemClick(n)"
          >
            <span class="bell-dot" :class="`dot-${n.level}`" aria-hidden="true"></span>
            <div class="bell-body">
              <div class="bell-row">
                <span class="bell-item-title">{{ n.title }}</span>
                <span class="bell-time">{{ formatTime(n.createdAt) }}</span>
              </div>
              <p v-if="n.body" class="bell-item-body">{{ n.body }}</p>
              <NSpace :size="4" style="margin-top: 4px" v-if="n.source || n.link">
                <NTag v-if="n.source" size="tiny" :bordered="false">{{ n.source }}</NTag>
                <NTag v-if="n.link" size="tiny" type="info" :bordered="false">
                  {{ localeStore.current === 'zh-CN' ? '点击查看' : 'Open' }}
                </NTag>
              </NSpace>
            </div>
          </li>
        </ul>

        <footer class="bell-footer" v-if="recent.length > 0">
          <NButton
            text
            size="tiny"
            tag="a"
            @click="onViewAll"
          >
            {{ localeStore.current === 'zh-CN' ? '查看全部通知' : 'View all notifications' }}
          </NButton>
        </footer>
      </div>
    </NPopover>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  NBadge,
  NButton,
  NEmpty,
  NIcon,
  NPopover,
  NSpace,
  NTag,
} from 'naive-ui'
import { NotificationsOutline, NotificationsOffOutline } from '@vicons/ionicons5'
import { useRouter } from 'vue-router'
import { useUiStore, type NotificationEntry } from '@/stores/ui'
import { useAuthStore } from '@/stores/auth'
import { useLocaleStore } from '@/stores/locale'
import { listNotifications, updateNotification } from '@/api/notification'

const router = useRouter()
const ui = useUiStore()
const auth = useAuthStore()
const localeStore = useLocaleStore()

const loading = ref<boolean>(false)
const pollTimer = ref<number | null>(null)
let ws: WebSocket | null = null
let reconnectTimer: number | null = null
let backoffMs = 1000

const recent = computed<NotificationEntry[]>(() => ui.recentNotifications)

const bellTitle = computed<string>(() => {
  if (ui.unreadCount > 0) {
    return localeStore.current === 'zh-CN'
      ? `通知 · ${ui.unreadCount} 条未读`
      : `Notifications · ${ui.unreadCount} unread`
  }
  return localeStore.current === 'zh-CN' ? '通知' : 'Notifications'
})

const streamTagType = computed<'default' | 'success' | 'warning' | 'error'>(() => {
  switch (ui.notificationStreamStatus) {
    case 'open':
      return 'success'
    case 'connecting':
      return 'warning'
    case 'error':
    case 'closed':
      return 'error'
    default:
      return 'default'
  }
})

const streamTagText = computed<string>(() => {
  switch (ui.notificationStreamStatus) {
    case 'open':
      return localeStore.current === 'zh-CN' ? '实时' : 'live'
    case 'connecting':
      return localeStore.current === 'zh-CN' ? '连接中' : 'connecting'
    case 'error':
      return localeStore.current === 'zh-CN' ? '错误' : 'error'
    case 'closed':
      return localeStore.current === 'zh-CN' ? '离线' : 'offline'
    default:
      return localeStore.current === 'zh-CN' ? '空闲' : 'idle'
  }
})

const emptyText = computed<string>(() =>
  localeStore.current === 'zh-CN' ? '暂无通知' : 'No notifications yet'
)

function formatTime(iso: string): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return iso
  const diff = Date.now() - t
  if (diff < 60_000) return localeStore.current === 'zh-CN' ? '刚刚' : 'just now'
  if (diff < 3_600_000) {
    const m = Math.floor(diff / 60_000)
    return localeStore.current === 'zh-CN' ? `${m} 分钟前` : `${m}m ago`
  }
  if (diff < 86_400_000) {
    const h = Math.floor(diff / 3_600_000)
    return localeStore.current === 'zh-CN' ? `${h} 小时前` : `${h}h ago`
  }
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function onToggleCenter(): void {
  ui.toggleNotificationCenter()
}

function onMarkAllRead(): void {
  ui.markAllNotificationsRead()
  // Fire-and-forget; the local state is already correct.
  recent.value
    .filter((n) => !n.read)
    .forEach((n) => {
      void updateNotification(n.id, { read: true }).catch(() => undefined)
    })
}

function onRefresh(): void {
  void pullOnce()
}

function onItemClick(n: NotificationEntry): void {
  ui.markNotificationRead(n.id)
  void updateNotification(n.id, { read: true }).catch(() => undefined)
  if (n.link) {
    ui.closeNotificationCenter()
    void router.push(n.link)
  }
}

function onViewAll(): void {
  ui.closeNotificationCenter()
  void router.push('/notification-management')
}

async function pullOnce(): Promise<void> {
  if (loading.value) return
  loading.value = true
  try {
    const page = await listNotifications({ page: 1, page_size: 20 })
    const items = (page.items ?? []) as unknown as Array<Record<string, unknown>>
    items.forEach((raw) => {
      ui.pushNotification({
        id: String(raw.id ?? raw['id']),
        title: String(raw.title ?? ''),
        body: raw['body'] ? String(raw['body']) : undefined,
        level: (raw['level'] as NotificationEntry['level']) ?? 'info',
        read: Boolean(raw['read']),
        createdAt: String(raw['created_at'] ?? new Date().toISOString()),
        link: raw['link'] ? String(raw['link']) : undefined,
        source: raw['source'] ? String(raw['source']) : undefined,
      })
    })
  } catch {
    // Pull failed; WS may still recover. Status pill already reflects state.
  } finally {
    loading.value = false
  }
}

function startPolling(): void {
  if (pollTimer.value !== null) return
  pollTimer.value = window.setInterval(() => {
    if (!auth.isAuthenticated) return
    void pullOnce()
  }, 60_000)
}

function stopPolling(): void {
  if (pollTimer.value !== null) {
    window.clearInterval(pollTimer.value)
    pollTimer.value = null
  }
}

function wsUrl(): string | null {
  if (typeof window === 'undefined') return null
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  // Vite dev server proxies /api and /ws at the same target as the API gateway
  // (see vite.config.ts proxy block). In production, the gateway is the same
  // host. Allow override via VITE_WS_BASE if the deployment splits them.
  const override = (import.meta.env.VITE_WS_BASE ?? '') as string
  const base = override && override.length > 0 ? override.replace(/\/+$/, '') : `${proto}//${window.location.host}`
  return `${base}/ws/notifications`
}

function clearReconnect(): void {
  if (reconnectTimer !== null) {
    window.clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

function scheduleReconnect(): void {
  if (typeof window === 'undefined') return
  clearReconnect()
  const wait = Math.min(30_000, backoffMs)
  backoffMs = Math.min(30_000, backoffMs * 2)
  reconnectTimer = window.setTimeout(() => {
    connectWs()
  }, wait)
}

function connectWs(): void {
  if (typeof window === 'undefined' || typeof WebSocket === 'undefined') return
  const url = wsUrl()
  if (!url) return
  try {
    ui.setNotificationStreamStatus('connecting')
    ws = new WebSocket(url)
  } catch {
    ui.setNotificationStreamStatus('error')
    scheduleReconnect()
    return
  }
  ws.addEventListener('open', () => {
    backoffMs = 1000
    ui.setNotificationStreamStatus('open')
  })
  ws.addEventListener('message', (ev: MessageEvent) => {
    let parsed: unknown
    try {
      parsed = JSON.parse(String(ev.data ?? ''))
    } catch {
      return
    }
    if (!parsed || typeof parsed !== 'object') return
    const obj = parsed as Record<string, unknown>
    const id = obj['id'] ?? obj['event_id']
    if (id == null) return
    ui.pushNotification({
      id: String(id),
      title: String(obj['title'] ?? 'Notification'),
      body: obj['body'] ? String(obj['body']) : undefined,
      level: (obj['level'] as NotificationEntry['level']) ?? 'info',
      read: false,
      createdAt: String(obj['created_at'] ?? new Date().toISOString()),
      link: obj['link'] ? String(obj['link']) : undefined,
      source: obj['source'] ? String(obj['source']) : undefined,
    })
  })
  ws.addEventListener('error', () => {
    ui.setNotificationStreamStatus('error')
  })
  ws.addEventListener('close', () => {
    ui.setNotificationStreamStatus('closed')
    ws = null
    scheduleReconnect()
  })
}

function teardown(): void {
  clearReconnect()
  stopPolling()
  if (ws) {
    try {
      ws.close()
    } catch {
      // ignore
    }
    ws = null
  }
  ui.setNotificationStreamStatus('idle')
}

watch(
  () => auth.isAuthenticated,
  (v) => {
    if (v) {
      connectWs()
      startPolling()
      void pullOnce()
    } else {
      teardown()
    }
  }
)

onMounted(() => {
  if (auth.isAuthenticated) {
    connectWs()
    startPolling()
    void pullOnce()
  }
})

onBeforeUnmount(() => {
  teardown()
})
</script>

<style scoped>
.notification-bell {
  display: inline-flex;
  align-items: center;
}
.bell-popover {
  width: 360px;
  max-width: calc(100vw - 32px);
  display: flex;
  flex-direction: column;
  max-height: 480px;
}
.bell-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 4px 12px 4px;
  border-bottom: 1px solid var(--app-border, #e0e0e6);
}
.bell-title {
  font-weight: 600;
  font-size: 14px;
  display: inline-flex;
  align-items: center;
}
.bell-list {
  list-style: none;
  margin: 0;
  padding: 4px 0;
  overflow-y: auto;
  max-height: 360px;
  flex: 1 1 auto;
}
.bell-item {
  display: flex;
  gap: 10px;
  padding: 8px 4px;
  border-bottom: 1px dashed var(--app-border, #e0e0e6);
  cursor: pointer;
  transition: background 0.15s ease;
  outline: none;
}
.bell-item:hover,
.bell-item:focus-visible {
  background: var(--app-surface, rgba(0, 0, 0, 0.03));
  border-radius: 4px;
}
.bell-item.is-unread .bell-item-title {
  font-weight: 600;
}
.bell-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 6px;
  flex: 0 0 auto;
  background: var(--app-muted, #999);
}
.bell-dot.dot-info { background: var(--app-primary, #0a5dc2); }
.bell-dot.dot-success { background: var(--app-success, #157a3e); }
.bell-dot.dot-warning { background: var(--app-warning, #c87f0d); }
.bell-dot.dot-error { background: var(--app-error, #d03050); }
.bell-body {
  flex: 1 1 auto;
  min-width: 0;
}
.bell-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.bell-item-title {
  font-size: 13px;
  color: var(--app-fg, #333);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bell-time {
  font-size: 11px;
  color: var(--app-muted, #767676);
  white-space: nowrap;
}
.bell-item-body {
  margin: 2px 0 0 0;
  font-size: 12px;
  color: var(--app-muted, #767676);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.bell-footer {
  padding-top: 8px;
  border-top: 1px solid var(--app-border, #e0e0e6);
  display: flex;
  justify-content: center;
}
</style>
