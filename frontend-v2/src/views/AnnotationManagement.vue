<template>
  <div class="page-root">
    <NCard title="标注管理" :bordered="false">
      <SearchBar v-model="keyword" placeholder="搜索标签/标注员" @search="onSearch" @reset="onReset">
        <template #extra>
          <PermissionGuard :roles="['admin', 'annotator']">
            <ActionButton type="primary" @click="openCreate">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              新建标注
            </ActionButton>
          </PermissionGuard>
        </template>
      </SearchBar>
      <DataTable :columns="columns" :data="rows" :loading="loading" :error="error" :total="total"
        v-model:page="page" v-model:page-size="pageSize"
        :row-key="(r: AnnotationItem) => r.id" @refresh="load">
        <template #empty><NEmpty description="暂无标注" /></template>
      </DataTable>
    </NCard>
    <ModalForm v-model:show="modalShow" :title="editingId ? '编辑标注' : '新建标注'" v-model="form"
      :rules="rules" :submitting="submitting" @submit="onSubmit">
      <template #default="{ form: f }">
        <NFormItem label="资产 ID" path="asset_id">
          <NInput v-model:value="(f as AnnotationCreate).asset_id" />
        </NFormItem>
        <NFormItem label="标签" path="label">
          <NInput v-model:value="(f as AnnotationCreate).label" />
        </NFormItem>
        <NFormItem label="标注员" path="annotator">
          <NInput v-model:value="(f as AnnotationCreate).annotator" />
        </NFormItem>
        <NFormItem label="状态" path="status">
          <NSelect v-model:value="(f as AnnotationCreate).status" :options="statusOptions" />
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
import { listAnnotations, createAnnotation, updateAnnotation, deleteAnnotation, type AnnotationItem, type AnnotationCreate } from '@/api/annotation'

const message = useMessage()
const keyword = ref('')
const page = ref(1); const pageSize = ref(20)
const rows = ref<AnnotationItem[]>([]); const total = ref(0)
const loading = ref(false); const error = ref<string | null>(null)

const modalShow = ref(false)
const editingId = ref<string | number | null>(null)
const submitting = ref(false)
const form = reactive<AnnotationCreate>({ asset_id: '', label: '', annotator: '', status: 'pending' })

const statusOptions = [
  { label: '待审核', value: 'pending' },
  { label: '已通过', value: 'approved' },
  { label: '已拒绝', value: 'rejected' }
]
const rules: FormRules = {
  asset_id: { required: true, message: '请输入资产 ID', trigger: 'blur' },
  label: { required: true, message: '请输入标签', trigger: 'blur' }
}
const statusType: Record<AnnotationItem['status'], 'default' | 'success' | 'warning' | 'error'> = {
  pending: 'warning', approved: 'success', rejected: 'error'
}

const columns: DataTableColumns<AnnotationItem> = [
  { title: 'ID', key: 'id', width: 80 },
  { title: '资产 ID', key: 'asset_id', width: 120 },
  { title: '标签', key: 'label', minWidth: 160 },
  { title: '标注员', key: 'annotator', width: 120 },
  { title: '状态', key: 'status', width: 100, render: (row) => h(NTag, { type: statusType[row.status] }, { default: () => row.status }) },
  { title: '创建时间', key: 'created_at', width: 180 },
  {
    title: '操作', key: 'actions', width: 180,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(PermissionGuard, { roles: ['admin', 'annotator'] }, { default: () => h(ActionButton, { icon: CreateOutline, onClick: () => openEdit(row) }, { default: () => '编辑' }) }),
        h(PermissionGuard, { roles: ['admin'] }, { default: () => h(ActionButton, { type: 'error', icon: TrashOutline, onClick: () => onDelete(row) }, { default: () => '删除' }) })
      ]
    })
  }
]

async function load() {
  loading.value = true; error.value = null
  try {
    const res = await listAnnotations({ page: page.value, page_size: pageSize.value, keyword: keyword.value })
    rows.value = res.items; total.value = res.total
  } catch (e) {
    error.value = (e as Error).message || '加载标注失败'; rows.value = []; total.value = 0
  } finally { loading.value = false }
}
function onSearch() { page.value = 1; load() }
function onReset() { keyword.value = ''; page.value = 1; load() }
function openCreate() {
  editingId.value = null
  Object.assign(form, { asset_id: '', label: '', annotator: '', status: 'pending' } as AnnotationCreate)
  modalShow.value = true
}
function openEdit(row: AnnotationItem) {
  editingId.value = row.id
  Object.assign(form, { asset_id: String(row.asset_id), label: row.label, annotator: row.annotator ?? '', status: row.status } as AnnotationCreate)
  modalShow.value = true
}
async function onSubmit(payload: AnnotationCreate) {
  submitting.value = true
  try {
    if (editingId.value !== null) {
      await updateAnnotation(editingId.value, { ...payload, asset_id: payload.asset_id })
      message.success('更新成功')
    } else {
      await createAnnotation(payload)
      message.success('创建成功')
    }
    modalShow.value = false; await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  } finally { submitting.value = false }
}
async function onDelete(row: AnnotationItem) {
  if (!window.confirm('确认删除该标注 ?')) return
  try { await deleteAnnotation(row.id); message.success('删除成功'); await load() }
  catch (e) { message.error((e as Error).message || '删除失败') }
}

onMounted(load)
</script>

<style scoped>
.page-root { padding: 16px; }
</style>
