<template>
  <section class="crowdsource-admin">
    <header class="admin-header">
      <h1>Crowdsource Management</h1>
      <p class="subtitle">
        V5 §13.4 / Chapter 17 — Full version (tasks / workers / payments / quality)
      </p>
    </header>

    <n-tabs v-model:value="activeTab" type="line" animated>
      <!-- Tab 1: Tasks -->
      <n-tab-pane name="tasks" tab="Tasks">
        <div v-if="store.loading" data-testid="tasks-loading">Loading...</div>
        <div v-else-if="!store.tasks.length" data-testid="tasks-empty" class="empty-state">
          <p>No crowdsource tasks yet.</p>
        </div>
        <n-data-table
          v-else
          :columns="taskColumns"
          :data="store.tasks"
          :pagination="{ pageSize: 10 }"
          :row-key="(row: any) => row.id"
          :bordered="false"
          :stripe="true"
          data-testid="tasks-table"
          @row-click="onTaskRowClick"
        />
      </n-tab-pane>

      <!-- Tab 2: Workers -->
      <n-tab-pane name="workers" tab="Workers">
        <div v-if="store.loading" data-testid="workers-loading">Loading...</div>
        <div v-else-if="!store.workers.length" data-testid="workers-empty" class="empty-state">
          <p>No workers in the pool.</p>
        </div>
        <n-data-table
          v-else
          :columns="workerColumns"
          :data="store.workers"
          :pagination="{ pageSize: 10 }"
          :row-key="(row: any) => row.id"
          :bordered="false"
          :stripe="true"
          data-testid="workers-table"
          @row-click="onWorkerRowClick"
        />
      </n-tab-pane>

      <!-- Tab 3: Payments -->
      <n-tab-pane name="payments" tab="Payments">
        <div v-if="store.loading" data-testid="payments-loading">Loading...</div>
        <div v-else-if="!store.payments.length" data-testid="payments-empty" class="empty-state">
          <p>No payments scheduled.</p>
        </div>
        <n-data-table
          v-else
          :columns="paymentColumns"
          :data="store.payments"
          :pagination="{ pageSize: 10 }"
          :row-key="(row: any) => row.id"
          :bordered="false"
          :stripe="true"
          data-testid="payments-table"
          @row-click="onPaymentRowClick"
        />
      </n-tab-pane>

      <!-- Tab 4: Quality -->
      <n-tab-pane name="quality" tab="Quality">
        <div v-if="store.loading" data-testid="quality-loading">Loading...</div>
        <div v-else data-testid="quality-chart" class="quality-chart">
          <h3>Worker Quality Score Distribution</h3>
          <div class="histogram">
            <div
              v-for="bin in qualityBins"
              :key="bin.label"
              class="bar"
              :style="{ height: `${bin.heightPct}%`, width: `${100 / qualityBins.length}%` }"
              :data-testid="`quality-bin-${bin.label}`"
              :title="`${bin.label}: ${bin.count} workers`"
            >
              <div class="bar-fill" />
              <div class="bar-label">
                <div class="bin-label">{{ bin.label }}</div>
                <div class="bin-count">{{ bin.count }}</div>
              </div>
            </div>
          </div>
        </div>
      </n-tab-pane>
    </n-tabs>
  </section>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { NTag, createDiscreteApi, type DataTableColumns } from 'naive-ui'
import { useCrowdsourceStore, type CrowdsourceTask, type Payment, type Worker } from '@/stores/crowdsource'

const store = useCrowdsourceStore()
// createDiscreteApi: works in jsdom without NMessageProvider wrapper (P19 v5.6 fix).
const { message } = createDiscreteApi(['message'])
const activeTab = ref<string>('tasks')

onMounted(async () => {
  if (!store.loaded) await store.loadAll()
})

// ────────────────────────────────────────────────────────────────────────────
// Tab 1: Tasks
// ────────────────────────────────────────────────────────────────────────────
const taskColumns = computed<DataTableColumns<CrowdsourceTask>>(() => [
  { title: 'ID', key: 'id', width: 100 },
  { title: 'Title', key: 'title' },
  {
    title: 'Status',
    key: 'status',
    width: 120,
    render: (row) =>
      h(NTag, {
        type:
          row.status === 'completed' ? 'success'
          : row.status === 'in_progress' ? 'info'
          : row.status === 'paused' ? 'warning'
          : 'default',
        bordered: false,
      }, () => row.status),
  },
  { title: 'Workers', key: 'workers_count', width: 100 },
  { title: 'Payment', key: 'payment', width: 100, render: (row) => `$${row.payment}` },
  { title: 'Deadline', key: 'deadline', width: 120 },
])

function onTaskRowClick(row: CrowdsourceTask) {
  message.info(`Task ${row.id} clicked — total payment $${row.payment}`)
}

// ────────────────────────────────────────────────────────────────────────────
// Tab 2: Workers
// ────────────────────────────────────────────────────────────────────────────
const workerColumns = computed<DataTableColumns<Worker>>(() => [
  { title: 'ID', key: 'id', width: 100 },
  { title: 'Name', key: 'name' },
  { title: 'Completed', key: 'completed_tasks', width: 120 },
  {
    title: 'Quality',
    key: 'quality_score',
    width: 120,
    render: (row) => `${row.quality_score.toFixed(1)}`,
  },
  {
    title: 'Earnings',
    key: 'earnings',
    width: 120,
    render: (row) => `$${row.earnings.toFixed(2)}`,
  },
])

function onWorkerRowClick(row: Worker) {
  message.info(`Worker ${row.name} — score ${row.quality_score}`)
}

// ────────────────────────────────────────────────────────────────────────────
// Tab 3: Payments
// ────────────────────────────────────────────────────────────────────────────
const paymentColumns = computed<DataTableColumns<Payment>>(() => [
  { title: 'ID', key: 'id', width: 100 },
  { title: 'Worker', key: 'worker_name' },
  {
    title: 'Amount',
    key: 'amount',
    width: 120,
    render: (row) => `$${row.amount.toFixed(2)}`,
  },
  {
    title: 'Status',
    key: 'status',
    width: 120,
    render: (row) =>
      h(NTag, {
        type:
          row.status === 'processed' ? 'success'
          : row.status === 'pending' ? 'info'
          : 'error',
        bordered: false,
      }, () => row.status),
  },
  { title: 'Scheduled For', key: 'scheduled_for', width: 140 },
])

function onPaymentRowClick(row: Payment) {
  message.info(`Payment ${row.id} — $${row.amount} → ${row.worker_name}`)
}

// ────────────────────────────────────────────────────────────────────────────
// Tab 4: Quality histogram (5 bins: 0-20, 20-40, 40-60, 60-80, 80-100)
// ────────────────────────────────────────────────────────────────────────────
const qualityBins = computed(() => {
  const bins = [
    { label: '0-20',   count: 0, heightPct: 0 },
    { label: '20-40',  count: 0, heightPct: 0 },
    { label: '40-60',  count: 0, heightPct: 0 },
    { label: '60-80',  count: 0, heightPct: 0 },
    { label: '80-100', count: 0, heightPct: 0 },
  ]
  for (const w of store.workers) {
    const idx = Math.min(4, Math.floor(w.quality_score / 20))
    bins[idx].count += 1
  }
  const max = Math.max(1, ...bins.map(b => b.count))
  for (const b of bins) b.heightPct = Math.round((b.count / max) * 100)
  return bins
})
</script>

<style scoped>
.crowdsource-admin { padding: 16px 24px; max-width: 1280px; }
.admin-header { margin-bottom: 16px; }
.admin-header h1 { margin: 0 0 4px; font-size: 22px; font-weight: 600; }
.subtitle { color: #6b7280; font-size: 13px; margin: 0; }
.empty-state { padding: 32px; text-align: center; color: #6b7280; }

.quality-chart {
  padding: 16px;
  border-radius: 6px;
  background: #fafafa;
}
.quality-chart h3 {
  margin: 0 0 16px;
  font-size: 14px;
  font-weight: 600;
}

.histogram {
  display: flex;
  align-items: flex-end;
  height: 220px;
  gap: 4px;
  border-bottom: 1px solid #d4d4d8;
}
.bar {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  align-items: center;
  height: 100%;
  position: relative;
}
.bar-fill {
  width: 60%;
  background: linear-gradient(180deg, #60a5fa 0%, #2563eb 100%);
  border-radius: 4px 4px 0 0;
  min-height: 2px;
  flex: 1 1 auto;
  align-self: flex-end;
}
.bar-label {
  position: absolute;
  bottom: -36px;
  text-align: center;
  font-size: 11px;
  color: #4b5563;
}
.bin-label { font-weight: 600; }
.bin-count { color: #6b7280; }
</style>
