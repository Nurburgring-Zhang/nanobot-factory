<template>
  <div class="page-root">
    <NCard title="资产管理" :bordered="false">
      <SearchBar v-model="keyword" placeholder="搜索资产名称/类型" @search="onSearch" @reset="onReset">
        <template #extra>
          <PermissionGuard :roles="['admin', 'engineer']">
            <ActionButton type="primary" @click="openCreate">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              新建资产
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
        :row-key="(r: AssetItem) => r.id"
        @refresh="load"
      >
        <template #empty><NEmpty description="暂无资产" /></template>
      </DataTable>
    </NCard>

    <ModalForm
      v-model:show="modalShow"
      :title="editingId ? '编辑资产' : '新建资产'"
      v-model="form"
      :rules="rules"
      :submitting="submitting"
      @submit="onSubmit"
    >
      <template #default="{ form: f }">
        <NFormItem label="名称" path="name">
          <NInput v-model:value="(f as AssetCreate).name" />
        </NFormItem>
        <NFormItem label="类型" path="type">
          <NSelect v-model:value="(f as AssetCreate).type" :options="typeOptions" />
        </NFormItem>
        <NFormItem label="URL" path="url">
          <NInput v-model:value="(f as AssetCreate).url" />
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
import { listAssets, createAsset, updateAsset, deleteAsset, type AssetItem, type AssetCreate } from '@/api/asset'

const message = useMessage()
const keyword = ref('')
const page = ref(1)
const pageSize = ref(20)
const rows = ref<AssetItem[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

const modalShow = ref(false)
const editingId = ref<string | number | null>(null)
const submitting = ref(false)
const form = reactive<AssetCreate>({ name: '', type: 'image', url: '' })

const typeOptions = [
  { label: '图片', value: 'image' },
  { label: '视频', value: 'video' },
  { label: '音频', value: 'audio' },
  { label: '文本', value: 'text' }
]

const rules: FormRules = {
  name: { required: true, message: '请输入名称', trigger: 'blur' },
  type: { required: true, message: '请选择类型', trigger: 'change' }
}

const columns: DataTableColumns<AssetItem> = [
  { title: 'ID', key: 'id', width: 80 },
  { title: '名称', key: 'name', minWidth: 160 },
  {
    title: '类型', key: 'type', width: 100,
    render: (row) => h(NTag, { size: 'small', type: 'info' }, { default: () => row.type })
  },
  { title: 'URL', key: 'url', minWidth: 200, ellipsis: { tooltip: true } },
  { title: '大小', key: 'size', width: 100 },
  { title: '创建时间', key: 'created_at', width: 180 },
  {
    title: '操作', key: 'actions', width: 180,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(PermissionGuard, { roles: ['admin', 'engineer'] }, {
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
    const res = await listAssets({ page: page.value, page_size: pageSize.value, keyword: keyword.value })
    rows.value = res.items
    total.value = res.total
  } catch (e) {
    error.value = (e as Error).message || '加载资产失败'
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
  Object.assign(form, { name: '', type: 'image', url: '' } as AssetCreate)
  modalShow.value = true
}
function openEdit(row: AssetItem) {
  editingId.value = row.id
  Object.assign(form, { name: row.name, type: row.type, url: row.url ?? '' } as AssetCreate)
  modalShow.value = true
}
async function onSubmit(payload: AssetCreate) {
  submitting.value = true
  try {
    if (editingId.value !== null) {
      await updateAsset(editingId.value, payload)
      message.success('更新成功')
    } else {
      await createAsset(payload)
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
async function onDelete(row: AssetItem) {
  if (!window.confirm(`确认删除资产 ${row.name} ?`)) return
  try {
    await deleteAsset(row.id)
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
