<template>
  <div class="knowledge-graph">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">Knowledge Graph (claude-obsidian 借鉴)</NText>
          <NText depth="3" style="margin-left: 8px">
            节点: page / tag / note · 边: link / tag / backlink · 缩放 / 拖拽 / 搜索
          </NText>
        </div>
        <NSpace>
          <NInput v-model:value="searchKw" placeholder="搜索节点..." size="small" style="width: 200px" @update:value="onSearch" />
          <NButton size="small" tertiary @click="zoomIn">+</NButton>
          <NButton size="small" tertiary @click="zoomOut">-</NButton>
          <NButton size="small" tertiary @click="resetView">重置</NButton>
          <NButton size="small" type="primary" @click="reload" :loading="loading">刷新图谱</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <div class="graph-grid">
      <NCard :bordered="false" class="canvas-card">
        <div ref="graphEl" class="graph-canvas" @mousedown="startPan" @mousemove="onPan" @mouseup="endPan" @wheel.prevent="onWheel">
          <svg :width="size.w" :height="size.h">
            <g :transform="`translate(${pan.x},${pan.y}) scale(${scale})`">
              <g v-for="e in filteredEdges" :key="`${e.source}-${e.target}`">
                <line
                  :x1="nodePos[e.source]?.x || 0"
                  :y1="nodePos[e.source]?.y || 0"
                  :x2="nodePos[e.target]?.x || 0"
                  :y2="nodePos[e.target]?.y || 0"
                  :stroke="edgeColor(e.kind)"
                  :stroke-width="Math.max(0.5, Math.min(3, e.weight))"
                  stroke-opacity="0.5"
                />
              </g>
              <g
                v-for="n in filteredNodes"
                :key="n.id"
                :transform="`translate(${nodePos[n.id]?.x || 0},${nodePos[n.id]?.y || 0})`"
                @click="onNodeClick(n)"
                @mouseenter="hovered = n.id"
                @mouseleave="hovered = ''"
                style="cursor: pointer"
              >
                <circle :r="Math.max(6, n.size)" :fill="nodeColor(n.group)" :opacity="hovered && hovered !== n.id ? 0.4 : 1" />
                <text :y="n.size + 12" text-anchor="middle" font-size="10" fill="#333">{{ truncate(n.title, 16) }}</text>
              </g>
            </g>
          </svg>
          <NEmpty v-if="!filteredNodes.length" description="无数据, 请刷新" />
        </div>
        <div class="legend">
          <NSpace size="small">
            <NTag :bordered="false" type="info" size="small">page</NTag>
            <NTag :bordered="false" type="success" size="small">tag</NTag>
            <NTag :bordered="false" type="warning" size="small">note</NTag>
            <NText depth="3" style="font-size: 11px">link —  /  tag ·· /  backlink ⇠</NText>
          </NSpace>
        </div>
      </NCard>

      <NCard :bordered="false" class="detail-card" :title="selected ? selected.title : '详情'">
        <NEmpty v-if="!selected" description="点击节点查看详情" />
        <div v-else>
          <NSpace align="center" style="margin-bottom: 8px">
            <NTag :type="selected.group === 'page' ? 'info' : selected.group === 'tag' ? 'success' : 'warning'" size="small">
              {{ selected.group }}
            </NTag>
            <NTag size="small" :bordered="false">度 {{ selected.degree }}</NTag>
          </NSpace>
          <NText v-if="selected.preview" style="font-size: 12px; line-height: 1.5">{{ selected.preview }}...</NText>
          <NDivider style="margin: 12px 0" title-placement="left">标签</NDivider>
          <NSpace>
            <NTag v-for="t in selected.tags" :key="t" size="small" :bordered="false">{{ t }}</NTag>
          </NSpace>
          <NDivider style="margin: 12px 0" title-placement="left">反向链接</NDivider>
          <NEmpty v-if="!backlinks.length" description="无" size="small" />
          <NList>
            <NListItem v-for="b in backlinks" :key="b.slug" @click="gotoPage(b.slug)">
              <NText>{{ b.title }}</NText>
            </NListItem>
          </NList>
          <NDivider style="margin: 12px 0" title-placement="left">正向链接</NDivider>
          <NEmpty v-if="!outgoing.length" description="无" size="small" />
          <NList>
            <NListItem v-for="o in outgoing" :key="o.slug" @click="gotoPage(o.slug)">
              <NText>{{ o.title }}</NText>
            </NListItem>
          </NList>
        </div>
      </NCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NCard, NSpace, NText, NInput, NButton, NTag, NEmpty, NDivider, NList, NListItem, useMessage
} from 'naive-ui'
import { obsidianApi, type GraphNode, type GraphEdge, type GraphPayload, type WikiPage } from '@/api/obsidian'

const router = useRouter()
const message = useMessage()
const graphEl = ref<HTMLElement | null>(null)
const size = ref({ w: 1000, h: 600 })
const scale = ref(1)
const pan = ref({ x: 0, y: 0 })
const panning = ref<{ x: number; y: number } | null>(null)
const hovered = ref('')
const searchKw = ref('')
const loading = ref(false)

const data = ref<GraphPayload>({ nodes: [], edges: [], stats: { pages: 0, tags: 0, links: 0, isolated: 0 } })
const selected = ref<GraphNode | null>(null)
const backlinks = ref<WikiPage[]>([])
const outgoing = ref<WikiPage[]>([])

const filteredNodes = computed(() => {
  if (!searchKw.value) return data.value.nodes
  const kw = searchKw.value.toLowerCase()
  return data.value.nodes.filter(n => n.title.toLowerCase().includes(kw) || n.tags.some(t => t.toLowerCase().includes(kw)))
})

const filteredEdges = computed(() => {
  const ids = new Set(filteredNodes.value.map(n => n.id))
  return data.value.edges.filter(e => ids.has(e.source) && ids.has(e.target))
})

// Position nodes on a circle (fruchterman-reingolf-lite) with seed for stability
const nodePos = computed(() => {
  const pos: Record<string, { x: number; y: number }> = {}
  const N = filteredNodes.value.length || 1
  const R = Math.min(size.value.w, size.value.h) * 0.4
  filteredNodes.value.forEach((n, i) => {
    const angle = (i / N) * 2 * Math.PI
    pos[n.id] = { x: size.value.w / 2 + R * Math.cos(angle), y: size.value.h / 2 + R * Math.sin(angle) }
  })
  return pos
})

function nodeColor(group: string) {
  return group === 'tag' ? '#18a058' : group === 'note' ? '#f0a020' : '#2080f0'
}
function edgeColor(kind: string) {
  return kind === 'tag' ? '#18a058' : kind === 'backlink' ? '#f0a020' : '#2080f0'
}
function truncate(s: string, n: number) { return s.length > n ? s.slice(0, n) + '…' : s }

async function reload() {
  loading.value = true
  try {
    data.value = await obsidianApi.graph()
    message.success(`图谱加载: ${data.value.stats.pages} page / ${data.value.stats.tags} tag / ${data.value.stats.links} link`)
  } catch (e: any) {
    data.value = localFallback()
    message.warning(`后端图谱暂不可用, 展示本地示例: ${e?.message || ''}`)
  } finally {
    loading.value = false
  }
}

function onSearch() {
  // filtering handled via computed
}

function zoomIn() { scale.value = Math.min(3, scale.value * 1.2) }
function zoomOut() { scale.value = Math.max(0.3, scale.value / 1.2) }
function resetView() { scale.value = 1; pan.value = { x: 0, y: 0 } }

function onWheel(e: WheelEvent) {
  if (e.deltaY < 0) zoomIn(); else zoomOut()
}

function startPan(e: MouseEvent) {
  if ((e.target as HTMLElement).closest('g[style*="cursor: pointer"]')) return
  panning.value = { x: e.clientX - pan.value.x, y: e.clientY - pan.value.y }
  window.addEventListener('mouseup', endPan)
}
function onPan(e: MouseEvent) {
  if (!panning.value) return
  pan.value = { x: e.clientX - panning.value.x, y: e.clientY - panning.value.y }
}
function endPan() { panning.value = null; window.removeEventListener('mouseup', endPan) }

async function onNodeClick(n: GraphNode) {
  selected.value = n
  if (n.group === 'page') {
    try {
      const page = await obsidianApi.getPage(n.id)
      backlinks.value = page.backlinks.map(slug => ({ slug, title: slug, id: slug, content_markdown: '', tags: [], outgoing_links: [], backlinks: [], created_at: '', updated_at: '', author: '', word_count: 0 }))
      outgoing.value = page.outgoing_links.map(slug => ({ slug, title: slug, id: slug, content_markdown: '', tags: [], outgoing_links: [], backlinks: [], created_at: '', updated_at: '', author: '', word_count: 0 }))
    } catch {
      backlinks.value = []
      outgoing.value = []
    }
  } else {
    backlinks.value = []
    outgoing.value = []
  }
}

function gotoPage(slug: string) {
  router.push({ name: 'obsidian-wiki-edit', params: { slug } })
}

onMounted(() => {
  if (graphEl.value) {
    size.value = { w: graphEl.value.clientWidth, h: graphEl.value.clientHeight }
  }
  reload()
})

// Local fallback graph (10-page demo)
function localFallback(): GraphPayload {
  const nodes: GraphNode[] = []
  const edges: GraphEdge[] = []
  const pages = ['首页', '产品手册', 'API 文档', '部署指南', '最佳实践', '故障排查', '案例研究', '更新日志', '路线图', '社区贡献']
  const tags = ['product', 'docs', 'ops', 'community']
  pages.forEach((p, i) => nodes.push({ id: p, title: p, group: 'page', degree: 2, size: 12, tags: [tags[i % tags.length]], preview: `${p} 的预览内容...` }))
  tags.forEach(t => nodes.push({ id: t, title: `#${t}`, group: 'tag', degree: pages.length / tags.length, size: 8, tags: [] }))
  // link pages in a chain
  for (let i = 0; i < pages.length - 1; i++) {
    edges.push({ source: pages[i], target: pages[i + 1], kind: 'link', weight: 2 })
  }
  // tag pages
  pages.forEach((p, i) => edges.push({ source: p, target: tags[i % tags.length], kind: 'tag', weight: 1 }))
  return {
    nodes,
    edges,
    stats: { pages: pages.length, tags: tags.length, links: edges.length, isolated: 0 },
  }
}
</script>

<style scoped>
.knowledge-graph { padding: 0; }
.header-card { margin-bottom: 12px; }
.graph-grid {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 12px;
}
.graph-canvas {
  position: relative;
  width: 100%;
  height: 600px;
  background:
    radial-gradient(circle, #e0e0e6 1px, transparent 1px) 0 0 / 20px 20px,
    #fafafc;
  border-radius: 6px;
  overflow: hidden;
  cursor: grab;
}
.graph-canvas:active { cursor: grabbing; }
.detail-card { min-height: 600px; }
.legend { padding: 8px 12px; border-top: 1px solid #e0e0e6; }
</style>
