<template>
  <div class="workflows-view" role="region" :aria-label="t('workflows.pageTitle')">
    <h2 class="sr-only">{{ t('workflows.pageTitle') }}</h2>
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">{{ t('workflows.pageTitle') }}</NText>
          <NText depth="3" style="margin-left: 8px">
            {{ t('workflows.pageSubtitle', { name: workflowName, n: templates.length }) }}
          </NText>
        </div>
        <NSpace>
          <NTag :type="selectedTemplate ? 'success' : 'default'" :bordered="false">
            {{ selectedTemplate?.name || t('workflows.emptyTemplates') }}
          </NTag>
          <ActionButton secondary @click="openTemplatePicker">
            <template #icon><NIcon><AppsOutline /></NIcon></template>
            {{ t('workflows.pickTemplate') }}
          </ActionButton>
          <ActionButton type="primary" :loading="loading" @click="load">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ t('workflows.refresh') }}
          </ActionButton>
          <ActionButton type="primary" :loading="running" :disabled="!workflowName" @click="onRun">
            <template #icon><NIcon><PlayOutline /></NIcon></template>
            {{ t('workflows.run') }}
          </ActionButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NAlert v-if="error" type="error" :show-icon="true" closable style="margin-bottom: 12px" @close="error = null">
      {{ error }}
    </NAlert>

    <!-- KPI tiles -->
    <NGrid :cols="4" :x-gap="12" :y-gap="12" style="margin-bottom: 12px">
      <NGi v-for="k in kpis" :key="k.key">
        <NCard :bordered="false" size="small" class="kpi-card">
          <NText depth="3" style="font-size: 11px">{{ k.label }}</NText>
          <div class="kpi-value">
            <NText strong style="font-size: 22px">{{ k.value }}</NText>
          </div>
          <NText depth="3" style="font-size: 11px">{{ k.hint }}</NText>
        </NCard>
      </NGi>
    </NGrid>

    <!-- Vue Flow canvas -->
    <NCard :bordered="false" class="flow-card" :title="t('workflows.flowCanvasTitle')">
      <template #header-extra>
        <NSpace size="small" :aria-label="t('workflows.flowCanvasTitle')">
          <NTag :type="nodes.length > 0 ? 'info' : 'default'" size="small">{{ t('workflows.nodesLabel', { n: nodes.length }) }}</NTag>
          <NTag :type="edges.length > 0 ? 'info' : 'default'" size="small">{{ t('workflows.edgesLabel', { n: edges.length }) }}</NTag>
          <NTag :type="categories.length > 0 ? 'info' : 'default'" size="small">{{ t('workflows.categoriesLabel', { n: categories.length }) }}</NTag>
        </NSpace>
      </template>
      <div class="flow-host" :aria-label="t('workflows.flowCanvasTitle')" role="application">
        <VueFlow
          v-model:nodes="nodes"
          v-model:edges="edges"
          :default-viewport="{ zoom: 1, x: 0, y: 0 }"
          :fit-view-on-init="true"
        >
          <template #node-default="{ data }">
            <div class="node-default">{{ data.label }}</div>
          </template>
          <Background pattern-color="#767676" :gap="16" />
          <Controls />
          <MiniMap />
        </VueFlow>
      </div>
    </NCard>

    <!-- Bottom: templates + runs -->
    <div class="bottom-grid">
      <NCard :title="t('workflows.templatesTitle')" :bordered="false">
        <SearchBar
          v-model="templateKeyword"
          :placeholder="t('workflows.searchPlaceholder')"
          @search="applyTemplateFilter"
          @reset="onTemplateReset"
        >
          <template #extra>
            <NSelect
              v-model:value="categoryFilter"
              :options="categoryOptions"
              :placeholder="t('workflows.category')"
              clearable
              style="width: 140px"
              :aria-label="t('workflows.category')"
              @update:value="applyTemplateFilter"
            />
          </template>
        </SearchBar>

        <NList>
          <NListItem v-for="tpl in templateFiltered" :key="tpl.id">
            <NSpace align="center" justify="space-between" style="width: 100%">
              <div>
                <NText strong style="font-size: 13px">{{ tpl.name }}</NText>
                <NText depth="3" style="font-size: 11px; margin-left: 8px">
                  {{ tpl.category }} · {{ (tpl.tags || []).join(', ') }}
                </NText>
                <NText depth="3" style="font-size: 11px; display: block">
                  {{ tpl.description }}
                </NText>
              </div>
              <NSpace size="small">
                <NTag size="tiny" :bordered="false">{{ tpl.nodes?.length || 0 }} 节点</NTag>
                <ActionButton size="tiny" type="primary" @click="onPickTemplate(tpl)">
                  {{ t('workflows.pickButton') }}
                </ActionButton>
              </NSpace>
            </NSpace>
          </NListItem>
          <NListItem v-if="templateFiltered.length === 0">
            <NEmpty :description="t('workflows.emptyTemplates')" />
          </NListItem>
        </NList>
      </NCard>

      <NCard :title="t('workflows.runsTitle')" :bordered="false">
        <NSpin :show="runsLoading">
          <DataTable
            :columns="runColumns"
            :data="runs"
            :loading="runsLoading"
            :error="runsError"
            :total="runs.length"
            :page="1"
            :page-size="10"
            :row-key="(r: any) => r.run_id"
            @refresh="loadRuns"
          >
            <template #empty><NEmpty :description="t('workflows.emptyRuns')" /></template>
          </DataTable>
        </NSpin>
      </NCard>
    </div>

    <!-- Template picker modal (large) -->
    <NModal v-model:show="pickerVisible" preset="card" :title="t('workflows.pickerTitle')" style="width: 800px">
      <NList>
        <NListItem v-for="tpl in templates" :key="tpl.id">
          <NSpace align="center" justify="space-between" style="width: 100%">
            <div>
              <NText strong style="font-size: 13px">{{ tpl.name }}</NText>
              <NText depth="3" style="font-size: 11px; display: block">{{ tpl.description }}</NText>
              <NText depth="3" style="font-size: 11px">类别: {{ tpl.category }} · 标签: {{ (tpl.tags || []).join(', ') }}</NText>
            </div>
            <ActionButton type="primary" size="small" @click="onPickTemplate(tpl); pickerVisible = false">
              {{ t('workflows.pickButton') }}
            </ActionButton>
          </NSpace>
        </NListItem>
      </NList>
    </NModal>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import {
  NCard, NSpace, NText, NTag, NIcon, NGrid, NGi, NList, NListItem, NEmpty, NAlert,
  NModal, NSelect, useMessage, type DataTableColumns,
} from 'naive-ui'
import { RefreshOutline, AppsOutline, PlayOutline } from '@vicons/ionicons5'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import { useI18n } from 'vue-i18n'
import SearchBar from '@/components/SearchBar.vue'
import DataTable from '@/components/DataTable.vue'
import ActionButton from '@/components/ActionButton.vue'
import { http } from '@/api/http'

interface WorkflowTemplate {
  id: string
  name: string
  description: string
  category: string
  tags: string[]
  nodes: any[]
  edges: any[]
}

interface WorkflowListItem {
  id: string
  name: string
  description?: string
  status?: string
  node_count?: number
  tags?: string[]
  created_at?: string
}

const message = useMessage()
const { t } = useI18n()

const templates = ref<WorkflowTemplate[]>([])
const workflows = ref<WorkflowListItem[]>([])
const templateKeyword = ref('')
const categoryFilter = ref<string | null>(null)
const selectedTemplate = ref<WorkflowTemplate | null>(null)

const nodes = ref<any[]>([])
const edges = ref<any[]>([])

const workflowName = computed(() => selectedTemplate.value?.name || '')

const loading = ref(false)
const error = ref<string | null>(null)

const pickerVisible = ref(false)

const runs = ref<any[]>([])
const runsLoading = ref(false)
const runsError = ref<string | null>(null)
const running = ref(false)

const categories = computed(() => {
  const set = new Set<string>()
  templates.value.forEach((t) => t.category && set.add(t.category))
  return Array.from(set).sort()
})

const categoryOptions = computed(() => categories.value.map((c) => ({ label: c, value: c })))

const templateFiltered = computed(() => {
  const k = templateKeyword.value.toLowerCase().trim()
  const c = categoryFilter.value
  return templates.value.filter((t) => {
    if (c && t.category !== c) return false
    if (!k) return true
    return (
      t.name.toLowerCase().includes(k) ||
      (t.description || '').toLowerCase().includes(k) ||
      (t.tags || []).some((tag) => tag.toLowerCase().includes(k))
    )
  })
})

const kpis = computed(() => [
  { key: 'templates', label: '模板数', value: templates.value.length, hint: '全部类别' },
  { key: 'workflows', label: '工作流实例', value: workflows.value.length, hint: '已保存 DAG' },
  { key: 'nodes', label: '画布节点', value: nodes.value.length, hint: '当前选中' },
  { key: 'runs', label: '运行历史', value: runs.value.length, hint: '本页可见' },
])

const runColumns: DataTableColumns<any> = [
  { title: () => t('workflows.colRunId'), key: 'run_id', width: 180 },
  { title: () => t('workflows.colWorkflow'), key: 'workflow_id', width: 180 },
  {
    title: () => t('workflows.colStatus'), key: 'status', width: 110,
    render: (r) => h(NTag, { type: runStatusBadge(r.status), size: 'small' }, { default: () => r.status }),
  },
  { title: () => t('workflows.colTrigger'), key: 'trigger', width: 100 },
  { title: () => t('workflows.colStarted'), key: 'started_at', width: 180 },
  { title: () => t('workflows.colFinished'), key: 'finished_at', width: 180 },
  {
    title: () => t('workflows.colActions'), key: 'actions', width: 120,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h('a', {
          style: 'color:#2080f0;cursor:pointer',
          onClick: () => onCancelRun(row),
        }, t('workflows.cancelRun')),
      ],
    }),
  },
]

function runStatusBadge(s?: string): 'default' | 'success' | 'warning' | 'error' | 'info' {
  switch ((s || '').toLowerCase()) {
    case 'succeeded':
    case 'completed':
      return 'success'
    case 'running':
    case 'pending':
      return 'warning'
    case 'failed':
    case 'error':
      return 'error'
    default:
      return 'info'
  }
}

async function load() {
  loading.value = true; error.value = null
  try {
    const [tplRes, wfRes] = await Promise.allSettled([
      http.get<{ total: number; items: WorkflowTemplate[]; categories?: string[] }>('/api/v1/workflows/templates'),
      http.get<{ total: number; items: WorkflowListItem[] }>('/api/v1/workflows'),
    ])
    if (tplRes.status === 'fulfilled') {
      templates.value = tplRes.value.data.items || []
    } else {
      templates.value = FALLBACK_TEMPLATES
    }
    if (wfRes.status === 'fulfilled') {
      workflows.value = wfRes.value.data.items || []
    } else {
      workflows.value = []
    }
    if (templates.value.length > 0 && !selectedTemplate.value) {
      onPickTemplate(templates.value[0])
    }
    await loadRuns()
  } catch (e) {
    error.value = (e as Error).message || '加载工作流失败'
    templates.value = FALLBACK_TEMPLATES
    workflows.value = []
  } finally { loading.value = false }
}

function onPickTemplate(tpl: WorkflowTemplate) {
  selectedTemplate.value = tpl
  nodes.value = (tpl.nodes || []).map((n: any, i: number) => ({
    id: n.id || `n-${i}`,
    type: n.type || (i === 0 ? 'input' : i === (tpl.nodes.length - 1) ? 'output' : 'default'),
    position: n.position || { x: 60 + i * 180, y: 80 },
    data: { label: n.name || n.label || n.id || `节点 ${i + 1}` },
  }))
  edges.value = (tpl.edges || []).map((e: any, i: number) => ({
    id: e.id || `e-${i}`,
    source: e.source,
    target: e.target,
    animated: e.animated ?? false,
  }))
}

function openTemplatePicker() { pickerVisible.value = true }

function applyTemplateFilter() {
  /* reactive computed already handles it */
}
function onTemplateReset() { templateKeyword.value = ''; categoryFilter.value = null }

async function onRun() {
  if (!selectedTemplate.value) return
  running.value = true
  try {
    // First create / get the workflow id
    const wfResp = await http.post<{ id: string }>('/api/v1/workflows', {
      id: `wf-${selectedTemplate.value.id}-${Date.now()}`,
      name: selectedTemplate.value.name,
      description: selectedTemplate.value.description,
      tags: selectedTemplate.value.tags || [],
      nodes: (selectedTemplate.value.nodes || []).map((n: any) => ({
        id: n.id,
        operator: n.operator || n.id,
        params: n.params || {},
      })),
    })
    const wfId = wfResp.data?.id
    if (!wfId) throw new Error('workflow id missing')
    // Trigger run
    const runResp = await http.post<{ run_id: string }>(`/api/v1/workflows/${wfId}/run`, {
      inputs: {},
      trigger: 'manual',
      sync: false,
    })
    message.success(`已启动运行 ${runResp.data?.run_id}`)
    await loadRuns()
  } catch (e) {
    message.warning(`后端未确认 — ${(e as Error).message}`)
  } finally { running.value = false }
}

async function loadRuns() {
  runsLoading.value = true; runsError.value = null
  try {
    const res = await http.get<{ total: number; items: any[] }>('/api/v1/workflows/runs', { params: { limit: 50 } })
    runs.value = res.data.items || []
  } catch (e) {
    runsError.value = (e as Error).message || '加载运行历史失败'
    runs.value = []
  } finally { runsLoading.value = false }
}

async function onCancelRun(row: any) {
  try {
    await http.post(`/api/v1/workflows/runs/${row.run_id}/cancel`)
    message.success('已请求取消')
    await loadRuns()
  } catch (e) {
    message.error((e as Error).message || '取消失败')
  }
}

const FALLBACK_TEMPLATES: WorkflowTemplate[] = [
  {
    id: 'wf-fallback-pipeline',
    name: '标准数据流水线',
    description: '采集 → 清洗 → 标注 → 审核 → 入库',
    category: 'pipeline',
    tags: ['standard', 'pipeline'],
    nodes: [
      { id: '1', name: '源数据', type: 'input' },
      { id: '2', name: '清洗' },
      { id: '3', name: '标注' },
      { id: '4', name: '审核' },
      { id: '5', name: '入库', type: 'output' },
    ],
    edges: [
      { source: '1', target: '2', animated: true },
      { source: '2', target: '3' },
      { source: '3', target: '4' },
      { source: '4', target: '5' },
    ],
  },
]

onMounted(load)
</script>

<style scoped>
.workflows-view {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.header-card { margin-bottom: 0; }
.kpi-card { min-height: 96px; }
.kpi-value { margin: 4px 0; }
.flow-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 420px;
}
.flow-host {
  flex: 1;
  min-height: 420px;
  width: 100%;
}
.node-default {
  padding: 8px 12px;
  border-radius: 4px;
  background: #fff;
  border: 1px solid #2080f0;
  font-size: 13px;
  color: #2080f0;
}
.bottom-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
</style>