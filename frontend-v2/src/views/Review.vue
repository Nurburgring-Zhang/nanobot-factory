<template>
  <div class="review-view">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">审核 / QA</NText>
          <NText depth="3" style="margin-left: 8px">
            多级审核队列 · 通过 / 驳回 / 退回
          </NText>
        </div>
        <NSpace>
          <NTag :type="'warning'" :bordered="false">
            待审 {{ stats.pending ?? 0 }}
          </NTag>
          <NTag :type="'info'" :bordered="false">
            处理中 {{ stats.in_review ?? 0 }}
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

    <!-- Queue + decision grid -->
    <div class="bottom-grid">
      <NCard title="审核队列" :bordered="false">
        <SearchBar
          v-model="keyword"
          placeholder="搜索标注 ID / 标注员 / 标签"
          @search="loadQueue"
          @reset="onReset"
        >
          <template #extra>
            <NSelect
              v-model:value="stageFilter"
              :options="stageOptions"
              placeholder="阶段"
              clearable
              style="width: 140px"
              @update:value="loadQueue"
            />
          </template>
        </SearchBar>

        <DataTable
          :columns="columns"
          :data="items"
          :loading="loading"
          :error="error"
          :total="items.length"
          :page="1"
          :page-size="20"
          :row-key="(r: any) => r.item_id || r.id"
          @refresh="loadQueue"
        >
          <template #empty><NEmpty description="审核队列为空" /></template>
        </DataTable>
      </NCard>

      <NCard title="审核操作" :bordered="false">
        <NSpin :show="processing">
          <NEmpty v-if="!selected" description="选择左侧队列项进行审核" />
          <NForm v-else label-placement="top" :model="decision">
            <NFormItem label="审核员 ID">
              <NInput v-model:value="decision.reviewer_id" placeholder="reviewer-001" />
            </NFormItem>
            <NFormItem label="决定">
              <NRadioGroup v-model:value="decision.decision">
                <NSpace>
                  <NRadio value="approve">通过</NRadio>
                  <NRadio value="reject">驳回</NRadio>
                  <NRadio value="return">退回修改</NRadio>
                </NSpace>
              </NRadioGroup>
            </NFormItem>
            <NFormItem label="备注">
              <NInput
                v-model:value="decision.comments"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 6 }"
                placeholder="（可选）审核意见、问题列表等"
              />
            </NFormItem>
            <NSpace>
              <NButton type="primary" :loading="processing" @click="onProcess">提交</NButton>
              <NButton :disabled="processing" @click="onResetSelection">清空</NButton>
            </NSpace>
            <div v-if="lastResult" class="result-block">
              <NText depth="3" style="font-size: 11px">最近响应</NText>
              <pre class="result-pre">{{ lastResultText }}</pre>
            </div>
          </NForm>
        </NSpin>
      </NCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from 'vue'
import {
  NCard, NSpace, NText, NTag, NIcon, NGrid, NGi, NSpin, NEmpty, NAlert, NSelect, NInput,
  NButton, NForm, NFormItem, NRadioGroup, NRadio, useMessage, type DataTableColumns
} from 'naive-ui'
import { RefreshOutline } from '@vicons/ionicons5'
import SearchBar from '@/components/SearchBar.vue'
import DataTable from '@/components/DataTable.vue'
import ActionButton from '@/components/ActionButton.vue'
import {
  getReviewQueueStats, getReviewEfficiency, listReviewAnnotations,
  processReview, submitForReview, type ReviewQueueStats,
} from '@/api/review'

const message = useMessage()

const stats = ref<ReviewQueueStats>({ pending: 0, in_review: 0, completed_today: 0, returned: 0 })
const efficiency = ref<any>(null)
const items = ref<any[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const keyword = ref('')
const stageFilter = ref<string | null>(null)

const stageOptions = [
  { label: '初审', value: 'initial' },
  { label: '复审', value: 'secondary' },
  { label: '终审', value: 'final' },
]

const selected = ref<any>(null)
const processing = ref(false)
const decision = reactive<{ reviewer_id: string; decision: 'approve' | 'reject' | 'return'; comments: string }>({
  reviewer_id: '',
  decision: 'approve',
  comments: '',
})
const lastResult = ref<any>(null)

const kpis = computed(() => [
  { key: 'pending', label: '待审', value: stats.value.pending ?? 0, hint: '积压量' },
  { key: 'in_review', label: '处理中', value: stats.value.in_review ?? 0, hint: '审核员处理' },
  { key: 'done', label: '今日完成', value: stats.value.completed_today ?? 0, hint: '已闭环' },
  { key: 'agreement', label: '平均一致性', value: efficiency.value?.avg_agreement ? `${(efficiency.value.avg_agreement * 100).toFixed(0)}%` : '—', hint: 'Kappa 系数' },
])

const columns: DataTableColumns<any> = [
  { title: 'Item ID', key: 'item_id', width: 160 },
  { title: '阶段', key: 'stage', width: 100, render: (r) => h(NTag, { type: stageBadge(r.stage), size: 'small' }, { default: () => r.stage || '—' }) },
  { title: '优先级', key: 'priority', width: 80 },
  { title: '资产', key: 'asset_id', width: 120 },
  { title: '提交人', key: 'submitted_by', width: 120, render: (r) => r.submitted_by || '—' },
  { title: '提交时间', key: 'submitted_at', width: 180 },
  {
    title: '操作', key: 'actions', width: 100,
    render: (row) => h('a', { style: 'color:#2080f0;cursor:pointer', onClick: () => selectRow(row) }, '选择'),
  },
]

function stageBadge(s?: string): 'default' | 'info' | 'success' | 'warning' {
  switch (s) {
    case 'initial': return 'info'
    case 'secondary': return 'warning'
    case 'final': return 'success'
    default: return 'default'
  }
}

async function load() {
  loading.value = true; error.value = null
  try {
    await Promise.allSettled([loadStats(), loadEfficiency(), loadQueue()])
  } catch (e) {
    error.value = (e as Error).message || '加载审核数据失败'
  } finally { loading.value = false }
}

async function loadStats() {
  try {
    const res = await getReviewQueueStats()
    if (res.success) stats.value = res.stats
  } catch {
    // 离线 fallback — 模拟数据
    stats.value = { pending: 42, in_review: 18, completed_today: 156, returned: 7, by_stage: { initial: 28, secondary: 12, final: 20 } }
  }
}

async function loadEfficiency() {
  try {
    const res = await getReviewEfficiency()
    if (res.success) efficiency.value = res.report
  } catch {
    efficiency.value = { avg_agreement: 0.82, total_completed: 156 }
  }
}

async function loadQueue() {
  loading.value = true
  try {
    const res = await listReviewAnnotations({ limit: 50 })
    const raw: any[] = res.items || []
    const filtered = raw.filter((r) => {
      if (stageFilter.value && r.stage !== stageFilter.value) return false
      if (keyword.value) {
        const k = keyword.value.toLowerCase()
        return String(r.id).toLowerCase().includes(k) || (r.label || '').toLowerCase().includes(k) || (r.annotator || '').toLowerCase().includes(k)
      }
      return true
    })
    items.value = filtered.map((r) => ({
      item_id: String(r.id),
      stage: r.stage || (r.status === 'pending' ? 'initial' : 'secondary'),
      priority: r.priority ?? 5,
      asset_id: r.asset_id,
      submitted_by: r.annotator,
      submitted_at: r.created_at,
      raw: r,
    }))
  } catch (e) {
    error.value = (e as Error).message || '加载队列失败'
    items.value = []
  } finally { loading.value = false }
}

function onReset() { keyword.value = ''; stageFilter.value = null; loadQueue() }

function selectRow(row: any) {
  selected.value = row
  lastResult.value = null
  decision.comments = ''
}

function onResetSelection() {
  selected.value = null
  decision.reviewer_id = ''
  decision.comments = ''
  lastResult.value = null
}

async function onProcess() {
  if (!selected.value) return
  if (!decision.reviewer_id.trim()) {
    message.warning('请输入审核员 ID')
    return
  }
  processing.value = true
  try {
    const res = await processReview({
      item_id: selected.value.item_id,
      reviewer_id: decision.reviewer_id.trim(),
      decision: decision.decision,
      comments: decision.comments,
    })
    lastResult.value = res
    message.success(`已 ${decision.decision === 'approve' ? '通过' : decision.decision === 'reject' ? '驳回' : '退回'}`)
    await load()
  } catch (e) {
    message.error((e as Error).message || '提交失败')
    lastResult.value = { error: (e as Error).message }
  } finally { processing.value = false }
}

const lastResultText = computed(() => lastResult.value ? JSON.stringify(lastResult.value, null, 2) : '')

onMounted(load)
</script>

<style scoped>
.review-view { padding: 16px; }
.header-card { margin-bottom: 12px; }
.kpi-card { min-height: 96px; }
.kpi-value { margin: 4px 0; }
.bottom-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.result-block { margin-top: 12px; }
.result-pre {
  font-size: 11px;
  background: #f7f8fa;
  padding: 8px;
  border-radius: 4px;
  margin: 4px 0 0;
  white-space: pre-wrap;
  max-height: 200px;
  overflow: auto;
}
</style>