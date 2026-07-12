<template>
  <div class="chat-panel" :class="{ 'chat-panel--collapsed': collapsed }">
    <div class="chat-header" @click="toggle">
      <div class="chat-header__title">
        <n-icon size="18"><ChatboxEllipsesOutline /></n-icon>
        <span>智影 V4 — 智能数据助手</span>
      </div>
      <div class="chat-header__actions">
        <n-tag v-if="status" :type="status.success ? 'success' : 'error'" size="small" round>
          {{ (status.sessions && status.sessions.active_sessions) || 0 }} 会话
        </n-tag>
        <n-button text @click.stop="toggle">
          <n-icon size="16">
            <ChevronUp v-if="!collapsed" />
            <ChevronDown v-else />
          </n-icon>
        </n-button>
      </div>
    </div>

    <div v-show="!collapsed" class="chat-body">
      <div ref="messagesRef" class="chat-messages">
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          :class="['chat-message', `chat-message--${msg.role}`]"
        >
          <div class="chat-message__avatar">
            <span v-if="msg.role === 'user'">👤</span>
            <span v-else>🤖</span>
          </div>
          <div class="chat-message__content">
            <div class="chat-message__text" v-html="formatText(msg.text)" />
            <div v-if="msg.meta" class="chat-message__meta">
              <n-tag v-if="msg.meta.intent" size="small" :bordered="false">{{ msg.meta.intent }}</n-tag>
              <n-tag v-if="msg.meta.action" size="small" type="info" :bordered="false">{{ msg.meta.action }}</n-tag>
              <span v-if="msg.meta.duration_ms" class="chat-message__duration">{{ msg.meta.duration_ms.toFixed(0) }}ms</span>
            </div>
            <div v-if="msg.suggestions && msg.suggestions.length" class="chat-message__suggestions">
              <n-button
                v-for="(s, i) in msg.suggestions"
                :key="i"
                size="tiny"
                round
                @click="sendText(s)"
              >
                {{ s }}
              </n-button>
            </div>
          </div>
        </div>
        <div v-if="loading" class="chat-message chat-message--assistant chat-message--loading">
          <div class="chat-message__avatar">🤖</div>
          <div class="chat-message__content">
            <div class="chat-message__text">
              <n-spin size="small" />
              思考中...
            </div>
          </div>
        </div>
      </div>

      <div class="chat-input">
        <n-input
          v-model:value="inputText"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          placeholder="输入指令,例如: 爬取 https://example.com / 搜索 transformer 论文 / 自动打标"
          @keydown.enter.exact.prevent="send"
          :disabled="loading"
        />
        <div class="chat-input__actions">
          <n-checkbox v-model:checked="useWebSocket">实时</n-checkbox>
          <n-button @click="clear" size="tiny">清空</n-button>
          <n-button @click="newSession" size="tiny">新会话</n-button>
          <n-button type="primary" @click="send" :loading="loading" size="tiny">发送</n-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import {
  NInput, NButton, NTag, NIcon, NCheckbox, NSpin,
  useMessage
} from 'naive-ui'
import { ChatboxEllipsesOutline, ChevronUp, ChevronDown } from '@vicons/ionicons5'
import * as intelligenceApi from '@/api/intelligence'

const collapsed = ref(false)
const inputText = ref('')
const messages = ref<Array<{
  role: 'user' | 'assistant'
  text: string
  meta?: any
  suggestions?: string[]
  ts: number
}>>([])
const loading = ref(false)
const useWebSocket = ref(true)
const sessionId = ref<string | null>(null)
const messagesRef = ref<HTMLElement | null>(null)
const status = ref<any>(null)
let ws: WebSocket | null = null

function toggle() {
  collapsed.value = !collapsed.value
}

function newSession() {
  sessionId.value = null
  messages.value = []
  if (ws) {
    ws.close()
    ws = null
  }
}

function clear() {
  messages.value = []
}

function addMessage(role: 'user' | 'assistant', text: string, meta?: any, suggestions?: string[]) {
  messages.value.push({ role, text, meta, suggestions, ts: Date.now() })
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

function formatText(text: string): string {
  if (!text) return ''
  let t = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  t = t.replace(/```([\s\S]*?)```/g, '<pre>$1</pre>')
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>')
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  t = t.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank">$1</a>')
  t = t.replace(/\n/g, '<br/>')
  return t
}

async function refreshStatus() {
  try {
    const r = await intelligenceApi.getStatus()
    status.value = r.status
  } catch (e) {
    // silent
  }
}

async function sendText(text: string) {
  inputText.value = text
  await send()
}

async function send() {
  const text = inputText.value.trim()
  if (!text || loading.value) return
  inputText.value = ''
  addMessage('user', text)
  loading.value = true
  try {
    if (useWebSocket.value) {
      await sendViaWebSocket(text)
    } else {
      await sendViaHttp(text)
    }
  } catch (e: any) {
    addMessage('assistant', `错误: ${e?.message || e}`, { intent: 'error' })
  } finally {
    loading.value = false
  }
}

async function sendViaHttp(text: string) {
  const r = await intelligenceApi.chat({
    text,
    session_id: sessionId.value,
    user_id: 'web-user',
  })
  sessionId.value = r.session_id
  addMessage(
    'assistant',
    r.response || r.error || '无响应',
    {
      intent: r.intent,
      action: r.action,
      success: r.success,
      duration_ms: r.duration_ms,
    },
    r.suggestions,
  )
}

async function sendViaWebSocket(text: string) {
  return new Promise<void>((resolve, reject) => {
    const ensureWs = () => {
      if (ws && ws.readyState === WebSocket.OPEN) return Promise.resolve(ws)
      return new Promise<WebSocket>((res, rej) => {
        const url = intelligenceApi.getChatWebSocketURL(sessionId.value || undefined)
        const sock = new WebSocket(url)
        sock.onopen = () => res(sock)
        sock.onerror = () => rej(new Error('WebSocket 连接失败'))
        ws = sock
      })
    }
    ensureWs().then((sock) => {
      const handler = (ev: MessageEvent) => {
        try {
          const data = JSON.parse(ev.data)
          if (data.type === 'turn') {
            sessionId.value = data.session_id
            addMessage(
              'assistant',
              data.response || data.error || '无响应',
              {
                intent: data.intent,
                action: data.action,
                success: data.success,
                duration_ms: data.duration_ms,
              },
              data.suggestions,
            )
            sock.removeEventListener('message', handler)
            resolve()
          } else if (data.type === 'error') {
            addMessage('assistant', `错误: ${data.error}`, { intent: 'error' })
            sock.removeEventListener('message', handler)
            reject(new Error(data.error))
          }
        } catch (e) {
          // ignore parse error
        }
      }
      sock.addEventListener('message', handler)
      sock.send(JSON.stringify({ text, session_id: sessionId.value, user_id: 'web-user' }))
    }).catch(reject)
  })
}

onMounted(() => {
  refreshStatus()
  setInterval(refreshStatus, 30000)
  addMessage(
    'assistant',
    '你好!我是智影 V4 智能数据助手。\n\n我可以帮你:\n- 🕷️ 爬取网页 (50+ 渠道: Web/API/RSS/Social/学术)\n- 🔍 搜索 (DuckDuckGo/Bing/SerpAPI/Google)\n- 🏷️ 自动打标 (多模型投票)\n- ⭐ 质量/美学评分\n- 📊 项目管理 + 工作流\n\n试试说: "爬取 https://arxiv.org/list/cs.AI/recent"',
    undefined,
    [
      '帮帮我',
      '爬取 arxiv 关于 diffusion 的论文',
      '搜索 reddit r/MachineLearning',
      '创建项目 名称 ai_research',
    ],
  )
})

onUnmounted(() => {
  if (ws) {
    ws.close()
    ws = null
  }
})
</script>

<style scoped>
.chat-panel {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 420px;
  max-width: calc(100vw - 48px);
  height: 600px;
  max-height: calc(100vh - 48px);
  background: var(--app-surface, #fff);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  z-index: 9999;
  border: 1px solid var(--app-border, #e4e7ed);
  transition: all 0.3s ease;
}

.chat-panel--collapsed {
  height: 48px;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--app-border, #e4e7ed);
  cursor: pointer;
  user-select: none;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border-radius: 12px 12px 0 0;
}

.chat-header__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 14px;
}

.chat-header__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chat-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-message {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.chat-message--user {
  flex-direction: row-reverse;
}

.chat-message--user .chat-message__content {
  background: var(--app-primary, #2080f0);
  color: #fff;
}

.chat-message__avatar {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--app-primary-light, #d9ecff);
  border-radius: 50%;
  font-size: 16px;
  flex-shrink: 0;
}

.chat-message--user .chat-message__avatar {
  background: var(--app-success-light, #e1f3d8);
}

.chat-message__content {
  background: var(--app-bg, #f5f7fa);
  padding: 8px 12px;
  border-radius: 8px;
  max-width: 80%;
  word-break: break-word;
}

.chat-message__text {
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.chat-message__text :deep(pre) {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 12px;
}

.chat-message__text :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 1px 4px;
  border-radius: 2px;
  font-size: 12px;
}

.chat-message__meta {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 6px;
  font-size: 12px;
  color: var(--app-muted, #909399);
}

.chat-message--user .chat-message__meta {
  color: rgba(255, 255, 255, 0.85);
}

.chat-message__duration {
  font-size: 11px;
  color: var(--app-muted, #c0c4cc);
}

.chat-message__suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.chat-input {
  border-top: 1px solid var(--app-border, #e4e7ed);
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.chat-input__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: flex-end;
}
</style>
