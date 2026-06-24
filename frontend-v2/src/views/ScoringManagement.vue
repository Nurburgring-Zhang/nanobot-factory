<template>
  <div class="page-root">
    <NCard title="评分管理" :bordered="false">
      <SearchBar v-model="keyword" placeholder="搜索指标/评分人" @search="onSearch" @reset="onReset">
        <template #extra>
          <PermissionGuard :roles="['admin', 'reviewer']">
            <ActionButton type="primary" @click="openCreate">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              新建评分
            </ActionButton>
          </PermissionGuard>
        </template>
      </SearchBar>
      <DataTable :columns="columns" :data="rows" :loading="loading" :error="error" :total="total"
        v-model:page="page" v-model:page-size="pageSize"
        :row-key="(r: ScoringItem) => r.id" @refresh="load">
        <template #empty><NEmpty description="暂无评分" /></template>
      </DataTable>
    </NCard>
    <ModalForm v-model:show="modalShow" :title="editingId ? '编辑评分' : '新建评分'" v-model="form"
      :rules="rules" :submitting="submitting" @submit="onSubmit">
      <template #default="{ form: f }">
        <NFormItem label="资产 ID" path="asset_id">
          <NInput v-model:value="(f as ScoringCreate).asset_id" />
        </NFormItem>
        <NFormItem label="指标" path="metric">
          <NInput v-model:value="(f as ScoringCreate).metric" />
        </NFormItem>
        <NFormItem label="分值" path="score">
          <NInputNumber v-model:value="(f as ScoringCreate).score" :min="0" :max="100" />
        </NFormItem>
        <NFormItem label="评分人" path="scorer">
          <NInput v-model:value="(f as ScoringCreate).scorer" />
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
import { listScorings, createScoring, updateScoring, deleteScoring, type ScoringItem, type ScoringCreate } from '@/api/scoring'

const message = useMessage()
const keyword = ref('')
const page = ref(1); const pageSize = ref(20)
const rows = ref<ScoringItem[]>([]); const total = ref(0)
const loading = ref(false); const error = ref<string | null>(null)

const modalShow = ref(false)
const editingId = ref<string | number | null>(null)
const submitting = ref(false)
const form = reactive<ScoringCreate>({ asset_id: '', metric: '', score: 0, scorer: '' })

const rules: FormRules = {
  asset_id: { required: true, message: '请输入资产 ID', trigger: 'blur' },
  metric: { required: true, message: '请输入指标', trigger: 'blur' }
}

const columns: DataTableColumns<ScoringItem> = [
  { title: 'ID', key: 'id', width: 80 },
  { title: '资产 ID', key: 'asset_id', width: 120 },
  { title: '指标', key: 'metric', width: 140 },
  { title: '分值', key: 'score', width: 100 },
  { title: '评分人', key: 'scorer', width: 120 },
  { title: '创建时间', key: 'created_at', width: 180 },
  {
    title: '操作', key: 'actions', width: 180,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(PermissionGuard, { roles: ['admin', 'reviewer'] }, { default: () => h(ActionButton, { icon: CreateOutline, onClick: () => openEdit(row) }, { default: () => '编辑' }) }),
        h(PermissionGuard, { roles: ['admin'] }, { default: () => h(ActionButton, { type: 'error', icon: TrashOutline, onClick: () => onDelete(row) }, { default: () => '删除' }) })
      ]
    })
  }
]

async function load() {
  loading.value = true; error.value = null
  try {
    const res = await listScorings({ page: page.value, page_size: pageSize.value, keyword: keyword.value })
    rows.value = res.items; total.value = res.total
  } catch (e) {
    error.value = (e as Error).message || '加载评分失败'; rows.value = []; total.value = 0
  } finally { loading.value = false }
}
function onSearch() { page.value = 1; load() }
function onReset() { keyword.value = ''; page.value = 1; load() }
function openCreate() {
  editingId.value = null
  Object.assign(form, { asset_id: '', metric: '', score: 0, scorer: '' } as ScoringCreate)
  modalShow.value = true
}
function openEdit(row: ScoringItem) {
  editingId.value = row.id
  Object.assign(form, { asset_id: String(row.asset_id), metric: row.metric, score: row.score, scorer: row.scorer ?? '' } as ScoringCreate)
  modalShow.value = true
}
async function onSubmit(payload: ScoringCreate) {
  submitting.value = true
  try {
    if (editingId.value !== null) {
      await updateScoring(editingId.value, payload); message.success('更新成功')
    } else {
      await createScoring(payload); message.success('创建成功')
    }
    modalShow.value = false; await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  } finally { submitting.value = false }
}
async function onDelete(row: ScoringItem) {
  if (!window.confirm('确认删除该评分 ?')) return
  try { await deleteScoring(row.id); message.success('删除成功'); await load() }
  catch (e) { message.error((e as Error).message || '删除失败') }
}

onMounted(load)
</script>

<style scoped>
.page-root { padding: 16px; }
</style>
