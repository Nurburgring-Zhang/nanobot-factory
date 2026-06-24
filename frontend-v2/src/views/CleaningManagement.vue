<template>
  <div class="page-root">
    <NCard title="清洗管理" :bordered="false">
      <SearchBar v-model="keyword" placeholder="搜索规则名/状态" @search="onSearch" @reset="onReset">
        <template #extra>
          <PermissionGuard :roles="['admin', 'engineer']">
            <ActionButton type="primary" @click="openCreate">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              新建清洗任务
            </ActionButton>
          </PermissionGuard>
        </template>
      </SearchBar>
      <DataTable :columns="columns" :data="rows" :loading="loading" :error="error" :total="total"
        v-model:page="page" v-model:page-size="pageSize"
        :row-key="(r: CleaningItem) => r.id" @refresh="load">
        <template #empty><NEmpty description="暂无清洗任务" /></template>
      </DataTable>
    </NCard>
    <ModalForm v-model:show="modalShow" :title="editingId ? '编辑清洗任务' : '新建清洗任务'" v-model="form"
      :rules="rules" :submitting="submitting" @submit="onSubmit">
      <template #default="{ form: f }">
        <NFormItem label="资产 ID" path="asset_id">
          <NInput v-model:value="(f as CleaningCreate).asset_id" />
        </NFormItem>
        <NFormItem label="清洗规则" path="rule">
          <NInput v-model:value="(f as CleaningCreate).rule" type="textarea" :rows="3" />
        </NFormItem>
      </template>
    </ModalForm>
  </div>
</template>

<script setup lang="ts">
import { h, onMounted, ref, reactive } from 'vue'
import { NCard, NEmpty, NFormItem, NInput, NIcon, NTag, NSpace, useMessage, type DataTableColumns, type FormRules } from 'naive-ui'
import { AddOutline, CreateOutline, TrashOutline } from '@vicons/ionicons5'
import SearchBar from '@/components/SearchBar.vue'
import DataTable from '@/components/DataTable.vue'
import ActionButton from '@/components/ActionButton.vue'
import ModalForm from '@/components/ModalForm.vue'
import PermissionGuard from '@/components/PermissionGuard.vue'
import { listCleanings, createCleaning, updateCleaning, deleteCleaning, type CleaningItem, type CleaningCreate } from '@/api/cleaning'

const message = useMessage()
const keyword = ref('')
const page = ref(1); const pageSize = ref(20)
const rows = ref<CleaningItem[]>([]); const total = ref(0)
const loading = ref(false); const error = ref<string | null>(null)

const modalShow = ref(false)
const editingId = ref<string | number | null>(null)
const submitting = ref(false)
const form = reactive<CleaningCreate>({ asset_id: '', rule: '' })

const rules: FormRules = {
  asset_id: { required: true, message: '请输入资产 ID', trigger: 'blur' },
  rule: { required: true, message: '请输入清洗规则', trigger: 'blur' }
}
const statusType: Record<CleaningItem['status'], 'default' | 'info' | 'success' | 'warning' | 'error'> = {
  queued: 'default', running: 'info', completed: 'success', failed: 'error'
}

const columns: DataTableColumns<CleaningItem> = [
  { title: 'ID', key: 'id', width: 80 },
  { title: '资产 ID', key: 'asset_id', width: 120 },
  { title: '规则', key: 'rule', minWidth: 200, ellipsis: { tooltip: true } },
  { title: '状态', key: 'status', width: 100, render: (row) => h(NTag, { type: statusType[row.status] }, { default: () => row.status }) },
  { title: '结果数', key: 'result_count', width: 100 },
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
    const res = await listCleanings({ page: page.value, page_size: pageSize.value, keyword: keyword.value })
    rows.value = res.items; total.value = res.total
  } catch (e) {
    error.value = (e as Error).message || '加载清洗任务失败'; rows.value = []; total.value = 0
  } finally { loading.value = false }
}
function onSearch() { page.value = 1; load() }
function onReset() { keyword.value = ''; page.value = 1; load() }
function openCreate() {
  editingId.value = null
  Object.assign(form, { asset_id: '', rule: '' } as CleaningCreate)
  modalShow.value = true
}
function openEdit(row: CleaningItem) {
  editingId.value = row.id
  Object.assign(form, { asset_id: String(row.asset_id), rule: row.rule } as CleaningCreate)
  modalShow.value = true
}
async function onSubmit(payload: CleaningCreate) {
  submitting.value = true
  try {
    if (editingId.value !== null) {
      await updateCleaning(editingId.value, payload); message.success('更新成功')
    } else {
      await createCleaning(payload); message.success('创建成功')
    }
    modalShow.value = false; await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  } finally { submitting.value = false }
}
async function onDelete(row: CleaningItem) {
  if (!window.confirm('确认删除该清洗任务 ?')) return
  try { await deleteCleaning(row.id); message.success('删除成功'); await load() }
  catch (e) { message.error((e as Error).message || '删除失败') }
}

onMounted(load)
</script>

<style scoped>
.page-root { padding: 16px; }
</style>
