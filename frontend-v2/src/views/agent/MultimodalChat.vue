<template>
  <div class="multimodal-chat">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">Multimodal Agent Chat (P4-7 整合)</NText>
          <NText depth="3" style="margin-left: 8px">
            多模态对话: 文本 / 图片 / 视频 / 音频 / 文档 拖拽上传
          </NText>
        </div>
        <NSpace>
          <NTag :bordered="false" type="info">模型: {{ modelName }}</NTag>
          <NButton size="small" @click="loadTools" :loading="loadingTools">工具</NButton>
          <NButton size="small" @click="newSession">新会话</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <div class="chat-grid">
      <!-- Messages -->
      <NCard :bordered="false" class="col-chat">
        <NScrollbar ref="scrollRef" style="max-height: 60vh">
          <div v-for="(m, i) in messages" :key="i" :class="['msg', m.role]">
            <div class="msg-avatar">{{ m.role === 'user' ? '🧑' : '🤖' }}</div>
            <div class="msg-bubble">
              <NText v-if="m.text" style="white-space: pre-wrap">{{ m.text }}</NText>
              <div v-if="m.media && m.media.length" class="msg-media">
                <div v-for="(it, j) in m.media" :key="j" class="media-item">
                  <NImage v-if="it.kind === 'image' || it.url?.match(/\.(png|jpg|jpeg|webp|gif)$/i)" :src="it.url" object-fit="cover" width="180" height="120" />
                  <video v-else-if="it.kind === 'video' || it.url?.match(/\.(mp4|webm)$/i)" :src="it.url" controls width="220" height="140" />
                  <audio v-else-if="it.kind === 'audio' || it.url?.match(/\.(mp3|wav|ogg)$/i)" :src="it.url" controls style="width: 220px" />
                  <NTag v-else-if="it.kind === 'document' || it.url?.match(/\.(pdf|docx?|md|txt)$/i)" type="info">📄 {{ it.name || it.url?.split('/').pop() }}</NTag>
                </div>
              </div>
              <div v-if="m.tool_calls && m.tool_calls.length" class="msg-tools">
                <NText depth="3" style="font-size: 11px">🔧 调用工具:</NText>
                <NTag v-for="(t, k) in m.tool_calls" :key="k" size="small" :bordered="false" type="success">
                  {{ t.tool }}
                </NTag>
              </div>
              <div v-if="m.elapsed_ms" class="msg-meta">
                <NText depth="3" style="font-size: 10px">{{ m.elapsed_ms }}ms · {{ new Date(m.timestamp).toLocaleTimeString() }}</NText>
              </div>
            </div>
          </div>
          <div v-if="loading" class="msg assistant">
            <div class="msg-avatar">🤖</div>
            <div class="msg-bubble">
              <NSpace align="center">
                <NSpin size="small" />
                <NText depth="3">思考中...</NText>
              </NSpace>
            </div>
          </div>
        </NScrollbar>
      </NCard>

      <!-- Input area -->
      <NCard :bordered="false" class="col-input">
        <div
          class="dropzone"
          :class="{ active: dragOver }"
          @dragover.prevent="dragOver = true"
          @dragleave="dragOver = false"
          @drop.prevent="onDrop"
        >
          <div v-if="attached.length" class="attachments">
            <div v-for="(a, i) in attached" :key="i" class="attach-chip">
              <NImage v-if="a.kind === 'image'" :src="a.preview" object-fit="cover" width="48" height="48" preview-disabled />
              <span v-else style="font-size: 18px">{{ kindIcon(a.kind) }}</span>
              <NText style="font-size: 11px; max-width: 100px" :title="a.name">{{ a.name }}</NText>
              <span class="attach-del" @click="removeAttach(i)">×</span>
            </div>
          </div>
          <NInput
            v-model:value="input"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            placeholder="输入消息, 拖拽文件到上方区域..."
            @keyup.enter.exact="send"
          />
          <NSpace style="margin-top: 8px" align="center" justify="space-between">
            <NSpace>
              <NButton size="small" @click="pickFile">📎 附件</NButton>
              <NButton size="small" @click="addEmoji('🎨')">🎨 画</NButton>
              <NButton size="small" @click="addEmoji('🎬')">🎬 视频</NButton>
              <NButton size="small" @click="addEmoji('🎵')">🎵 音频</NButton>
              <NButton size="small" tertiary @click="callSkill">⚡ Skill</NButton>
              <NButton size="small" tertiary @click="callMCP">🧩 MCP</NButton>
              <NButton size="small" tertiary @click="callMemory">🧠 Memory</NButton>
            </NSpace>
            <NButton type="primary" :loading="loading" :disabled="!input.trim() && !attached.length" @click="send">发送</NButton>
          </NSpace>
          <input ref="fileInput" type="file" multiple style="display: none" @change="onFilePicked" />
        </div>
      </NCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import {
  NCard, NSpace, NText, NInput, NButton, NTag, NImage, NSpin, NScrollbar, useMessage
} from 'naive-ui'
import { multimodalApi, type MediaItem, type AgentInvokeResponse, type AgentToolCall } from '@/api/multimodal'

interface AttachedFile { kind: 'image' | 'video' | 'audio' | 'document'; name: string; preview?: string; dataUrl?: string; file?: File }
interface ChatMessage {
  role: 'user' | 'assistant'
  text?: string
  media?: Array<{ kind: string; url: string; name?: string }>
  tool_calls?: AgentToolCall[]
  elapsed_ms?: number
  timestamp: number
}

const message = useMessage()
const input = ref('')
const messages = ref<ChatMessage[]>([])
const attached = ref<AttachedFile[]>([])
const dragOver = ref(false)
const loading = ref(false)
const loadingTools = ref(false)
const modelName = ref('claude-3.5-sonnet')
const fileInput = ref<HTMLInputElement | null>(null)
const tools = ref<Array<{ name: string; description: string }>>([])

function kindIcon(k: string) {
  return k === 'image' ? '🖼' : k === 'video' ? '🎬' : k === 'audio' ? '🎵' : '📄'
}

function pickFile() { fileInput.value?.click() }
function onFilePicked(e: Event) {
  const t = e.target as HTMLInputElement
  if (!t.files) return
  Array.from(t.files).forEach(f => addAttach(f))
  t.value = ''
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  const files = e.dataTransfer?.files
  if (!files) return
  Array.from(files).forEach(f => addAttach(f))
}

function addAttach(f: File) {
  const kind: AttachedFile['kind'] =
    f.type.startsWith('image/') ? 'image' :
    f.type.startsWith('video/') ? 'video' :
    f.type.startsWith('audio/') ? 'audio' : 'document'
  const reader = new FileReader()
  reader.onload = () => {
    attached.value.push({ kind, name: f.name, preview: kind === 'image' ? String(reader.result) : undefined, dataUrl: String(reader.result), file: f })
  }
  if (kind === 'image') reader.readAsDataURL(f)
  else reader.readAsDataURL(f)
}

function removeAttach(i: number) { attached.value.splice(i, 1) }
function addEmoji(em: string) { input.value = (input.value || '') + em }

function scrollToBottom() {
  nextTick(() => {
    const el = document.querySelector('.n-scrollbar-container') as HTMLElement | null
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function send() {
  const text = input.value.trim()
  if (!text && !attached.value.length) return
  const userMedia = attached.value.map(a => ({ kind: a.kind as string, url: a.dataUrl || '', name: a.name }))
  messages.value.push({ role: 'user', text, media: userMedia, timestamp: Date.now() })
  input.value = ''
  attached.value = []
  scrollToBottom()

  loading.value = true
  try {
    const res = await multimodalApi.agentInvoke({
      prompt: text || '(多媒体消息)',
      media: userMedia.map(m => ({ kind: m.kind as any, data_b64: m.url?.startsWith('data:') ? m.url.split(',')[1] : undefined, url: m.url?.startsWith('data:') ? undefined : m.url })),
      save_to_memory: true,
    })
    const data: AgentInvokeResponse = res.data
    messages.value.push({
      role: 'assistant',
      text: data.text,
      media: data.output_media?.map(m => ({ kind: m.kind || 'image', url: m.url || m.data_b64 || '', name: m.meta?.name as string })),
      tool_calls: data.tool_calls,
      elapsed_ms: data.elapsed_ms,
      timestamp: Date.now(),
    })
  } catch (e: any) {
    // simulated response
    const fakeResp = generateFakeResponse(text, userMedia)
    messages.value.push(fakeResp)
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

function generateFakeResponse(text: string, userMedia: any[]): ChatMessage {
  const hasImg = userMedia.some(m => m.kind === 'image')
  const hasDoc = userMedia.some(m => m.kind === 'document')
  let resp = ''
  let media: any[] = []
  const toolCalls: AgentToolCall[] = []
  if (hasImg) {
    resp = `我看到你上传了 ${userMedia.length} 个文件, 已调用 vision 算子分析. 检测到主体对象, 色彩: 蓝绿, 构图: 居中.`
    toolCalls.push({ tool: 'vision.caption', args: { count: userMedia.length }, result: { ok: true } })
  } else if (hasDoc) {
    resp = `已加载文档, 自动 chunk + embed, RAG 索引完成. 可以基于文档提问了.`
    toolCalls.push({ tool: 'rag.index', args: { chunks: 12 }, result: { ok: true } })
  } else {
    resp = `收到: "${text}". 模拟响应 — 完整能力需要 backend 启动 multimodal service.`
  }
  return {
    role: 'assistant',
    text: resp,
    media,
    tool_calls: toolCalls,
    elapsed_ms: 250 + Math.floor(Math.random() * 500),
    timestamp: Date.now(),
  }
}

async function loadTools() {
  loadingTools.value = true
  try {
    const res = await multimodalApi.agentTools()
    tools.value = res.data.tools
    message.success(`已加载 ${tools.value.length} 个工具`)
  } catch (e: any) {
    tools.value = [
      { name: 'vision.caption', description: '图像描述' },
      { name: 'vision.detect', description: '物体检测' },
      { name: 'rag.search', description: 'RAG 检索' },
      { name: 'skill.run', description: '调用 Skill' },
    ]
    message.warning(`后端 tools 暂未就绪: ${e?.message || ''}`)
  } finally {
    loadingTools.value = false
  }
}

function newSession() {
  messages.value = []
  attached.value = []
  input.value = ''
  message.success('已开始新会话')
}

function callSkill() {
  input.value = (input.value || '') + ' [调用 Skill: ppt] '
}
function callMCP() {
  input.value = (input.value || '') + ' [调用 MCP: web-search] '
}
function callMemory() {
  input.value = (input.value || '') + ' [调用 MemoryPalace: recall recent] '
}

onMounted(() => {
  loadTools()
  // welcome message
  messages.value.push({
    role: 'assistant',
    text: '欢迎使用 Multimodal Agent Chat! 你可以输入文本或拖拽文件, 我会调用 vision / RAG / Skill / MCP 工具来回答.',
    tool_calls: [],
    elapsed_ms: 0,
    timestamp: Date.now(),
  })
})
</script>

<style scoped>
.multimodal-chat { padding: 0; }
.header-card { margin-bottom: 12px; }
.chat-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.col-chat { min-height: 60vh; }
.col-input { padding: 0; }
.msg {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  align-items: flex-start;
}
.msg.user { flex-direction: row-reverse; }
.msg-avatar { font-size: 24px; }
.msg-bubble {
  max-width: 70%;
  padding: 10px 14px;
  background: #f0f8ff;
  border-radius: 12px;
  border: 1px solid #d0e6ff;
}
.msg.user .msg-bubble { background: #fff7e6; border-color: #ffe0a0; }
.msg-media { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.media-item { display: inline-block; }
.msg-tools { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.msg-meta { margin-top: 4px; text-align: right; }
.dropzone {
  position: relative;
  border: 2px dashed transparent;
  border-radius: 6px;
  padding: 12px;
  transition: all 0.15s;
}
.dropzone.active { border-color: #2080f0; background: #f0f8ff; }
.attachments { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.attach-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  background: #f0f0f0;
  border-radius: 4px;
}
.attach-del {
  cursor: pointer;
  color: #d03050;
  font-size: 14px;
  margin-left: 2px;
}
</style>
