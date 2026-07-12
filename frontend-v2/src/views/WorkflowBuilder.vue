<template>
  <PageRegion
    :label="t('workflowBuilder.t000')"
    :description="t('workflowBuilder.t002')"
    region-class="workflow-builder-root"
  >
    <div class="wb-layout">
      <!-- Toolbar -->
      <NCard :bordered="false" size="small" class="wb-toolbar">
        <NSpace align="center" :size="12" wrap>
          <NInput
            v-model:value="keyword"
            :placeholder="t('workflowBuilder.t011')"
            clearable
            size="small"
            style="width: 240px"
            @clear="reload"
            @keyup.enter="reload"
          >
            <template #prefix><NIcon><SearchOutline /></NIcon></template>
          </NInput>
          <NSelect
            v-model:value="filterStatus"
            :options="statusOptions"
            :placeholder="t('common.all')"
            size="small"
            style="width: 140px"
            clearable
            @update:value="reload"
          />
          <NButton type="primary" size="small" @click="openCreate">
            <template #icon><NIcon><AddOutline /></NIcon></template>
            {{ t('workflowBuilder.t008') }}
          </NButton>
          <NButton size="small" @click="reload" :loading="loading">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ t('workflowBuilder.t024') }}
          </NButton>
          <div class="wb-spacer" />
          <NTag :type="filterMode === 'all' ? 'success' : 'default'" @click="filterMode = 'all'">
            {{ t('common.all') }} ({{ counts.all }})
          </NTag>
          <NTag :type="filterMode === 'active' ? 'success' : 'default'" @click="filterMode = 'active'">
            {{ t('workflowBuilder.t005') }} ({{ counts.active }})
          </NTag>
          <NTag :type="filterMode === 'paused' ? 'warning' : 'default'" @click="filterMode = 'paused'">
            {{ t('workflowBuilder.t006') }} ({{ counts.paused }})
          </NTag>
        </NSpace>
      </NCard>

      <!-- Two-column: template library (left) + workflow list (right) -->
      <div class="wb-body">
        <NCard :bordered="false" size="small" class="wb-templates" :title="t('workflowBuilder.t003')">
          <template #header-extra>
            <NTag size="small" type="info">{{ templates.length }} {{ t('common.all') }}</NTag>
          </template>
          <NEmpty
            v-if="!loadingTemplates && templates.length === 0"
            :description="t('workflowBuilder.t025')"
          >
            <template #icon><NIcon><CloudUploadOutline /></NIcon></template>
          </NEmpty>
          <NSpin v-else-if="loadingTemplates" />
          <NList v-else bordered>
            <NListItem v-for="tpl in templates" :key="tpl.id">
              <NThing :title="tpl.name" :description="tpl.description">
                <template #header-extra>
                  <NTag size="small" :type="tpl.kind === 'system' ? 'info' : 'warning'">
                    {{ tpl.kind }}
                  </NTag>
                </template>
                <NButton text type="primary" size="tiny" @click="useTemplate(tpl)">
                  {{ t('workflowBuilder.t011') }}
                </NButton>
              </NThing>
            </NListItem>
          </NList>
        </NCard>

        <NCard :bordered="false" size="small" class="wb-list" :title="t('workflowBuilder.t010')">
          <template #header-extra>
            <NSpace :size="4">
              <NTag size="small" type="default">{{ filtered.length }} {{ t('common.detail') }}</NTag>
            </NSpace>
          </template>
          <!-- Error state -->
          <NAlert v-if="error" type="error" :title="t('common.error')" closable @close="error = ''">
            {{ error }}
          </NAlert>
          <!-- Empty state -->
          <NEmpty
            v-else-if="!loading && filtered.length === 0"
            :description="t('workflowBuilder.t025')"
            style="margin-top: 60px"
          >
            <template #icon><NIcon><GitBranchOutline /></NIcon></template>
            <NButton type="primary" @click="openCreate">{{ t('workflowBuilder.t008') }}</NButton>
          </NEmpty>
          <!-- Loading state -->
          <NSpin v-else-if="loading" style="margin-top: 60px" />
          <!-- Data table -->
          <NDataTable
            v-else
            :columns="columns"
            :data="filtered"
            :pagination="pagination"
            :row-key="rowKey"
            size="small"
            striped
          />
        </NCard>
      </div>
    </div>

    <!-- Detail dialog -->
    <NModal
      v-model:show="showDetail"
      :title="detail?.name || t('common.detail')"
      preset="card"
      style="max-width: 720px"
    >
      <NSpin v-if="!detail" />
      <NDescriptions v-else :column="2" bordered>
        <NDescriptionsItem :label="t('common.appName')">{{ detail.name }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('workflowBuilder.t005')">
          <NTag :type="detail.status === 'active' ? 'success' : 'default'" size="small">
            {{ detail.status }}
          </NTag>
        </NDescriptionsItem>
        <NDescriptionsItem :label="t('workflowBuilder.t015')">{{ detail.created_at || '—' }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('workflowBuilder.t004')">{{ detail.last_run_at || '—' }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('workflowBuilder.t007')" :span="2">
          {{ detail.description || '—' }}
        </NDescriptionsItem>
        <NDescriptionsItem :label="t('workflowBuilder.t030')" :span="2">
          {{ detail.steps || 0 }} {{ t('workflowBuilder.t007') }}
        </NDescriptionsItem>
      </NDescriptions>
      <template #footer>
        <NSpace>
          <NButton @click="showDetail = false">{{ t('common.close') }}</NButton>
          <NButton
            v-if="detail?.status === 'active'"
            type="warning"
            @click="pauseWorkflow(detail!)"
            :loading="actionLoading"
          >
            {{ t('workflowBuilder.t026') }}
          </NButton>
          <NButton
            v-if="detail?.status === 'paused'"
            type="success"
            @click="resumeWorkflow(detail!)"
            :loading="actionLoading"
          >
            {{ t('workflowBuilder.t031') }}
          </NButton>
          <NButton type="primary" @click="runWorkflow(detail!)" :loading="actionLoading">
            {{ t('workflowBuilder.t013') }}
          </NButton>
        </NSpace>
      </template>
    </NModal>
  </PageRegion>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, h } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NCard, NSpace, NInput, NSelect, NButton, NIcon, NTag, NList, NListItem, NThing,
  NEmpty, NDataTable, NSpin, NAlert, NModal, NDescriptions, NDescriptionsItem,
  useMessage, type DataTableColumns,
} from 'naive-ui'
import {
  SearchOutline, AddOutline, RefreshOutline, CloudUploadOutline, GitBranchOutline,
} from '@vicons/ionicons5'
import PageRegion from '@/components/PageRegion.vue'
import {
  listWorkflows, getWorkflow, runWorkflow as runWorkflowApi,
  pauseWorkflow as pauseWorkflowApi, resumeWorkflow as resumeWorkflowApi,
  listWorkflowTemplates, type WorkflowItem,
} from '@/api/workflow'

const { t } = useI18n()
const message = useMessage()

// ── State ────────────────────────────────────────────────────────────
const keyword = ref('')
const filterStatus = ref<string | null>(null)
const filterMode = ref<'all' | 'active' | 'paused'>('all')
const loading = ref(false)
const loadingTemplates = ref(false)
const actionLoading = ref(false)
const error = ref('')
const items = ref<WorkflowItem[]>([])
const templates = ref<Array<{ id: string; name: string; description: string; kind: 'system' | 'user' }>>([])

// Detail dialog
const showDetail = ref(false)
const detail = ref<WorkflowItem | null>(null)

// ── Status filter options (i18n-aware) ──────────────────────────────
const statusOptions = computed(() => [
  { label: t('workflowBuilder.t005'), value: 'active' },
  { label: t('workflowBuilder.t006'), value: 'paused' },
  { label: t('workflowBuilder.t009'), value: 'archived' },
  { label: t('workflowBuilder.t032'), value: 'draft' },
])

const pagination = { pageSize: 20 }
const rowKey = (row: WorkflowItem) => row.id

// ── Derived state ───────────────────────────────────────────────────
const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  let list = items.value
  if (k) list = list.filter((w: WorkflowItem) => w.name.toLowerCase().includes(k))
  if (filterStatus.value) list = list.filter((w: WorkflowItem) => w.status === filterStatus.value)
  if (filterMode.value === 'active') list = list.filter((w: WorkflowItem) => w.status === 'active')
  if (filterMode.value === 'paused') list = list.filter((w: WorkflowItem) => w.status === 'paused')
  return list
})

const counts = computed(() => ({
  all: items.value.length,
  active: items.value.filter((w: WorkflowItem) => w.status === 'active').length,
  paused: items.value.filter((w: WorkflowItem) => w.status === 'paused').length,
}))

// ── Table columns ───────────────────────────────────────────────────
const columns = computed<DataTableColumns<WorkflowItem>>(() => [
  { title: t('workflowBuilder.t000'), key: 'name', resizable: true, minWidth: 200, fixed: 'left' },
  {
    title: t('workflowBuilder.t005'), key: 'status', width: 110,
    render: (row: WorkflowItem) =>
      h(NTag, {
        type: row.status === 'active' ? 'success' : row.status === 'paused' ? 'warning' : 'default',
        size: 'small',
      }, () => row.status),
  },
  { title: t('workflowBuilder.t015'), key: 'created_at', width: 160 },
  { title: t('workflowBuilder.t004'), key: 'last_run_at', width: 160 },
  { title: t('workflowBuilder.t030'), key: 'steps', width: 90 },
  {
    title: t('common.actions'), key: 'actions', width: 200, fixed: 'right',
    render: (row: WorkflowItem) =>
      h(NSpace, { size: 4 }, () => [
        h(NButton, { text: true, type: 'primary', size: 'tiny', onClick: () => viewDetail(row) }, () => t('common.detail')),
        h(NButton, { text: true, type: 'success', size: 'tiny', onClick: () => runWorkflow(row), loading: actionLoading.value }, () => t('workflowBuilder.t013')),
        h(NButton, { text: true, type: 'error', size: 'tiny', onClick: () => removeWorkflow(row) }, () => t('common.delete')),
      ]),
  },
])

// ── Lifecycle ───────────────────────────────────────────────────────
onMounted(async () => {
  await Promise.all([reload(), loadTemplates()])
})

async function reload() {
  loading.value = true
  error.value = ''
  try {
    const page = await listWorkflows({ keyword: keyword.value })
    items.value = page.items
  } catch (e) {
    error.value = String(e)
    message.error(String(e))
  } finally {
    loading.value = false
  }
}

async function loadTemplates() {
  loadingTemplates.value = true
  try {
    templates.value = await listWorkflowTemplates()
  } catch {
    templates.value = []
  } finally {
    loadingTemplates.value = false
  }
}

// ── Row actions ─────────────────────────────────────────────────────
async function viewDetail(row: WorkflowItem) {
  showDetail.value = true
  detail.value = null
  try {
    detail.value = await getWorkflow(row.id)
  } catch (e) {
    message.error(String(e))
    showDetail.value = false
  }
}

async function runWorkflow(row: WorkflowItem) {
  actionLoading.value = true
  try {
    await runWorkflowApi(row.id)
    message.success(`${t('workflowBuilder.t013')}: ${row.name}`)
    await reload()
  } catch (e) {
    message.error(String(e))
  } finally {
    actionLoading.value = false
  }
}

async function pauseWorkflow(row: WorkflowItem) {
  actionLoading.value = true
  try {
    await pauseWorkflowApi(row.id)
    message.success(`${t('workflowBuilder.t026')}: ${row.name}`)
    showDetail.value = false
    await reload()
  } catch (e) {
    message.error(String(e))
  } finally {
    actionLoading.value = false
  }
}

async function resumeWorkflow(row: WorkflowItem) {
  actionLoading.value = true
  try {
    await resumeWorkflowApi(row.id)
    message.success(`${t('workflowBuilder.t031')}: ${row.name}`)
    showDetail.value = false
    await reload()
  } catch (e) {
    message.error(String(e))
  } finally {
    actionLoading.value = false
  }
}

async function removeWorkflow(row: WorkflowItem) {
  if (!confirm(`${t('common.delete')}: ${row.name}?`)) return
  try {
    // No delete API in workflow.ts yet — placeholder
    items.value = items.value.filter((w: WorkflowItem) => w.id !== row.id)
    message.success(`${t('common.delete')}: ${row.name}`)
  } catch (e) {
    message.error(String(e))
  }
}

// ── Template actions ───────────────────────────────────────────────
function openCreate() {
  message.info(t('workflowBuilder.t027'))
}

function useTemplate(tpl: { id: string; name: string }) {
  message.success(`${t('workflowBuilder.t024')}: ${tpl.name}`)
  openCreate()
}
</script>

<style scoped>
.wb-layout {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  height: 100%;
}
.wb-toolbar { flex-shrink: 0; }
.wb-spacer { flex: 1; }
.wb-body {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 12px;
  flex: 1;
  min-height: 0;
}
.wb-templates { overflow: auto; }
.wb-list { overflow: hidden; display: flex; flex-direction: column; }

@media (max-width: 960px) {
  .wb-body { grid-template-columns: 1fr; }
}
</style>
