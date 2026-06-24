<template>
  <div class="run-monitor">
    <n-card title="Workflow Run Monitor" :bordered="false">
      <n-space vertical>
        <n-space>
          <n-select
            v-model:value="selectedDagId"
            :options="dagOptions"
            placeholder="Select a DAG"
            style="width: 320px"
            @update:value="loadRuns"
          />
          <n-button type="primary" :loading="busy" @click="onStartRun">Start new run</n-button>
          <n-tag :type="liveStatus === 'connected' ? 'success' : 'warning'">
            WebSocket: {{ liveStatus }}
          </n-tag>
        </n-space>
        <n-alert v-if="error" type="error" :title="error" />
        <n-empty v-if="runs.length === 0 && !lastRun" description="No runs yet" />

        <n-card v-if="lastRun" size="small" :title="`Run ${lastRun.run_id.slice(0, 8)}`">
          <template #header-extra>
            <n-tag :type="runTag(lastRun.status)">{{ lastRun.status }}</n-tag>
          </template>
          <n-progress :percentage="Math.round(lastRun.progress * 100)" :show-indicator="false" />
          <n-table size="small" :columns="stepCols" :data="stepRows" />
        </n-card>

        <n-card v-if="runs.length > 0" size="small" title="History">
          <n-table size="small" :columns="runCols" :data="runRows" />
        </n-card>
      </n-space>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, h } from 'vue'
import { NCard, NSpace, NSelect, NButton, NAlert, NEmpty, NTag, NProgress, NTable } from 'naive-ui'
import { listDAGs, listRuns, runDAG, getRun, type WorkflowRun, type RunStepState } from '@/api/workflow_v2'

const dagOptions = ref<{ label: string, value: string }[]>([])
const selectedDagId = ref<string>('')
const runs = ref<WorkflowRun[]>([])
const lastRun = ref<WorkflowRun | null>(null)
const busy = ref(false)
const error = ref('')
const liveStatus = ref<'connected' | 'disconnected' | 'connecting'>('disconnected')
let pollHandle: number | null = null

onMounted(async () => {
  const { items } = await listDAGs()
  dagOptions.value = items.map(d => ({ label: d.name, value: d.id }))
  if (items.length > 0) {
    selectedDagId.value = items[0].id
    await loadRuns(items[0].id)
  }
  // Open WebSocket for live progress (graceful degrade if backend not running)
  try {
    liveStatus.value = 'connecting'
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${location.host}/api/v1/workflow/dag/runs/ws`
    const ws = new WebSocket(url)
    ws.onopen = () => { liveStatus.value = 'connected' }
    ws.onclose = () => { liveStatus.value = 'disconnected' }
    ws.onerror = () => { liveStatus.value = 'disconnected' }
  } catch { liveStatus.value = 'disconnected' }
})

onUnmounted(() => {
  if (pollHandle) { clearInterval(pollHandle); pollHandle = null }
})

async function loadRuns(id: string) {
  if (!id) return
  try {
    const r = await listRuns(id)
    runs.value = r.items
  } catch (e: any) {
    error.value = e?.response?.data?.detail || String(e)
  }
}

async function onStartRun() {
  if (!selectedDagId.value) return
  busy.value = true; error.value = ''
  try {
    const r = await runDAG(selectedDagId.value, {}, 'manual', false)
    lastRun.value = r
    await loadRuns(selectedDagId.value)
    if (pollHandle) clearInterval(pollHandle)
    pollHandle = window.setInterval(async () => {
      try {
        const cur = await getRun(r.run_id)
        lastRun.value = cur
        if (cur.status !== 'running' && cur.status !== 'pending') {
          if (pollHandle) { clearInterval(pollHandle); pollHandle = null }
          await loadRuns(selectedDagId.value)
        }
      } catch { /* ignore */ }
    }, 1500)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || String(e)
  } finally {
    busy.value = false
  }
}

const stepCols = [
  { title: 'Node', key: 'node_id' },
  { title: 'Status', key: 'status' },
  { title: 'Attempt', key: 'attempt' },
  { title: 'Error', key: 'error' },
]
const stepRows = computed(() => {
  if (!lastRun.value) return []
  return Object.values(lastRun.value.steps).map(s => ({
    node_id: s.node_id,
    status: s.status,
    attempt: s.attempt,
    error: s.error || '',
  }))
})

const runCols = [
  { title: 'Run id', key: 'run_id' },
  { title: 'Status', key: 'status' },
  { title: 'Trigger', key: 'trigger' },
  { title: 'Progress', key: 'progress' },
  { title: 'Started', key: 'started_at' },
]
const runRows = computed(() => runs.value.map(r => ({
  run_id: r.run_id.slice(0, 8),
  status: r.status,
  trigger: r.trigger,
  progress: Math.round((r.progress || 0) * 100) + '%',
  started_at: r.started_at,
})))

function runTag(s: string) {
  if (s === 'succeeded') return 'success'
  if (s === 'failed') return 'error'
  if (s === 'partial') return 'warning'
  if (s === 'running') return 'info'
  return 'default'
}
</script>

<style scoped>
.run-monitor { padding: 16px; }
</style>
