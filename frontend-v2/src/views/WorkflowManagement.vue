<template>
  <div class="page-root">
    <NCard title="工作流管理" :bordered="false">
      <SearchBar v-model="keyword" placeholder="搜索工作流名" @search="onSearch" @reset="onReset">
        <template #extra>
          <PermissionGuard :roles="['admin', 'engineer']">
            <ActionButton type="primary" @click="openCreate">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              新建工作流
            </ActionButton>
          </PermissionGuard>
        </template>
      </SearchBar>
      <DataTable :columns="columns" :data="rows" :loading="loading" :error="error" :total="total"
        v-model:page="page" v-model:page-size="pageSize"
        :row-key="(r: WorkflowItem) => r.id" @refresh="load">
        <template #empty><NEmpty description="暂无工作流" /></template>
      </DataTable>
    </NCard>
    <ModalForm v-model:show="modalShow" :title="editingId ? '编辑工作流' : '新建工作流'" v-model="form"
      :rules="rules" :submitting="submitting" @submit="onSubmit">
      <template #default="{ form: f }">
        <NFormItem label="名称" path="name">
          <NInput v-model:value="(f as WorkflowCreate).name" />
        </NFormItem>
        <NFormItem label="状态" path="status">
          <NSelect v-model:value="(f as WorkflowCreate).status" :options="statusOptions" />
        </NFormItem>
        <NFormItem label="步骤数" path="steps">
          <NInputNumber v-model:value="(f as WorkflowCreate).steps" :min="1" />
        </NFormItem>
      </template>
    </ModalForm>
  </div>
</template>

<script setup lang="ts">
import { h, onMounted, ref, reactive } from 'vue'
import { NCard, NEmpty, NFormItem, NInput, NSelect, NInputNumber, NIcon, NTag, NSpace, useMessage, type DataTableColumns, type FormRules } from 'naive-ui'
import { AddOutline, CreateOutline, TrashOutline, PlayOutline } from '@vicons/ionicons5'
import SearchBar from '@/components/SearchBar.vue'
import DataTable from '@/components/DataTable.vue'
import ActionButton from '@/components/ActionButton.vue'
import ModalForm from '@/components/ModalForm.vue'
import PermissionGuard from '@/components/PermissionGuard.vue'
import { listWorkflows, createWorkflow, updateWorkflow, deleteWorkflow, type WorkflowItem, type WorkflowCreate } from '@/api/workflow'

const message = useMessage()
const keyword = ref('')
const page = ref(1); const pageSize = ref(20)
const rows = ref<WorkflowItem[]>([]); const total = ref(0)
const loading = ref(false); const error = ref<string | null>(null)

const modalShow = ref(false)
const editingId = ref<string | number | null>(null)
const submitting = ref(false)
const form = reactive<WorkflowCreate>({ name: '', status: 'draft', steps: 1 })

const statusOptions = [
  { label: '草稿', value: 'draft' },
  { label: '运行中', value: 'active' },
  { label: '已暂停', value: 'paused' },
  { label: '已归档', value: 'archived' }
]
const rules: FormRules = {
  name: { required: true, message: '请输入名称', trigger: 'blur' }
}
const statusType: Record<WorkflowItem['status'], 'default' | 'success' | 'warning' | 'info'> = {
  draft: 'default', active: 'success', paused: 'warning', archived: 'info'
}

const columns: DataTableColumns<WorkflowItem> = [
  { title: 'ID', key: 'id', width: 80 },
  { title: '名称', key: 'name', minWidth: 160 },
  { title: '状态', key: 'status', width: 100, render: (row) => h(NTag, { type: statusType[row.status] }, { default: () => row.status }) },
  { title: '步骤数', key: 'steps', width: 100 },
  { title: '创建时间', key: 'created_at', width: 180 },
  {
    title: '操作', key: 'actions', width: 240,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(PermissionGuard, { roles: ['admin', 'engineer'] }, { default: () => h(ActionButton, { icon: PlayOutline, onClick: () => message.info(`触发 ${row.name}`) }, { default: () => '触发' }) }),
        h(PermissionGuard, { roles: ['admin', 'engineer'] }, { default: () => h(ActionButton, { icon: CreateOutline, onClick: () => openEdit(row) }, { default: () => '编辑' }) }),
        h(PermissionGuard, { roles: ['admin'] }, { default: () => h(ActionButton, { type: 'error', icon: TrashOutline, onClick: () => onDelete(row) }, { default: () => '删除' }) })
      ]
    })
  }
]

async function load() {
  loading.value = true; error.value = null
  try {
    const res = await listWorkflows({ page: page.value, page_size: pageSize.value, keyword: keyword.value })
    rows.value = res.items; total.value = res.total
  } catch (e) {
    error.value = (e as Error).message || '加载工作流失败'; rows.value = []; total.value = 0
  } finally { loading.value = false }
}
function onSearch() { page.value = 1; load() }
function onReset() { keyword.value = ''; page.value = 1; load() }
function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', status: 'draft', steps: 1 } as WorkflowCreate)
  modalShow.value = true
}
function openEdit(row: WorkflowItem) {
  editingId.value = row.id
  Object.assign(form, { name: row.name, status: row.status, steps: row.steps ?? 1 } as WorkflowCreate)
  modalShow.value = true
}
async function onSubmit(payload: WorkflowCreate) {
  submitting.value = true
  try {
    if (editingId.value !== null) {
      await updateWorkflow(editingId.value, payload); message.success('更新成功')
    } else {
      await createWorkflow(payload); message.success('创建成功')
    }
    modalShow.value = false; await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  } finally { submitting.value = false }
}
async function onDelete(row: WorkflowItem) {
  if (!window.confirm(`确认删除工作流 ${row.name} ?`)) return
  try { await deleteWorkflow(row.id); message.success('删除成功'); await load() }
  catch (e) { message.error((e as Error).message || '删除失败') }
}

onMounted(load)
</script>

<style scoped>
.page-root { padding: 16px; }
</style>
