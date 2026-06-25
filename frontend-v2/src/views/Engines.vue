<template>
  <div class="engines-view" role="region" :aria-label="t('engines.pageTitle')">
    <h2 class="sr-only">{{ t('engines.pageTitle') }}</h2>
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">{{ t('engines.pageTitle') }}</NText>
          <NText depth="3" style="margin-left: 8px">
            {{ t('engines.pageSubtitle', { n: engines.length }) }}
          </NText>
        </div>
        <NSpace>
          <NTag :type="'success'" :bordered="false">{{ activeCount }} {{ t('engines.activeCount') }}</NTag>
          <NTag :type="'info'" :bordered="false">{{ totalTasks }} {{ t('engines.totalTasks') }}</NTag>
          <ActionButton type="primary" :loading="loading" @click="load">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ t('engines.refresh') }}
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
        <NCard :bordered="false" size="small" class="kpi-card" :aria-label="k.label">
          <NText depth="3" style="font-size: 11px">{{ k.label }}</NText>
          <div class="kpi-value">
            <NText strong style="font-size: 22px">{{ k.value }}</NText>
          </div>
          <NText depth="3" style="font-size: 11px">{{ k.hint }}</NText>
        </NCard>
      </NGi>
    </NGrid>

    <!-- Search + table -->
    <NCard :bordered="false" class="table-card">
      <SearchBar
        v-model="keyword"
        :placeholder="t('engines.searchPlaceholder')"
        @search="onSearch"
        @reset="onReset"
      >
        <template #extra>
          <NSelect
            v-model:value="modeFilter"
            :options="modeOptions"
            :placeholder="t('engines.modeFilter')"
            clearable
            style="width: 160px"
            :aria-label="t('engines.modeFilter')"
            @update:value="onSearch"
          />
        </template>
      </SearchBar>

      <DataTable
        :columns="columns"
        :data="filtered"
        :loading="loading"
        :error="error"
        :total="filtered.length"
        :page="1"
        :page-size="20"
        :row-key="(r: EngineType) => r.id"
        @refresh="load"
      >
        <template #empty><NEmpty :description="t('engines.empty')" /></template>
      </DataTable>
    </NCard>

    <!-- Engine detail + run panel -->
    <div class="bottom-grid">
      <NCard :title="t('engines.detailTitle')" :bordered="false">
        <NSpin :show="detailLoading">
          <NEmpty v-if="!selected" :description="t('engines.detailEmpty')" />
          <div v-else>
            <NDescriptions :column="2" size="small" bordered>
              <NDescriptionsItem :label="t('engines.colId')">{{ selected.id }}</NDescriptionsItem>
              <NDescriptionsItem :label="t('engines.colName')">{{ selected.name }}</NDescriptionsItem>
              <NDescriptionsItem :label="t('engines.colMode')">
                <NTag :type="modeBadge(selected.default_mode)" size="small">{{ selected.default_mode }}</NTag>
              </NDescriptionsItem>
              <NDescriptionsItem :label="t('engines.colPriority')">{{ selected.default_priority }}</NDescriptionsItem>
              <NDescriptionsItem :label="t('engines.colDownstream')">{{ selected.downstream_service || '—' }}</NDescriptionsItem>
              <NDescriptionsItem :label="t('engines.colCapabilities')">{{ (selected.capabilities || []).length }}</NDescriptionsItem>
              <NDescriptionsItem label="description" :span="2">{{ selected.description || '—' }}</NDescriptionsItem>
              <NDescriptionsItem v-if="selected.capabilities" :label="t('engines.colCapabilities')" :span="2">
                <NSpace size="small" :wrap-item="true">
                  <NTag v-for="(c, i) in selected.capabilities" :key="i" size="tiny" :bordered="false">
                    {{ c }}
                  </NTag>
                </NSpace>
              </NDescriptionsItem>
            </NDescriptions>

            <div class="run-form">
              <NText strong style="font-size: 13px">{{ t('engines.runSection') }}</NText>
              <NInput
                v-model:value="runPayload"
                type="textarea"
                :placeholder="t('engines.runPayloadPlaceholder')"
                :autosize="{ minRows: 3, maxRows: 8 }"
                :aria-label="t('engines.runPayloadPlaceholder')"
              />
              <NSpace>
                <NButton type="primary" :loading="running" @click="onRun">{{ t('engines.runSync') }}</NButton>
                <NButton :loading="runningAsync" @click="onRunAsync">{{ t('engines.runAsync') }}</NButton>
                <NButton tertiary :disabled="!lastTaskId" @click="onCancel">{{ t('engines.cancelLast') }}</NButton>
              </NSpace>
            </div>
          </div>
        </NSpin>
      </NCard>

      <NCard :title="t('engines.resultTitle')" :bordered="false">
        <NSpin :show="resultLoading">
          <NEmpty v-if="!lastResult" :description="t('engines.resultEmpty')" />
          <pre v-else class="result-pre" role="region" :aria-label="t('engines.resultTitle')">{{ lastResultText }}</pre>
        </NSpin>
      </NCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import {
  NCard, NSpace, NText, NTag, NIcon, NGrid, NGi, NDescriptions, NDescriptionsItem,
  NSpin, NEmpty, NAlert, NSelect, NInput, NButton, useMessage, type DataTableColumns
} from 'naive-ui'
import { RefreshOutline } from '@vicons/ionicons5'
import { useI18n } from 'vue-i18n'
import SearchBar from '@/components/SearchBar.vue'
import DataTable from '@/components/DataTable.vue'
import ActionButton from '@/components/ActionButton.vue'
import {
  listEngines, listEngineTypes, runEngine, cancelEngineTask,
  getEngineTask, type EngineType,
} from '@/api/engines'
import { listAgentTasks } from '@/api/tasks'

const message = useMessage()
const { t } = useI18n()

const engines = ref<EngineType[]>([])
const typeSlugs = ref<string[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const keyword = ref('')
const modeFilter = ref<string | null>(null)
const filtered = ref<EngineType[]>([])
const totalTasks = ref(0)

const selected = ref<EngineType | null>(null)
const detailLoading = ref(false)

const runPayload = ref('{}')
const running = ref(false)
const runningAsync = ref(false)
const lastTaskId = ref<string | null>(null)
const lastResult = ref<any>(null)
const resultLoading = ref(false)

const modeOptions = [
  { label: t('engines.modeFullAuto'), value: 'full_auto' },
  { label: t('engines.modeSemiAuto'), value: 'semi_auto' },
  { label: t('engines.modeManual'), value: 'manual' },
]

const activeCount = computed(() => engines.value.length)

const kpis = computed(() => [
  { key: 'total', label: '引擎总数', value: engines.value.length, hint: '注册在 AGENT_REGISTRY' },
  { key: 'types', label: '类型枚举', value: typeSlugs.value.length, hint: '用于下拉选择' },
  { key: 'tasks', label: '关联任务', value: totalTasks.value, hint: 'agent_tasks 表内记录' },
  { key: 'selected', label: '当前选中', value: selected.value?.id || '—', hint: selected.value?.default_mode || '' },
])

function modeBadge(m?: string): 'success' | 'warning' | 'info' | 'default' {
  switch (m) {
    case 'full_auto': return 'success'
    case 'semi_auto': return 'warning'
    case 'manual': return 'info'
    default: return 'default'
  }
}

const columns: DataTableColumns<EngineType> = [
  { title: () => t('engines.colId'), key: 'id', width: 200, render: (r) => h('code', { style: 'font-size:11px' }, r.id) },
  { title: () => t('engines.colName'), key: 'name', minWidth: 160 },
  {
    title: () => t('engines.colMode'), key: 'default_mode', width: 110,
    render: (row) => h(NTag, { type: modeBadge(row.default_mode), size: 'small' }, { default: () => row.default_mode }),
  },
  { title: () => t('engines.colPriority'), key: 'default_priority', width: 80 },
  { title: () => t('engines.colDownstream'), key: 'downstream_service', width: 160 },
  { title: () => t('engines.colCapabilities'), key: 'capabilities', minWidth: 160, render: (r) => (r.capabilities || []).slice(0, 3).join(', ') + ((r.capabilities?.length ?? 0) > 3 ? '…' : '') },
  {
    title: () => t('engines.colActions'), key: 'actions', width: 120,
    render: (row) => h('a', { style: 'color:#2080f0;cursor:pointer', onClick: () => selectEngine(row) }, t('engines.actionDetail')),
  },
]

async function load() {
  loading.value = true; error.value = null
  try {
    const [summary, types, tasks] = await Promise.allSettled([
      listEngines(),
      listEngineTypes(),
      listAgentTasks({ limit: 1 }),
    ])
    if (summary.status === 'fulfilled') engines.value = summary.value.agents || []
    if (types.status === 'fulfilled') typeSlugs.value = types.value.types || []
    if (tasks.status === 'fulfilled') totalTasks.value = tasks.value.count ?? 0
    applyFilter()
  } catch (e) {
    error.value = (e as Error).message || '加载引擎列表失败'
    message.error(error.value)
    engines.value = []; typeSlugs.value = []
  } finally { loading.value = false }
}

function applyFilter() {
  const k = keyword.value.toLowerCase().trim()
  const m = modeFilter.value
  filtered.value = engines.value.filter((e) => {
    if (m && e.default_mode !== m) return false
    if (!k) return true
    return (
      e.id.toLowerCase().includes(k) ||
      (e.name || '').toLowerCase().includes(k) ||
      (e.capabilities || []).some((c) => c.toLowerCase().includes(k))
    )
  })
}

function onSearch() { applyFilter() }
function onReset() { keyword.value = ''; modeFilter.value = null; applyFilter() }

function selectEngine(row: EngineType) {
  detailLoading.value = true; selected.value = row; lastResult.value = null
  try {
    // selected row already has summary data — no detail fetch needed.
  } finally { detailLoading.value = false }
}

async function onRun() {
  if (!selected.value) { message.warning('请先选择引擎'); return }
  running.value = true
  try {
    const payload = parsePayload()
    const res = await runEngine(selected.value.id, { payload, mode: selected.value.default_mode })
    lastTaskId.value = res.task?.task_id ?? null
    lastResult.value = res
    message.success('同步运行完成')
  } catch (e) {
    message.error((e as Error).message || '运行失败')
    lastResult.value = { error: (e as Error).message }
  } finally { running.value = false }
}

async function onRunAsync() {
  if (!selected.value) { message.warning('请先选择引擎'); return }
  runningAsync.value = true
  try {
    const payload = parsePayload()
    const res = await runEngine(selected.value.id, { payload, mode: selected.value.default_mode })
    lastTaskId.value = res.task?.task_id ?? null
    message.success(`已提交任务 ${lastTaskId.value}`)
  } catch (e) {
    message.error((e as Error).message || '提交失败')
  } finally { runningAsync.value = false }
}

async function onCancel() {
  if (!lastTaskId.value) return
  try {
    await cancelEngineTask(lastTaskId.value)
    message.success('已请求取消')
  } catch (e) {
    message.error((e as Error).message || '取消失败')
  }
}

function parsePayload(): Record<string, unknown> {
  try {
    const v = JSON.parse(runPayload.value || '{}')
    if (typeof v !== 'object' || v === null) return {}
    return v as Record<string, unknown>
  } catch {
    message.warning('payload 不是合法 JSON，已忽略')
    return {}
  }
}

const lastResultText = computed(() => lastResult.value ? JSON.stringify(lastResult.value, null, 2) : '')

onMounted(load)
</script>

<style scoped>
.engines-view { padding: 16px; }
.header-card { margin-bottom: 12px; }
.kpi-card { min-height: 100px; }
.kpi-value { margin: 4px 0; }
.bottom-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}
.run-form {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.result-pre {
  font-size: 11px;
  background: #f7f8fa;
  padding: 12px;
  border-radius: 4px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 320px;
  overflow: auto;
}
</style>