<template>
  <PageRegion
    :label="t('workflowBuilder.t000')"
    :description="t('workflowBuilder.t002')"
    region-class="workflow-builder-root"
  >
    <div class="wb-layout">
      <!-- Toolbar -->
      <NCard :bordered="false" size="small" class="wb-toolbar">
        <NSpace align="center" :size="12">
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
          <NButton type="primary" size="small" @click="openCreate">
            <template #icon><NIcon><AddOutline /></NIcon></template>
            {{ t('workflowBuilder.t008') }}
          </NButton>
          <NButton size="small" @click="reload">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ t('workflowBuilder.t024') }}
          </NButton>
          <div class="wb-spacer" />
          <NTag :type="filterMode === 'all' ? 'success' : 'default'" @click="filterMode = 'all'">
            {{ t('common.all') }} ({{ counts.all }})
          </NTag>
          <NTag :type="filterMode === 'mine' ? 'success' : 'default'" @click="filterMode = 'mine'">
            {{ t('workflowBuilder.t012') }} ({{ counts.mine }})
          </NTag>
        </NSpace>
      </NCard>

      <!-- Two-column: template library (left) + workflow list (right) -->
      <div class="wb-body">
        <NCard :bordered="false" size="small" class="wb-templates" :title="t('workflowBuilder.t003')">
          <NEmpty v-if="templates.length === 0" :description="t('workflowBuilder.t025')" />
          <NList v-else bordered>
            <NListItem v-for="tpl in templates" :key="tpl.id">
              <NThing :title="tpl.name" :description="tpl.description">
                <template #header-extra>
                  <NTag size="small" :type="tpl.kind === 'system' ? 'info' : 'warning'">
                    {{ tpl.kind }}
                  </NTag>
                </template>
                {{ t('workflowBuilder.t011') }}
                <NButton text type="primary" size="tiny" @click="useTemplate(tpl)">
                  {{ t('workflowBuilder.t011') }}
                </NButton>
              </NThing>
            </NListItem>
          </NList>
        </NCard>

        <NCard :bordered="false" size="small" class="wb-list" :title="t('workflowBuilder.t010')">
          <NDataTable
            :columns="columns"
            :data="filtered"
            :loading="loading"
            :pagination="pagination"
            size="small"
            striped
          />
        </NCard>
      </div>
    </div>
  </PageRegion>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, h } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NCard, NSpace, NInput, NButton, NIcon, NTag, NList, NListItem, NThing,
  NEmpty, NDataTable, useMessage, type DataTableColumns,
} from 'naive-ui'
import { SearchOutline, AddOutline, RefreshOutline } from '@vicons/ionicons5'
import PageRegion from '@/components/PageRegion.vue'
import { listWorkflows, type WorkflowItem } from '@/api/workflow'

const { t } = useI18n()
const message = useMessage()

// State
const keyword = ref('')
const filterMode = ref<'all' | 'mine'>('all')
const loading = ref(false)
const items = ref<WorkflowItem[]>([])
const templates = ref<Array<{ id: string; name: string; description: string; kind: 'system' | 'user' }>>([])

const pagination = { pageSize: 20 }

// Computed
const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  let list = items.value
  if (k) list = list.filter((w: WorkflowItem) => w.name.toLowerCase().includes(k))
  if (filterMode.value === 'mine') list = list.filter((w: WorkflowItem) => w.status !== 'archived')
  return list
})

const counts = computed(() => ({
  all: items.value.length,
  mine: items.value.filter((w: WorkflowItem) => w.status !== 'archived').length,
}))

// Table columns
const columns = computed<DataTableColumns<WorkflowItem>>(() => [
  { title: t('workflowBuilder.t000'), key: 'name', resizable: true, minWidth: 200 },
  { title: t('workflowBuilder.t005'), key: 'status', width: 110, render: (row: WorkflowItem) =>
      h(NTag, { type: row.status === 'active' ? 'success' : 'default', size: 'small' }, () => row.status),
  },
  { title: t('workflowBuilder.t015'), key: 'created_at', width: 160 },
  { title: t('workflowBuilder.t030'), key: 'steps', width: 90 },
  {
    title: t('common.actions'),
    key: 'actions',
    width: 160,
    render: (row: WorkflowItem) =>
      h(NSpace, { size: 4 }, () => [
        h(NButton, { text: true, type: 'primary', size: 'tiny', onClick: () => editWorkflow(row) }, () => t('common.edit')),
        h(NButton, { text: true, type: 'error', size: 'tiny', onClick: () => removeWorkflow(row) }, () => t('common.delete')),
      ]),
  },
])

// Lifecycle
onMounted(async () => {
  await Promise.all([reload(), loadTemplates()])
})

async function reload() {
  loading.value = true
  try {
    const page = await listWorkflows({ keyword: keyword.value })
    items.value = page.items
  } catch (e) {
    message.error(String(e))
  } finally {
    loading.value = false
  }
}

async function loadTemplates() {
  // templates are best-effort
  templates.value = []
}

function openCreate() {
  message.info(t('workflowBuilder.t027'))
}

function useTemplate(tpl: { id: string; name: string }) {
  message.success(`${t('workflowBuilder.t024')}: ${tpl.name}`)
}

function editWorkflow(row: WorkflowItem) {
  message.info(`${t('common.edit')}: ${row.name}`)
}

function removeWorkflow(row: WorkflowItem) {
  message.warning(`${t('common.delete')}: ${row.name}`)
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
</style>
