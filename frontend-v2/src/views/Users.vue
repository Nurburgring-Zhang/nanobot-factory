<template>
  <div class="users-view">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">用户管理</NText>
          <NText depth="3" style="margin-left: 8px">
            RBAC · SSO · GDPR — {{ total }} 用户
          </NText>
        </div>
        <NSpace>
          <NTag :type="'info'" :bordered="false">{{ activeCount }} 活跃</NTag>
          <NTag :type="'warning'" :bordered="false">{{ disabledCount }} 已禁用</NTag>
          <ActionButton type="primary" :loading="loading" @click="load">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            刷新
          </ActionButton>
          <PermissionGuard :roles="['admin']">
            <ActionButton type="primary" @click="openCreate">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              新建用户
            </ActionButton>
          </PermissionGuard>
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

    <!-- Search + table -->
    <NCard :bordered="false">
      <SearchBar
        v-model="keyword"
        placeholder="搜索用户名 / 邮箱 / 角色"
        @search="onSearch"
        @reset="onReset"
      >
        <template #extra>
          <NSelect
            v-model:value="roleFilter"
            :options="roleOptions"
            placeholder="角色"
            clearable
            style="width: 140px"
            @update:value="onSearch"
          />
        </template>
      </SearchBar>

      <DataTable
        :columns="columns"
        :data="filteredRows"
        :loading="loading"
        :error="error"
        :total="filteredRows.length"
        v-model:page="page"
        v-model:page-size="pageSize"
        :row-key="(r: UserRow) => String(r.username || r.id)"
        @refresh="load"
      >
        <template #empty><NEmpty description="暂无用户" /></template>
      </DataTable>
    </NCard>

    <!-- Edit / Create modal -->
    <ModalForm
      v-model:show="modalShow"
      :title="creating ? '新建用户' : `编辑 ${form.username}`"
      v-model="form"
      :rules="rules"
      :submitting="submitting"
      @submit="onSubmit"
    >
      <template #default="{ form: f }">
        <NFormItem v-if="creating" label="用户名" path="username">
          <NInput v-model:value="(f as any).username" placeholder="例如 alice" />
        </NFormItem>
        <NFormItem v-if="creating" label="密码" path="password">
          <NInput v-model:value="(f as any).password" type="password" show-password-on="click" placeholder="初始密码" />
        </NFormItem>
        <NFormItem label="邮箱" path="email">
          <NInput v-model:value="(f as any).email" placeholder="(可选)" />
        </NFormItem>
        <NFormItem label="角色" path="role">
          <NSelect v-model:value="(f as any).role" :options="roleOptions" />
        </NFormItem>
        <NFormItem v-if="!creating" label="状态" path="disabled">
          <NSwitch v-model:value="(f as any).disabled" />
          <NText depth="3" style="margin-left: 8px; font-size: 11px">禁用后用户无法登录</NText>
        </NFormItem>
      </template>
    </ModalForm>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from 'vue'
import {
  NCard, NSpace, NText, NTag, NIcon, NGrid, NGi, NSelect, NInput, NSwitch, NFormItem,
  NSpin, NEmpty, NAlert, useMessage, type DataTableColumns, type FormRules,
} from 'naive-ui'
import { RefreshOutline, AddOutline, TrashOutline } from '@vicons/ionicons5'
import SearchBar from '@/components/SearchBar.vue'
import DataTable from '@/components/DataTable.vue'
import ActionButton from '@/components/ActionButton.vue'
import ModalForm from '@/components/ModalForm.vue'
import PermissionGuard from '@/components/PermissionGuard.vue'
import { http } from '@/api/http'

interface UserRow {
  username?: string
  email?: string
  role?: string
  disabled?: boolean
  created_at?: string
  id?: string | number
}

const message = useMessage()

const rows = ref<UserRow[]>([])
const filteredRows = ref<UserRow[]>([])
const total = ref(0)
const activeCount = ref(0)
const disabledCount = ref(0)

const loading = ref(false)
const error = ref<string | null>(null)

const keyword = ref('')
const roleFilter = ref<string | null>(null)
const page = ref(1)
const pageSize = ref(20)

const roleOptions = [
  { label: '管理员 (admin)', value: 'admin' },
  { label: '标注员 (annotator)', value: 'annotator' },
  { label: '审核员 (reviewer)', value: 'reviewer' },
  { label: '工程师 (engineer)', value: 'engineer' },
  { label: '访客 (guest)', value: 'guest' },
]

const kpis = computed(() => [
  { key: 'total', label: '用户总数', value: total.value, hint: '已注册' },
  { key: 'active', label: '活跃', value: activeCount.value, hint: '未禁用' },
  { key: 'disabled', label: '已禁用', value: disabledCount.value, hint: '禁止登录' },
  { key: 'admin', label: '管理员', value: filteredRows.value.filter((r) => r.role === 'admin').length, hint: '含全权限' },
])

function roleBadge(r?: string): 'default' | 'success' | 'info' | 'warning' | 'error' {
  switch (r) {
    case 'admin': return 'error'
    case 'engineer': return 'warning'
    case 'annotator': return 'info'
    case 'reviewer': return 'success'
    default: return 'default'
  }
}

const columns: DataTableColumns<UserRow> = [
  { title: '用户名', key: 'username', width: 140 },
  { title: '邮箱', key: 'email', minWidth: 200, render: (r) => r.email || '—' },
  {
    title: '角色', key: 'role', width: 140,
    render: (row) => h(NTag, { type: roleBadge(row.role), size: 'small' }, { default: () => row.role || 'guest' }),
  },
  {
    title: '状态', key: 'disabled', width: 100,
    render: (row) => h(NTag, {
      type: row.disabled ? 'warning' : 'success',
      size: 'small',
    }, { default: () => row.disabled ? '已禁用' : '正常' }),
  },
  { title: '创建时间', key: 'created_at', width: 180 },
  {
    title: '操作', key: 'actions', width: 240,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(PermissionGuard, { roles: ['admin'] }, {
          default: () => h(ActionButton, {
            size: 'tiny', onClick: () => openEdit(row),
          }, { default: () => '编辑' }),
        }),
        h(PermissionGuard, { roles: ['admin'] }, {
          default: () => h(ActionButton, {
            size: 'tiny',
            type: row.disabled ? 'success' : 'warning',
            onClick: () => onToggleDisable(row),
          }, { default: () => row.disabled ? '启用' : '禁用' }),
        }),
        h(PermissionGuard, { roles: ['admin'] }, {
          default: () => h(ActionButton, {
            size: 'tiny',
            type: 'error',
            icon: TrashOutline,
            onClick: () => onDelete(row),
          }, { default: () => '删除' }),
        }),
      ],
    }),
  },
]

async function load() {
  loading.value = true; error.value = null
  try {
    const res = await http.get<any>('/api/v1/users')
    // user_service returns either List[UserSummary] or { items, total }
    let items: UserRow[]
    if (Array.isArray(res.data)) items = res.data
    else items = res.data?.items || []
    rows.value = items
    total.value = items.length
    activeCount.value = items.filter((u) => !u.disabled).length
    disabledCount.value = items.filter((u) => u.disabled).length
    applyFilter()
  } catch (e) {
    error.value = (e as Error).message || '加载用户失败'
    rows.value = []; total.value = 0; activeCount.value = 0; disabledCount.value = 0
    filteredRows.value = []
  } finally { loading.value = false }
}

function applyFilter() {
  const k = keyword.value.toLowerCase().trim()
  const r = roleFilter.value
  filteredRows.value = rows.value.filter((u) => {
    if (r && u.role !== r) return false
    if (!k) return true
    return (u.username || '').toLowerCase().includes(k)
        || (u.email || '').toLowerCase().includes(k)
        || (u.role || '').toLowerCase().includes(k)
  })
}

function onSearch() { applyFilter() }
function onReset() { keyword.value = ''; roleFilter.value = null; applyFilter() }

const modalShow = ref(false)
const creating = ref(true)
const submitting = ref(false)
const editingUsername = ref<string | null>(null)

const form = reactive<any>({
  username: '',
  password: '',
  email: '',
  role: 'annotator',
  disabled: false,
})

const rules: FormRules = {
  username: { required: true, message: '请输入用户名', trigger: 'blur' },
  password: { required: true, message: '请输入密码', trigger: 'blur' },
  role: { required: true, message: '请选择角色', trigger: 'change' },
}

function openCreate() {
  creating.value = true; editingUsername.value = null
  Object.assign(form, { username: '', password: '', email: '', role: 'annotator', disabled: false })
  modalShow.value = true
}

function openEdit(row: UserRow) {
  creating.value = false; editingUsername.value = row.username || null
  Object.assign(form, { username: row.username || '', email: row.email || '', role: row.role || 'guest', disabled: !!row.disabled })
  modalShow.value = true
}

async function onSubmit(payload: any) {
  submitting.value = true
  try {
    if (creating.value) {
      await http.post('/api/v1/users', payload)
      message.success('用户已创建')
    } else if (editingUsername.value) {
      await http.put(`/api/v1/users/${editingUsername.value}/role`, { role: payload.role })
      if (payload.email) {
        await http.put(`/api/v1/users/${editingUsername.value}`, { email: payload.email })
      }
      if (payload.disabled !== undefined) {
        await http.put(`/api/v1/users/${editingUsername.value}/disable`, { disabled: payload.disabled })
      }
      message.success('用户已更新')
    }
    modalShow.value = false
    await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  } finally { submitting.value = false }
}

async function onToggleDisable(row: UserRow) {
  try {
    await http.put(`/api/v1/users/${row.username}/disable`, { disabled: !row.disabled })
    message.success(row.disabled ? '已启用' : '已禁用')
    await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  }
}

async function onDelete(row: UserRow) {
  if (!window.confirm(`确认删除用户 ${row.username} ?`)) return
  try {
    await http.delete(`/api/v1/users/${row.username}`)
    message.success('已删除')
    await load()
  } catch (e) {
    message.error((e as Error).message || '删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.users-view { padding: 16px; }
.header-card { margin-bottom: 12px; }
.kpi-card { min-height: 96px; }
.kpi-value { margin: 4px 0; }
</style>