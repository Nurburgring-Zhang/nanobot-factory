<template>
  <div class="page-root">
    <NCard title="数据集管理" :bordered="false">
      <SearchBar v-model="keyword" placeholder="搜索数据集名/版本" @search="onSearch" @reset="onReset">
        <template #extra>
          <PermissionGuard :roles="['admin', 'engineer']">
            <ActionButton type="primary" @click="openCreate">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              新建数据集
            </ActionButton>
          </PermissionGuard>
        </template>
      </SearchBar>
      <DataTable :columns="columns" :data="rows" :loading="loading" :error="error" :total="total"
        v-model:page="page" v-model:page-size="pageSize"
        :row-key="(r: DatasetItem) => r.id" @refresh="load">
        <template #empty><NEmpty description="暂无数据集" /></template>
      </DataTable>
    </NCard>
    <ModalForm v-model:show="modalShow" :title="editingId ? '编辑数据集' : '新建数据集'" v-model="form"
      :rules="rules" :submitting="submitting" @submit="onSubmit">
      <template #default="{ form: f }">
        <NFormItem label="名称" path="name">
          <NInput v-model:value="(f as DatasetCreate).name" />
        </NFormItem>
        <NFormItem label="版本" path="version">
          <NInput v-model:value="(f as DatasetCreate).version" placeholder="v1.0.0" />
        </NFormItem>
        <NFormItem label="状态" path="status">
          <NSelect v-model:value="(f as DatasetCreate).status" :options="statusOptions" />
        </NFormItem>
      </template>
    </ModalForm>
  </div>
</template>

<script setup lang="ts">
import { h, onMounted, ref, reactive } from 'vue'
import { NCard, NEmpty, NFormItem, NInput, NSelect, NIcon, NTag, NSpace, useMessage, type DataTableColumns, type FormRules } from 'naive-ui'
import { AddOutline, CreateOutline, TrashOutline } from '@vicons/ionicons5'
import SearchBar from '@/components/SearchBar.vue'
import DataTable from '@/components/DataTable.vue'
import ActionButton from '@/components/ActionButton.vue'
import ModalForm from '@/components/ModalForm.vue'
import PermissionGuard from '@/components/PermissionGuard.vue'
import { listDatasets, createDataset, updateDataset, deleteDataset, type DatasetItem, type DatasetCreate } from '@/api/dataset'

const message = useMessage()
const keyword = ref('')
const page = ref(1); const pageSize = ref(20)
const rows = ref<DatasetItem[]>([]); const total = ref(0)
const loading = ref(false); const error = ref<string | null>(null)

const modalShow = ref(false)
const editingId = ref<string | number | null>(null)
const submitting = ref(false)
const form = reactive<DatasetCreate>({ name: '', version: 'v1.0.0', status: 'draft' })

const statusOptions = [
  { label: '草稿', value: 'draft' },
  { label: '已发布', value: 'published' },
  { label: '已归档', value: 'archived' }
]
const rules: FormRules = {
  name: { required: true, message: '请输入名称', trigger: 'blur' },
  version: { required: true, message: '请输入版本', trigger: 'blur' }
}
const statusType: Record<DatasetItem['status'], 'default' | 'success' | 'warning'> = {
  draft: 'default', published: 'success', archived: 'warning'
}

const columns: DataTableColumns<DatasetItem> = [
  { title: 'ID', key: 'id', width: 80 },
  { title: '名称', key: 'name', minWidth: 180 },
  { title: '版本', key: 'version', width: 100 },
  { title: '大小', key: 'size', width: 100 },
  { title: '状态', key: 'status', width: 100, render: (row) => h(NTag, { type: statusType[row.status] }, { default: () => row.status }) },
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
    const res = await listDatasets({ page: page.value, page_size: pageSize.value, keyword: keyword.value })
    rows.value = res.items; total.value = res.total
  } catch (e) {
    error.value = (e as Error).message || '加载数据集失败'; rows.value = []; total.value = 0
  } finally { loading.value = false }
}
function onSearch() { page.value = 1; load() }
function onReset() { keyword.value = ''; page.value = 1; load() }
function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', version: 'v1.0.0', status: 'draft' } as DatasetCreate)
  modalShow.value = true
}
function openEdit(row: DatasetItem) {
  editingId.value = row.id
  Object.assign(form, { name: row.name, version: row.version, status: row.status } as DatasetCreate)
  modalShow.value = true
}
async function onSubmit(payload: DatasetCreate) {
  submitting.value = true
  try {
    if (editingId.value !== null) {
      await updateDataset(editingId.value, payload); message.success('更新成功')
    } else {
      await createDataset(payload); message.success('创建成功')
    }
    modalShow.value = false; await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  } finally { submitting.value = false }
}
async function onDelete(row: DatasetItem) {
  if (!window.confirm(`确认删除数据集 ${row.name} ?`)) return
  try { await deleteDataset(row.id); message.success('删除成功'); await load() }
  catch (e) { message.error((e as Error).message || '删除失败') }
}

onMounted(load)
</script>

<style scoped>
.page-root { padding: 16px; }
</style>
