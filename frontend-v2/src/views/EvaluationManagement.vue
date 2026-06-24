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
          <NInput v-model:value="(f as EvaluationCreate).dataset_id" />
        </NFormItem>
        <NFormItem label="模型" path="model">
          <NInput v-model:value="(f as EvaluationCreate).model" />
        </NFormItem>
        <NFormItem label="指标" path="metric">
          <NInput v-model:value="(f as EvaluationCreate).metric" />
        </NFormItem>
        <NFormItem label="分值" path="value">
          <NInputNumber v-model:value="(f as EvaluationCreate).value" :min="0" :max="100" />
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

const message = useMessage()
const keyword = ref('')
const page = ref(1); const pageSize = ref(20)
const rows = ref<EvaluationItem[]>([]); const total = ref(0)
const loading = ref(false); const error = ref<string | null>(null)

const modalShow = ref(false)
const editingId = ref<string | number | null>(null)
const submitting = ref(false)
const form = reactive<EvaluationCreate>({ dataset_id: '', model: '', metric: '', value: 0 })

const rules: FormRules = {
  dataset_id: { required: true, message: '请输入数据集 ID', trigger: 'blur' },
  model: { required: true, message: '请输入模型名', trigger: 'blur' },
  metric: { required: true, message: '请输入指标', trigger: 'blur' }
}

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
    const res = await listEvaluations({ page: page.value, page_size: pageSize.value, keyword: keyword.value })
    rows.value = res.items; total.value = res.total
  } catch (e) {
    error.value = (e as Error).message || '加载评测失败'; rows.value = []; total.value = 0
  } finally { loading.value = false }
}
function onSearch() { page.value = 1; load() }
function onReset() { keyword.value = ''; page.value = 1; load() }
function openCreate() {
  editingId.value = null
  Object.assign(form, { dataset_id: '', model: '', metric: '', value: 0 } as EvaluationCreate)
  modalShow.value = true
}
function openEdit(row: EvaluationItem) {
  editingId.value = row.id
  Object.assign(form, { dataset_id: String(row.dataset_id), model: row.model, metric: row.metric, value: row.value } as EvaluationCreate)
  modalShow.value = true
}
async function onSubmit(payload: EvaluationCreate) {
  submitting.value = true
  try {
    if (editingId.value !== null) {
      await updateEvaluation(editingId.value, payload); message.success('更新成功')
    } else {
      await createEvaluation(payload); message.success('创建成功')
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
