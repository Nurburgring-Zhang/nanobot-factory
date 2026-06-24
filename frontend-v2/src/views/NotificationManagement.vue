<template>
  <div class="page-root">
    <NCard title="通知管理" :bordered="false">
      <SearchBar v-model="keyword" placeholder="搜索标题/等级" @search="onSearch" @reset="onReset">
        <template #extra>
          <PermissionGuard :roles="['admin']">
            <ActionButton type="primary" @click="openCreate">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              发送通知
            </ActionButton>
          </PermissionGuard>
          <PermissionGuard :roles="['admin', 'engineer', 'annotator', 'reviewer']">
            <ActionButton @click="markAllRead">
              <template #icon><NIcon><CheckmarkDoneOutline /></NIcon></template>
              全部已读
            </ActionButton>
          </PermissionGuard>
        </template>
      </SearchBar>
      <DataTable :columns="columns" :data="rows" :loading="loading" :error="error" :total="total"
        v-model:page="page" v-model:page-size="pageSize"
        :row-key="(r: NotificationItem) => r.id" @refresh="load">
        <template #empty><NEmpty description="暂无通知" /></template>
      </DataTable>
    </NCard>
    <ModalForm v-model:show="modalShow" :title="editingId ? '编辑通知' : '发送通知'" v-model="form"
      :rules="rules" :submitting="submitting" @submit="onSubmit">
      <template #default="{ form: f }">
        <NFormItem label="标题" path="title">
          <NInput v-model:value="(f as NotificationCreate).title" />
        </NFormItem>
        <NFormItem label="内容" path="body">
          <NInput v-model:value="(f as NotificationCreate).body" type="textarea" :rows="3" />
        </NFormItem>
        <NFormItem label="等级" path="level">
          <NSelect v-model:value="(f as NotificationCreate).level" :options="levelOptions" />
        </NFormItem>
      </template>
    </ModalForm>
  </div>
</template>

<script setup lang="ts">
import { h, onMounted, ref, reactive } from 'vue'
import { NCard, NEmpty, NFormItem, NInput, NSelect, NIcon, NTag, NSpace, useMessage, type DataTableColumns, type FormRules } from 'naive-ui'
import { AddOutline, CreateOutline, TrashOutline, CheckmarkDoneOutline } from '@vicons/ionicons5'
import SearchBar from '@/components/SearchBar.vue'
import DataTable from '@/components/DataTable.vue'
import ActionButton from '@/components/ActionButton.vue'
import ModalForm from '@/components/ModalForm.vue'
import PermissionGuard from '@/components/PermissionGuard.vue'
import { listNotifications, createNotification, updateNotification, deleteNotification, type NotificationItem, type NotificationCreate } from '@/api/notification'

const message = useMessage()
const keyword = ref('')
const page = ref(1); const pageSize = ref(20)
const rows = ref<NotificationItem[]>([]); const total = ref(0)
const loading = ref(false); const error = ref<string | null>(null)

const modalShow = ref(false)
const editingId = ref<string | number | null>(null)
const submitting = ref(false)
const form = reactive<NotificationCreate>({ title: '', body: '', level: 'info' })

const levelOptions = [
  { label: '信息', value: 'info' },
  { label: '成功', value: 'success' },
  { label: '警告', value: 'warning' },
  { label: '错误', value: 'error' }
]
const rules: FormRules = {
  title: { required: true, message: '请输入标题', trigger: 'blur' },
  level: { required: true, message: '请选择等级', trigger: 'change' }
}
const levelType: Record<NotificationItem['level'], 'info' | 'success' | 'warning' | 'error'> = {
  info: 'info', success: 'success', warning: 'warning', error: 'error'
}

const columns: DataTableColumns<NotificationItem> = [
  { title: 'ID', key: 'id', width: 80 },
  {
    title: '已读', key: 'read', width: 70,
    render: (row) => h(NTag, { size: 'small', type: row.read ? 'default' : 'warning', bordered: false }, { default: () => row.read ? '已读' : '未读' })
  },
  { title: '标题', key: 'title', minWidth: 180 },
  { title: '等级', key: 'level', width: 90, render: (row) => h(NTag, { type: levelType[row.level] }, { default: () => row.level }) },
  { title: '内容', key: 'body', minWidth: 200, ellipsis: { tooltip: true } },
  { title: '创建时间', key: 'created_at', width: 180 },
  {
    title: '操作', key: 'actions', width: 180,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(PermissionGuard, { roles: ['admin'] }, { default: () => h(ActionButton, { icon: CreateOutline, onClick: () => openEdit(row) }, { default: () => '编辑' }) }),
        h(PermissionGuard, { roles: ['admin'] }, { default: () => h(ActionButton, { type: 'error', icon: TrashOutline, onClick: () => onDelete(row) }, { default: () => '删除' }) })
      ]
    })
  }
]

async function load() {
  loading.value = true; error.value = null
  try {
    const res = await listNotifications({ page: page.value, page_size: pageSize.value, keyword: keyword.value })
    rows.value = res.items; total.value = res.total
  } catch (e) {
    error.value = (e as Error).message || '加载通知失败'; rows.value = []; total.value = 0
  } finally { loading.value = false }
}
function onSearch() { page.value = 1; load() }
function onReset() { keyword.value = ''; page.value = 1; load() }
function openCreate() {
  editingId.value = null
  Object.assign(form, { title: '', body: '', level: 'info' } as NotificationCreate)
  modalShow.value = true
}
function openEdit(row: NotificationItem) {
  editingId.value = row.id
  Object.assign(form, { title: row.title, body: row.body ?? '', level: row.level } as NotificationCreate)
  modalShow.value = true
}
async function onSubmit(payload: NotificationCreate) {
  submitting.value = true
  try {
    if (editingId.value !== null) {
      await updateNotification(editingId.value, payload); message.success('更新成功')
    } else {
      await createNotification(payload); message.success('发送成功')
    }
    modalShow.value = false; await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  } finally { submitting.value = false }
}
async function onDelete(row: NotificationItem) {
  if (!window.confirm('确认删除该通知 ?')) return
  try { await deleteNotification(row.id); message.success('删除成功'); await load() }
  catch (e) { message.error((e as Error).message || '删除失败') }
}
async function markAllRead() {
  try {
    for (const row of rows.value) {
      if (!row.read) await updateNotification(row.id, { read: true } as Partial<NotificationCreate & { read: boolean }>)
    }
    message.success('已全部标记为已读'); await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  }
}

onMounted(load)
</script>

<style scoped>
.page-root { padding: 16px; }
</style>
