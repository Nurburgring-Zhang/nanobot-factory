<template>
  <div class="page-root">
    <NCard :bordered="false" title="画布设计器">
      <template #header-extra>
        <NSpace align="center">
          <NInput v-model:value="canvasId" placeholder="画布 ID" style="width: 200px" />
          <ActionButton type="primary" :loading="loading" @click="loadCanvas">
            <template #icon><NIcon><CloudDownloadOutline /></NIcon></template>
            加载
          </ActionButton>
          <ActionButton type="success" :loading="saving" :disabled="!doc" @click="saveCanvas">
            <template #icon><NIcon><SaveOutline /></NIcon></template>
            保存
          </ActionButton>
          <ActionButton type="error" :disabled="!doc" @click="deleteCanvas">
            <template #icon><NIcon><TrashOutline /></NIcon></template>
            删除
          </ActionButton>
        </NSpace>
      </template>

      <NAlert v-if="error" type="error" style="margin-bottom: 12px">{{ error }}</NAlert>

      <div class="canvas-meta" v-if="doc">
        <NSpace>
          <NTag type="info">名称: {{ doc.name }}</NTag>
          <NTag type="success">节点: {{ doc.nodes.length }}</NTag>
          <NTag type="warning">边: {{ doc.edges.length }}</NTag>
          <NTag>v{{ doc.version }}</NTag>
        </NSpace>
      </div>

      <div class="canvas-frame">
        <VueFlow
          :nodes="nodes"
          :edges="edges"
          @nodes-change="(c: unknown) => { /* handled by watch below */ }"
          @edges-change="(c: unknown) => { /* handled by watch below */ }"
          :default-viewport="{ x: 0, y: 0, zoom: 1 }"
          :min-zoom="0.2"
          :max-zoom="2"
          fit-view-on-init
          class="vue-flow-canvas"
        >
          <Background pattern-color="#aaa" :gap="16" />
          <MiniMap />
          <Controls />
        </VueFlow>
      </div>

      <NEmpty v-if="!doc && !loading" description="请输入画布 ID 后点击加载" style="margin-top: 32px" />
    </NCard>
  </div>
</template>

<script setup lang="ts">
import { ref, shallowRef, watch } from 'vue'
import { NCard, NInput, NTag, NSpace, NAlert, NEmpty, NIcon, useMessage, useDialog } from 'naive-ui'
import { SaveOutline, CloudDownloadOutline, TrashOutline } from '@vicons/ionicons5'
import { VueFlow } from '@vue-flow/core'
import type { Node as VfNode, Edge as VfEdge } from '@vue-flow/core'
type Node = VfNode<Record<string, unknown>>
type Edge = VfEdge<Record<string, unknown>>
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
import ActionButton from '@/components/ActionButton.vue'
import { getCanvas, saveCanvas as apiSave, deleteCanvas as apiDelete, type CanvasDoc, type CanvasNode, type CanvasEdge } from '@/api/canvas'

const message = useMessage()
const dialog = useDialog()

const canvasId = ref<string>('')
const doc = shallowRef<CanvasDoc | null>(null)
const nodes = ref<Node[]>([])
const edges = ref<Edge[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)

watch(doc, (v) => {
  if (!v) { nodes.value = []; edges.value = []; return }
  nodes.value = v.nodes.map((n: CanvasNode) => ({
    id: String(n.id),
    type: 'default',
    position: n.position,
    data: { label: n.data?.label ?? n.type }
  }))
  edges.value = v.edges.map((e: CanvasEdge) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.label
  }))
})

async function loadCanvas() {
  if (!canvasId.value.trim()) { message.warning('请输入画布 ID'); return }
  loading.value = true; error.value = null
  try {
    doc.value = await getCanvas(canvasId.value.trim())
    message.success('画布加载成功')
  } catch (e) {
    error.value = (e as Error).message || '加载画布失败'
    doc.value = null
  } finally {
    loading.value = false
  }
}

async function saveCanvas() {
  if (!doc.value) return
  saving.value = true; error.value = null
  try {
    const currentNodes = nodes.value as unknown as Array<{ id: string; position: { x: number; y: number }; data?: { label?: unknown; kind?: unknown } }>
    const currentEdges = edges.value as unknown as Array<{ id: string; source: string; target: string; label?: unknown }>
    const payload: Partial<CanvasDoc> = {
      nodes: currentNodes.map<CanvasNode>((n) => ({
        id: n.id,
        type: String(n.data?.kind ?? 'default'),
        position: { x: n.position.x, y: n.position.y },
        data: { label: String(n.data?.label ?? n.id) }
      })),
      edges: currentEdges.map<CanvasEdge>((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: typeof e.label === 'string' ? e.label : undefined
      }))
    }
    const updated = await apiSave(doc.value.id, payload)
    doc.value = updated
    message.success(`已保存 v${updated.version}`)
  } catch (e) {
    error.value = (e as Error).message || '保存画布失败'
  } finally {
    saving.value = false
  }
}

function deleteCanvas() {
  if (!doc.value) return
  dialog.warning({
    title: '确认删除',
    content: `确认删除画布 ${doc.value.name} ?`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await apiDelete(doc.value!.id)
        message.success('已删除')
        doc.value = null
        canvasId.value = ''
      } catch (e) {
        message.error((e as Error).message || '删除失败')
      }
    }
  })
}
</script>

<style scoped>
.page-root { padding: 16px; }
.canvas-meta { margin-bottom: 12px; }
.canvas-frame {
  width: 100%;
  height: 560px;
  border: 1px solid var(--n-border-color);
  border-radius: 6px;
  overflow: hidden;
  background: #fafafa;
}
.vue-flow-canvas { width: 100%; height: 100%; }
</style>
