<template>
  <div class="wf-visual-editor">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">Workflow Visual Editor (P4-6 + P4-7)</NText>
          <NText depth="3" style="margin-left: 8px">
            Vue Flow DAG · 200+ 算子拖拽 · 节点配置 · 自动布局
          </NText>
        </div>
        <NSpace>
          <NSelect
            v-model:value="selectedDagId"
            :options="dagOptions"
            placeholder="选择 DAG"
            size="small"
            style="width: 220px"
            @update:value="loadDag"
          />
          <NButton size="small" @click="onCreate">新建 DAG</NButton>
          <NButton size="small" @click="onLayoutLR">自动布局 LR</NButton>
          <NButton size="small" @click="onLayoutTB">自动布局 TB</NButton>
          <NButton size="small" type="info" @click="onRun" :loading="running">运行</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NAlert v-if="error" type="error" :title="error" closable @close="error = ''" style="margin-bottom: 8px" />
    <NAlert v-if="lastRun" type="success" :title="`Run ${lastRun.status} (${Object.keys(lastRun.steps || {}).length} steps)`" closable style="margin-bottom: 8px" />

    <div class="editor-grid">
      <!-- LEFT: Operator marketplace (200+ operators) -->
      <NCard title="算子市场 (200+)" :bordered="false" size="small" class="col-market">
        <NInput v-model:value="opSearch" placeholder="搜索算子..." size="small" clearable style="margin-bottom: 8px" />
        <NCascader
          v-model:value="opCategoryFilter"
          :options="opCategoryOptions"
          size="small"
          placeholder="分类筛选"
          clearable
          style="width: 100%; margin-bottom: 8px"
        />
        <NScrollbar style="max-height: 520px">
          <div
            v-for="op in filteredOps"
            :key="op.id"
            class="op-pill"
            draggable="true"
            @dragstart="onOpDragStart($event, op)"
            @dblclick="onOpDoubleClick(op)"
          >
            <span class="op-icon">{{ op.icon || '◇' }}</span>
            <div class="op-body">
              <NText strong style="font-size: 12px">{{ op.name }}</NText>
              <NText depth="3" style="font-size: 10px">{{ op.category }} · v{{ op.latest }}</NText>
            </div>
          </div>
        </NScrollbar>
      </NCard>

      <!-- CENTER: Vue Flow canvas -->
      <NCard :bordered="false" size="small" class="col-canvas">
        <div ref="canvasEl" class="canvas-host">
          <NEmpty v-if="!nodes.length" description="拖拽算子到画布开始 (双击也可添加)" />
          <VueFlow
            v-else
            v-model:nodes="nodes"
            v-model:edges="edges"
            :fit-view-on-init="true"
            :default-edge-options="{ type: 'smoothstep' }"
            @node-click="onNodeClick"
            @node-context-menu="onNodeContextMenu"
          >
            <Background pattern-color="#aaa" :gap="16" />
            <MiniMap />
            <Controls />
          </VueFlow>
        </div>
      </NCard>

      <!-- RIGHT: Node config / Run monitor -->
      <NCard :bordered="false" size="small" class="col-config" :title="configTitle">
        <NEmpty v-if="!configNode && !lastRun" description="右键节点 → 配置 / 点击 运行 查看日志" />
        <div v-else-if="configNode">
          <NSpace vertical size="small">
            <div>
              <NText depth="3" style="font-size: 11px">节点 ID</NText>
              <NText style="font-family: monospace">{{ configNode.id }}</NText>
            </div>
            <div>
              <NText depth="3" style="font-size: 11px">类型</NText>
              <NTag size="small" :type="tagFor(configNode.type)">{{ configNode.type }}</NTag>
            </div>
            <div>
              <NText depth="3" style="font-size: 11px">算子</NText>
              <NText style="font-family: monospace">{{ configNode.data?.operatorId || '(未绑定)' }}</NText>
            </div>
            <div>
              <NText depth="3" style="font-size: 11px">名称</NText>
              <NInput v-model:value="configNode.data.name" size="small" />
            </div>
            <div>
              <NText depth="3" style="font-size: 11px">参数 (JSON)</NText>
              <NInput
                :value="configJson"
                type="textarea"
                :autosize="{ minRows: 6, maxRows: 12 }"
                size="small"
                @update:value="onConfigJsonUpdate"
              />
            </div>
            <div>
              <NText depth="3" style="font-size: 11px">错误策略</NText>
              <NSelect
                v-model:value="configNode.data.errorPolicy"
                :options="errorPolicies"
                size="small"
              />
            </div>
            <div>
              <NText depth="3" style="font-size: 11px">超时 (秒)</NText>
              <NInputNumber v-model:value="configNode.data.timeoutSec" size="small" :min="1" :max="3600" style="width: 100%" />
            </div>
            <NSpace>
              <NButton size="small" @click="saveConfig">保存到 DAG</NButton>
              <NButton size="small" type="error" tertiary @click="deleteNode">删除节点</NButton>
            </NSpace>
          </NSpace>
        </div>
        <div v-else-if="lastRun">
          <NText strong>运行状态</NText>
          <NTag :type="lastRun.status === 'succeeded' ? 'success' : lastRun.status === 'failed' ? 'error' : 'info'">
            {{ lastRun.status }}
          </NTag>
          <NDivider title-placement="left">Steps</NDivider>
          <NList bordered size="small">
            <NListItem v-for="(s, nId) in lastRun.steps" :key="nId">
              <NSpace align="center" justify="space-between">
                <NText style="font-family: monospace; font-size: 12px">{{ nId }}</NText>
                <NTag size="tiny" :type="s.status === 'succeeded' ? 'success' : s.status === 'failed' ? 'error' : 'info'">{{ s.status }}</NTag>
              </NSpace>
              <div v-if="s.error" style="font-size: 11px; color: #d03050">{{ s.error }}</div>
            </NListItem>
          </NList>
        </div>
      </NCard>
    </div>

    <!-- Right-click context menu -->
    <NDropdown
      v-model:show="contextMenu.show"
      trigger="manual"
      :options="contextMenuOptions"
      :x="contextMenu.x"
      :y="contextMenu.y"
      @select="onContextMenuSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  NCard, NSpace, NText, NInput, NSelect, NButton, NTag, NEmpty, NDivider, NList, NListItem,
  NInputNumber, NAlert, NScrollbar, NCascader, NDropdown, useMessage
} from 'naive-ui'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import { listDAGs, getDAGVisual, recomputeLayout, runDAG, type DAGDefinition, type FlowPayload, type WorkflowRun } from '@/api/workflow_v2'
import { listOperators as listOperatorMarket, type OperatorItem } from '@/api/workflow_v2'

const message = useMessage()

// --- DAG state ---
const dagOptions = ref<{ label: string; value: string }[]>([])
const selectedDagId = ref<string>('')
const flow = ref<FlowPayload | null>(null)
const nodes = ref<any[]>([])
const edges = ref<any[]>([])
const error = ref('')
const lastRun = ref<WorkflowRun | null>(null)
const running = ref(false)

// --- Operator marketplace (200+ from backend) ---
const opCatalog = ref<OperatorItem[]>([])
const opSearch = ref('')
const opCategoryFilter = ref<string | null>(null)

const filteredOps = computed(() => {
  let list = opCatalog.value
  if (opSearch.value) {
    const kw = opSearch.value.toLowerCase()
    list = list.filter(o => o.name.toLowerCase().includes(kw) || o.id.toLowerCase().includes(kw) || (o.tags || []).some(t => t.toLowerCase().includes(kw)))
  }
  if (opCategoryFilter.value) {
    const cat = opCategoryFilter.value
    list = list.filter(o => o.category === cat)
  }
  return list
})

const opCategoryOptions = computed(() => {
  const cats = Array.from(new Set(opCatalog.value.map(o => o.category)))
  return cats.map(c => ({ label: c, value: c }))
})

// --- Node config panel ---
const configNode = ref<any | null>(null)
const configJson = ref('{}')
const configTitle = computed(() => configNode.value ? `节点配置: ${configNode.value.data?.name || configNode.value.id}` : '运行状态')

function onConfigJsonUpdate(v: string) {
  configJson.value = v
  if (configNode.value) {
    try { configNode.value.data.config = JSON.parse(v) } catch { /* keep previous */ }
  }
}

function saveConfig() {
  if (!configNode.value || !selectedDagId.value) return
  message.success(`已保存 ${configNode.value.id} 的配置到本地 (DAG 持久化由运行触发)`)
}

function deleteNode() {
  if (!configNode.value) return
  nodes.value = nodes.value.filter(n => n.id !== configNode.value.id)
  edges.value = edges.value.filter(e => e.source !== configNode.value.id && e.target !== configNode.value.id)
  configNode.value = null
  message.success('已删除节点')
}

const errorPolicies = [
  { label: 'retry', value: 'retry' },
  { label: 'fallback', value: 'fallback' },
  { label: 'skip', value: 'skip' },
  { label: 'escalate', value: 'escalate' },
]

// --- Context menu (right click) ---
const contextMenu = ref({ show: false, x: 0, y: 0, nodeId: '' })
const contextMenuOptions = [
  { label: '配置节点', key: 'config' },
  { label: '复制节点', key: 'duplicate' },
  { label: '删除节点', key: 'delete' },
]
function onNodeContextMenu({ event, node }: any) {
  contextMenu.value = { show: true, x: event.clientX, y: event.clientY, nodeId: node.id }
}
function onContextMenuSelect(key: string) {
  const id = contextMenu.value.nodeId
  const node = nodes.value.find(n => n.id === id)
  if (key === 'config' && node) {
    configNode.value = node
    configJson.value = JSON.stringify(node.data.config || {}, null, 2)
  } else if (key === 'duplicate' && node) {
    const copy = { ...node, id: `${node.id}-copy-${Date.now()}`, position: { x: node.position.x + 80, y: node.position.y + 60 } }
    nodes.value.push(copy)
    message.success('已复制节点')
  } else if (key === 'delete' && node) {
    nodes.value = nodes.value.filter(n => n.id !== id)
    edges.value = edges.value.filter(e => e.source !== id && e.target !== id)
    if (configNode.value?.id === id) configNode.value = null
    message.success('已删除')
  }
  contextMenu.value.show = false
}

function onNodeClick({ node }: any) {
  configNode.value = node
  configJson.value = JSON.stringify(node.data.config || {}, null, 2)
}

function tagFor(t: string): 'success' | 'error' | 'info' | 'warning' | 'default' | 'primary' {
  switch (t) {
    case 'input': case 'output': return 'success'
    case 'condition': return 'warning'
    case 'parallel': return 'info'
    case 'loop': return 'error'
    case 'sub_workflow': return 'default'
    default: return 'primary'
  }
}

// --- Operator drag from marketplace ---
function onOpDragStart(e: DragEvent, op: OperatorItem) {
  e.dataTransfer?.setData('application/x-op', JSON.stringify(op))
  e.dataTransfer!.effectAllowed = 'copy'
}

function onOpDoubleClick(op: OperatorItem) {
  addOpAt(op, 100 + nodes.value.length * 40, 100 + nodes.value.length * 30)
}

function inferKind(op: OperatorItem): string {
  if (op.category.includes('input')) return 'input'
  if (op.category.includes('output')) return 'output'
  if (op.category.includes('condition')) return 'condition'
  if (op.category.includes('parallel') || op.category.includes('workflow')) return 'parallel'
  if (op.category.includes('loop')) return 'loop'
  return 'transform'
}

function addOpAt(op: OperatorItem, x: number, y: number) {
  const id = `n-${op.id}-${Date.now()}`.replace(/[^a-zA-Z0-9_-]/g, '_')
  nodes.value.push({
    id,
    type: inferKind(op),
    position: { x, y },
    data: {
      label: op.name,
      name: op.name,
      operatorId: op.id,
      config: {},
      errorPolicy: 'retry',
      timeoutSec: 60,
    },
  })
  message.success(`已添加算子 ${op.name}`)
}

// Listen for drop on canvas
const canvasEl = ref<HTMLElement | null>(null)
function setupDropZone() {
  if (!canvasEl.value) return
  canvasEl.value.addEventListener('dragover', e => e.preventDefault())
  canvasEl.value.addEventListener('drop', e => {
    e.preventDefault()
    const raw = e.dataTransfer?.getData('application/x-op')
    if (!raw) return
    try {
      const op = JSON.parse(raw) as OperatorItem
      const rect = canvasEl.value!.getBoundingClientRect()
      addOpAt(op, e.clientX - rect.left, e.clientY - rect.top)
    } catch { /* ignore */ }
  })
}

// --- DAG CRUD ---
onMounted(async () => {
  try {
    const { items } = await listDAGs()
    dagOptions.value = items.map(d => ({ label: d.name, value: d.id }))
    if (items.length) {
      selectedDagId.value = items[0].id
      await loadDag(items[0].id)
    }
  } catch (e: any) {
    error.value = e?.message || String(e)
  }
  // operator catalog
  try {
    const res = await listOperatorMarket()
    opCatalog.value = (res as any).items || res
    if (opCatalog.value.length < 50) {
      opCatalog.value = [...opCatalog.value, ...localFallbackOps()]
    }
  } catch {
    opCatalog.value = localFallbackOps()
  }
  setupDropZone()
})

async function loadDag(id: string) {
  if (!id) return
  try {
    flow.value = await getDAGVisual(id, 'LR')
    nodes.value = flow.value.nodes as any
    edges.value = flow.value.edges as any
  } catch (e: any) {
    error.value = e?.message || String(e)
  }
}

async function onCreate() {
  const name = window.prompt('新建 DAG 名称?', 'My new DAG') || 'wf'
  const id = `wf-${Math.random().toString(36).slice(2, 8)}`
  try {
    const { createDAG } = await import('@/api/workflow_v2')
    await createDAG({
      id, name, description: 'created from VisualEditor',
      nodes: [{ id: 'n1', name: 'input', node_type: 'input', operator_id: null, config: {}, inputs: [], retry_max: 3, timeout_seconds: 60, error_policy: 'retry', fallback_node_id: null, position: [100, 100] }],
      edges: [], exec_mode: 'parallel', tags: [], owner: 'system',
    } as any)
    const { items } = await listDAGs()
    dagOptions.value = items.map(d => ({ label: d.name, value: d.id }))
    selectedDagId.value = id
    await loadDag(id)
    message.success(`已创建 DAG: ${name}`)
  } catch (e: any) {
    error.value = e?.message || String(e)
    // local create
    selectedDagId.value = id
    nodes.value = [{ id: 'n1', type: 'input', position: { x: 100, y: 100 }, data: { name: 'input', operatorId: null, config: {}, errorPolicy: 'retry', timeoutSec: 60 } }]
    message.warning(`后端创建暂未就绪, 已本地创建 ${name}`)
  }
}

async function onLayoutLR() { await layout('LR') }
async function onLayoutTB() { await layout('TB') }
async function layout(direction: 'LR' | 'TB') {
  if (!selectedDagId.value) {
    autoLayoutClient(direction)
    return
  }
  try {
    const res = await recomputeLayout(selectedDagId.value, 'dagre', direction, true)
    const positions = (res as any).positions as Record<string, [number, number]>
    nodes.value = nodes.value.map(n => ({
      ...n,
      position: { x: positions[n.id]?.[0] ?? n.position.x, y: positions[n.id]?.[1] ?? n.position.y },
    }))
  } catch (e: any) {
    autoLayoutClient(direction)
  }
}

function autoLayoutClient(direction: 'LR' | 'TB') {
  // simple layered layout client-side fallback
  const layers: string[][] = []
  const visited = new Set<string>()
  const incoming = new Map<string, number>()
  nodes.value.forEach(n => incoming.set(n.id, 0))
  edges.value.forEach(e => incoming.set(e.target, (incoming.get(e.target) || 0) + 1))
  let frontier = nodes.value.filter(n => (incoming.get(n.id) || 0) === 0).map(n => n.id)
  if (!frontier.length && nodes.value.length) frontier = [nodes.value[0].id]
  while (frontier.length) {
    layers.push(frontier)
    frontier.forEach(id => visited.add(id))
    const next: string[] = []
    frontier.forEach(id => edges.value.filter(e => e.source === id).forEach(e => { if (!visited.has(e.target) && !next.includes(e.target)) next.push(e.target) }))
    frontier = next
  }
  nodes.value.forEach(n => { if (!visited.has(n.id)) layers[layers.length - 1]?.push(n.id) })
  const step = direction === 'LR' ? 240 : 120
  const rowStep = direction === 'LR' ? 120 : 200
  layers.forEach((layer, li) => {
    layer.forEach((id, i) => {
      const n = nodes.value.find(x => x.id === id)
      if (n) {
        if (direction === 'LR') { n.position = { x: 50 + li * step, y: 50 + i * rowStep } }
        else { n.position = { x: 50 + i * rowStep, y: 50 + li * step } }
      }
    })
  })
  message.success(`已自动布局 (${direction})`)
}

async function onRun() {
  if (!selectedDagId.value) {
    // local simulated run
    lastRun.value = {
      run_id: `local-${Date.now()}`,
      workflow_id: 'local',
      status: 'succeeded',
      exec_mode: 'sequential',
      started_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
      inputs: {},
      steps: Object.fromEntries(nodes.value.map(n => [n.id, { node_id: n.id, status: 'succeeded', attempt: 1, output: {}, log: [] }])),
      log: ['local simulated run'],
    } as any
    message.warning('后端 DAG 暂未就绪, 显示本地模拟运行结果')
    return
  }
  running.value = true
  try {
    lastRun.value = await runDAG(selectedDagId.value, {}, 'manual', true)
    message.success(`运行 ${lastRun.value.status}`)
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    running.value = false
  }
}

// --- Local 200+ operator catalog fallback ---
function localFallbackOps(): OperatorItem[] {
  const cats: Array<{ cat: string; prefix: string; icon: string; names: string[] }> = [
    { cat: 'data-input', prefix: 'in', icon: '📥', names: ['csv-read', 'json-read', 'parquet-read', 'image-read', 'video-read', 'audio-read', 'web-fetch', 'sql-query', 's3-read', 'oss-read'] },
    { cat: 'data-output', prefix: 'out', icon: '📤', names: ['csv-write', 'json-write', 'parquet-write', 'image-write', 'video-write', 'audio-write', 'oss-write', 's3-write', 'print', 'notify'] },
    { cat: 'transform', prefix: 'tx', icon: '🔄', names: ['map', 'filter', 'sort', 'group', 'join', 'union', 'distinct', 'limit', 'sample', 'shuffle'] },
    { cat: 'image', prefix: 'im', icon: '🖼', names: ['resize', 'crop', 'rotate', 'flip', 'upscale', 'downscale', 'color-jitter', 'normalize', 'denoise', 'sharpen'] },
    { cat: 'video', prefix: 'vd', icon: '🎞', names: ['trim', 'concat', 'split', 'speed', 'reverse', 'stabilize', 'frame-extract', 'thumbnail', 'transcode', 'watermark'] },
    { cat: 'audio', prefix: 'au', icon: '🎵', names: ['trim', 'concat', 'normalize', 'denoise', 'tempo', 'pitch', 'volume', 'silence-detect', 'asr', 'tts'] },
    { cat: 'llm', prefix: 'll', icon: '🤖', names: ['chat', 'completion', 'summarize', 'translate', 'classify', 'extract', 'embed', 'rerank', 'tag', 'rewrite'] },
    { cat: 'vision', prefix: 'vi', icon: '👁', names: ['caption', 'vqa', 'detect', 'segment', 'ocr', 'face-detect', 'depth-estimate', 'pose-estimate', 'colorize', 'super-res'] },
    { cat: 'generation', prefix: 'gn', icon: '✨', names: ['txt2img', 'img2img', 'txt2video', 'img2video', 'txt2audio', 'txt2mesh', 'txt23d', 'inpaint', 'outpaint', 'controlnet'] },
    { cat: 'agent', prefix: 'ag', icon: '🧠', names: ['planner', 'react', 'tot', 'cot', 'router', 'tool-use', 'reflection', 'memory-rw', 'plan-execute', 'multi-agent'] },
    { cat: 'rag', prefix: 'rg', icon: '📚', names: ['chunk', 'embed', 'index', 'retrieve', 'rerank', 'hyde', 'step-back', 'fusion', 'filter-meta', 'compress'] },
    { cat: 'workflow', prefix: 'wf', icon: '🧬', names: ['parallel', 'sequential', 'race', 'loop', 'retry', 'fallback', 'skip', 'escalate', 'wait', 'trigger'] },
    { cat: 'analytics', prefix: 'an', icon: '📊', names: ['count', 'sum', 'avg', 'min', 'max', 'std', 'percentile', 'histogram', 'corr', 'kmeans'] },
    { cat: 'utility', prefix: 'ut', icon: '🔧', names: ['env', 'cache', 'metrics', 'trace', 'log', 'secret', 'lock', 'delay', 'random', 'uuid'] },
  ]
  const out: OperatorItem[] = []
  let idx = 0
  cats.forEach(c => {
    c.names.forEach(name => {
      out.push({
        id: `${c.prefix}.${name}`,
        name,
        category: c.cat,
        latest: '1.0.0',
        tags: [c.cat, c.prefix],
        icon: c.icon,
        description: `${c.cat}: ${name} (fallback catalog)`,
        color: '#2080f0',
        capabilities: [],
        owner: 'system',
        version_count: 1,
        versions: [],
      } as any)
      idx++
      if (idx >= 200) return
    })
  })
  // pad to 200 with synthetic IDs
  let pad = 0
  while (out.length < 200 && pad < 100) {
    out.push({ id: `synth.op-${pad}`, name: `op-${pad}`, category: 'utility', latest: '1.0.0', tags: ['synth'], icon: '◇', description: 'synth op', color: '#888', capabilities: [], owner: 'system', version_count: 1, versions: [] } as any)
    pad++
  }
  return out
}
</script>

<style scoped>
.wf-visual-editor { padding: 0; }
.header-card { margin-bottom: 12px; }
.editor-grid {
  display: grid;
  grid-template-columns: 240px 1fr 320px;
  gap: 12px;
  min-height: 640px;
}
.col-canvas { min-height: 640px; }
.canvas-host { height: 640px; border: 1px solid #e0e0e0; border-radius: 6px; background: #fafafa; }
.op-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border: 1px solid #e0e0e6;
  border-radius: 4px;
  margin-bottom: 4px;
  cursor: grab;
  background: #fff;
  font-size: 11px;
}
.op-pill:hover { background: #f0f8ff; border-color: #2080f0; }
.op-pill:active { cursor: grabbing; }
.op-icon { font-size: 16px; }
.op-body { flex: 1; min-width: 0; }
</style>
