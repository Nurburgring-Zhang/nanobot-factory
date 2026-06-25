<template>
  <div class="annotation-view" role="region" :aria-label="t('annotation.pageTitle')">
    <h2 class="sr-only">{{ t('annotation.pageTitle') }}</h2>
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">{{ t('annotation.pageTitle') }}</NText>
          <NText depth="3" style="margin-left: 8px">
            {{ t('annotation.pageSubtitle') }}
          </NText>
        </div>
        <NSpace>
          <NTag :type="openCount > 0 ? 'warning' : 'success'" :bordered="false">
            {{ t('annotation.pending') }} {{ openCount }}
          </NTag>
          <NTag :type="'info'" :bordered="false">{{ t('annotation.operatorsCount') }} {{ operators.length }}</NTag>
          <ActionButton type="primary" :loading="loading" @click="load">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ t('annotation.refresh') }}
          </ActionButton>
        </NSpace>
      </NSpace>
    </NCard>

    <!-- KPI tiles -->
    <NGrid :cols="4" :x-gap="12" :y-gap="12" style="margin-bottom: 12px">
      <NGi v-for="kpi in kpis" :key="kpi.key">
        <NCard :bordered="false" size="small" class="kpi-card" :aria-label="kpi.label">
          <NText depth="3" style="font-size: 11px">{{ kpi.label }}</NText>
          <div class="kpi-value">
            <NText strong style="font-size: 22px">{{ kpi.value }}</NText>
          </div>
          <NText depth="3" style="font-size: 11px">{{ kpi.hint }}</NText>
        </NCard>
      </NGi>
    </NGrid>

    <!-- Task table -->
    <NCard :bordered="false" class="table-card">
      <SearchBar
        v-model="keyword"
        :placeholder="t('annotation.searchPlaceholder')"
        @search="onSearch"
        @reset="onReset"
      >
        <template #extra>
          <NSelect
            v-model:value="statusFilter"
            :options="statusOptions"
            :placeholder="t('annotation.statusFilter')"
            clearable
            style="width: 160px"
            :aria-label="t('annotation.statusFilter')"
            @update:value="onSearch"
          />
        </template>
      </SearchBar>

      <DataTable
        :columns="columns"
        :data="taskRows"
        :loading="loading"
        :error="error"
        :total="total"
        v-model:page="page"
        v-model:page-size="pageSize"
        :row-key="(r: AnnotationTask) => r.id"
        @refresh="load"
      >
        <template #empty><NEmpty :description="t('annotation.emptyTasks')" /></template>
      </DataTable>
    </NCard>

    <!-- Operators + task drawer -->
    <div class="bottom-grid">
      <NCard :title="t('annotation.operatorsTitle')" :bordered="false">
        <NSpin :show="opsLoading">
          <NList>
            <NListItem v-for="op in operators" :key="op.id">
              <NSpace align="center" justify="space-between" style="width: 100%">
                <div>
                  <NText strong style="font-size: 13px">{{ op.name }}</NText>
                  <NText depth="3" style="font-size: 11px; margin-left: 8px">
                    {{ op.category || 'generic' }} · v{{ op.version || '1.0' }}
                  </NText>
                </div>
                <NTag :type="op.status === 'active' ? 'success' : 'default'" size="small">
                  {{ op.status || 'active' }}
                </NTag>
              </NSpace>
            </NListItem>
            <NListItem v-if="!opsLoading && operators.length === 0">
              <NEmpty :description="t('annotation.emptyOperators')" />
            </NListItem>
          </NList>
        </NSpin>
      </NCard>

      <NCard :title="t('annotation.taskDetailTitle')" :bordered="false">
        <NSpin :show="detailLoading">
          <div v-if="selectedTask" class="task-detail">
            <NDescriptions :column="2" size="small" bordered>
              <NDescriptionsItem :label="t('annotation.colId')">{{ selectedTask.id }}</NDescriptionsItem>
              <NDescriptionsItem :label="t('annotation.colName')">{{ selectedTask.name }}</NDescriptionsItem>
              <NDescriptionsItem :label="t('annotation.colType')">{{ selectedTask.type }}</NDescriptionsItem>
              <NDescriptionsItem :label="t('annotation.colStatus')">
                <NTag :type="statusBadge(selectedTask.status)">{{ selectedTask.status }}</NTag>
              </NDescriptionsItem>
              <NDescriptionsItem :label="t('annotation.colAssignee')">{{ selectedTask.assignee || '—' }}</NDescriptionsItem>
              <NDescriptionsItem :label="t('annotation.colAssets')">{{ selectedTask.asset_ids?.length ?? 0 }}</NDescriptionsItem>
              <NDescriptionsItem :label="t('annotation.colCreatedAt')" :span="2">{{ selectedTask.created_at || '—' }}</NDescriptionsItem>
              <NDescriptionsItem v-if="selectedTask.metadata" label="metadata" :span="2">
                <pre class="meta-pre">{{ JSON.stringify(selectedTask.metadata, null, 2) }}</pre>
              </NDescriptionsItem>
            </NDescriptions>
          </div>
          <NEmpty v-else :description="t('annotation.taskDetailEmpty')" />
        </NSpin>
      </NCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import {
  NCard, NSpace, NText, NTag, NIcon, NGrid, NGi, NList, NListItem, NSelect, NDescriptions, NDescriptionsItem,
  NSpin, NEmpty, useMessage, type DataTableColumns
} from 'naive-ui'
import { RefreshOutline } from '@vicons/ionicons5'
import { useI18n } from 'vue-i18n'
import SearchBar from '@/components/SearchBar.vue'
import DataTable from '@/components/DataTable.vue'
import ActionButton from '@/components/ActionButton.vue'
import { listAnnotations } from '@/api/annotation'

// Backend may return either { items, total } (paginated) or a raw List.
// We coerce to a single shape for the DataTable.
interface AnnotationTask {
  id: string | number
  name?: string
  type?: string
  status?: string
  assignee?: string
  asset_id?: string | number
  asset_ids?: Array<string | number>
  label?: string
  created_at?: string
  metadata?: Record<string, unknown>
}

interface OperatorItem {
  id: string
  name: string
  category?: string
  version?: string
  status?: string
}

const message = useMessage()
const { t } = useI18n()

const keyword = ref('')
const statusFilter = ref<string | null>(null)
const page = ref(1)
const pageSize = ref(20)
const taskRows = ref<AnnotationTask[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

const operators = ref<OperatorItem[]>([])
const opsLoading = ref(false)

const selectedTask = ref<AnnotationTask | null>(null)
const detailLoading = ref(false)

const statusOptions = [
  { label: t('annotation.statusPending'), value: 'pending' },
  { label: t('annotation.statusApproved'), value: 'approved' },
  { label: t('annotation.statusRejected'), value: 'rejected' },
  { label: t('annotation.statusCompleted'), value: 'completed' },
  { label: t('annotation.statusClosed'), value: 'closed' },
]

const statusBadge = (s?: string): 'default' | 'success' | 'error' | 'warning' | 'info' => {
  switch ((s || '').toLowerCase()) {
    case 'approved':
    case 'completed':
    case 'success':
      return 'success'
    case 'rejected':
    case 'failed':
    case 'error':
      return 'error'
    case 'pending':
    case 'open':
      return 'warning'
    case 'in_progress':
    case 'running':
      return 'info'
    default:
      return 'default'
  }
}

const openCount = computed(() => taskRows.value.filter((t) => (t.status || '').toLowerCase() === 'pending' || (t.status || '').toLowerCase() === 'open').length)

const kpis = computed(() => [
  { key: 'total', label: t('annotation.kpiTotal'), value: taskRows.value.length, hint: t('annotation.kpiTotalHint', { total: total.value }) },
  { key: 'pending', label: t('annotation.kpiPending'), value: openCount.value, hint: t('annotation.kpiPendingHint') },
  { key: 'operators', label: t('annotation.kpiOperators'), value: operators.value.length, hint: t('annotation.kpiOperatorsHint') },
  { key: 'page', label: t('annotation.kpiPage'), value: page.value, hint: t('annotation.kpiPageHint', { size: pageSize.value }) },
])

const columns: DataTableColumns<AnnotationTask> = [
  { title: () => t('annotation.colId'), key: 'id', width: 90 },
  { title: () => t('annotation.colName'), key: 'name', minWidth: 160 },
  {
    title: () => t('annotation.colType'), key: 'type', width: 140,
    render: (row) => h(NText, { depth: 3 }, { default: () => row.type || row.label || '—' }),
  },
  {
    title: () => t('annotation.colStatus'), key: 'status', width: 110,
    render: (row) => h(NTag, { type: statusBadge(row.status), size: 'small' }, { default: () => row.status || 'pending' }),
  },
  { title: () => t('annotation.colAssignee'), key: 'assignee', width: 120, render: (r) => r.assignee || '—' },
  { title: () => t('annotation.colAssets'), key: 'asset_ids', width: 80, render: (r) => String((r.asset_ids || (r.asset_id ? [r.asset_id] : [])).length) },
  { title: () => t('annotation.colCreatedAt'), key: 'created_at', width: 180 },
  {
    title: () => t('annotation.colActions'), key: 'actions', width: 100,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [h('a', { style: 'color:#2080f0;cursor:pointer', onClick: () => selectTask(row) }, t('annotation.actionDetail'))],
    }),
  },
]

async function load() {
  loading.value = true; error.value = null
  try {
    const res = await listAnnotations({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
    })
    // The annotation endpoint returns { items, total, page, page_size } via the http helper
    taskRows.value = (res.items || []) as AnnotationTask[]
    total.value = res.total ?? taskRows.value.length
  } catch (e) {
    error.value = (e as Error).message || '加载标注任务失败'
    message.error(error.value)
    taskRows.value = []; total.value = 0
  } finally { loading.value = false }
}

async function loadOperators() {
  opsLoading.value = true
  try {
    const res = await fetch('/api/v1/operators').then((r) => r.json())
    operators.value = Array.isArray(res) ? res : (res.operators || res.items || [])
  } catch (e) {
    // annotation_service returns raw List; failure here is non-fatal
    operators.value = []
  } finally { opsLoading.value = false }
}

function onSearch() { page.value = 1; load() }
function onReset() { keyword.value = ''; statusFilter.value = null; page.value = 1; load() }

async function selectTask(row: AnnotationTask) {
  detailLoading.value = true; selectedTask.value = row
  try {
    const res = await fetch(`/api/v1/tasks/${row.id}`)
    if (res.ok) selectedTask.value = await res.json()
  } catch {
    /* keep row-only view */
  } finally { detailLoading.value = false }
}

onMounted(() => { load(); loadOperators() })
</script>

<style scoped>
.annotation-view { padding: 16px; }
.header-card { margin-bottom: 12px; }
.kpi-card { min-height: 96px; }
.kpi-value { margin: 4px 0; }
.bottom-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}
.task-detail { padding: 4px 0; }
.meta-pre {
  font-size: 11px;
  background: #f7f8fa;
  padding: 8px;
  border-radius: 4px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 160px;
  overflow: auto;
}
</style>