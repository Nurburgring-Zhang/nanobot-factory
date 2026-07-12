<template>
  <div class="internal-qc-view">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">{{ t('internalQC.t000') }} (Internal QC)</NText>
          <NText depth="3" style="margin-left: 8px">
            {{ t('internalQC.t001') }} / {{ t('internalQC.t002') }} / AQL / {{ t('internalQC.t003') }} — ISO 2859-1
          </NText>
        </div>
        <NSpace>
          <NTag :type="'success'" :bordered="false">{{ records.length }} {{ t('internalQC.t004') }}</NTag>
          <ActionButton type="primary" :loading="loading" @click="loadAll">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ t('common.refresh') }}
          </ActionButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NAlert v-if="error" type="error" :show-icon="true" closable style="margin-bottom: 12px" @close="error = null">
      {{ error }}
    </NAlert>

    <div class="main-grid">
      <!-- 左: {{ t('internalQC.t005') }} -->
      <NCard title="数据集" :bordered="false" class="left-pane">
        <NSpace vertical :size="8">
          <NInput v-model:value="datasetFilter" placeholder="搜索数据集 ID" clearable size="small" />
          <NButton block secondary size="small" @click="onAddDataset" :disabled="!newDatasetId.trim()">
            <template #icon><NIcon><AddOutline /></NIcon></template>
            {{ t('internalQC.t006') }}
          </NButton>
        </NSpace>
        <NDivider />
        <NSpin :show="loading && !datasets.length">
          <NEmpty v-if="!datasets.length" description="暂无数据集,请添加" />
          <NList v-else hoverable clickable>
            <NListItem
              v-for="ds in filteredDatasets"
              :key="ds.id"
              :class="{ active: selectedDataset === ds.id }"
              @click="selectedDataset = ds.id"
            >
              <NThing>
                <template #header>
                  <NSpace align="center" :size="6">
                    <NText strong>{{ ds.name }}</NText>
                    <NTag size="tiny" :type="ds.last_result === 'passed' ? 'success' : ds.last_result === 'failed' ? 'error' : 'default'">
                      {{ ds.last_result || t('internalQC.t007') }}
                    </NTag>
                  </NSpace>
                </template>
                <template #description>
                  <NText depth="3" style="font-size: 11px">
                    ID: {{ ds.id }} · {{ t('internalQC.t008') }} {{ ds.size }} {{ t('annotation.colAssets') }}
                  </NText>
                </template>
              </NThing>
            </NListItem>
          </NList>
        </NSpin>
      </NCard>

      <!-- 中: {{ t('agent.action') }} + {{ t('internalQC.t009') }} -->
      <NCard :bordered="false" class="center-pane">
        <template #header>
          <NSpace align="center" justify="space-between" style="width: 100%">
            <NText strong>{{ selectedDataset || t('internalQC.t010') }}</NText>
            <NSpace :size="6">
              <NTag size="small">{{ t('menu.tabSchema') }}: {{ runMode || '—' }}</NTag>
              <NTag size="small" :type="runProgress >= 100 ? 'success' : 'info'">
                {{ t('internalQC.t011') }} {{ runProgress }}%
              </NTag>
            </NSpace>
          </NSpace>
        </template>

        <NGrid :cols="4" :x-gap="8" :y-gap="8" style="margin-bottom: 12px">
          <NGi>
            <NButton block type="primary" :loading="running && runMode==='full'" @click="runModeClick('full')">
              <template #icon><NIcon><CheckmarkDoneOutline /></NIcon></template>
              {{ t('internalQC.t012') }}
            </NButton>
          </NGi>
          <NGi>
            <NSelect v-model:value="sampleRate" :options="sampleRateOpts" size="small" />
            <NButton block type="info" style="margin-top: 4px" :loading="running && runMode==='sample'" @click="runModeClick('sample')">
              <template #icon><NIcon><AnalyticsOutline /></NIcon></template>
              {{ t('internalQC.t013') }} {{ Math.round(sampleRate * 100) }}%
            </NButton>
          </NGi>
          <NGi>
            <NSelect v-model:value="aqlLevel" :options="aqlOpts" size="small" />
            <NButton block type="warning" style="margin-top: 4px" :loading="running && runMode==='aql'" @click="runModeClick('aql')">
              <template #icon><NIcon><StatsChartOutline /></NIcon></template>
              AQL {{ aqlLevel }}
            </NButton>
          </NGi>
          <NGi>
            <NInputNumber v-model:value="stratSampleSize" :min="10" :max="1000" size="small" />
            <NButton block type="success" style="margin-top: 4px" :loading="running && runMode==='stratified'" @click="runModeClick('stratified')">
              <template #icon><NIcon><LayersOutline /></NIcon></template>
              {{ t('internalQC.t014') }} {{ stratSampleSize }}
            </NButton>
          </NGi>
        </NGrid>

        <NProgress
          v-if="running"
          type="line"
          :percentage="runProgress"
          :indicator-placement="'inside'"
          processing
        />

        <NDivider />

        <template v-if="currentRecord">
          <NGrid :cols="4" :x-gap="12" :y-gap="12" class="kpi-row">
            <NGi>
              <NCard size="small" :bordered="false">
                <NText depth="3" style="font-size: 11px">{{ t('internalQC.t015') }}</NText>
                <div class="kpi-value">
                  <NTag :type="currentRecord.result === 'passed' ? 'success' : 'error'" size="large">
                    {{ currentRecord.result === 'passed' ? `✓ ${t('common.approve')}` : `✗ ${t('common.failed')}` }}
                  </NTag>
                </div>
              </NCard>
            </NGi>
            <NGi>
              <NCard size="small" :bordered="false">
                <NText depth="3" style="font-size: 11px">{{ t('internalQC.t016') }}</NText>
                <div class="kpi-value">
                  <NText strong style="font-size: 22px">{{ (currentStats?.defect_rate ?? 0).toFixed(2) }}%</NText>
                </div>
              </NCard>
            </NGi>
            <NGi>
              <NCard size="small" :bordered="false">
                <NText depth="3" style="font-size: 11px">{{ t('internalQC.t017') }}/{{ t('internalQC.t018') }}</NText>
                <div class="kpi-value">
                  <NText strong style="font-size: 18px">{{ currentRecord.sample_size }} / {{ currentRecord.total_assets }}</NText>
                </div>
              </NCard>
            </NGi>
            <NGi>
              <NCard size="small" :bordered="false">
                <NText depth="3" style="font-size: 11px">{{ t('internalQC.t019') }}</NText>
                <div class="kpi-value">
                  <NText strong style="font-size: 22px; color: #d03050">{{ currentRecord.issue_count }}</NText>
                </div>
              </NCard>
            </NGi>
          </NGrid>

          <NDivider style="margin: 12px 0" />

          <NGrid :cols="2" :x-gap="12" :y-gap="12">
            <NGi>
              <NText depth="3" style="font-size: 12px">{{ t('internalQC.t020') }}</NText>
              <div class="bar-chart">
                <div v-for="(v, k) in currentStats?.by_severity" :key="k" class="bar-row">
                  <NTag size="tiny" :type="severityType(k)" :bordered="false">{{ k }}</NTag>
                  <div class="bar-track">
                    <div class="bar-fill" :style="{ width: barWidth(v, currentRecord.issue_count), background: severityColor(k) }"></div>
                  </div>
                  <NText depth="3" style="min-width: 24px; text-align: right; font-size: 12px">{{ v }}</NText>
                </div>
              </div>
            </NGi>
            <NGi>
              <NText depth="3" style="font-size: 12px">{{ t('internalQC.t021') }}</NText>
              <div class="bar-chart">
                <div v-for="(v, k) in currentStats?.by_type" :key="k" class="bar-row">
                  <NTag size="tiny" :bordered="false">{{ k }}</NTag>
                  <div class="bar-track">
                    <div class="bar-fill" :style="{ width: barWidth(v, currentRecord.issue_count), background: '#0a5dc2' }"></div>
                  </div>
                  <NText depth="3" style="min-width: 24px; text-align: right; font-size: 12px">{{ v }}</NText>
                </div>
              </div>
            </NGi>
          </NGrid>

          <NSpace style="margin-top: 12px">
            <NButton size="small" @click="onExport('json')">{{ t('common.export') }} JSON</NButton>
            <NButton size="small" @click="onExport('csv')">{{ t('common.export') }} CSV</NButton>
            <NButton size="small" @click="onExport('pdf')">{{ t('common.export') }} PDF (HTML)</NButton>
            <NButton size="small" type="warning" @click="onRerun">{{ t('internalQC.t022') }}</NButton>
          </NSpace>
        </template>

        <NEmpty v-else-if="!running && !currentRecord" description="选择数据集并运行质检模式" />
      </NCard>

      <!-- 右: Issue {{ t('internalQC.t023') }} / {{ t('menu.contextHistory') }} -->
      <NCard title="Issue 列表" :bordered="false" class="right-pane">
        <NEmpty v-if="!currentRecord" description="暂无 Issue" />
        <template v-else>
          <NScrollbar style="max-height: 400px">
            <NList>
              <NListItem v-for="iss in (currentRecord.issues || []).slice(0, 50)" :key="iss.id">
                <NThing>
                  <template #header>
                    <NSpace :size="6">
                      <NTag size="tiny" :type="severityType(iss.severity)" :bordered="false">{{ iss.severity }}</NTag>
                      <NTag size="tiny" :bordered="false">{{ iss.type }}</NTag>
                      <NText depth="3" style="font-size: 11px">{{ iss.asset_id }}</NText>
                    </NSpace>
                  </template>
                  <template #description>
                    <NText style="font-size: 12px">{{ iss.description }}</NText>
                    <div v-if="iss.suggested_action" class="issue-action">
                      → {{ iss.suggested_action }}
                    </div>
                  </template>
                </NThing>
              </NListItem>
            </NList>
          </NScrollbar>
          <NDivider />
          <NText depth="3" style="font-size: 11px">{{ t('annotation.historyTitle') }} ({{ t('internalQC.t024') }})</NText>
          <NList>
            <NListItem v-for="r in historyRecords" :key="r.id" :class="{ active: currentRecord?.id === r.id }">
              <NThing @click="onSelectHistory(r)">
                <template #header>
                  <NSpace :size="6">
                    <NTag size="tiny" :bordered="false">{{ r.mode }}</NTag>
                    <NTag size="tiny" :type="r.result === 'passed' ? 'success' : 'error'" :bordered="false">{{ r.result }}</NTag>
                  </NSpace>
                </template>
                <template #description>
                  <NText depth="3" style="font-size: 11px">
                    {{ r.sample_size }}/{{ r.total_assets }} · {{ t('common.question') }} {{ r.issue_count }}
                  </NText>
                </template>
              </NThing>
            </NListItem>
          </NList>
        </template>
      </NCard>
    </div>
  </div>
</template>

<script setup lang="ts">import { useI18n } from 'vue-i18n'

const { t } = useI18n()

import { computed, onMounted, ref } from 'vue'
import {
  NCard, NSpace, NText, NTag, NIcon, NButton, NInput, NInputNumber,
  NSelect, NGrid, NGi, NAlert, NDivider, NEmpty, NList, NListItem, NThing,
  NProgress, NScrollbar, useMessage,
} from 'naive-ui'
import {
  RefreshOutline, AddOutline, CheckmarkDoneOutline, AnalyticsOutline,
  StatsChartOutline, LayersOutline,
} from '@vicons/ionicons5'
import ActionButton from '@/components/ActionButton.vue'
import {
  runFullCheck, runSampleCheck, runAQLCheck, runStratifiedCheck,
  listQCRecords, getQCStats, exportQCReport, rerunQC,
  type QCRecord, type QCStats, type Severity,
} from '@/api/qc'

const message = useMessage()

const records = ref<QCRecord[]>([])
const selectedDataset = ref<string>('')
const datasetFilter = ref('')
const newDatasetId = ref('')
const datasets = ref<Array<{ id: string; name: string; size: number; last_result?: string }>>([])
const loading = ref(false)
const running = ref(false)
const runMode = ref<'full' | 'sample' | 'aql' | 'stratified' | ''>('')
const runProgress = ref(0)
const error = ref<string | null>(null)

const sampleRate = ref(0.05)
const aqlLevel = ref(1.0)
const stratSampleSize = ref(50)

const sampleRateOpts = [
  { label: '5%', value: 0.05 },
  { label: '10%', value: 0.10 },
  { label: '20%', value: 0.20 },
]
const aqlOpts = [
  { label: 'AQL 0.65', value: 0.65 },
  { label: 'AQL 1.0', value: 1.0 },
  { label: 'AQL 2.5', value: 2.5 },
  { label: 'AQL 4.0', value: 4.0 },
]

const currentRecord = ref<QCRecord | null>(null)
const currentStats = ref<QCStats | null>(null)
const historyRecords = computed(() =>
  records.value.filter((r) => r.dataset_id === selectedDataset.value)
)

const filteredDatasets = computed(() =>
  datasets.value.filter((d) => !datasetFilter.value || d.id.toLowerCase().includes(datasetFilter.value.toLowerCase()))
)

function onAddDataset() {
  const id = newDatasetId.value.trim()
  if (!id || datasets.value.find((d) => d.id === id)) return
  datasets.value.push({
    id, name: id,
    size: (id.charCodeAt(0) * 17 + 100) % 1000 + 100,
    last_result: t("internalQC.t025"),
  })
  selectedDataset.value = id
  newDatasetId.value = ''
  loadHistory()
}

function severityType(s: string): 'success' | 'warning' | 'error' | 'default' {
  if (s === 'critical') return 'error'
  if (s === 'major') return 'warning'
  if (s === 'minor') return 'default'
  return 'success'
}

function severityColor(s: string): string {
  return s === 'critical' ? '#d03050' : s === 'major' ? '#d08000' : '#909090'
}

function barWidth(v: number, total: number): string {
  if (!total) return '0%'
  return `${Math.min(100, (v / total) * 100)}%`
}

async function loadAll() {
  loading.value = true
  error.value = null
  try {
    const resp = await listQCRecords({ page: 1, page_size: 50 })
    records.value = resp.items || []
    // ${t('internalQC.t026')}
    const dsMap = new Map<string, { id: string; name: string; size: number; last_result?: string }>()
    for (const r of records.value) {
      const existing = dsMap.get(r.dataset_id)
      if (!existing) {
        dsMap.set(r.dataset_id, {
          id: r.dataset_id,
          name: r.dataset_id,
          size: r.total_assets,
          last_result: r.result,
        })
      } else if (!existing.last_result || existing.last_result === '未质检') {
        existing.last_result = r.result
      }
    }
    datasets.value = Array.from(dsMap.values())
  } catch (e) {
    error.value = (e as Error).message || t("dataFlowTracker.loadFailed")
    records.value = []
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  if (!selectedDataset.value) return
  try {
    const resp = await listQCRecords({
      dataset_id: selectedDataset.value, page: 1, page_size: 20,
    })
    records.value = [
      ...resp.items,
      ...records.value.filter((r) => r.dataset_id !== selectedDataset.value),
    ]
  } catch {
    // ignore
  }
}

async function runModeClick(mode: 'full' | 'sample' | 'aql' | 'stratified') {
  if (!selectedDataset.value) {
    message.warning(t("internalQC.t027"))
    return
  }
  running.value = true
  runMode.value = mode
  runProgress.value = 0
  error.value = null
  // ${t('internalQC.t028')}
  const interval = setInterval(() => {
    if (runProgress.value < 95) runProgress.value += 8
  }, 200)
  try {
    let resp
    if (mode === 'full') {
      resp = await runFullCheck({
        dataset_id: selectedDataset.value, qcer_id: 'qcer_001', seed: 42,
      } as any)
    } else if (mode === 'sample') {
      resp = await runSampleCheck({
        dataset_id: selectedDataset.value, sample_rate: sampleRate.value,
        qcer_id: 'qcer_001', seed: 42,
      })
    } else if (mode === 'aql') {
      resp = await runAQLCheck({
        dataset_id: selectedDataset.value, aql_level: aqlLevel.value,
        lot_size: 500, qcer_id: 'qcer_001', seed: 42,
      })
    } else {
      resp = await runStratifiedCheck({
        dataset_id: selectedDataset.value, sample_size: stratSampleSize.value,
        qcer_id: 'qcer_001', seed: 42,
      })
    }
    if (!resp.success) throw new Error(resp.message || t("internalQC.t029"))
    currentRecord.value = resp.data
    // ${t('internalQC.t030')} stats
    try {
      const s = await getQCStats(resp.data.id)
      if (s.success) currentStats.value = s.data
    } catch {
      // fallback - 用 record ${t('internalQC.t031')}
      currentStats.value = {
        qc_id: resp.data.id,
        dataset_id: resp.data.dataset_id,
        mode: resp.data.mode,
        result: resp.data.result,
        sample_size: resp.data.sample_size,
        total_assets: resp.data.total_assets,
        issue_count: resp.data.issue_count,
        defect_rate: (resp.data.issue_count / Math.max(1, resp.data.sample_size)) * 100,
        pass_rate: 100 - (resp.data.issue_count / Math.max(1, resp.data.sample_size)) * 100,
        by_severity: (resp.data.issue_summary?.by_severity || { critical: 0, major: 0, minor: 0 }) as any,
        by_type: (resp.data.issue_summary?.by_type || {}) as any,
        qcer_id: resp.data.qcer_id,
        created_at: resp.data.created_at,
      }
    }
    // ${t('internalQC.t032')}
    const ds = datasets.value.find((d) => d.id === selectedDataset.value)
    if (ds) ds.last_result = resp.data.result
    // ${t('internalQC.t033')}
    await loadHistory()
    message.success(mode + ' ' + t('internalQC.t034'))
  } catch (e) {
    error.value = (e as Error).message || t('internalQC.t035')
    message.error(error.value || 'Error')
  } finally {
    clearInterval(interval)
    runProgress.value = 100
    setTimeout(() => {
      running.value = false
      runMode.value = ''
      runProgress.value = 0
    }, 600)
  }
}

async function onExport(format: 'json' | 'csv' | 'pdf') {
  if (!currentRecord.value) return
  try {
    const resp = await exportQCReport(currentRecord.value.id, format)
    if (resp.success) {
      message.success(`${t('internalQC.t036')}: ${resp.data.file_path}`)
    }
  } catch (e) {
    message.error(`${t('internalQC.t037')}: ${(e as Error).message}`)
  }
}

async function onRerun() {
  if (!currentRecord.value) return
  try {
    const resp = await rerunQC(currentRecord.value.id)
    if (resp.success) {
      currentRecord.value = resp.data
      message.success(t("internalQC.t038"))
      await loadHistory()
    }
  } catch (e) {
    message.error(t('internalQC.t039') + ': ' + (e as Error).message)
  }
}

function onSelectHistory(r: QCRecord) {
  currentRecord.value = r
  getQCStats(r.id).then((s) => {
    if (s.success) currentStats.value = s.data
  }).catch(() => null)
}

onMounted(loadAll)
</script>

<style scoped>
.internal-qc-view { padding: 16px; }
.header-card { margin-bottom: 12px; }
.main-grid {
  display: grid;
  grid-template-columns: 280px 1fr 360px;
  gap: 12px;
  align-items: start;
}
.left-pane { max-height: calc(100vh - 200px); overflow: auto; }
.center-pane {}
.right-pane { max-height: calc(100vh - 200px); overflow: auto; }
.kpi-row { margin-top: 8px; }
.kpi-value { margin: 6px 0; }
.bar-chart { margin-top: 6px; }
.bar-row { display: flex; align-items: center; gap: 8px; margin: 4px 0; }
.bar-track {
  flex: 1;
  height: 12px;
  background: #f0f0f0;
  border-radius: 4px;
  overflow: hidden;
}
.bar-fill { height: 100%; transition: width 0.3s ease; }
.issue-action {
  margin-top: 4px;
  font-size: 11px;
  color: #d08000;
}
.active { background: #e6f0fa; }
</style>