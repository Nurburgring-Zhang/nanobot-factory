<template>
  <div class="v5-chat-panel" :class="{ 'v5-chat-panel--collapsed': collapsed }">
    <div class="v5-header" @click="toggle">
      <div class="v5-header__title">
        <n-icon size="18"><SparklesOutline /></n-icon>
        <span>智影 V5 — 智能体 (Hermes/Loop/Obsidian/MoA/Pavo/Gooseworks)</span>
      </div>
      <div class="v5-header__actions">
        <n-tag v-if="stats" :type="statsOk ? 'success' : 'warning'" size="small" round>
          {{ stats.bots || 0 }} Bots · {{ stats.roles || 0 }} Roles · {{ stats.mcp_tools || 0 }} Tools
        </n-tag>
        <n-button text @click.stop="toggle">
          <n-icon size="16">
            <ChevronUp v-if="!collapsed" />
            <ChevronDown v-else />
          </n-icon>
        </n-button>
      </div>
    </div>

    <div v-show="!collapsed" class="v5-body">
      <!-- 功能快捷面板 -->
      <div class="v5-quickbar">
        <n-dropdown :options="quickActions" trigger="click" @select="onQuickAction">
          <n-button size="tiny">V5 能力 ▾</n-button>
        </n-dropdown>
        <n-tag :type="activeTab === 'chat' ? 'primary' : 'default'" size="small" @click="activeTab = 'chat'" style="cursor: pointer">
          对话
        </n-tag>
        <n-tag :type="activeTab === 'harness' ? 'primary' : 'default'" size="small" @click="activeTab = 'harness'" style="cursor: pointer">
          Harness
        </n-tag>
        <n-tag :type="activeTab === 'memory' ? 'primary' : 'default'" size="small" @click="activeTab = 'memory'" style="cursor: pointer">
          Memory
        </n-tag>
        <n-tag :type="activeTab === 'roles' ? 'primary' : 'default'" size="small" @click="activeTab = 'roles'" style="cursor: pointer">
          Roles
        </n-tag>
        <n-tag :type="activeTab === 'mcp' ? 'primary' : 'default'" size="small" @click="activeTab = 'mcp'" style="cursor: pointer">
          MCP
        </n-tag>
        <n-tag :type="activeTab === 'video' ? 'primary' : 'default'" size="small" @click="activeTab = 'video'" style="cursor: pointer">
          Video
        </n-tag>
        <n-tag :type="activeTab === 'geo' ? 'primary' : 'default'" size="small" @click="activeTab = 'geo'" style="cursor: pointer">
          Geo
        </n-tag>
      </div>

      <!-- 对话 Tab -->
      <div v-if="activeTab === 'chat'" class="v5-tab-body">
        <div ref="messagesRef" class="v5-messages">
          <div
            v-for="(msg, idx) in messages"
            :key="idx"
            :class="['v5-message', `v5-message--${msg.role}`]"
          >
            <div class="v5-message__avatar">
              <span v-if="msg.role === 'user'">👤</span>
              <span v-else>🤖</span>
            </div>
            <div class="v5-message__content">
              <div class="v5-message__text" v-html="formatText(msg.text)" />
              <div v-if="msg.meta" class="v5-message__meta">
                <n-tag v-if="msg.meta.tab" size="small" :bordered="false" type="info">{{ msg.meta.tab }}</n-tag>
                <span v-if="msg.meta.duration_ms" class="v5-message__duration">{{ msg.meta.duration_ms.toFixed(0) }}ms</span>
              </div>
            </div>
          </div>
        </div>
        <div class="v5-input">
          <n-input
            v-model:value="inputText"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            placeholder="试试: 规划一个爬虫项目 / 创建一个营销视频 / 搜索平台数据 / 列出所有角色"
            @keydown.enter.exact.prevent="send"
            :disabled="loading"
          />
          <div class="v5-input__actions">
            <n-button @click="clear" size="tiny">清空</n-button>
            <n-button type="primary" @click="send" :loading="loading" size="tiny">发送</n-button>
          </div>
        </div>
      </div>

      <!-- Harness Tab -->
      <div v-else-if="activeTab === 'harness'" class="v5-tab-body">
        <n-space vertical>
          <n-input v-model:value="harnessPrompt" type="textarea" placeholder="输入需求,例如: 做一个新闻爬虫" :rows="3" />
          <n-space>
            <n-button @click="runHarness('plan')" :loading="loading" size="small">规划</n-button>
            <n-button @click="runHarness('full')" :loading="loading" size="small" type="primary">完整 Loop</n-button>
          </n-space>
          <div v-if="harnessResult" class="v5-result">
            <pre>{{ JSON.stringify(harnessResult, null, 2) }}</pre>
          </div>
        </n-space>
      </div>

      <!-- Memory Tab -->
      <div v-else-if="activeTab === 'memory'" class="v5-tab-body">
        <n-space vertical>
          <n-input v-model:value="memoryTitle" placeholder="标题" />
          <n-input v-model:value="memoryContent" type="textarea" placeholder="内容" :rows="2" />
          <n-space>
            <n-button @click="addMemory('raw')" :loading="loading" size="small">RAW 写入</n-button>
            <n-button @click="addMemory('inbox')" :loading="loading" size="small">INBOX 写入</n-button>
            <n-button @click="addMemory('palace')" :loading="loading" size="small">安装 Palace</n-button>
          </n-space>
          <div v-if="memoryResult" class="v5-result">
            <pre>{{ JSON.stringify(memoryResult, null, 2) }}</pre>
          </div>
        </n-space>
      </div>

      <!-- Roles Tab -->
      <div v-else-if="activeTab === 'roles'" class="v5-tab-body">
        <n-space vertical>
          <n-button @click="loadRoles" :loading="loading" size="small" type="primary">加载角色列表</n-button>
          <div v-if="roles.length" class="v5-result">
            <n-list>
              <n-list-item v-for="r in roles.slice(0, 20)" :key="r.role_id">
                <div><strong>{{ r.name }}</strong> · {{ r.department }}</div>
                <div style="font-size: 12px; color: #888">{{ r.description || '' }}</div>
              </n-list-item>
            </n-list>
          </div>
        </n-space>
      </div>

      <!-- MCP Tab -->
      <div v-else-if="activeTab === 'mcp'" class="v5-tab-body">
        <n-space vertical>
          <n-button @click="loadMcpTools" :loading="loading" size="small" type="primary">加载 MCP 工具</n-button>
          <div v-if="mcpTools.length" class="v5-result">
            <n-list>
              <n-list-item v-for="t in mcpTools" :key="t.name">
                <div><strong>{{ t.name }}</strong></div>
                <div style="font-size: 12px; color: #888">{{ t.description }}</div>
              </n-list-item>
            </n-list>
          </div>
        </n-space>
      </div>

      <!-- Video Tab -->
      <div v-else-if="activeTab === 'video'" class="v5-tab-body">
        <n-space vertical>
          <n-input v-model:value="videoPrompt" type="textarea" placeholder="视频描述,例如: 赛博朋克短剧" :rows="2" />
          <n-button @click="createVideoProject" :loading="loading" size="small" type="primary">创建视频项目</n-button>
          <div v-if="videoProjects.length" class="v5-result">
            <n-list>
              <n-list-item v-for="p in videoProjects" :key="p.project_id">
                <div><strong>{{ p.project_id }}</strong> · {{ p.status }}</div>
              </n-list-item>
            </n-list>
          </div>
        </n-space>
      </div>

      <!-- Geo Tab -->
      <div v-else-if="activeTab === 'geo'" class="v5-tab-body">
        <n-space vertical>
          <n-input v-model:value="geoRgb" placeholder="RGB, 例如: 128,0,0" />
          <n-space>
            <n-button @click="geoDecode" :loading="loading" size="small">RGB → 高程</n-button>
            <n-button @click="geoEncode(0)" :loading="loading" size="small">0m → RGB</n-button>
            <n-button @click="geoEncode(8848)" :loading="loading" size="small">8848m (珠峰) → RGB</n-button>
          </n-space>
          <div v-if="geoResult" class="v5-result">
            <pre>{{ JSON.stringify(geoResult, null, 2) }}</pre>
          </div>
        </n-space>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import {
  NInput, NButton, NTag, NIcon, NSpace, NList, NListItem, NDropdown,
} from 'naive-ui'
import { SparklesOutline, ChevronUp, ChevronDown } from '@vicons/ionicons5'
import { http } from '@/api/http'
import { getV5Client } from '@/api/v5'

const v5 = getV5Client(http)
const collapsed = ref(false)
const inputText = ref('')
const messages = ref<Array<{ role: 'user' | 'assistant'; text: string; meta?: any; ts: number }>>([])
const messagesRef = ref<HTMLElement | null>(null)
const loading = ref(false)
const stats = ref<any>(null)
const statsOk = ref(false)
const activeTab = ref<'chat' | 'harness' | 'memory' | 'roles' | 'mcp' | 'video' | 'geo'>('chat')

// Harness
const harnessPrompt = ref('')
const harnessResult = ref<any>(null)

// Memory
const memoryTitle = ref('')
const memoryContent = ref('')
const memoryResult = ref<any>(null)

// Roles
const roles = ref<any[]>([])

// MCP
const mcpTools = ref<any[]>([])

// Video
const videoPrompt = ref('')
const videoProjects = ref<any[]>([])

// Geo
const geoRgb = ref('128,0,0')
const geoResult = ref<any>(null)

const quickActions = [
  { label: 'V5 健康检查', key: 'health' },
  { label: '全平台统计', key: 'stats' },
  { label: '列出所有 Bot', key: 'bots' },
  { label: '列出所有角色', key: 'roles' },
  { label: '列出 MCP 工具', key: 'mcp' },
  { label: '列出 13 数据平台', key: 'platforms' },
  { label: '安装 Memory Palace', key: 'palace' },
  { label: '生成今日战报', key: 'daily_report' },
]

function toggle() {
  collapsed.value = !collapsed.value
}

function addMessage(role: 'user' | 'assistant', text: string, meta?: any) {
  messages.value.push({ role, text, meta, ts: Date.now() })
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

function clear() {
  messages.value = []
}

async function onQuickAction(key: string) {
  loading.value = true
  try {
    let r: any
    switch (key) {
      case 'health': r = await v5.health(); break
      case 'stats': r = await v5.stats(); stats.value = r; statsOk.value = true; break
      case 'bots': r = await v5.listBots(); break
      case 'roles': r = await v5.listRoles(); break
      case 'mcp': r = await v5.listMcpTools(); break
      case 'platforms': r = await v5.listPlatforms(); break
      case 'palace': r = await v5.installPalace(); break
      case 'daily_report': r = await v5.dailyReport('default'); break
      default: r = { error: 'unknown action' }
    }
    addMessage('assistant', JSON.stringify(r, null, 2), { tab: 'quick' })
  } catch (e: any) {
    addMessage('assistant', `错误: ${e?.message || e}`, { tab: 'error' })
  } finally {
    loading.value = false
  }
}

async function send() {
  const text = inputText.value.trim()
  if (!text || loading.value) return
  inputText.value = ''
  addMessage('user', text)
  loading.value = true
  const start = Date.now()
  try {
    // 简单的命令解析
    const lower = text.toLowerCase()
    let r: any
    if (lower.includes('角色')) {
      activeTab.value = 'roles'
      r = await v5.listRoles()
    } else if (lower.includes('mcp') || lower.includes('工具')) {
      activeTab.value = 'mcp'
      r = await v5.listMcpTools()
    } else if (lower.includes('视频') || lower.includes('短剧')) {
      activeTab.value = 'video'
      r = await v5.createVideoProject(text)
    } else if (lower.includes('规划') || lower.includes('harness')) {
      activeTab.value = 'harness'
      harnessPrompt.value = text
      r = await v5.planHarness(text)
      harnessResult.value = r
    } else if (lower.includes('统计') || lower.includes('状态')) {
      r = await v5.stats()
    } else if (lower.includes('平台') || lower.includes('数据')) {
      r = await v5.listPlatforms()
    } else {
      // 默认: Harness
      activeTab.value = 'harness'
      harnessPrompt.value = text
      r = await v5.planHarness(text)
      harnessResult.value = r
    }
    addMessage('assistant', JSON.stringify(r, null, 2), { tab: activeTab.value, duration_ms: Date.now() - start })
  } catch (e: any) {
    addMessage('assistant', `错误: ${e?.message || e}`, { tab: 'error' })
  } finally {
    loading.value = false
  }
}

// Harness
async function runHarness(mode: 'plan' | 'full') {
  if (!harnessPrompt.value.trim()) return
  loading.value = true
  try {
    harnessResult.value = mode === 'plan'
      ? await v5.planHarness(harnessPrompt.value)
      : await v5.runHarness(harnessPrompt.value)
  } catch (e: any) {
    harnessResult.value = { error: e?.message || e }
  } finally {
    loading.value = false
  }
}

// Memory
async function addMemory(kind: 'raw' | 'inbox' | 'palace') {
  loading.value = true
  try {
    if (kind === 'palace') {
      memoryResult.value = await v5.installPalace()
    } else {
      const title = memoryTitle.value || `V5 test ${Date.now()}`
      const content = memoryContent.value || 'Default content'
      memoryResult.value = kind === 'raw'
        ? await v5.addRawMemory(title, content)
        : await v5.addInboxMemory(title, content)
    }
  } catch (e: any) {
    memoryResult.value = { error: e?.message || e }
  } finally {
    loading.value = false
  }
}

// Roles
async function loadRoles() {
  loading.value = true
  try {
    const r = await v5.listRoles()
    roles.value = r.roles || []
  } catch (e: any) {
    roles.value = []
  } finally {
    loading.value = false
  }
}

// MCP
async function loadMcpTools() {
  loading.value = true
  try {
    const r = await v5.listMcpTools()
    mcpTools.value = r.tools || []
  } catch (e: any) {
    mcpTools.value = []
  } finally {
    loading.value = false
  }
}

// Video
async function createVideoProject() {
  if (!videoPrompt.value.trim()) return
  loading.value = true
  try {
    await v5.createVideoProject(videoPrompt.value)
    const r = await v5.listVideoProjects()
    videoProjects.value = r.projects || []
  } catch (e: any) {
    videoProjects.value = []
  } finally {
    loading.value = false
  }
}

// Geo
async function geoDecode() {
  const parts = geoRgb.value.split(',').map(p => parseInt(p.trim(), 10))
  if (parts.length !== 3) return
  loading.value = true
  try {
    geoResult.value = await v5.terrariumDecode(parts[0], parts[1], parts[2])
  } catch (e: any) {
    geoResult.value = { error: e?.message || e }
  } finally {
    loading.value = false
  }
}

async function geoEncode(elevation: number) {
  loading.value = true
  try {
    geoResult.value = await v5.terrariumEncode(elevation)
  } catch (e: any) {
    geoResult.value = { error: e?.message || e }
  } finally {
    loading.value = false
  }
}

async function refreshStats() {
  try {
    const r = await v5.stats()
    stats.value = {
      bots: 0,
      roles: r.roles?.role_count || 0,
      mcp_tools: r.mcp?.total_tools || 0,
    }
    statsOk.value = true
  } catch {
    statsOk.value = false
  }
}

let refreshTimer: any = null
onMounted(() => {
  refreshStats()
  refreshTimer = setInterval(refreshStats, 30000)
})
onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.v5-chat-panel {
  position: fixed;
  bottom: 0;
  right: 24px;
  width: 480px;
  max-height: 80vh;
  background: var(--n-card-color, #fff);
  border: 1px solid var(--n-border-color, #e0e0e0);
  border-radius: 12px 12px 0 0;
  box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.08);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  font-size: 14px;
}

.v5-chat-panel--collapsed {
  max-height: 48px;
}

.v5-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  border-bottom: 1px solid var(--n-border-color, #e0e0e0);
  user-select: none;
}

.v5-header__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--n-text-color, #333);
}

.v5-header__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.v5-body {
  display: flex;
  flex-direction: column;
  height: 600px;
  overflow: hidden;
}

.v5-quickbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--n-border-color, #f0f0f0);
  flex-wrap: wrap;
}

.v5-tab-body {
  flex: 1;
  padding: 12px;
  overflow-y: auto;
}

.v5-messages {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
  max-height: 380px;
}

.v5-message {
  display: flex;
  gap: 8px;
  margin: 8px 0;
  padding: 0 8px;
}

.v5-message--user {
  flex-direction: row-reverse;
}

.v5-message__avatar {
  font-size: 24px;
  flex-shrink: 0;
}

.v5-message__content {
  max-width: 80%;
  background: var(--n-fill-color-tertiary, #f5f5f5);
  padding: 8px 12px;
  border-radius: 8px;
  word-break: break-word;
}

.v5-message--user .v5-message__content {
  background: var(--n-primary-color, #18a058);
  color: white;
}

.v5-message__text {
  line-height: 1.5;
}

.v5-message__text pre {
  background: rgba(0, 0, 0, 0.05);
  padding: 4px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 12px;
}

.v5-message__text code {
  background: rgba(0, 0, 0, 0.05);
  padding: 0 4px;
  border-radius: 3px;
  font-family: monospace;
}

.v5-message__meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  font-size: 11px;
  opacity: 0.8;
}

.v5-input {
  padding: 8px;
  border-top: 1px solid var(--n-border-color, #f0f0f0);
}

.v5-input__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.v5-result {
  background: rgba(0, 0, 0, 0.04);
  border-radius: 4px;
  padding: 8px;
  max-height: 400px;
  overflow: auto;
}

.v5-result pre {
  font-size: 12px;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
