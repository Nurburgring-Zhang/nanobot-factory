<template>
  <div class="page-root">
    <NCard title="智能体管理" :bordered="false">
      <SearchBar v-model="keyword" placeholder="搜索名称/类型" @search="onSearch" @reset="onReset">
        <template #extra>
          <PermissionGuard :roles="['admin', 'engineer']">
            <ActionButton type="primary" @click="openCreate">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              新建智能体
            </ActionButton>
          </PermissionGuard>
        </template>
      </SearchBar>
      <DataTable :columns="columns" :data="rows" :loading="loading" :error="error" :total="total"
        v-model:page="page" v-model:page-size="pageSize"
        :row-key="(r: AgentItem) => r.id" @refresh="load">
        <template #empty><NEmpty description="暂无智能体" /></template>
      </DataTable>
    </NCard>
    <ModalForm v-model:show="modalShow" :title="editingId ? '编辑智能体' : '新建智能体'" v-model="form"
      :rules="rules" :submitting="submitting" @submit="onSubmit">
      <template #default="{ form: f }">
        <NFormItem label="名称" path="name">
          <NInput v-model:value="(f as AgentCreate).name" />
        </NFormItem>
        <NFormItem label="类型" path="kind">
          <NInput v-model:value="(f as AgentCreate).kind" placeholder="chat / task / code" />
        </NFormItem>
        <NFormItem label="状态" path="status">
          <NSelect v-model:value="(f as AgentCreate).status" :options="statusOptions" />
        </NFormItem>
      </template>
    </ModalForm>
  </div>
</template>

<script setup lang="ts">
import { h, onMounted, ref, reactive } from 'vue'
import { NCard, NEmpty, NFormItem, NInput, NSelect, NIcon, NTag, NSpace, useMessage, type DataTableColumns, type FormRules } from 'naive-ui'
import { AddOutline, CreateOutline, TrashOutline, PlayOutline } from '@vicons/ionicons5'
import SearchBar from '@/components/SearchBar.vue'
import DataTable from '@/components/DataTable.vue'
import ActionButton from '@/components/ActionButton.vue'
import ModalForm from '@/components/ModalForm.vue'
import PermissionGuard from '@/components/PermissionGuard.vue'
import { listAgents, createAgent, updateAgent, deleteAgent, type AgentItem, type AgentCreate } from '@/api/agent'

const message = useMessage()
const keyword = ref('')
const page = ref(1); const pageSize = ref(20)
const rows = ref<AgentItem[]>([]); const total = ref(0)
const loading = ref(false); const error = ref<string | null>(null)

const modalShow = ref(false)
const editingId = ref<string | number | null>(null)
const submitting = ref(false)
const form = reactive<AgentCreate>({ name: '', kind: 'chat', status: 'idle' })

const statusOptions = [
  { label: '空闲', value: 'idle' },
  { label: '运行中', value: 'running' },
  { label: '已停止', value: 'stopped' },
  { label: '异常', value: 'error' }
]
const rules: FormRules = {
  name: { required: true, message: '请输入名称', trigger: 'blur' },
  kind: { required: true, message: '请输入类型', trigger: 'blur' }
}
const statusType: Record<AgentItem['status'], 'default' | 'success' | 'info' | 'error'> = {
  idle: 'default', running: 'info', stopped: 'default', error: 'error'
}

const columns: DataTableColumns<AgentItem> = [
  { title: 'ID', key: 'id', width: 80 },
  { title: '名称', key: 'name', minWidth: 160 },
  { title: '类型', key: 'kind', width: 120 },
  { title: '状态', key: 'status', width: 100, render: (row) => h(NTag, { type: statusType[row.status] }, { default: () => row.status }) },
  { title: '创建时间', key: 'created_at', width: 180 },
  {
    title: '操作', key: 'actions', width: 240,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(PermissionGuard, { roles: ['admin', 'engineer'] }, { default: () => h(ActionButton, { icon: PlayOutline, onClick: () => message.info(`启动 ${row.name}`) }, { default: () => '启动' }) }),
        h(PermissionGuard, { roles: ['admin', 'engineer'] }, { default: () => h(ActionButton, { icon: CreateOutline, onClick: () => openEdit(row) }, { default: () => '编辑' }) }),
        h(PermissionGuard, { roles: ['admin'] }, { default: () => h(ActionButton, { type: 'error', icon: TrashOutline, onClick: () => onDelete(row) }, { default: () => '删除' }) })
      ]
    })
  }
]

async function load() {
  loading.value = true; error.value = null
  try {
    const res = await listAgents({ page: page.value, page_size: pageSize.value, keyword: keyword.value })
    rows.value = res.items; total.value = res.total
  } catch (e) {
    error.value = (e as Error).message || '加载智能体失败'; rows.value = []; total.value = 0
  } finally { loading.value = false }
}
function onSearch() { page.value = 1; load() }
function onReset() { keyword.value = ''; page.value = 1; load() }
function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', kind: 'chat', status: 'idle' } as AgentCreate)
  modalShow.value = true
}
function openEdit(row: AgentItem) {
  editingId.value = row.id
  Object.assign(form, { name: row.name, kind: row.kind, status: row.status } as AgentCreate)
  modalShow.value = true
}
async function onSubmit(payload: AgentCreate) {
  submitting.value = true
  try {
    if (editingId.value !== null) {
      await updateAgent(editingId.value, payload); message.success('更新成功')
    } else {
      await createAgent(payload); message.success('创建成功')
    }
    modalShow.value = false; await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  } finally { submitting.value = false }
}
async function onDelete(row: AgentItem) {
  if (!window.confirm(`确认删除智能体 ${row.name} ?`)) return
  try { await deleteAgent(row.id); message.success('删除成功'); await load() }
  catch (e) { message.error((e as Error).message || '删除失败') }
}

onMounted(load)
</script>

<style scoped>
.page-root { padding: 16px; }
</style>
