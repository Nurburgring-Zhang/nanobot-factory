<!--
  V5 Visual Editor — Workflow Editor Scaffold (P21 P3 P2 focused)

  A focused single-file workflow editor shell that complements (not replaces)
  the existing InfiniteCanvas.vue. Use case: edit a single workflow definition
  with 7 well-known node types: Start, End, Process, Decision, Loop, AI Skill,
  Provider.

  Features (scaffold scope):
    1. SVG canvas with pan (middle/right-mouse drag) and zoom (Ctrl+wheel)
    2. Right-side palette with the 7 draggable node types
    3. Drop-on-canvas to create a node at the cursor position
    4. Per-node type colour + input (left) / output (right) handle
    5. Click output handle, drag to input handle, draw edge
    6. Click node to select; properties panel edits label + JSON params
    7. JSON save / load to a textarea in the toolbar
    8. Empty-state hint when canvas is empty

  Out of scope (next tasks): undo/redo, copy/paste, multi-select, alignment,
  validate, execute.
-->
<template>
  <div class="visual-editor" data-testid="visual-editor">
    <div class="ve-toolbar" role="toolbar">
      <span class="ve-title">Visual Editor</span>
      <span class="ve-status" data-testid="status-bar">
        nodes: {{ nodes.length }} | edges: {{ edges.length }}
        <span v-if="selectedNodeId"> | selected: {{ selectedNode?.label ?? '?' }}</span>
      </span>
      <span class="ve-spacer"></span>
      <input v-model="jsonInput" data-testid="json-input" class="ve-json-input"
             placeholder='{"nodes":[],"edges":[]}' />
      <button type="button" class="ve-btn" data-testid="save-btn" @click="onSaveClick">Save</button>
      <button type="button" class="ve-btn" data-testid="load-btn" @click="onLoadClick">Load</button>
      <button type="button" class="ve-btn ve-btn-danger" data-testid="clear-btn" @click="onClear">Clear</button>
    </div>

    <div class="ve-body">
      <div ref="canvasRef" class="ve-canvas" data-testid="ve-canvas" tabindex="0"
           @dragover.prevent="onCanvasDragOver" @drop="onCanvasDrop"
           @mousedown="onCanvasMouseDown" @mousemove="onMouseMove"
           @mouseup="onMouseUp" @mouseleave="onMouseUp"
           @wheel.prevent="onWheel" @keydown="onKeyDown">
        <svg class="ve-svg" :viewBox="`${viewport.x} ${viewport.y} ${viewBox.w} ${viewBox.h}`"
             preserveAspectRatio="xMidYMid meet" role="application" data-testid="ve-svg">
          <defs>
            <pattern id="ve-grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <circle cx="2" cy="2" r="1.2" fill="#d8d8d8"></circle>
            </pattern>
            <marker id="ve-arrow" viewBox="0 0 10 10" refX="9" refY="5"
                    markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 Z" fill="#888"></path>
            </marker>
          </defs>
          <rect :x="viewport.x" :y="viewport.y" :width="viewBox.w" :height="viewBox.h" fill="url(#ve-grid)"></rect>
          <g class="ve-edges">
            <path v-for="edge in edges" :key="edge.id" :data-testid="'edge-' + edge.id"
                  :d="edgePath(edge)" stroke="#888" stroke-width="2" fill="none"
                  marker-end="url(#ve-arrow)"></path>
            <path v-if="pendingConnection" :d="pendingConnectionPath"
                  stroke="#0a5dc2" stroke-width="2" stroke-dasharray="4 4" fill="none"
                  marker-end="url(#ve-arrow)"></path>
          </g>
          <g class="ve-nodes">
            <g v-for="node in nodes" :key="node.id" class="ve-node"
               :class="{ selected: node.id === selectedNodeId }"
               :data-node-id="node.id" :data-testid="'canvas-node-' + node.id"
               :transform="`translate(${node.x},${node.y})`"
               @mousedown.stop="onNodeMouseDown($event, node.id)"
               @click.stop="onNodeClick($event, node.id)">
              <rect :width="node.width" :height="node.height" rx="6"
                    :fill="nodeColor(node)"
                    :stroke="node.id === selectedNodeId ? '#0a5dc2' : '#888'"
                    :stroke-width="node.id === selectedNodeId ? 2.5 : 1"></rect>
              <text :x="10" :y="16" font-size="10" font-weight="700" fill="#222">{{ node.type }}</text>
              <text :x="10" :y="34" font-size="13" fill="#333">{{ node.label }}</text>
              <text :x="10" :y="node.height - 6" font-size="9" fill="#888">{{ node.id }}</text>
              <circle v-if="canInput(node.type)" :cx="0" :cy="node.height / 2" r="6"
                      class="ve-handle ve-handle-in" :data-handle="'in-' + node.id"
                      :data-testid="'handle-in-' + node.id"
                      @mousedown.stop="onHandleMouseDown($event, node.id, 'in')"></circle>
              <circle v-if="canOutput(node.type)" :cx="node.width" :cy="node.height / 2" r="6"
                      class="ve-handle ve-handle-out" :data-handle="'out-' + node.id"
                      :data-testid="'handle-out-' + node.id"
                      @mousedown.stop="onHandleMouseDown($event, node.id, 'out')"></circle>
            </g>
          </g>
        </svg>
        <div v-if="nodes.length === 0" class="ve-empty" data-testid="empty-state">
          Drag a node from the palette to start building your workflow.
        </div>
        <div class="ve-zoom-label" data-testid="zoom-label">{{ Math.round(viewport.scale * 100) }}%</div>
      </div>

      <div class="ve-right">
        <div class="ve-palette" data-testid="palette" aria-label="Node palette">
          <h3 class="ve-section-title">Palette</h3>
          <div v-for="t in palette" :key="t.type" class="ve-palette-item"
               :data-testid="'palette-' + t.type" :data-node-type="t.type"
               draggable="true" @dragstart="onPaletteDragStart($event, t.type)">
            <span class="ve-dot" :style="{ background: t.color }"></span>
            <span class="ve-palette-label">{{ t.label }}</span>
          </div>
        </div>

        <div class="ve-properties" data-testid="properties" aria-label="Node properties">
          <h3 class="ve-section-title">Properties</h3>
          <div v-if="!selectedNode" class="ve-empty-prop" data-testid="no-selection">No node selected</div>
          <div v-else class="ve-prop-form">
            <label class="ve-field">
              <span class="ve-field-label">Label</span>
              <input v-model="selectedNode.label" data-testid="prop-label" type="text" class="ve-input" />
            </label>
            <label class="ve-field">
              <span class="ve-field-label">Type</span>
              <input :value="selectedNode.type" type="text" class="ve-input" disabled />
            </label>
            <label class="ve-field">
              <span class="ve-field-label">Params (JSON)</span>
              <textarea v-model="paramsText" data-testid="prop-params" rows="4"
                        class="ve-input ve-textarea" @blur="onParamsBlur"></textarea>
            </label>
            <div class="ve-prop-actions">
              <button type="button" class="ve-btn ve-btn-danger" data-testid="prop-delete"
                      @click="onDeleteSelected">Delete</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'

/* ------------------------------------------------------------------ types */

export type VisualEditorNodeType =
  | 'start'
  | 'end'
  | 'process'
  | 'decision'
  | 'loop'
  | 'ai_skill'
  | 'provider'

export interface VisualEditorNode {
  id: string
  type: VisualEditorNodeType
  label: string
  x: number
  y: number
  width: number
  height: number
  params: Record<string, unknown>
}

export interface VisualEditorEdge {
  id: string
  source: string
  target: string
  label?: string
}

export interface VisualEditorDocument {
  version: 1
  nodes: VisualEditorNode[]
  edges: VisualEditorEdge[]
}

interface PaletteItem {
  type: VisualEditorNodeType
  label: string
  color: string
  width: number
  height: number
}

interface Viewport { x: number; y: number; scale: number }

/* -------------------------------------------------------------- constants */

const palette: PaletteItem[] = [
  { type: 'start',     label: 'Start',     color: '#d6f5d6', width: 140, height: 60 },
  { type: 'end',       label: 'End',       color: '#fad6d6', width: 140, height: 60 },
  { type: 'process',   label: 'Process',   color: '#d6e4f5', width: 160, height: 70 },
  { type: 'decision',  label: 'Decision',  color: '#fff5d6', width: 160, height: 80 },
  { type: 'loop',      label: 'Loop',      color: '#f5e1d6', width: 160, height: 70 },
  { type: 'ai_skill',  label: 'AI Skill',  color: '#e8d6f5', width: 170, height: 80 },
  { type: 'provider',  label: 'Provider',  color: '#d6f5f0', width: 160, height: 70 }
]

const STORAGE_KEY = 'vdp-visual-editor.doc.v1'

/* ----------------------------------------------------------------- props */

const props = withDefaults(defineProps<{
  initialDoc?: VisualEditorDocument | null
  storageKey?: string
}>(), {
  initialDoc: null,
  storageKey: STORAGE_KEY
})

const emit = defineEmits<{
  'update:doc': [doc: VisualEditorDocument]
  'select': [nodeId: string | null]
  'save': [doc: VisualEditorDocument]
  'load': [doc: VisualEditorDocument]
}>()

/* ----------------------------------------------------------- core state */

const nodes = ref<VisualEditorNode[]>([])
const edges = ref<VisualEditorEdge[]>([])
const selectedNodeId = ref<string | null>(null)
const viewport = reactive<Viewport>({ x: 0, y: 0, scale: 1 })
const jsonInput = ref<string>('')

const canvasRef = ref<HTMLDivElement | null>(null)
const dragNode = ref<{ id: string; offsetX: number; offsetY: number } | null>(null)
const panState = ref<{ startX: number; startY: number; startVx: number; startVy: number } | null>(null)
const pendingSource = ref<string | null>(null) // when output handle is held down, draw pending line to mouse
const pendingMouse = ref<{ x: number; y: number } | null>(null)
const dragGhostType = ref<VisualEditorNodeType | null>(null)

/* ------------------------------------------------------------- viewbox */

const viewBox = computed(() => ({
  w: 1000 / viewport.scale,
  h: 600 / viewport.scale
}))

const selectedNode = computed<VisualEditorNode | null>(() =>
  nodes.value.find(n => n.id === selectedNodeId.value) ?? null
)

const pendingConnection = computed(() => {
  if (!pendingSource.value) return null
  const src = nodes.value.find(n => n.id === pendingSource.value)
  if (!src) return null
  return { sx: src.x + src.width, sy: src.y + src.height / 2, mx: pendingMouse.value?.x ?? src.x + src.width + 50, my: pendingMouse.value?.y ?? src.y }
})

const pendingConnectionPath = computed(() => {
  if (!pendingConnection.value) return ''
  const p = pendingConnection.value
  return 'M ' + p.sx + ' ' + p.sy + ' L ' + p.mx + ' ' + p.my
})

/* ----------------------------------------------------------- persistence */

function schedulePersist(): void {
  if (typeof localStorage === 'undefined') return
  try {
    const doc = exportDoc()
    localStorage.setItem(props.storageKey, JSON.stringify(doc))
  } catch { /* quota / private mode */ }
}

function restorePersisted(): void {
  if (typeof localStorage === 'undefined') return
  try {
    const raw = localStorage.getItem(props.storageKey)
    if (!raw) return
    const doc = JSON.parse(raw) as VisualEditorDocument
    if (Array.isArray(doc.nodes) && Array.isArray(doc.edges)) {
      nodes.value = doc.nodes
      edges.value = doc.edges
    }
  } catch { /* corrupt */ }
}

/* ----------------------------------------------------------- import/export */

function exportDoc(): VisualEditorDocument {
  return { version: 1, nodes: JSON.parse(JSON.stringify(nodes.value)), edges: JSON.parse(JSON.stringify(edges.value)) }
}

function importDoc(doc: VisualEditorDocument): void {
  if (!doc || !Array.isArray(doc.nodes) || !Array.isArray(doc.edges)) {
    throw new Error('Invalid document: nodes/edges arrays required')
  }
  nodes.value = doc.nodes.map(n => ({ ...n, params: n.params && typeof n.params === 'object' ? { ...n.params } : {} }))
  edges.value = doc.edges.map(e => ({ ...e }))
  selectedNodeId.value = null
  pendingSource.value = null
  emit('update:doc', exportDoc())
}

/* ------------------------------------------------------------- node ops */

function makeId(prefix: string): string {
  return prefix + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8)
}

function findNode(id: string): VisualEditorNode | undefined {
  return nodes.value.find(n => n.id === id)
}

function nodeColor(n: VisualEditorNode): string {
  return palette.find(p => p.type === n.type)?.color ?? '#fff'
}

function canInput(type: VisualEditorNodeType): boolean {
  return type !== 'start'
}

function canOutput(type: VisualEditorNodeType): boolean {
  return type !== 'end'
}

function clientToWorld(clientX: number, clientY: number): { x: number; y: number } {
  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return { x: 0, y: 0 }
  return {
    x: viewport.x + (clientX - rect.left) / rect.width * viewBox.value.w,
    y: viewport.y + (clientY - rect.top) / rect.height * viewBox.value.h
  }
}

function addNode(type: VisualEditorNodeType, worldX: number, worldY: number): VisualEditorNode {
  const def = palette.find(p => p.type === type)!
  const node: VisualEditorNode = {
    id: makeId(type),
    type,
    label: def.label + ' ' + (nodes.value.filter(n => n.type === type).length + 1),
    x: worldX - def.width / 2,
    y: worldY - def.height / 2,
    width: def.width,
    height: def.height,
    params: {}
  }
  nodes.value.push(node)
  selectedNodeId.value = node.id
  schedulePersist()
  emit('update:doc', exportDoc())
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
  edges.value = edges.value.filter(e => e.source !== id && e.target !== id)
  if (selectedNodeId.value === id) selectedNodeId.value = null
  if (pendingSource.value === id) pendingSource.value = null
  schedulePersist()
  emit('update:doc', exportDoc())
}

function connectNodes(sourceId: string, targetId: string): VisualEditorEdge | null {
  if (sourceId === targetId) return null
  if (edges.value.some(e => e.source === sourceId && e.target === targetId)) return null
  const edge: VisualEditorEdge = { id: makeId('edge'), source: sourceId, target: targetId }
  edges.value.push(edge)
  schedulePersist()
  emit('update:doc', exportDoc())
  return edge
}

function edgePath(edge: VisualEditorEdge): string {
  const s = findNode(edge.source)
  const t = findNode(edge.target)
  if (!s || !t) return ''
  const sx = s.x + s.width, sy = s.y + s.height / 2
  const tx = t.x, ty = t.y + t.height / 2
  const dx = Math.max(40, Math.abs(tx - sx) / 2)
  return 'M ' + sx + ' ' + sy + ' C ' + (sx + dx) + ' ' + sy + ', ' + (tx - dx) + ' ' + ty + ', ' + tx + ' ' + ty
}

function clearAll(): void {
  nodes.value = []
  edges.value = []
  selectedNodeId.value = null
  pendingSource.value = null
  schedulePersist()
  emit('update:doc', exportDoc())
}

function resetViewport(): void {
  viewport.x = 0
  viewport.y = 0
  viewport.scale = 1
}

/* ------------------------------------------------------------- mouse / drag */

function onPaletteDragStart(e: DragEvent, type: VisualEditorNodeType): void {
  if (!e.dataTransfer) return
  dragGhostType.value = type
  e.dataTransfer.setData('application/x-vdp-node-type', type)
  e.dataTransfer.effectAllowed = 'copy'
}

function onCanvasDragOver(_e: DragEvent): void {
  // dragover.preventDefault is declared on the template; no further work needed.
}

function onCanvasDrop(e: DragEvent): void {
  e.preventDefault()
  const type = (e.dataTransfer?.getData('application/x-vdp-node-type') ?? dragGhostType.value) as VisualEditorNodeType | null
  dragGhostType.value = null
  if (!type || !palette.some(p => p.type === type)) return
  const world = clientToWorld(e.clientX, e.clientY)
  addNode(type, world.x, world.y)
}

function onNodeMouseDown(e: MouseEvent, id: string): void {
  if (e.button !== 0) return
  const world = clientToWorld(e.clientX, e.clientY)
  const n = findNode(id)
  if (!n) return
  dragNode.value = { id, offsetX: world.x - n.x, offsetY: world.y - n.y }
}

function onNodeClick(_e: MouseEvent, id: string): void {
  if (pendingSource.value) {
    if (pendingSource.value !== id) {
      connectNodes(pendingSource.value, id)
    }
    pendingSource.value = null
    return
  }
  selectNode(id)
}

function onCanvasMouseDown(e: MouseEvent): void {
  if (e.button === 1 || e.button === 2) {
    panState.value = { startX: e.clientX, startY: e.clientY, startVx: viewport.x, startVy: viewport.y }
    e.preventDefault()
    return
  }
  if (e.button === 0) {
    if (pendingSource.value) pendingSource.value = null
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
    const rect = canvasRef.value?.getBoundingClientRect()
    if (!rect) return
    viewport.x = panState.value.startVx - (e.clientX - panState.value.startX) / rect.width * viewBox.value.w
    viewport.y = panState.value.startVy - (e.clientY - panState.value.startY) / rect.height * viewBox.value.h
    return
  }
  if (pendingSource.value) {
    pendingMouse.value = clientToWorld(e.clientX, e.clientY)
  }
}

function onMouseUp(_e: MouseEvent): void {
  dragNode.value = null
  panState.value = null
  if (pendingSource.value && pendingMouse.value) {
    // Released on empty space: cancel pending connection
    pendingSource.value = null
    pendingMouse.value = null
  }
}

function onWheel(e: WheelEvent): void {
  if (e.ctrlKey || e.metaKey) {
    const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1
    const newScale = Math.min(2, Math.max(0.3, viewport.scale * factor))
    const rect = canvasRef.value?.getBoundingClientRect()
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
    const rect = canvasRef.value?.getBoundingClientRect()
    if (!rect) return
    viewport.x += (e.deltaX / rect.width) * viewBox.value.w
    viewport.y += (e.deltaY / rect.height) * viewBox.value.h
  }
}

function onHandleMouseDown(e: MouseEvent, id: string, side: 'in' | 'out'): void {
  if (e.button !== 0) return
  if (side === 'out') {
    pendingSource.value = id
    pendingMouse.value = clientToWorld(e.clientX, e.clientY)
  } else {
    // input handle click: complete a connection from current pendingSource (if any)
    if (pendingSource.value && pendingSource.value !== id) {
      connectNodes(pendingSource.value, id)
      pendingSource.value = null
      pendingMouse.value = null
    }
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
    pendingSource.value = null
    pendingMouse.value = null
  }
}

/* -------------------------------------------------------------- properties */

const paramsText = ref<string>('{}')
watch(selectedNode, n => { paramsText.value = n ? JSON.stringify(n.params ?? {}, null, 2) : '{}' }, { immediate: true })

function onParamsBlur(): void {
  if (!selectedNode.value) return
  try {
    const parsed = JSON.parse(paramsText.value || '{}')
    selectedNode.value.params = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
    paramsText.value = JSON.stringify(selectedNode.value.params, null, 2)
    schedulePersist()
    emit('update:doc', exportDoc())
  } catch {
    // revert on parse error
    paramsText.value = JSON.stringify(selectedNode.value.params ?? {}, null, 2)
  }
}

function onDeleteSelected(): void {
  if (selectedNodeId.value) deleteNode(selectedNodeId.value)
}

/* ----------------------------------------------------------------- save/load */

function onSaveClick(): void {
  const doc = exportDoc()
  jsonInput.value = JSON.stringify(doc, null, 2)
  emit('save', doc)
}

function onLoadClick(): void {
  try {
    const doc = JSON.parse(jsonInput.value) as VisualEditorDocument
    importDoc(doc)
    emit('load', doc)
  } catch {
    // keep existing state on parse error
  }
}

function onClear(): void {
  if (typeof confirm === 'function' && !confirm('Clear the entire workflow?')) return
  clearAll()
}

/* -------------------------------------------------------------- bootstrap */

if (props.initialDoc) {
  try { importDoc(props.initialDoc) } catch { /* ignore */ }
} else {
  restorePersisted()
}

onBeforeUnmount(() => { /* no timer-based resources */ })

defineExpose({
  addNode, deleteNode, moveNode, selectNode, connectNodes,
  clearAll, resetViewport, exportDoc, importDoc,
  nodes, edges, selectedNodeId, viewport
})
</script>

<style scoped>
.visual-editor { display: flex; flex-direction: column; height: 100%; min-height: 540px; background: var(--app-surface, #fff); border: 1px solid var(--app-border, #e0e0e6); border-radius: 6px; overflow: hidden; }
.ve-toolbar { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-bottom: 1px solid var(--app-border, #e0e0e6); background: var(--app-surface, #fafafa); flex-wrap: wrap; }
.ve-title { font-weight: 600; font-size: 14px; color: var(--app-fg, #333); }
.ve-status { font-size: 11px; color: var(--app-muted, #666); }
.ve-spacer { flex: 1; }
.ve-json-input { width: 280px; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; padding: 4px 6px; border: 1px solid var(--app-border, #ccc); border-radius: 4px; background: var(--app-surface, #fff); }
.ve-btn { padding: 4px 10px; font-size: 12px; border: 1px solid var(--app-border, #ccc); background: var(--app-surface, #fff); border-radius: 4px; cursor: pointer; color: var(--app-fg, #333); }
.ve-btn:hover { background: var(--app-primary, #0a5dc2); color: #fff; border-color: var(--app-primary, #0a5dc2); }
.ve-btn-danger { color: var(--app-error, #d03050); border-color: var(--app-error, #d03050); }
.ve-btn-danger:hover { background: var(--app-error, #d03050); color: #fff; }
.ve-body { display: flex; flex: 1; min-height: 0; }
.ve-canvas { position: relative; flex: 7; background: var(--app-surface, #fafafa); outline: none; overflow: hidden; }
.ve-canvas:focus-visible { box-shadow: inset 0 0 0 2px var(--app-primary, #0a5dc2); }
.ve-svg { width: 100%; height: 100%; display: block; cursor: grab; }
.ve-node { cursor: move; }
.ve-node.selected rect { filter: drop-shadow(0 2px 6px rgba(10, 93, 194, 0.35)); }
.ve-handle { fill: #fff; stroke: #0a5dc2; stroke-width: 2; cursor: crosshair; }
.ve-handle:hover { fill: #0a5dc2; }
.ve-empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; pointer-events: none; color: var(--app-muted, #999); font-size: 13px; padding: 20px; text-align: center; }
.ve-zoom-label { position: absolute; bottom: 6px; left: 8px; font-size: 11px; color: var(--app-muted, #767676); }
.ve-right { flex: 3; min-width: 220px; max-width: 320px; display: flex; flex-direction: column; border-left: 1px solid var(--app-border, #e0e0e6); background: var(--app-surface, #fff); }
.ve-palette, .ve-properties { padding: 10px; display: flex; flex-direction: column; gap: 6px; }
.ve-palette { border-bottom: 1px solid var(--app-border, #e0e0e6); }
.ve-section-title { font-size: 12px; text-transform: uppercase; color: var(--app-muted, #666); margin: 0 0 4px 0; font-weight: 600; letter-spacing: 0.4px; }
.ve-palette-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid var(--app-border, #e0e0e6); border-radius: 4px; cursor: grab; font-size: 12px; user-select: none; background: var(--app-surface, #fcfcfc); }
.ve-palette-item:active { cursor: grabbing; }
.ve-palette-item:hover { border-color: var(--app-primary, #0a5dc2); }
.ve-dot { width: 12px; height: 12px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.1); }
.ve-palette-label { color: var(--app-fg, #333); }
.ve-empty-prop { color: var(--app-muted, #888); font-size: 12px; font-style: italic; }
.ve-prop-form { display: flex; flex-direction: column; gap: 8px; }
.ve-field { display: flex; flex-direction: column; gap: 2px; font-size: 12px; }
.ve-field-label { color: var(--app-muted, #666); font-size: 11px; }
.ve-input { padding: 4px 6px; font-size: 12px; border: 1px solid var(--app-border, #ccc); border-radius: 4px; background: var(--app-surface, #fff); color: var(--app-fg, #333); }
.ve-input:disabled { background: var(--app-surface, #f0f0f0); color: var(--app-muted, #888); }
.ve-textarea { font-family: ui-monospace, SFMono-Regular, monospace; resize: vertical; min-height: 60px; }
.ve-prop-actions { display: flex; gap: 6px; margin-top: 4px; }
</style>
