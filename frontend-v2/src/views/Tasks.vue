<template>
  <div class="tasks-view">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">任务队列</NText>
          <NText depth="3" style="margin-left: 8px">
            标注任务 · Agent 任务 · 工作流运行 — 统一视图
          </NText>
        </div>
        <NSpace>
          <NTag :type="totalActive > 0 ? 'warning' : 'success'" :bordered="false">
            进行中 {{ totalActive }}
          </NTag>
          <NTag :type="'error'" :bordered="false">
            失败 {{ totalFailed }}
          </NTag>
          <ActionButton type="primary" :loading="loading" @click="load">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            刷新
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

    <!-- Tabs -->
    <NCard :bordered="false">
      <NTabs v-model:value="activeTab" type="line" animated>
        <NTabPane :name="'all'" tab="全部">
          <DataTable
            :columns="columns"
            :data="mergedRows"
            :loading="loading"
            :error="error"
            :total="mergedRows.length"
            :page="1"
            :page-size="20"
            :row-key="(r: UnifiedTask) => `${r.source}-${r.id}`"
            @refresh="load"
          >
            <template #empty><NEmpty description="暂无任务" /></template>
          </DataTable>
        </NTabPane>

        <NTabPane :name="'annotation'" tab="标注任务">
          <DataTable
            :columns="columns"
            :data="annotationRows"
            :loading="loading"
            :error="error"
            :total="annotationRows.length"
            :page="1"
            :page-size="20"
            :row-key="(r: UnifiedTask) => `annotation-${r.id}`"
            @refresh="load"
          >
            <template #empty><NEmpty description="暂无标注任务" /></template>
          </DataTable>
        </NTabPane>

        <NTabPane :name="'agent'" tab="Agent 任务">
          <DataTable
            :columns="columns"
            :data="agentRows"
            :loading="loading"
            :error="error"
            :total="agentRows.length"
            :page="1"
            :page-size="20"
            :row-key="(r: UnifiedTask) => `agent-${r.id}`"
            @refresh="load"
          >
            <template #empty><NEmpty description="暂无 Agent 任务" /></template>
          </DataTable>
        </NTabPane>

        <NTabPane :name="'workflow'" tab="工作流运行">
          <DataTable
            :columns="columns"
            :data="workflowRows"
            :loading="loading"
            :error="error"
            :total="workflowRows.length"
            :page="1"
            :page-size="20"
            :row-key="(r: UnifiedTask) => `workflow-${r.id}`"
            @refresh="load"
          >
            <template #empty><NEmpty description="暂无工作流运行" /></template>
          </DataTable>
        </NTabPane>
      </NTabs>
    </NCard>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import {
  NCard, NSpace, NText, NTag, NIcon, NTabs, NTabPane, NGrid, NGi, NEmpty, NAlert, NButton,
  useMessage, type DataTableColumns
} from 'naive-ui'
import { RefreshOutline } from '@vicons/ionicons5'
import DataTable from '@/components/DataTable.vue'
import ActionButton from '@/components/ActionButton.vue'
import {
  listAnnotationTasks, listAgentTasks, listWorkflowRuns, getAgentTaskStats,
  cancelAgentTask, retryAgentTask, cancelWorkflowRun,
  normalizeStatus, type UnifiedTask,
} from '@/api/tasks'

const message = useMessage()

const loading = ref(false)
const error = ref<string | null>(null)

const annotationRows = ref<UnifiedTask[]>([])
const agentRows = ref<UnifiedTask[]>([])
const workflowRows = ref<UnifiedTask[]>([])
const stats = ref<Record<string, number>>({})

const activeTab = ref<'all' | 'annotation' | 'agent' | 'workflow'>('all')

const mergedRows = computed<UnifiedTask[]>(() => {
  return [...annotationRows.value, ...agentRows.value, ...workflowRows.value]
    .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
})

const totalActive = computed(() => mergedRows.value.filter((t) => ['pending', 'running'].includes(t.status)).length)
const totalFailed = computed(() => mergedRows.value.filter((t) => t.status === 'failed').length)

const kpis = computed(() => [
  { key: 'total', label: '合并任务数', value: mergedRows.value.length, hint: '全部来源合计' },
  { key: 'active', label: '进行中', value: totalActive.value, hint: 'pending + running' },
  { key: 'failed', label: '失败', value: totalFailed.value, hint: '需要重试 / 排查' },
  { key: 'agent_stats', label: 'Agent 任务统计', value: Object.values(stats.value).reduce((s, n) => s + n, 0), hint: `${Object.keys(stats.value).length} 个状态` },
])

function statusBadge(s: string): 'default' | 'success' | 'error' | 'warning' | 'info' {
  switch (s) {
    case 'completed':
    case 'succeeded':
      return 'success'
    case 'failed':
    case 'error':
      return 'error'
    case 'pending':
    case 'open':
      return 'warning'
    case 'running':
    case 'in_progress':
      return 'info'
    default:
      return 'default'
  }
}

function sourceBadge(s: string): 'default' | 'info' | 'success' | 'warning' {
  switch (s) {
    case 'annotation': return 'info'
    case 'agent': return 'success'
    case 'workflow': return 'warning'
    default: return 'default'
  }
}

const columns: DataTableColumns<UnifiedTask> = [
  {
    title: '来源', key: 'source', width: 100,
    render: (r) => h(NTag, { type: sourceBadge(r.source), size: 'small' }, { default: () => r.source }),
  },
  { title: 'ID', key: 'id', width: 200 },
  { title: '名称 / 类型', key: 'type', minWidth: 200 },
  {
    title: '状态', key: 'status', width: 110,
    render: (r) => h(NTag, { type: statusBadge(r.status), size: 'small' }, { default: () => r.status }),
  },
  { title: '负责人', key: 'owner', width: 140 },
  { title: '创建时间', key: 'created_at', width: 180 },
  { title: '结束时间', key: 'finished_at', width: 180 },
  {
    title: '操作', key: 'actions', width: 200,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => actionsFor(row),
    }),
  },
]

function actionsFor(row: UnifiedTask) {
  const acts: any[] = []
  if (row.source === 'agent' && ['running', 'pending'].includes(row.status)) {
    acts.push(h(NButton, {
      size: 'tiny', type: 'warning', ghost: true,
      onClick: () => onCancelAgent(row),
    }, { default: () => '取消' }))
    if (row.status === 'failed') {
      acts.push(h(NButton, {
        size: 'tiny', type: 'primary', ghost: true,
        onClick: () => onRetryAgent(row),
      }, { default: () => '重试' }))
    }
  }
  if (row.source === 'workflow' && ['running', 'pending'].includes(row.status)) {
    acts.push(h(NButton, {
      size: 'tiny', type: 'warning', ghost: true,
      onClick: () => onCancelWorkflow(row),
    }, { default: () => '取消' }))
  }
  if (acts.length === 0) {
    acts.push(h(NText, { depth: 3 }, { default: () => '—' }))
  }
  return acts
}

async function load() {
  loading.value = true; error.value = null
  try {
    await Promise.allSettled([loadAnnotation(), loadAgent(), loadWorkflow(), loadStats()])
  } catch (e) {
    error.value = (e as Error).message || '加载任务失败'
  } finally { loading.value = false }
}

async function loadAnnotation() {
  try {
    const items = await listAnnotationTasks({ limit: 100 })
    annotationRows.value = items.map((t) => ({
      source: 'annotation',
      id: String(t.id),
      name: t.name,
      type: t.type,
      status: normalizeStatus(t.status),
      owner: t.assignee,
      created_at: t.created_at,
      raw: t,
    }))
  } catch {
    annotationRows.value = []
  }
}

async function loadAgent() {
  try {
    const res = await listAgentTasks({ limit: 100 })
    agentRows.value = (res.tasks || []).map((t) => ({
      source: 'agent',
      id: String(t.task_id),
      name: t.agent_type,
      type: t.mode,
      status: normalizeStatus(t.status),
      owner: t.submitted_by,
      created_at: t.created_at || '',
      finished_at: t.finished_at,
      raw: t,
    }))
  } catch {
    agentRows.value = []
  }
}

async function loadWorkflow() {
  try {
    const res = await listWorkflowRuns({ limit: 100 })
    workflowRows.value = (res.items || []).map((r) => ({
      source: 'workflow',
      id: String(r.run_id),
      name: r.workflow_id,
      type: r.trigger,
      status: normalizeStatus(r.status),
      owner: '—',
      created_at: r.started_at || '',
      finished_at: r.finished_at,
      raw: r,
    }))
  } catch {
    workflowRows.value = []
  }
}

async function loadStats() {
  try { stats.value = await getAgentTaskStats() } catch { stats.value = {} }
}

async function onCancelAgent(row: UnifiedTask) {
  try {
    await cancelAgentTask(row.id)
    message.success(`已取消 Agent 任务 ${row.id}`)
    await load()
  } catch (e) {
    message.error((e as Error).message || '取消失败')
  }
}
async function onRetryAgent(row: UnifiedTask) {
  try {
    await retryAgentTask(row.id)
    message.success(`已重试 Agent 任务 ${row.id}`)
    await load()
  } catch (e) {
    message.error((e as Error).message || '重试失败')
  }
}
async function onCancelWorkflow(row: UnifiedTask) {
  try {
    await cancelWorkflowRun(row.id)
    message.success(`已取消运行 ${row.id}`)
    await load()
  } catch (e) {
    message.error((e as Error).message || '取消失败')
  }
}

onMounted(load)
</script>

<style scoped>
.tasks-view { padding: 16px; }
.header-card { margin-bottom: 12px; }
.kpi-card { min-height: 96px; }
.kpi-value { margin: 4px 0; }
</style>