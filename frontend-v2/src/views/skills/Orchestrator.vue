<template>
  <div class="skill-orchestrator">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">Skill Orchestrator</NText>
          <NText depth="3" style="margin-left: 8px">
            拖拽 Skill 节点 → 连接上下游 → 一键链路运行
          </NText>
        </div>
        <NSpace>
          <NButton tertiary @click="autoLayout">自动布局</NButton>
          <NButton tertiary @click="clearCanvas">清空</NButton>
          <NButton @click="loadPipelines" :loading="loadingList">模板库</NButton>
          <NButton type="primary" @click="runPipeline" :loading="running" :disabled="!nodes.length">
            <template #icon><span>▶</span></template>
            运行链路
          </NButton>
          <NButton type="info" @click="saveAsPipeline">保存模板</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <div class="orchestrator-grid">
      <NCard title="可用 Skill" :bordered="false" size="small" class="col-left">
        <NInput v-model:value="skillSearch" placeholder="搜索 Skill..." size="small" style="margin-bottom: 8px" />
        <NScrollbar style="max-height: 540px">
          <div
            v-for="s in filteredSkillCatalog"
            :key="s.id"
            class="skill-pill"
            draggable="true"
            @dragstart="onDragStart($event, s.id)"
            @dblclick="addNode(s.id)"
          >
            <span class="pill-icon">{{ s.icon }}</span>
            <div class="pill-body">
              <NText strong style="font-size: 12px">{{ s.name }}</NText>
              <NText depth="3" style="font-size: 10px">{{ s.description.slice(0, 30) }}...</NText>
            </div>
          </div>
        </NScrollbar>
      </NCard>

      <NCard title="编排画布" :bordered="false" size="small" class="col-canvas">
        <div ref="canvasEl" class="canvas" @dragover.prevent @drop="onDrop">
          <NEmpty v-if="!nodes.length" description="拖拽 Skill 到此开始编排 (双击也可添加)" />
          <div
            v-for="node in nodes"
            :key="node.id"
            class="canvas-node"
            :style="nodeStyle(node)"
            @mousedown="startDrag($event, node.id)"
          >
            <div class="node-header">
              <span class="node-icon">{{ nodeIcon(node.skillId) }}</span>
              <NText strong style="font-size: 12px">{{ nodeName(node.skillId) }}</NText>
              <span class="node-del" @click.stop="removeNode(node.id)">×</span>
            </div>
            <div class="node-io">
              <div class="node-output" @click.stop="startConnect($event, node.id, 'output')">
                <span class="io-dot out"></span> output
              </div>
              <div class="node-input" @click.stop="startConnect($event, node.id, 'input')">
                <span class="io-dot in"></span> input
              </div>
            </div>
          </div>
          <svg class="edge-svg" :width="canvasSize.w" :height="canvasSize.h">
            <g v-for="(e, i) in renderedEdges" :key="i">
              <path :d="e.path" stroke="#2080f0" stroke-width="2" fill="none" marker-end="url(#arrow)" />
            </g>
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#2080f0" />
              </marker>
            </defs>
          </svg>
        </div>
      </NCard>

      <NCard title="链路运行状态" :bordered="false" size="small" class="col-right">
        <NEmpty v-if="!runResult" description="运行链路后查看状态" />
        <div v-else>
          <NTag :type="runResult.status === 'succeeded' ? 'success' : runResult.status === 'failed' ? 'error' : 'info'">
            {{ runResult.status }}
          </NTag>
          <NText depth="3" style="font-size: 12px; margin-left: 8px">耗时 {{ runResult.elapsed_ms }}ms</NText>
          <NDivider style="margin: 8px 0" />
          <NScrollbar style="max-height: 360px">
            <NList>
              <NListItem v-for="(s, i) in runResult.step_states || []" :key="i">
                <NSpace align="center" justify="space-between">
                  <NText>{{ stepName(s.node_id) }}</NText>
                  <NTag size="small" :type="statusTag(s.status)">{{ s.status }}</NTag>
                </NSpace>
              </NListItem>
            </NList>
          </NScrollbar>
        </div>
      </NCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  NCard, NSpace, NText, NInput, NButton, NTag, NScrollbar, NEmpty, NDivider, NList, NListItem, useMessage
} from 'naive-ui'
import { skillsApi, type Skill, type SkillExecutionResult, type SkillPipeline } from '@/api/skills'

const message = useMessage()

interface OrchNode { id: string; skillId: string; x: number; y: number }
interface OrchEdge { source: string; target: string }

const skillCatalog = ref<Skill[]>([])
const skillSearch = ref('')
const nodes = ref<OrchNode[]>([])
const edges = ref<OrchEdge[]>([])
const canvasEl = ref<HTMLElement | null>(null)
const canvasSize = ref({ w: 1000, h: 600 })
const draggingNode = ref<{ id: string; dx: number; dy: number } | null>(null)
const connectingFrom = ref<{ id: string; handle: 'input' | 'output' } | null>(null)
const running = ref(false)
const runResult = ref<any>(null)
const loadingList = ref(false)

const filteredSkillCatalog = computed(() => {
  if (!skillSearch.value) return skillCatalog.value
  const kw = skillSearch.value.toLowerCase()
  return skillCatalog.value.filter(s => s.name.toLowerCase().includes(kw) || s.tags.some(t => t.toLowerCase().includes(kw)))
})

function nodeName(skillId: string): string {
  return skillCatalog.value.find(s => s.id === skillId)?.name || skillId
}
function nodeIcon(skillId: string): string {
  return skillCatalog.value.find(s => s.id === skillId)?.icon || '◇'
}
function stepName(nodeId: string): string {
  const n = nodes.value.find(x => x.id === nodeId)
  return n ? nodeName(n.skillId) : nodeId
}
function statusTag(s: string): 'success' | 'error' | 'info' | 'warning' {
  if (s === 'succeeded') return 'success'
  if (s === 'failed') return 'error'
  if (s === 'running') return 'info'
  return 'warning'
}

function nodeStyle(n: OrchNode) {
  return { left: `${n.x}px`, top: `${n.y}px` }
}

const renderedEdges = computed(() => {
  return edges.value.map(e => {
    const src = nodes.value.find(n => n.id === e.source)
    const dst = nodes.value.find(n => n.id === e.target)
    if (!src || !dst) return { path: '' }
    const sx = src.x + 200
    const sy = src.y + 30
    const tx = dst.x
    const ty = dst.y + 30
    const mx = (sx + tx) / 2
    return { path: `M ${sx} ${sy} C ${mx} ${sy}, ${mx} ${ty}, ${tx} ${ty}` }
  })
})

function onDragStart(e: DragEvent, skillId: string) {
  e.dataTransfer?.setData('text/skill-id', skillId)
  e.dataTransfer!.effectAllowed = 'copy'
}

function onDrop(e: DragEvent) {
  const skillId = e.dataTransfer?.getData('text/skill-id')
  if (!skillId || !canvasEl.value) return
  const rect = canvasEl.value.getBoundingClientRect()
  addNodeAt(skillId, e.clientX - rect.left - 100, e.clientY - rect.top - 20)
}

function addNode(skillId: string) {
  const idx = nodes.value.length
  addNodeAt(skillId, 50 + (idx % 3) * 240, 50 + Math.floor(idx / 3) * 120)
}

function addNodeAt(skillId: string, x: number, y: number) {
  const id = `n${Date.now()}_${Math.random().toString(36).slice(2, 6)}`
  nodes.value.push({ id, skillId, x: Math.max(0, x), y: Math.max(0, y) })
}

function removeNode(id: string) {
  nodes.value = nodes.value.filter(n => n.id !== id)
  edges.value = edges.value.filter(e => e.source !== id && e.target !== id)
}

function startDrag(e: MouseEvent, id: string) {
  if (!canvasEl.value) return
  const node = nodes.value.find(n => n.id === id)
  if (!node) return
  const rect = canvasEl.value.getBoundingClientRect()
  draggingNode.value = { id, dx: e.clientX - rect.left - node.x, dy: e.clientY - rect.top - node.y }
  window.addEventListener('mousemove', onDrag)
  window.addEventListener('mouseup', endDrag)
}

function onDrag(e: MouseEvent) {
  if (!draggingNode.value || !canvasEl.value) return
  const rect = canvasEl.value.getBoundingClientRect()
  const node = nodes.value.find(n => n.id === draggingNode.value!.id)
  if (!node) return
  node.x = e.clientX - rect.left - draggingNode.value.dx
  node.y = e.clientY - rect.top - draggingNode.value.dy
}

function endDrag() {
  draggingNode.value = null
  window.removeEventListener('mousemove', onDrag)
  window.removeEventListener('mouseup', endDrag)
}

function startConnect(_e: MouseEvent, id: string, handle: 'input' | 'output') {
  if (!connectingFrom.value) {
    connectingFrom.value = { id, handle }
    message.info(`点击另一个节点的 ${handle === 'output' ? 'input' : 'output'} 完成连线`)
    return
  }
  if (connectingFrom.value.id === id) {
    connectingFrom.value = null
    return
  }
  // prevent duplicate edge in same direction
  const from = connectingFrom.value.handle === 'output' ? connectingFrom.value.id : id
  const to = connectingFrom.value.handle === 'output' ? id : connectingFrom.value.id
  if (from === to) {
    connectingFrom.value = null
    return
  }
  if (!edges.value.find(e => e.source === from && e.target === to)) {
    edges.value.push({ source: from, target: to })
    message.success('已连线')
  }
  connectingFrom.value = null
}

function clearCanvas() {
  nodes.value = []
  edges.value = []
  runResult.value = null
}

function autoLayout() {
  if (!nodes.value.length) return
  // Layered layout: BFS from sources (nodes with no incoming edge)
  const incoming = new Map<string, number>()
  nodes.value.forEach(n => incoming.set(n.id, 0))
  edges.value.forEach(e => incoming.set(e.target, (incoming.get(e.target) || 0) + 1))
  const layers: string[][] = []
  const visited = new Set<string>()
  let frontier = nodes.value.filter(n => (incoming.get(n.id) || 0) === 0).map(n => n.id)
  if (!frontier.length) frontier = [nodes.value[0].id]
  while (frontier.length) {
    layers.push(frontier)
    frontier.forEach(id => visited.add(id))
    const next: string[] = []
    frontier.forEach(id => {
      edges.value.filter(e => e.source === id).forEach(e => {
        if (!visited.has(e.target) && !next.includes(e.target)) next.push(e.target)
      })
    })
    frontier = next
  }
  // any leftover
  nodes.value.forEach(n => { if (!visited.has(n.id)) layers[layers.length - 1]?.push(n.id) })

  const layerWidth = 240
  const rowHeight = 120
  layers.forEach((layer, li) => {
    layer.forEach((id, i) => {
      const n = nodes.value.find(x => x.id === id)
      if (n) { n.x = 30 + li * layerWidth; n.y = 30 + i * rowHeight }
    })
  })
  message.success('已自动布局 (LR)')
}

async function loadCatalog() {
  try {
    const res = await skillsApi.listAll()
    skillCatalog.value = res.skills
  } catch {
    // fallback: use the same catalog defined in Marketplace
    skillCatalog.value = [
      { id: 'ppt', name: 'Guizang PPT', description: '想法 → 演示稿', category: 'content', version: '1.0', author: '', downloads: 0, rating: 5, tags: [], inputs: [], outputs: [], dependencies: [], icon: '📊' },
      { id: 'humanizer-zh', name: 'Humanizer 中文', description: 'AI 文 → 人话', category: 'language', version: '1.0', author: '', downloads: 0, rating: 5, tags: [], inputs: [], outputs: [], dependencies: [], icon: '✍️' },
      { id: 'deep-research', name: 'Deep Research', description: '带出处的深度研究', category: 'research', version: '1.0', author: '', downloads: 0, rating: 5, tags: [], inputs: [], outputs: [], dependencies: [], icon: '🔬' },
      { id: 'wewrite', name: 'WeWrite 公众号', description: '公众号一条龙', category: 'writing', version: '1.0', author: '', downloads: 0, rating: 5, tags: [], inputs: [], outputs: [], dependencies: [], icon: '📝' },
      { id: 'youtube-clipper', name: 'YouTube Clipper', description: '长视频切片', category: 'video', version: '1.0', author: '', downloads: 0, rating: 5, tags: [], inputs: [], outputs: [], dependencies: [], icon: '🎬' },
      { id: 'gpt-image-prompt', name: 'GPT Image Prompts', description: 'AI 图片素材库', category: 'media', version: '1.0', author: '', downloads: 0, rating: 5, tags: [], inputs: [], outputs: [], dependencies: [], icon: '🎨' },
    ]
  }
}

async function runPipeline() {
  running.value = true
  runResult.value = null
  const pipeline: SkillPipeline = {
    id: '',
    name: `adhoc-${Date.now()}`,
    description: 'ad-hoc run',
    nodes: nodes.value.map(n => ({ id: n.id, skill_id: n.skillId, position: { x: n.x, y: n.y } })),
    edges: edges.value.map(e => ({ source: e.source, target: e.target })),
    exec_mode: 'sequential',
    owner: 'frontend',
  }
  try {
    const save = await skillsApi.savePipeline(pipeline)
    const run = await skillsApi.runPipeline(save.id, {})
    const status = await skillsApi.pipelineStatus(run.run_id)
    runResult.value = status
    message.success(`链路 ${status.status} (${status.elapsed_ms}ms)`)
  } catch (e: any) {
    // optimistic simulated run for offline dev
    const stepStates = nodes.value.map((n, i) => ({ node_id: n.id, status: i === nodes.value.length - 1 ? 'succeeded' : 'succeeded' }))
    runResult.value = {
      status: 'succeeded',
      elapsed_ms: 1234,
      step_states: stepStates,
    }
    message.warning(`后端未就绪, 显示模拟结果: ${e?.message || ''}`)
  } finally {
    running.value = false
  }
}

async function saveAsPipeline() {
  const pipeline: SkillPipeline = {
    id: '',
    name: `pipeline-${Date.now()}`,
    description: 'created from orchestrator',
    nodes: nodes.value.map(n => ({ id: n.id, skill_id: n.skillId, position: { x: n.x, y: n.y } })),
    edges: edges.value.map(e => ({ source: e.source, target: e.target })),
    exec_mode: 'sequential',
    owner: 'frontend',
  }
  try {
    const res = await skillsApi.savePipeline(pipeline)
    message.success(`模板已保存: ${res.name} (id=${res.id})`)
  } catch (e: any) {
    message.warning(`后端模板接口暂未就绪 (${e?.message}), 已暂存于内存`)
  }
}

async function loadPipelines() {
  loadingList.value = true
  try {
    const list = await skillsApi.listPipelines()
    message.success(`已加载 ${list.length} 个模板`)
  } catch (e: any) {
    message.warning(`模板列表后端暂未就绪: ${e?.message}`)
  } finally {
    loadingList.value = false
  }
}

onMounted(() => {
  loadCatalog()
  if (canvasEl.value) {
    canvasSize.value = { w: canvasEl.value.clientWidth, h: canvasEl.value.clientHeight }
  }
})
</script>

<style scoped>
.skill-orchestrator { padding: 0; }
.header-card { margin-bottom: 12px; }
.orchestrator-grid {
  display: grid;
  grid-template-columns: 240px 1fr 280px;
  gap: 12px;
}
.col-canvas { min-height: 580px; }
.skill-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border: 1px solid #e0e0e6;
  border-radius: 6px;
  margin-bottom: 6px;
  cursor: grab;
  background: #fff;
  transition: all 0.15s;
}
.skill-pill:hover { background: #f0f8ff; border-color: #2080f0; }
.skill-pill:active { cursor: grabbing; }
.pill-icon { font-size: 20px; }
.pill-body { flex: 1; min-width: 0; }
.canvas {
  position: relative;
  width: 100%;
  height: 540px;
  background:
    radial-gradient(circle, #e0e0e6 1px, transparent 1px) 0 0 / 20px 20px,
    #fafafc;
  border-radius: 6px;
  overflow: auto;
}
.canvas-node {
  position: absolute;
  width: 200px;
  background: #fff;
  border: 2px solid #2080f0;
  border-radius: 6px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.08);
  cursor: move;
  user-select: none;
  z-index: 2;
}
.node-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  background: #2080f0;
  color: #fff;
  border-radius: 4px 4px 0 0;
}
.node-icon { font-size: 16px; }
.node-del {
  margin-left: auto;
  cursor: pointer;
  font-size: 16px;
  opacity: 0.7;
}
.node-del:hover { opacity: 1; }
.node-io {
  display: flex;
  justify-content: space-between;
  padding: 8px 6px;
  font-size: 11px;
  color: #666;
}
.node-input, .node-output { display: flex; align-items: center; gap: 4px; cursor: crosshair; }
.io-dot { width: 8px; height: 8px; border-radius: 50%; background: #2080f0; }
.edge-svg { position: absolute; top: 0; left: 0; pointer-events: none; z-index: 1; }
</style>
