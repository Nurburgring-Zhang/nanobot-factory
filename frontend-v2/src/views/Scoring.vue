<template>
  <div class="scoring-view">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">评分 / 评测</NText>
          <NText depth="3" style="margin-left: 8px">
            {{ operators.length }} 个评分算子 · 同步 / 异步执行
          </NText>
        </div>
        <NSpace>
          <NTag :type="'info'" :bordered="false">{{ selectedOp?.id || '未选择算子' }}</NTag>
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

    <!-- Operators + run panel -->
    <div class="scoring-grid">
      <NCard title="评分算子" :bordered="false">
        <SearchBar
          v-model="keyword"
          placeholder="搜索算子 ID / 名称 / 类别"
          @search="onSearch"
          @reset="onReset"
        >
          <template #extra>
            <NSelect
              v-model:value="categoryFilter"
              :options="categoryOptions"
              placeholder="类别"
              clearable
              style="width: 140px"
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
          :row-key="(r: ScorerOperator) => r.id"
          @refresh="load"
        >
          <template #empty><NEmpty description="暂无评分算子" /></template>
        </DataTable>
      </NCard>

      <NCard title="执行评分" :bordered="false">
        <NSpin :show="running">
          <NEmpty v-if="!selectedOp" description="选择左侧算子以配置输入" />
          <NForm v-else label-placement="top" :model="form">
            <NFormItem label="算子">
              <NInput :value="selectedOp.id" readonly />
            </NFormItem>
            <NFormItem label="输入数据 (JSON 字符串 / 数组 / 对象)">
              <NInput
                v-model:value="form.data"
                type="textarea"
                :autosize="{ minRows: 4, maxRows: 12 }"
                placeholder='例如 "hello world" 或 ["a","b"] 或 {"image":"..."}'
              />
            </NFormItem>
            <NFormItem label="参数 (JSON 对象)">
              <NInput
                v-model:value="form.params"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 6 }"
                placeholder='例如 {"language":"zh","threshold":0.8}'
              />
            </NFormItem>
            <NSpace>
              <NButton type="primary" :loading="running" @click="onRun">运行</NButton>
              <NButton @click="onBatchRun">批量评分 (串联多算子)</NButton>
              <NButton tertiary @click="onClearResult">清空</NButton>
            </NSpace>

            <div v-if="lastResult" class="result-block">
              <NText depth="3" style="font-size: 11px">最近响应 ({{ lastElapsedMs }} ms)</NText>
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
  NForm, NFormItem, NButton, useMessage, type DataTableColumns
} from 'naive-ui'
import { RefreshOutline } from '@vicons/ionicons5'
import SearchBar from '@/components/SearchBar.vue'
import DataTable from '@/components/DataTable.vue'
import ActionButton from '@/components/ActionButton.vue'
import { http } from '@/api/http'

interface ScorerOperator {
  id: string
  name?: string
  description?: string
  category?: string
  version?: string
  input_schema?: Record<string, unknown>
  output_schema?: Record<string, unknown>
}

const message = useMessage()

const operators = ref<ScorerOperator[]>([])
const filtered = ref<ScorerOperator[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const keyword = ref('')
const categoryFilter = ref<string | null>(null)
const selectedOp = ref<ScorerOperator | null>(null)

const running = ref(false)
const lastResult = ref<any>(null)
const lastElapsedMs = ref(0)

const form = reactive<{ data: string; params: string }>({
  data: '"hello world"',
  params: '{}',
})

const categoryOptions = [
  { label: '美学', value: 'aesthetic' },
  { label: '质量', value: 'quality' },
  { label: '安全', value: 'safety' },
  { label: '多模态', value: 'multimodal' },
  { label: '其他', value: 'misc' },
]

const kpis = computed(() => [
  { key: 'total', label: '算子总数', value: operators.value.length, hint: 'scoring_service 注册' },
  { key: 'visible', label: '当前可见', value: filtered.value.length, hint: '已应用搜索/类别' },
  { key: 'selected', label: '已选算子', value: selectedOp.value?.id || '—', hint: selectedOp.value?.category || '' },
  { key: 'latency', label: '最近耗时', value: lastElapsedMs.value, hint: 'ms / 同步运行' },
])

const columns: DataTableColumns<ScorerOperator> = [
  { title: 'ID', key: 'id', width: 220, render: (r) => h('code', { style: 'font-size:11px' }, r.id) },
  { title: '名称', key: 'name', minWidth: 140 },
  { title: '类别', key: 'category', width: 110, render: (r) => h(NTag, { size: 'small' }, { default: () => r.category || 'misc' }) },
  { title: '版本', key: 'version', width: 80 },
  { title: '描述', key: 'description', minWidth: 200, ellipsis: { tooltip: true } },
  {
    title: '操作', key: 'actions', width: 100,
    render: (row) => h('a', { style: 'color:#2080f0;cursor:pointer', onClick: () => selectOp(row) }, '选择'),
  },
]

async function load() {
  loading.value = true; error.value = null
  try {
    const res = await http.get<{ count: number; operators: ScorerOperator[] }>('/api/v1/score/operators')
    operators.value = res.data?.operators || []
    applyFilter()
  } catch (e) {
    error.value = (e as Error).message || '加载算子失败'
    // Fallback: use legacy /api/v1/score/list
    try {
      const legacy = await http.get<{ count: number; operators: ScorerOperator[] }>('/api/v1/score/list')
      operators.value = legacy.data?.operators || []
      applyFilter()
    } catch {
      operators.value = FALLBACK_OPERATORS
      applyFilter()
    }
  } finally { loading.value = false }
}

function applyFilter() {
  const k = keyword.value.toLowerCase().trim()
  const c = categoryFilter.value
  filtered.value = operators.value.filter((op) => {
    if (c && op.category !== c) return false
    if (!k) return true
    return (
      op.id.toLowerCase().includes(k) ||
      (op.name || '').toLowerCase().includes(k) ||
      (op.category || '').toLowerCase().includes(k)
    )
  })
}

function onSearch() { applyFilter() }
function onReset() { keyword.value = ''; categoryFilter.value = null; applyFilter() }

function selectOp(op: ScorerOperator) {
  selectedOp.value = op
  lastResult.value = null
}

async function onRun() {
  if (!selectedOp.value) { message.warning('请先选择算子'); return }
  running.value = true
  const t0 = performance.now()
  try {
    const body = {
      op_id: selectedOp.value.id,
      data: parseLoose(form.data),
      params: parseJsonOrDefault(form.params, {}),
    }
    const res = await http.post<{ result: any; elapsed_ms: number }>('/api/v1/score/run', body)
    lastResult.value = res.data
    lastElapsedMs.value = res.data?.elapsed_ms ?? Math.round(performance.now() - t0)
    message.success('评分完成')
  } catch (e) {
    message.error((e as Error).message || '评分失败')
    lastResult.value = { error: (e as Error).message }
    lastElapsedMs.value = Math.round(performance.now() - t0)
  } finally { running.value = false }
}

async function onBatchRun() {
  if (!selectedOp.value) { message.warning('请先选择算子'); return }
  running.value = true
  const t0 = performance.now()
  try {
    const body = {
      steps: [
        { op_id: selectedOp.value.id, params: parseJsonOrDefault(form.params, {}) },
      ],
      data: parseLoose(form.data),
    }
    const res = await http.post<{ scores: Record<string, any>; elapsed_ms: number }>('/api/v1/score/run/batch', body)
    lastResult.value = res.data
    lastElapsedMs.value = res.data?.elapsed_ms ?? Math.round(performance.now() - t0)
    message.success('批量评分完成')
  } catch (e) {
    message.error((e as Error).message || '批量评分失败')
    lastResult.value = { error: (e as Error).message }
  } finally { running.value = false }
}

function onClearResult() { lastResult.value = null; lastElapsedMs.value = 0 }

function parseLoose(s: string): unknown {
  try { return JSON.parse(s) } catch { return s }
}
function parseJsonOrDefault(s: string, fallback: unknown): unknown {
  try { return JSON.parse(s) } catch { return fallback }
}

const lastResultText = computed(() => lastResult.value ? JSON.stringify(lastResult.value, null, 2) : '')

const FALLBACK_OPERATORS: ScorerOperator[] = [
  { id: 'score.aesthetic.v1', name: '美学评分', category: 'aesthetic', version: '1.0.0', description: '图片美学质量评分' },
  { id: 'score.quality.v1', name: '通用质量', category: 'quality', version: '1.0.0', description: '图像 / 视频通用质量' },
  { id: 'score.safety.v1', name: '安全过滤', category: 'safety', version: '1.0.0', description: 'NSFW / 政治敏感检测' },
  { id: 'score.text-coherence.v1', name: '文本连贯', category: 'misc', version: '1.0.0', description: '文本文本一致性' },
  { id: 'score.image-text-align.v1', name: '图文对齐', category: 'multimodal', version: '1.0.0', description: '图文相似度' },
]

onMounted(load)
</script>

<style scoped>
.scoring-view { padding: 16px; }
.header-card { margin-bottom: 12px; }
.kpi-card { min-height: 100px; }
.kpi-value { margin: 4px 0; }
.scoring-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
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
  max-height: 240px;
  overflow: auto;
}
</style>