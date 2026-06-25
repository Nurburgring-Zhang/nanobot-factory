<template>
  <div class="monitoring-view">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">监控 / 告警</NText>
          <NText depth="3" style="margin-left: 8px">
            13 个微服务健康检查 · Prometheus 指标 · Grafana 入口
          </NText>
        </div>
        <NSpace>
          <NTag :type="overallBadge" :bordered="false" size="large">
            {{ okCount }} / {{ services.length }} 健康
          </NTag>
          <ActionButton type="primary" :loading="healthLoading || metricsLoading" @click="loadAll">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            刷新
          </ActionButton>
          <ActionButton secondary @click="openGrafana">
            <template #icon><NIcon><BarChartOutline /></NIcon></template>
            打开 Grafana
          </ActionButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NAlert v-if="error" type="error" :show-icon="true" closable style="margin-bottom: 12px" @close="error = null">
      {{ error }}
    </NAlert>

    <!-- KPI tiles: high-level process metrics -->
    <NGrid :cols="4" :x-gap="12" :y-gap="12" style="margin-bottom: 12px">
      <NGi v-for="k in kpis" :key="k.key">
        <NCard :bordered="false" size="small" class="kpi-card">
          <NText depth="3" style="font-size: 11px">{{ k.label }}</NText>
          <div class="kpi-value">
            <NText strong style="font-size: 22px">{{ k.value }}</NText>
            <NText depth="3" style="font-size: 11px; margin-left: 4px">{{ k.unit }}</NText>
          </div>
          <NText depth="3" style="font-size: 11px">{{ k.hint }}</NText>
        </NCard>
      </NGi>
    </NGrid>

    <!-- Services health grid -->
    <NCard title="微服务健康" :bordered="false" style="margin-bottom: 12px">
      <template #header-extra>
        <NSelect
          v-model:value="filterMode"
          :options="filterOptions"
          size="small"
          style="width: 140px"
        />
      </template>
      <NSpin :show="healthLoading">
        <NGrid :cols="4" :x-gap="12" :y-gap="12">
          <NGi v-for="s in filteredServices" :key="s.name">
            <NCard size="small" :bordered="false" class="svc-card" :class="`svc-${s.status}`">
              <NSpace align="center" justify="space-between">
                <div>
                  <NText strong style="font-size: 13px">{{ s.name }}</NText>
                  <NText depth="3" style="font-size: 10px; display: block">{{ s.baseUrl || '/' }}</NText>
                </div>
                <NTag :type="statusBadge(s.status)" size="small">{{ statusLabel(s.status) }}</NTag>
              </NSpace>
              <div class="svc-meta">
                <NText depth="3" style="font-size: 11px">
                  延迟 {{ s.latencyMs ?? '—' }} ms
                </NText>
                <NText v-if="s.detail?.version" depth="3" style="font-size: 11px">
                  v{{ s.detail.version }}
                </NText>
              </div>
              <NButton
                v-if="s.detail"
                size="tiny"
                tertiary
                style="margin-top: 6px"
                @click="showDetail(s)"
              >
                查看详情
              </NButton>
            </NCard>
          </NGi>
        </NGrid>
        <div v-if="filteredServices.length === 0 && !healthLoading" class="empty-wrap">
          <NEmpty :description="`没有 ${filterMode} 状态的服务`" />
        </div>
      </NSpin>
    </NCard>

    <!-- Metrics + sample panel -->
    <div class="bottom-grid">
      <NCard title="Prometheus 指标" :bordered="false">
        <NSpace style="margin-bottom: 8px">
          <NTag :type="metricsPayload.samples.length > 0 ? 'success' : 'warning'" size="small">
            {{ metricsPayload.samples.length }} 样本
          </NTag>
          <NText depth="3" style="font-size: 11px">
            最后更新 {{ formatTime(metricsPayload.fetchedAt) }}
          </NText>
        </NSpace>
        <NSpin :show="metricsLoading">
          <NEmpty v-if="metricsPayload.samples.length === 0 && !metricsLoading" description="未拉取到指标" />
          <NDataTable
            v-else
            :columns="metricColumns"
            :data="metricRows"
            :pagination="{ pageSize: 8 }"
            size="small"
            :row-key="(r: any) => `${r.name}-${JSON.stringify(r.labels)}`"
          />
        </NSpin>
      </NCard>

      <NCard title="原始 /metrics 输出" :bordered="false">
        <NInput
          v-model:value="metricsRawText"
          type="textarea"
          readonly
          :autosize="{ minRows: 8, maxRows: 16 }"
          placeholder="(尚未拉取)"
        />
      </NCard>
    </div>

    <!-- Service detail drawer -->
    <NModal v-model:show="detailVisible" preset="card" :title="detailSvc?.name || '服务详情'" style="width: 600px">
      <pre v-if="detailSvc" class="detail-pre">{{ JSON.stringify(detailSvc, null, 2) }}</pre>
    </NModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  NCard, NSpace, NText, NTag, NIcon, NGrid, NGi, NSpin, NEmpty, NAlert, NButton, NSelect,
  NInput, NDataTable, NModal, useMessage, type DataTableColumns
} from 'naive-ui'
import { RefreshOutline, BarChartOutline } from '@vicons/ionicons5'
import ActionButton from '@/components/ActionButton.vue'
import {
  fetchMetrics, fetchHealth, DEFAULT_SERVICES,
  type ServiceHealth, type PrometheusPayload, type MetricSample,
} from '@/api/monitoring'

const message = useMessage()

const services = ref<ServiceHealth[]>([])
const metricsPayload = ref<PrometheusPayload>({ raw: '', samples: [], summary: {}, fetchedAt: new Date().toISOString() })
const metricsRawText = computed(() => metricsPayload.value.raw || '(no data)')
const healthLoading = ref(false)
const metricsLoading = ref(false)
const error = ref<string | null>(null)

const filterMode = ref<'all' | 'ok' | 'down' | 'unknown'>('all')

const detailVisible = ref(false)
const detailSvc = ref<ServiceHealth | null>(null)

const filterOptions = [
  { label: '全部', value: 'all' },
  { label: '健康', value: 'ok' },
  { label: '故障', value: 'down' },
  { label: '未知', value: 'unknown' },
]

const okCount = computed(() => services.value.filter((s) => s.status === 'ok').length)
const overallBadge = computed<'success' | 'warning' | 'error'>(() => {
  if (okCount.value === services.value.length) return 'success'
  if (okCount.value === 0) return 'error'
  return 'warning'
})

const kpis = computed(() => {
  const s = metricsPayload.value.summary
  return [
    { key: 'cpu', label: 'CPU 总秒', value: (s.cpuSeconds ?? 0).toFixed(2), unit: 's', hint: 'process_cpu_seconds_total' },
    { key: 'rss', label: '常驻内存', value: formatBytes(s.memoryRssBytes ?? 0), unit: '', hint: 'process_resident_memory_bytes' },
    { key: 'threads', label: '线程数', value: s.threads ?? '—', unit: '', hint: 'process_threads' },
    { key: 'fds', label: '打开文件描述符', value: s.openFds ?? '—', unit: '', hint: 'process_open_fds' },
  ]
})

const filteredServices = computed(() => {
  if (filterMode.value === 'all') return services.value
  return services.value.filter((s) => s.status === filterMode.value)
})

const metricColumns: DataTableColumns<MetricSample> = [
  { title: '指标', key: 'name', minWidth: 200 },
  { title: '标签', key: 'labels', minWidth: 160, render: (r) => JSON.stringify(r.labels) },
  {
    title: '值', key: 'value', width: 160,
    render: (r) => {
      if (r.value > 1e6) return (r.value / 1e6).toFixed(2) + 'M'
      if (r.value > 1e3) return (r.value / 1e3).toFixed(2) + 'k'
      return r.value.toFixed(2)
    },
  },
]

const metricRows = computed<MetricSample[]>(() => metricsPayload.value.samples.slice(0, 80))

function statusBadge(s: ServiceHealth['status']): 'success' | 'error' | 'warning' | 'default' {
  switch (s) {
    case 'ok': return 'success'
    case 'down': return 'error'
    case 'unknown': return 'default'
    default: return 'warning'
  }
}
function statusLabel(s: ServiceHealth['status']): string {
  return s === 'ok' ? '健康' : s === 'down' ? '故障' : '未知'
}
function formatBytes(n: number): string {
  if (n > 1e9) return (n / 1e9).toFixed(2) + ' GB'
  if (n > 1e6) return (n / 1e6).toFixed(2) + ' MB'
  if (n > 1e3) return (n / 1e3).toFixed(2) + ' KB'
  return `${n} B`
}
function formatTime(iso: string): string {
  try { return new Date(iso).toLocaleString() } catch { return iso }
}

async function loadAll() {
  error.value = null
  services.value = DEFAULT_SERVICES
  await Promise.allSettled([loadHealth(), loadMetrics()])
}

async function loadHealth() {
  healthLoading.value = true
  try {
    services.value = await fetchHealth(DEFAULT_SERVICES)
  } catch (e) {
    error.value = (e as Error).message || '健康检查失败'
  } finally { healthLoading.value = false }
}

async function loadMetrics() {
  metricsLoading.value = true
  try {
    metricsPayload.value = await fetchMetrics()
  } catch (e) {
    error.value = (e as Error).message || '指标拉取失败'
  } finally { metricsLoading.value = false }
}

function openGrafana() {
  const url = (import.meta.env.VITE_GRAFANA_URL as string) || 'http://localhost:3000'
  window.open(url, '_blank', 'noopener,noreferrer')
}

function showDetail(s: ServiceHealth) {
  detailSvc.value = s
  detailVisible.value = true
}

// Auto-refresh every 30s
let timer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  loadAll()
  timer = setInterval(loadAll, 30_000)
})
// Cleanup on unmount
import { onBeforeUnmount } from 'vue'
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.monitoring-view { padding: 16px; }
.header-card { margin-bottom: 12px; }
.kpi-card { min-height: 100px; }
.kpi-value { margin: 4px 0; }
.svc-card {
  min-height: 100px;
  transition: all 0.15s;
}
.svc-card.svc-ok { border-left: 3px solid #18a058; }
.svc-card.svc-down { border-left: 3px solid #d03050; }
.svc-card.svc-unknown { border-left: 3px solid #999; }
.svc-meta { display: flex; justify-content: space-between; margin-top: 4px; }
.bottom-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 12px;
}
.detail-pre {
  font-size: 11px;
  background: #f7f8fa;
  padding: 12px;
  border-radius: 4px;
  margin: 0;
  white-space: pre-wrap;
  max-height: 400px;
  overflow: auto;
}
.empty-wrap { padding: 24px; }
</style>