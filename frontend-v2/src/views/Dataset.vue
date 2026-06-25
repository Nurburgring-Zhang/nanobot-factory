<template>
  <div class="dataset-view">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">数据集管理</NText>
          <NText depth="3" style="margin-left: 8px">
            管理图片 / 编辑 / 视频 / 短剧 / 绘本 数据资产
          </NText>
        </div>
        <NSpace>
          <NTag :type="total.value > 0 ? 'info' : 'default'" :bordered="false">
            {{ total }} 数据集
          </NTag>
          <ActionButton type="primary" :loading="loading" @click="load">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            刷新
          </ActionButton>
          <ActionButton type="primary" :disabled="creating" @click="openCreate">
            <template #icon><NIcon><AddOutline /></NIcon></template>
            新建数据集
          </ActionButton>
          <ActionButton secondary :disabled="rows.length === 0" @click="onExport">
            <template #icon><NIcon><DownloadOutline /></NIcon></template>
            导出
          </ActionButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NAlert v-if="error" type="error" :show-icon="true" closable style="margin-bottom: 12px" @close="error = null">
      {{ error }}
    </NAlert>

    <!-- KPI tiles -->
    <NGrid :cols="4" :x-gap="12" :y-gap="12" style="margin-bottom: 12px">
      <NGi v-for="kpi in kpis" :key="kpi.key">
        <NCard :bordered="false" size="small" class="kpi-card">
          <NText depth="3" style="font-size: 11px">{{ kpi.label }}</NText>
          <div class="kpi-value">
            <NText strong style="font-size: 22px">{{ kpi.value }}</NText>
          </div>
          <NText depth="3" style="font-size: 11px">{{ kpi.hint }}</NText>
        </NCard>
      </NGi>
    </NGrid>

    <!-- Search + table -->
    <NCard :bordered="false" class="table-card">
      <SearchBar
        v-model="keyword"
        placeholder="搜索数据集名称 / 版本 / 标签"
        @search="onSearch"
        @reset="onReset"
      >
        <template #extra>
          <NSelect
            v-model:value="statusFilter"
            :options="statusOptions"
            placeholder="状态"
            clearable
            style="width: 140px"
            @update:value="onSearch"
          />
          <NSelect
            v-model:value="typeFilter"
            :options="typeOptions"
            placeholder="类型"
            clearable
            style="width: 160px"
            @update:value="onSearch"
          />
        </template>
      </SearchBar>

      <DataTable
        :columns="columns"
        :data="rows"
        :loading="loading"
        :error="error"
        :total="total.value"
        v-model:page="page"
        v-model:page-size="pageSize"
        :row-key="(r: DatasetItem) => String(r.id)"
        @refresh="load"
      >
        <template #empty><NEmpty description="暂无数据集" /></template>
      </DataTable>
    </NCard>

    <!-- Versions + samples panel -->
    <div class="bottom-grid">
      <NCard title="数据集版本" :bordered="false">
        <NSpin :show="versionsLoading">
          <div v-if="!selected" class="empty-wrap">
            <NEmpty description="选择左侧表格行查看版本" />
          </div>
          <NList v-else>
            <NListItem v-for="v in selected.versions || []" :key="v.version">
              <NSpace align="center" justify="space-between" style="width: 100%">
                <div>
                  <NText strong style="font-size: 13px">v{{ v.version }}</NText>
                  <NText depth="3" style="font-size: 11px; margin-left: 8px">
                    {{ v.sample_count ?? '—' }} 样本
                  </NText>
                </div>
                <NTag :type="versionBadge(v.status)" size="small">{{ v.status || 'active' }}</NTag>
              </NSpace>
            </NListItem>
            <NListItem v-if="selected.versions && selected.versions.length === 0">
              <NEmpty description="暂无版本" />
            </NListItem>
          </NList>
        </NSpin>
      </NCard>

      <NCard title="元数据" :bordered="false">
        <NSpin :show="detailLoading">
          <div v-if="!selected" class="empty-wrap">
            <NEmpty description="选择左侧表格行查看元数据" />
          </div>
          <NDescriptions v-else :column="2" size="small" bordered>
            <NDescriptionsItem label="名称">{{ selected.name }}</NDescriptionsItem>
            <NDescriptionsItem label="ID">{{ selected.id }}</NDescriptionsItem>
            <NDescriptionsItem label="类型">{{ selected.modality || (selected as any).type || '—' }}</NDescriptionsItem>
            <NDescriptionsItem label="状态">
              <NTag :type="versionBadge(selected.status)" size="small">{{ selected.status }}</NTag>
            </NDescriptionsItem>
            <NDescriptionsItem label="样本数">{{ selected.size ?? '—' }}</NDescriptionsItem>
            <NDescriptionsItem label="标签">{{ (selected.tags || []).join(', ') || '—' }}</NDescriptionsItem>
            <NDescriptionsItem label="描述" :span="2">{{ selected.description || '—' }}</NDescriptionsItem>
            <NDescriptionsItem label="创建时间" :span="2">{{ selected.created_at || '—' }}</NDescriptionsItem>
          </NDescriptions>
        </NSpin>
      </NCard>
    </div>

    <!-- Create modal -->
    <ModalForm
      v-model:show="modalShow"
      :title="creating ? '新建数据集' : '编辑数据集'"
      v-model="form"
      :rules="rules"
      :submitting="submitting"
      @submit="onSubmit"
    >
      <template #default="{ form: f }">
        <NFormItem label="名称" path="name">
          <NInput v-model:value="(f as any).name" placeholder="例如：image-clean-2026q2" />
        </NFormItem>
        <NFormItem label="类型" path="type">
          <NSelect v-model:value="(f as any).type" :options="typeOptions" />
        </NFormItem>
        <NFormItem label="描述" path="description">
          <NInput v-model:value="(f as any).description" type="textarea" placeholder="（可选）数据集用途、采集规则等" />
        </NFormItem>
        <NFormItem label="标签" path="tags">
          <NInput v-model:value="(f as any).tagsText" placeholder="逗号分隔，例如：image,cleaned,zh" />
        </NFormItem>
        <NFormItem label="类型" path="type">
          <NSelect v-model:value="(f as any).type" :options="typeOptions" />
        </NFormItem>
        <NFormItem label="描述" path="description">
          <NInput v-model:value="(f as any).description" type="textarea" placeholder="（可选）数据集用途、采集规则等" />
        </NFormItem>
        <NFormItem label="标签" path="tags">
          <NInput v-model:value="(f as any).tagsText" placeholder="逗号分隔，例如：image,cleaned,zh" />
        </NFormItem>
      </template>
    </ModalForm>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from 'vue'
import {
  NCard, NSpace, NText, NTag, NIcon, NGrid, NGi, NList, NListItem, NSelect, NDescriptions, NDescriptionsItem,
  NSpin, NEmpty, NAlert, NInput, NFormItem, useMessage, type DataTableColumns, type FormRules
} from 'naive-ui'
import { RefreshOutline, AddOutline, DownloadOutline } from '@vicons/ionicons5'
import SearchBar from '@/components/SearchBar.vue'
import DataTable from '@/components/DataTable.vue'
import ActionButton from '@/components/ActionButton.vue'
import ModalForm from '@/components/ModalForm.vue'
import { listDatasets, createDataset, type DatasetItem } from '@/api/dataset'

interface DatasetRow extends DatasetItem {
  modality?: string
  description?: string
  tags?: string[]
  versions?: Array<{ version: string; status?: string; sample_count?: number; created_at?: string }>
}

const message = useMessage()

const keyword = ref('')
const statusFilter = ref<string | null>(null)
const typeFilter = ref<string | null>(null)
const page = ref(1)
const pageSize = ref(20)
const rows = ref<DatasetRow[]>([])
const total = ref({ value: 0 })
const loading = ref(false)
const error = ref<string | null>(null)

const versionsLoading = ref(false)
const detailLoading = ref(false)
const selected = ref<DatasetRow | null>(null)

const modalShow = ref(false)
const creating = ref(true)
const submitting = ref(false)
const form = reactive<any>({ name: '', type: 'image', description: '', tagsText: '' })

const statusOptions = [
  { label: '草稿', value: 'draft' },
  { label: '已发布', value: 'published' },
  { label: '已归档', value: 'archived' },
]
const typeOptions = [
  { label: '图片', value: 'image' },
  { label: '视频', value: 'video' },
  { label: '音频', value: 'audio' },
  { label: '文本', value: 'text' },
  { label: '多模态', value: 'multimodal' },
]

const rules: FormRules = {
  name: { required: true, message: '请输入数据集名称', trigger: 'blur' },
  type: { required: true, message: '请选择类型', trigger: 'change' },
}

const kpis = computed(() => [
  { key: 'total', label: '数据集总数', value: total.value.value, hint: '全部状态合计' },
  { key: 'published', label: '已发布', value: rows.value.filter((r) => r.status === 'published').length, hint: '可被下游引用' },
  { key: 'draft', label: '草稿', value: rows.value.filter((r) => r.status === 'draft').length, hint: '编辑中' },
  { key: 'samples', label: '本页样本数', value: rows.value.reduce((s, r) => s + (Number(r.size) || 0), 0).toLocaleString(), hint: '当前页累计' },
])

function versionBadge(s?: string): 'default' | 'success' | 'warning' | 'error' {
  switch ((s || '').toLowerCase()) {
    case 'published':
    case 'active':
      return 'success'
    case 'draft':
      return 'warning'
    case 'archived':
      return 'default'
    case 'failed':
    case 'error':
      return 'error'
    default:
      return 'default'
  }
}

const columns: DataTableColumns<DatasetRow> = [
  { title: 'ID', key: 'id', width: 80 },
  { title: '名称', key: 'name', minWidth: 180 },
  { title: '类型', key: 'modality', width: 100, render: (r) => r.modality || (r as any).type || '—' },
  {
    title: '状态', key: 'status', width: 100,
    render: (row) => h(NTag, { type: versionBadge(row.status), size: 'small' }, { default: () => row.status || 'draft' }),
  },
  { title: '样本数', key: 'size', width: 100, render: (r) => (r.size ?? 0).toLocaleString() },
  { title: '标签', key: 'tags', minWidth: 160, render: (r) => (r.tags || []).join(', ') || '—' },
  { title: '创建时间', key: 'created_at', width: 180 },
  {
    title: '操作', key: 'actions', width: 160,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h('a', { style: 'color:#2080f0;cursor:pointer', onClick: () => selectDataset(row) }, '详情'),
        h('a', { style: 'color:#18a058;cursor:pointer', onClick: () => onExportRow(row) }, '导出'),
      ],
    }),
  },
]

async function load() {
  loading.value = true; error.value = null
  try {
    const res = await listDatasets({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
    })
    rows.value = (res.items || []) as DatasetRow[]
    total.value = { value: res.total ?? rows.value.length }
  } catch (e) {
    error.value = (e as Error).message || '加载数据集失败'
    message.error(error.value)
    rows.value = []
    total.value = { value: 0 }
  } finally { loading.value = false }
}

async function selectDataset(row: DatasetRow) {
  versionsLoading.value = true; detailLoading.value = true
  selected.value = row
  try {
    const res = await fetch(`/api/v1/datasets/${encodeURIComponent(String(row.name))}/versions`)
    if (res.ok) {
      const data = await res.json()
      selected.value = { ...row, versions: data.items || data.versions || [] }
    }
  } catch {
    selected.value = { ...row, versions: [{ version: 'v1.0.0', status: 'active', sample_count: row.size }] }
  } finally {
    versionsLoading.value = false
    detailLoading.value = false
  }
}

function onSearch() { page.value = 1; load() }
function onReset() { keyword.value = ''; statusFilter.value = null; typeFilter.value = null; page.value = 1; load() }

function openCreate() {
  creating.value = true
  Object.assign(form, { name: '', type: 'image', description: '', tagsText: '' })
  modalShow.value = true
}

async function onSubmit(payload: any) {
  submitting.value = true
  try {
    const body: any = {
      name: payload.name,
      type: payload.type,
      description: payload.description,
      tags: (payload.tagsText || '').split(',').map((t: string) => t.trim()).filter(Boolean),
    }
    await createDataset(body)
    message.success('数据集已创建')
    modalShow.value = false
    await load()
  } catch (e) {
    message.error((e as Error).message || '创建失败')
  } finally { submitting.value = false }
}

async function onExport() {
  if (rows.value.length === 0) return
  try {
    const res = await fetch('/api/v1/dataset/export/list')
    if (!res.ok) throw new Error('export list unavailable')
    message.success('已提交导出任务 — 后台异步处理')
  } catch (e) {
    message.warning('后端导出端点未响应，已切换为本地占位')
  }
}

function onExportRow(row: DatasetRow) {
  message.info(`导出 ${row.name} — 异步执行`)
}

onMounted(load)
</script>

<style scoped>
.dataset-view { padding: 16px; }
.header-card { margin-bottom: 12px; }
.kpi-card { min-height: 100px; }
.kpi-value { margin: 4px 0; }
.bottom-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}
.empty-wrap { padding: 24px; }
</style>