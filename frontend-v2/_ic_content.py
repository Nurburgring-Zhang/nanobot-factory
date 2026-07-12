"""InfiniteCanvas.vue content. Simple triple-quoted strings only."""
IC_TEMPLATE = """<!--
  V5 Chapter 38 - Infinite Canvas (Excalidraw / tldraw style)
  Drag-and-drop visual orchestration surface for assets, capabilities,
  agents and workflows on a pannable / zoomable 2D plane.
-->
<template>
  <div ref="containerRef" class="infinite-canvas" :class="{ 'is-connecting': !!pendingSourceId }" tabindex="0" @keydown="onKeyDown" @wheel.prevent="onWheel" @mousedown="onCanvasMouseDown" @mousemove="onMouseMove" @mouseup="onMouseUp" @mouseleave="onMouseUp">
    <div class="ic-toolbar" role="toolbar">
      <button v-for="t in nodePalette" :key="t.type" type="button" class="ic-palette-btn" :data-testid="'palette-' + t.type" @click="addNode(t.type, t.label, t.color)">
        <span class="dot" :style="{ background: t.color }"></span>{{ t.label }}
      </button>
      <span class="ic-spacer"></span>
      <button type="button" class="ic-icon-btn" data-testid="connect-btn" @click="toggleConnectMode">{{ pendingSourceId ? 'X' : 'C' }}</button>
      <button type="button" class="ic-icon-btn" title="reset" @click="resetViewport">R</button>
      <button type="button" class="ic-icon-btn" title="clear" @click="clearAll">DEL</button>
      <span class="ic-zoom-label" data-testid="zoom-label">{{ Math.round(viewport.scale * 100) }}%</span>
    </div>
    <div v-if="pendingSourceId" class="ic-hint">Connect from <strong>{{ findNodeLabel(pendingSourceId) }}</strong> to target. Esc to cancel.</div>
    <svg class="ic-svg" :viewBox="viewBox" preserveAspectRatio="xMidYMid meet" role="application" data-testid="ic-svg">
      <defs>
        <pattern id="ic-grid" width="40" height="40" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1.2" fill="#d8d8d8"></circle>
        </pattern>
      </defs>
      <rect :x="viewBox.x" :y="viewBox.y" :width="viewBox.w" :height="viewBox.h" fill="url(#ic-grid)"></rect>
      <g class="ic-edges">
        <g v-for="edge in edges" :key="edge.id" :data-testid="'edge-' + edge.id">
          <path :d="edgePath(edge)" stroke="#888" stroke-width="2" fill="none" marker-end="url(#ic-arrow)"></path>
        </g>
      </g>
      <defs>
        <marker id="ic-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 Z" fill="#888"></path>
        </marker>
      </defs>
      <g class="ic-nodes">
        <g v-for="node in nodes" :key="node.id" :transform="'translate(' + node.x + ',' + node.y + ')'" class="ic-node" :class="{ selected: node.id === selectedNodeId }" :data-node-id="node.id" :data-testid="'canvas-node-' + node.id" @mousedown.stop="onNodeMouseDown($event, node.id)" @click.stop="onNodeClick($event, node.id)">
          <rect :width="node.width" :height="node.height" rx="8" :fill="nodeColor(node)" :stroke="node.id === selectedNodeId ? '#0a5dc2' : '#888'" :stroke-width="node.id === selectedNodeId ? 2.5 : 1"></rect>
          <text :x="10" :y="20" font-size="12" font-weight="600" fill="#222">{{ typeLabel(node.type) }}</text>
          <text :x="10" :y="40" font-size="13" fill="#333">{{ node.label }}</text>
          <text :x="10" :y="node.height - 8" font-size="10" fill="#888">{{ node.id }}</text>
        </g>
      </g>
    </svg>
    <div v-if="nodes.length === 0" class="ic-empty" data-testid="empty-state"><p>Canvas is empty. Click a palette button to add a node.</p></div>
    <div class="ic-statusbar">
      <span>nodes: {{ nodes.length }}</span>
      <span>edges: {{ edges.length }}</span>
      <span v-if="selectedNodeId" data-testid="selected-label">selected: {{ findNodeLabel(selectedNodeId) }}</span>
    </div>
  </div>
</template>
"""

IC_SCRIPT = """<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

export type CanvasNodeType = 'asset' | 'capability' | 'agent' | 'workflow'
export interface CanvasNode {
  id: string
  type: CanvasNodeType
  x: number
  y: number
  width: number
  height: number
  label: string
  data?: Record<string, unknown>
}
export interface CanvasEdge {
  id: string
  sourceId: string
  targetId: string
  label?: string
}
interface Viewport { x: number; y: number; scale: number }
interface PaletteItem { type: CanvasNodeType; label: string; color: string; width: number; height: number }

const props = withDefaults(defineProps<{
  initialNodes?: CanvasNode[]
  initialEdges?: CanvasEdge[]
  storageKey?: string
}>(), {
  initialNodes: () => [],
  initialEdges: () => [],
  storageKey: 'vdp-canvas.state.v1'
})

const emit = defineEmits<{
  'update:nodes': [nodes: CanvasNode[]]
  'update:edges': [edges: CanvasEdge[]]
  'select': [nodeId: string | null]
}>()

const nodePalette: PaletteItem[] = [
  { type: 'asset',      label: 'asset',      color: '#fff7e6', width: 160, height: 80 },
  { type: 'capability', label: 'capability', color: '#e6f0ff', width: 160, height: 80 },
  { type: 'agent',      label: 'agent',      color: '#f0fff6', width: 160, height: 80 },
  { type: 'workflow',   label: 'workflow',   color: '#fde6f0', width: 160, height: 80 }
]

function typeLabel(t: CanvasNodeType): string {
  return nodePalette.find(p => p.type === t)?.label ?? t
}

const nodes = ref<CanvasNode[]>([])
const edges = ref<CanvasEdge[]>([])
const selectedNodeId = ref<string | null>(null)
const pendingSourceId = ref<string | null>(null)
const viewport = reactive<Viewport>({ x: 0, y: 0, scale: 1 })
const dragNode = ref<{ id: string; offsetX: number; offsetY: number } | null>(null)
const panState = ref<{ startX: number; startY: number; startVx: number; startVy: number } | null>(null)
const containerRef = ref<HTMLDivElement | null>(null)

const viewBox = computed(() => ({
  x: viewport.x,
  y: viewport.y,
  w: 1000 / viewport.scale,
  h: 600 / viewport.scale
}))

let persistTimer: ReturnType<typeof setTimeout> | null = null
function schedulePersist(): void {
  if (typeof localStorage === 'undefined') return
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(() => {
    try {
      localStorage.setItem(props.storageKey, JSON.stringify({ nodes: nodes.value, edges: edges.value }))
    } catch { /* quota / private mode */ }
  }, 500)
}

function restorePersisted(): void {
  if (typeof localStorage === 'undefined') return
  try {
    const raw = localStorage.getItem(props.storageKey)
    if (!raw) return
    const parsed = JSON.parse(raw) as { nodes?: CanvasNode[]; edges?: CanvasEdge[] }
    if (Array.isArray(parsed.nodes)) nodes.value = parsed.nodes
    if (Array.isArray(parsed.edges)) edges.value = parsed.edges
  } catch { /* corrupt */ }
}

function makeId(prefix: string): string {
  return prefix + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8)
}
function findNode(id: string): CanvasNode | undefined {
  return nodes.value.find(n => n.id === id)
}
function findNodeLabel(id: string): string {
  const n = findNode(id)
  return n ? typeLabel(n.type) + ' - ' + n.label : '(deleted)'
}
function nodeColor(n: CanvasNode): string {
  return nodePalette.find(p => p.type === n.type)?.color ?? '#fff'
}
function edgePath(edge: CanvasEdge): string {
  const s = findNode(edge.sourceId)
  const t = findNode(edge.targetId)
  if (!s || !t) return ''
  const sx = s.x + s.width
  const sy = s.y + s.height / 2
  const tx = t.x
  const ty = t.y + t.height / 2
  const dx = Math.max(40, Math.abs(tx - sx) / 2)
  return 'M ' + sx + ' ' + sy + ' C ' + (sx + dx) + ' ' + sy + ', ' + (tx - dx) + ' ' + ty + ', ' + tx + ' ' + ty
}

function clientToWorld(clientX: number, clientY: number): { x: number; y: number } {
  const rect = containerRef.value?.getBoundingClientRect()
  if (!rect) return { x: 0, y: 0 }
  return {
    x: viewport.x + (clientX - rect.left) / rect.width * viewBox.value.w,
    y: viewport.y + (clientY - rect.top) / rect.height * viewBox.value.h
  }
}
"""

IC_HANDLERS = """function addNode(type: CanvasNodeType, label: string, _color: string): CanvasNode {
  const palette = nodePalette.find(p => p.type === type)!
  const node: CanvasNode = {
    id: makeId(type),
    type,
    x: viewport.x + viewBox.value.w / 2 - palette.width / 2,
    y: viewport.y + viewBox.value.h / 2 - palette.height / 2,
    width: palette.width,
    height: palette.height,
    label: label + ' ' + (nodes.value.filter(n => n.type === type).length + 1)
  }
  nodes.value.push(node)
  selectedNodeId.value = node.id
  schedulePersist()
  emit('update:nodes', nodes.value)
  return node
}

function moveNode(id: string, x: number, y: number): void {
  const n = findNode(id)
  if (!n) return
  n.x = x
  n.y = y
  schedulePersist()
}

function selectNode(id: string | null): void {
  selectedNodeId.value = id
  emit('select', id)
}

function deleteNode(id: string): void {
  const idx = nodes.value.findIndex(n => n.id === id)
  if (idx >= 0) nodes.value.splice(idx, 1)
  edges.value = edges.value.filter(e => e.sourceId !== id && e.targetId !== id)
  if (selectedNodeId.value === id) selectedNodeId.value = null
  if (pendingSourceId.value === id) pendingSourceId.value = null
  schedulePersist()
  emit('update:nodes', nodes.value)
  emit('update:edges', edges.value)
}

function connectNodes(sourceId: string, targetId: string, label?: string): CanvasEdge | null {
  if (sourceId === targetId) return null
  if (edges.value.some(e => e.sourceId === sourceId && e.targetId === targetId)) return null
  const edge: CanvasEdge = { id: makeId('edge'), sourceId, targetId, label }
  edges.value.push(edge)
  schedulePersist()
  emit('update:edges', edges.value)
  return edge
}

function toggleConnectMode(): void {
  if (pendingSourceId.value) {
    pendingSourceId.value = null
    return
  }
  if (selectedNodeId.value) {
    pendingSourceId.value = selectedNodeId.value
  }
}

function resetViewport(): void {
  viewport.x = 0
  viewport.y = 0
  viewport.scale = 1
}

function clearAll(): void {
  nodes.value = []
  edges.value = []
  selectedNodeId.value = null
  pendingSourceId.value = null
  schedulePersist()
  emit('update:nodes', nodes.value)
  emit('update:edges', edges.value)
}

defineExpose({
  addNode, moveNode, selectNode, deleteNode, connectNodes,
  toggleConnectMode, resetViewport, clearAll,
  nodes, edges, selectedNodeId, viewport
})

function onNodeMouseDown(e: MouseEvent, id: string): void {
  if (e.button !== 0) return
  const world = clientToWorld(e.clientX, e.clientY)
  const n = findNode(id)
  if (!n) return
  dragNode.value = { id, offsetX: world.x - n.x, offsetY: world.y - n.y }
}

function onNodeClick(_e: MouseEvent, id: string): void {
  if (pendingSourceId.value && pendingSourceId.value !== id) {
    connectNodes(pendingSourceId.value, id)
    pendingSourceId.value = null
    return
  }
  selectNode(id)
}

function onCanvasMouseDown(e: MouseEvent): void {
  if (e.button === 1) {
    panState.value = { startX: e.clientX, startY: e.clientY, startVx: viewport.x, startVy: viewport.y }
    e.preventDefault()
    return
  }
  if (e.button === 0) {
    if (pendingSourceId.value) pendingSourceId.value = null
    else selectNode(null)
  }
}

function onMouseMove(e: MouseEvent): void {
  if (dragNode.value) {
    const world = clientToWorld(e.clientX, e.clientY)
    moveNode(dragNode.value.id, world.x - dragNode.value.offsetX, world.y - dragNode.value.offsetY)
    return
  }
  if (panState.value) {
    const rect = containerRef.value?.getBoundingClientRect()
    if (!rect) return
    viewport.x = panState.value.startVx - (e.clientX - panState.value.startX) / rect.width * viewBox.value.w
    viewport.y = panState.value.startVy - (e.clientY - panState.value.startY) / rect.height * viewBox.value.h
  }
}

function onMouseUp(_e: MouseEvent): void {
  dragNode.value = null
  panState.value = null
}

function onWheel(e: WheelEvent): void {
  if (e.ctrlKey || e.metaKey) {
    const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1
    const oldScale = viewport.scale
    const newScale = Math.min(3, Math.max(0.25, oldScale * factor))
    const rect = containerRef.value?.getBoundingClientRect()
    if (rect) {
      const relX = e.clientX - rect.left
      const relY = e.clientY - rect.top
      const worldX = viewport.x + (relX / rect.width) * viewBox.value.w
      const worldY = viewport.y + (relY / rect.height) * viewBox.value.h
      viewport.scale = newScale
      viewport.x = worldX - (relX / rect.width) * (1000 / newScale)
      viewport.y = worldY - (relY / rect.height) * (600 / newScale)
    } else {
      viewport.scale = newScale
    }
  } else {
    const rect = containerRef.value?.getBoundingClientRect()
    if (!rect) return
    viewport.x += (e.deltaX / rect.width) * viewBox.value.w
    viewport.y += (e.deltaY / rect.height) * viewBox.value.h
  }
}

function onKeyDown(e: KeyboardEvent): void {
  const target = e.target as HTMLElement | null
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return
  if (e.key === 'Delete' || e.key === 'Backspace') {
    if (selectedNodeId.value) {
      deleteNode(selectedNodeId.value)
      e.preventDefault()
    }
  } else if (e.key === 'Escape') {
    pendingSourceId.value = null
  } else if (e.key === 'c' || e.key === 'C') {
    if (selectedNodeId.value) pendingSourceId.value = selectedNodeId.value
  }
}

watch(() => [nodes.value, edges.value], () => schedulePersist(), { deep: true })

onMounted(() => {
  if (props.initialNodes.length > 0) {
    nodes.value = [...props.initialNodes]
  } else {
    restorePersisted()
  }
  if (props.initialEdges.length > 0) {
    edges.value = [...props.initialEdges]
  }
  containerRef.value?.focus()
})

onBeforeUnmount(() => {
  if (persistTimer) clearTimeout(persistTimer)
})
</script>
"""

IC_STYLE = """<style scoped>
.infinite-canvas { position: relative; width: 100%; height: 100%; min-height: 480px; background: var(--app-surface, #fafafa); outline: none; user-select: none; overflow: hidden; }
.infinite-canvas:focus-visible { box-shadow: inset 0 0 0 2px var(--app-primary, #0a5dc2); }
.ic-svg { width: 100%; height: calc(100% - 50px); display: block; cursor: grab; }
.infinite-canvas.is-connecting .ic-svg { cursor: crosshair; }
.ic-node { cursor: move; }
.ic-node.selected rect { filter: drop-shadow(0 2px 6px rgba(10, 93, 194, 0.35)); }
.ic-toolbar { display: flex; align-items: center; gap: 6px; padding: 4px 10px; height: 28px; border-bottom: 1px solid var(--app-border, #e0e0e6); background: var(--app-surface, #fff); }
.ic-palette-btn, .ic-icon-btn { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; font-size: 12px; border: 1px solid var(--app-border, #e0e0e6); background: var(--app-surface, #fff); border-radius: 4px; cursor: pointer; color: var(--app-fg, #333); }
.ic-palette-btn:hover, .ic-icon-btn:hover { background: var(--app-primary, #0a5dc2); color: #fff; border-color: var(--app-primary, #0a5dc2); }
.ic-palette-btn .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.ic-spacer { flex: 1; }
.ic-zoom-label { font-size: 11px; color: var(--app-muted, #767676); }
.ic-hint { position: absolute; top: 36px; left: 50%; transform: translateX(-50%); padding: 4px 12px; background: var(--app-primary, #0a5dc2); color: #fff; font-size: 12px; border-radius: 4px; z-index: 5; pointer-events: none; }
.ic-empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; pointer-events: none; color: var(--app-muted, #999); font-size: 14px; }
.ic-statusbar { position: absolute; bottom: 0; left: 0; right: 0; height: 22px; display: flex; align-items: center; gap: 18px; padding: 0 10px; font-size: 11px; color: var(--app-muted, #666); border-top: 1px solid var(--app-border, #e0e0e6); background: var(--app-surface, #fff); }
</style>
"""

INFINITE_CANVAS_VUE = IC_TEMPLATE + IC_SCRIPT + IC_HANDLERS + IC_STYLE