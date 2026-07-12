<template>
  <PageRegion
    :label="t('nav.packs')"
    :description="t('common.detail')"
    region-class="pack-manager-root"
  >
    <div class="pm-layout">
      <NCard :bordered="false" size="small" class="pm-toolbar">
        <NSpace align="center" :size="12" wrap>
          <NInput
            v-model:value="keyword"
            :placeholder="t('common.search')"
            clearable
            size="small"
            style="width: 240px"
            @keyup.enter="reload"
            @clear="reload"
          >
            <template #prefix><NIcon><SearchOutline /></NIcon></template>
          </NInput>
          <NSelect
            v-model:value="packType"
            :options="typeOptions"
            :placeholder="t('common.all')"
            size="small"
            style="width: 140px"
            clearable
            @update:value="reload"
          />
          <NSelect
            v-model:value="packStatus"
            :options="statusOptions"
            :placeholder="t('common.all')"
            size="small"
            style="width: 160px"
            clearable
            @update:value="reload"
          />
          <NButton type="primary" size="small" @click="openCreate">
            <template #icon><NIcon><AddOutline /></NIcon></template>
            {{ t('common.create') }}
          </NButton>
          <NButton size="small" @click="reload" :loading="loading">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ t('common.refresh') }}
          </NButton>
        </NSpace>
      </NCard>

      <NCard :bordered="false" size="small" class="pm-list" :title="t('common.detail')">
        <NAlert v-if="error" type="error" :title="t('common.error')" closable @close="error = ''">
          {{ error }}
        </NAlert>
        <NEmpty v-else-if="!loading && filtered.length === 0" :description="t('common.empty')" style="margin-top: 60px">
          <template #icon><NIcon><CubeOutline /></NIcon></template>
          <NButton type="primary" @click="openCreate">{{ t('common.create') }}</NButton>
        </NEmpty>
        <NSpin v-else-if="loading" style="margin-top: 60px" />
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
        <NDescriptionsItem :label="'Type'">
          <NTag :type="detail.type === 'data_pack' ? 'info' : 'warning'" size="small">{{ detail.type }}</NTag>
        </NDescriptionsItem>
        <NDescriptionsItem :label="t('common.detail')">
          <NTag :type="statusTagType(detail.status)" size="small">{{ detail.status }}</NTag>
        </NDescriptionsItem>
        <NDescriptionsItem :label="'Source'">{{ detail.source }}</NDescriptionsItem>
        <NDescriptionsItem :label="'Assets'">{{ detail.asset_count ?? 0 }}</NDescriptionsItem>
        <NDescriptionsItem :label="'Task'">{{ detail.task_type || '—' }}</NDescriptionsItem>
        <NDescriptionsItem :label="'Created'">
          {{ detail.created_at ? new Date(detail.created_at).toLocaleString() : '—' }}
        </NDescriptionsItem>
        <NDescriptionsItem :label="'Route History'">
          {{ detail.route_history?.length ?? 0 }} steps
        </NDescriptionsItem>
      </NDescriptions>
      <template #footer>
        <NSpace>
          <NButton @click="showDetail = false">{{ t('common.close') }}</NButton>
          <NButton
            v-if="detail && nextTransition(detail.status)"
            type="primary"
            @click="transition(detail!)"
            :loading="actionLoading"
          >{{ nextTransition(detail.status) }}</NButton>
        </NSpace>
      </template>
    </NModal>
  </PageRegion>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, h } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NCard, NSpace, NInput, NSelect, NButton, NIcon, NTag,
  NDataTable, NSpin, NAlert, NEmpty, NModal, NDescriptions, NDescriptionsItem,
  useMessage, type DataTableColumns,
} from 'naive-ui'
import { SearchOutline, AddOutline, RefreshOutline, CubeOutline } from '@vicons/ionicons5'
import PageRegion from '@/components/PageRegion.vue'
import { listPacks, transitionPack, type PackItem, type PackType, type PackStatus } from '@/api/pack'

const { t } = useI18n()
const message = useMessage()

const keyword = ref('')
const packType = ref<PackType | null>(null)
const packStatus = ref<PackStatus | null>(null)
const loading = ref(false)
const actionLoading = ref(false)
const error = ref('')
const items = ref<PackItem[]>([])

const showDetail = ref(false)
const detail = ref<PackItem | null>(null)

const typeOptions: Array<{ label: string; value: PackType }> = [
  { label: 'data_pack', value: 'data_pack' },
  { label: 'task_pack', value: 'task_pack' },
]
const statusOptions: Array<{ label: string; value: PackStatus }> = [
  { label: 'created', value: 'created' },
  { label: 'ready', value: 'ready' },
  { label: 'in_annotation', value: 'in_annotation' },
  { label: 'annotated', value: 'annotated' },
  { label: 'reviewed', value: 'reviewed' },
  { label: 'qc_passed', value: 'qc_passed' },
  { label: 'delivered', value: 'delivered' },
]

const pagination = { pageSize: 20 }
const rowKey = (row: PackItem) => row.id

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  let list = items.value
  if (k) list = list.filter((it: PackItem) => it.name.toLowerCase().includes(k))
  if (packType.value) list = list.filter((it: PackItem) => it.type === packType.value)
  if (packStatus.value) list = list.filter((it: PackItem) => it.status === packStatus.value)
  return list
})

const statusTagType = (s: PackStatus): 'success' | 'warning' | 'info' | 'default' => {
  if (s === 'qc_passed' || s === 'delivered') return 'success'
  if (s === 'in_annotation' || s === 'reviewed') return 'warning'
  if (s === 'ready' || s === 'annotated') return 'info'
  return 'default'
}

const columns = computed<DataTableColumns<PackItem>>(() => [
  { title: t('common.appName'), key: 'name', resizable: true, minWidth: 200, fixed: 'left' },
  { title: 'Type', key: 'type', width: 110, render: (row: PackItem) =>
      h(NTag, { type: row.type === 'data_pack' ? 'info' : 'warning', size: 'small' }, () => row.type),
  },
  { title: t('common.detail'), key: 'status', width: 140, render: (row: PackItem) =>
      h(NTag, { type: statusTagType(row.status), size: 'small' }, () => row.status),
  },
  { title: 'Source', key: 'source', width: 110 },
  { title: 'Assets', key: 'asset_count', width: 90 },
  { title: 'Task', key: 'task_type', width: 120 },
  {
    title: t('common.actions'), key: 'actions', width: 180, fixed: 'right',
    render: (row: PackItem) =>
      h(NSpace, { size: 4 }, () => [
        h(NButton, { text: true, type: 'primary', size: 'tiny', onClick: () => viewDetail(row) }, () => t('common.detail')),
        h(NButton, { text: true, type: 'success', size: 'tiny', onClick: () => transition(row), loading: actionLoading.value }, () => t('common.submit')),
      ]),
  },
])

onMounted(reload)

async function reload() {
  loading.value = true
  error.value = ''
  try {
    const page = await listPacks({
      keyword: keyword.value,
      type: packType.value ?? undefined,
      status: packStatus.value ?? undefined,
    })
    items.value = page.items
  } catch (e) {
    error.value = String(e)
    message.error(String(e))
  } finally {
    loading.value = false
  }
}

async function viewDetail(row: PackItem) {
  showDetail.value = true
  detail.value = row
}

function nextTransition(s: PackStatus): string {
  // Workflow state machine
  const flow: Record<PackStatus, string> = {
    created: 'ready',
    ready: 'in_annotation',
    in_annotation: 'annotated',
    annotated: 'reviewed',
    reviewed: 'qc_passed',
    qc_passed: 'delivered',
    delivered: '',
  }
  return flow[s] ? `→ ${flow[s]}` : ''
}

async function transition(row: PackItem) {
  const next = nextTransition(row.status).replace('→ ', '')
  if (!next) return
  actionLoading.value = true
  try {
    await transitionPack(row.id, { new_status: next as PackStatus })
    message.success(`${row.name} → ${next}`)
    showDetail.value = false
    await reload()
  } catch (e) {
    message.error(String(e))
  } finally {
    actionLoading.value = false
  }
}

function openCreate() { message.info(t('common.create')) }
</script>

<style scoped>
.pm-layout { display: flex; flex-direction: column; gap: 12px; padding: 12px; height: 100%; }
.pm-toolbar { flex-shrink: 0; }
.pm-list { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
</style>
