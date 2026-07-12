<template>
  <div class="page-root">
    <NCard title="评测管理" :bordered="false">
      <SearchBar v-model="keyword" placeholder="搜索模型/指标" @search="onSearch" @reset="onReset">
        <template #extra>
          <PermissionGuard :roles="['admin', 'engineer']">
            <ActionButton type="primary" @click="openCreate">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              新建评测
            </ActionButton>
          </PermissionGuard>
        </template>
      </SearchBar>
      <DataTable :columns="columns" :data="rows" :loading="loading" :error="error" :total="total"
        v-model:page="page" v-model:page-size="pageSize"
        :row-key="(r: EvaluationItem) => r.id" @refresh="load">
        <template #empty><NEmpty description="暂无评测" /></template>
      </DataTable>
    </NCard>
    <ModalForm v-model:show="modalShow" :title="editingId ? '编辑评测' : '新建评测'" v-model="form"
      :rules="rules" :submitting="submitting" @submit="onSubmit">
      <template #default="{ form: f }">
        <NFormItem label="数据集 ID" path="dataset_id">
          <!-- P21 P3 P1 fix (TS2339 + TS2551): cast to EvaluationFormShape so legacy
               field names (dataset_id / model / metric / value) type-check; the
               onSubmit handler converts them to EvaluationCreate. -->
          <NInput v-model:value="(f as EvaluationFormShape).dataset_id" />
        </NFormItem>
        <NFormItem label="模型" path="model">
          <NInput v-model:value="(f as EvaluationFormShape).model" />
        </NFormItem>
        <NFormItem label="指标" path="metric">
          <NInput v-model:value="(f as EvaluationFormShape).metric" />
        </NFormItem>
        <NFormItem label="分值" path="value">
          <NInputNumber v-model:value="(f as EvaluationFormShape).value" :min="0" :max="100" />
        </NFormItem>
      </template>
    </ModalForm>
  </div>
</template>

<script setup lang="ts">
import { h, onMounted, ref, reactive } from 'vue'
import { NCard, NEmpty, NFormItem, NInput, NInputNumber, NIcon, NSpace, useMessage, type DataTableColumns, type FormRules } from 'naive-ui'
import { AddOutline, CreateOutline, TrashOutline } from '@vicons/ionicons5'
import SearchBar from '@/components/SearchBar.vue'
import DataTable from '@/components/DataTable.vue'
import ActionButton from '@/components/ActionButton.vue'
import ModalForm from '@/components/ModalForm.vue'
import PermissionGuard from '@/components/PermissionGuard.vue'
import { listEvaluations, createEvaluation, updateEvaluation, deleteEvaluation, type EvaluationItem, type EvaluationCreate } from '@/api/evaluation'

// P21 P3 P1 fix (TS2339 + TS2352 + TS2551): the legacy form schema used
// {dataset_id, model, metric, value} but the backend EvaluationCreate uses
// {name, model_name, dataset_name, dataset_version, metrics, sample_size}.
// Extend the type with the legacy fields as optional so the v-model bindings
// compile; the onSubmit handler still produces a proper EvaluationCreate
// via the helpers below.
interface EvaluationFormShape extends Partial<EvaluationCreate> {
  dataset_id?: string
  model?: string
  metric?: string
  value?: number
  [key: string]: unknown
}

const message = useMessage()
const keyword = ref('')
const page = ref(1); const pageSize = ref(20)
const rows = ref<EvaluationItem[]>([]); const total = ref(0)
const loading = ref(false); const error = ref<string | null>(null)

const modalShow = ref(false)
const editingId = ref<string | number | null>(null)
const submitting = ref(false)
const form = reactive<EvaluationFormShape>({ dataset_id: '', model: '', metric: '', value: 0 })

// P21 P3 P1 fix (TS2551 + TS2353): legacy form fields -> backend EvaluationCreate
function toBackendCreate(f: EvaluationFormShape): EvaluationCreate {
  return {
    name: f.dataset_id || f.name || '',
    model_name: f.model || f.model_name || '',
    dataset_name: f.dataset_id || f.dataset_name || '',
    dataset_version: f.dataset_version || 'v1',
    metrics: f.metric ? [f.metric] : (f.metrics || ['accuracy']),
    sample_size: typeof f.value === 'number' && f.value > 0 ? Math.min(100000, Math.max(1, f.value)) : (f.sample_size ?? 100),
    description: f.description || ''
  }
}

const rules: FormRules = {
  dataset_id: { required: true, message: '请输入数据集 ID', trigger: 'blur' },
  model: { required: true, message: '请输入模型名', trigger: 'blur' },
  metric: { required: true, message: '请输入指标', trigger: 'blur' }
} as FormRules

const columns: DataTableColumns<EvaluationItem> = [
  { title: 'ID', key: 'id', width: 80 },
  { title: '数据集 ID', key: 'dataset_id', width: 120 },
  { title: '模型', key: 'model', width: 160 },
  { title: '指标', key: 'metric', width: 120 },
  { title: '分值', key: 'value', width: 100 },
  { title: '创建时间', key: 'created_at', width: 180 },
  {
    title: '操作', key: 'actions', width: 180,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(PermissionGuard, { roles: ['admin', 'engineer'] }, { default: () => h(ActionButton, { icon: CreateOutline, onClick: () => openEdit(row) }, { default: () => '编辑' }) }),
        h(PermissionGuard, { roles: ['admin'] }, { default: () => h(ActionButton, { type: 'error', icon: TrashOutline, onClick: () => onDelete(row) }, { default: () => '删除' }) })
      ]
    })
  }
]

async function load() {
  loading.value = true; error.value = null
  try {
    // P21 P3 P1 fix (TS2353): listEvaluations accepts {model_name, status_filter, limit, offset},
    // not {page, page_size, keyword}. Map legacy pagination fields.
    const res = await listEvaluations({
      model_name: keyword.value || undefined,
      limit: pageSize.value,
      offset: Math.max(0, (page.value - 1) * pageSize.value)
    })
    rows.value = res.evaluations; total.value = res.count
  } catch (e) {
    error.value = (e as Error).message || '加载评测失败'; rows.value = []; total.value = 0
  } finally { loading.value = false }
}
function onSearch() { page.value = 1; load() }
function onReset() { keyword.value = ''; page.value = 1; load() }
function openCreate() {
  editingId.value = null
  Object.assign(form, { dataset_id: '', model: '', metric: '', value: 0 } as EvaluationFormShape)
  modalShow.value = true
}
function openEdit(row: EvaluationItem) {
  editingId.value = row.id
  // P21 P3 P1 fix (TS2551): backend EvaluationItem has metrics: string[], not metric: string
  const firstMetric = Array.isArray((row as any).metrics) ? (row as any).metrics[0] : ''
  Object.assign(form, {
    dataset_id: String((row as any).dataset_name ?? row.id),
    model: row.model_name,
    metric: firstMetric,
    value: row.sample_size
  } as EvaluationFormShape)
  modalShow.value = true
}
async function onSubmit(payload: EvaluationFormShape) {
  submitting.value = true
  try {
    const backend = toBackendCreate(payload)
    if (editingId.value !== null) {
      await updateEvaluation(editingId.value, { description: backend.description, metrics: backend.metrics, sample_size: backend.sample_size }); message.success('更新成功')
    } else {
      await createEvaluation(backend); message.success('创建成功')
    }
    modalShow.value = false; await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  } finally { submitting.value = false }
}
async function onDelete(row: EvaluationItem) {
  if (!window.confirm('确认删除该评测 ?')) return
  try { await deleteEvaluation(row.id); message.success('删除成功'); await load() }
  catch (e) { message.error((e as Error).message || '删除失败') }
}

onMounted(load)
</script>

<style scoped>
.page-root { padding: 16px; }
</style>
