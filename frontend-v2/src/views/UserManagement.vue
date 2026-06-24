<template>
  <div class="page-root">
    <NCard title="用户管理" :bordered="false">
      <SearchBar v-model="keyword" placeholder="搜索用户名/邮箱" @search="onSearch" @reset="onReset">
        <template #extra>
          <PermissionGuard :roles="['admin']">
            <ActionButton type="primary" @click="openCreate">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              新建用户
            </ActionButton>
          </PermissionGuard>
        </template>
      </SearchBar>

      <DataTable
        :columns="columns"
        :data="rows"
        :loading="loading"
        :error="error"
        :total="total"
        v-model:page="page"
        v-model:page-size="pageSize"
        :row-key="(r: UserItem) => r.id"
        @refresh="load"
      >
        <template #empty>
          <NEmpty description="暂无用户数据" />
        </template>
      </DataTable>
    </NCard>

    <ModalForm
      v-model:show="modalShow"
      :title="editingId ? '编辑用户' : '新建用户'"
      v-model="form"
      :rules="rules"
      :submitting="submitting"
      @submit="onSubmit"
    >
      <template #default="{ form: f }">
        <NFormItem label="用户名" path="username">
          <NInput v-model:value="(f as UserCreate).username" placeholder="请输入用户名" />
        </NFormItem>
        <NFormItem label="邮箱" path="email">
          <NInput v-model:value="(f as UserCreate).email" placeholder="请输入邮箱" />
        </NFormItem>
        <NFormItem v-if="!editingId" label="密码" path="password">
          <NInput v-model:value="(f as UserCreate).password" type="password" show-password-on="click" placeholder="请输入密码" />
        </NFormItem>
        <NFormItem label="角色" path="role">
          <NSelect v-model:value="(f as UserCreate).role" :options="roleOptions" />
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
import { listUsers, createUser, updateUser, deleteUser, type UserItem, type UserCreate } from '@/api/user'

const message = useMessage()
const keyword = ref('')
const page = ref(1)
const pageSize = ref(20)
const rows = ref<UserItem[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

const modalShow = ref(false)
const editingId = ref<string | number | null>(null)
const submitting = ref(false)
const form = reactive<UserCreate>({ username: '', email: '', password: '', role: 'guest' })

const roleOptions = [
  { label: '管理员', value: 'admin' },
  { label: '标注员', value: 'annotator' },
  { label: '审核员', value: 'reviewer' },
  { label: '工程师', value: 'engineer' },
  { label: '访客', value: 'guest' }
]

const rules: FormRules = {
  username: { required: true, message: '请输入用户名', trigger: 'blur' },
  password: { required: true, message: '请输入密码', trigger: 'blur' },
  role: { required: true, message: '请选择角色', trigger: 'change' }
}

const columns: DataTableColumns<UserItem> = [
  { title: 'ID', key: 'id', width: 80 },
  { title: '用户名', key: 'username', minWidth: 140 },
  { title: '邮箱', key: 'email', minWidth: 180 },
  {
    title: '角色',
    key: 'role',
    width: 100,
    render: (row) => h(NTag, { size: 'small', type: row.role === 'admin' ? 'error' : 'info' }, { default: () => row.role })
  },
  { title: '创建时间', key: 'created_at', width: 180 },
  {
    title: '操作',
    key: 'actions',
    width: 180,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(PermissionGuard, { roles: ['admin'] }, {
          default: () => h(ActionButton, { icon: CreateOutline, onClick: () => openEdit(row) }, { default: () => '编辑' })
        }),
        h(PermissionGuard, { roles: ['admin'] }, {
          default: () => h(ActionButton, { type: 'error', icon: TrashOutline, onClick: () => onDelete(row) }, { default: () => '删除' })
        })
      ]
    })
  }
]

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await listUsers({ page: page.value, page_size: pageSize.value, keyword: keyword.value })
    rows.value = res.items
    total.value = res.total
  } catch (e) {
    error.value = (e as Error).message || '加载用户列表失败'
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function onSearch() { page.value = 1; load() }
function onReset() { keyword.value = ''; page.value = 1; load() }

function openCreate() {
  editingId.value = null
  Object.assign(form, { username: '', email: '', password: '', role: 'guest' } as UserCreate)
  modalShow.value = true
}

function openEdit(row: UserItem) {
  editingId.value = row.id
  Object.assign(form, { username: row.username, email: row.email ?? '', role: row.role } as UserCreate)
  modalShow.value = true
}

async function onSubmit(payload: UserCreate) {
  submitting.value = true
  try {
    if (editingId.value !== null) {
      await updateUser(editingId.value, payload)
      message.success('更新成功')
    } else {
      await createUser(payload)
      message.success('创建成功')
    }
    modalShow.value = false
    await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  } finally {
    submitting.value = false
  }
}

async function onDelete(row: UserItem) {
  if (!window.confirm(`确认删除用户 ${row.username} ?`)) return
  try {
    await deleteUser(row.id)
    message.success('删除成功')
    await load()
  } catch (e) {
    message.error((e as Error).message || '删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.page-root { padding: 16px; }
</style>
