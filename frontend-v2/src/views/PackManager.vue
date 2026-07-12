<template>
  <PageRegion
    :label="t('nav.packs')"
    :description="t('common.detail')"
    region-class="pack-manager-root"
  >
    <div class="pm-layout">
      <NCard :bordered="false" size="small" class="pm-toolbar">
        <NSpace align="center" :size="12">
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
          <NButton size="small" @click="reload">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ t('common.refresh') }}
          </NButton>
        </NSpace>
      </NCard>

      <NCard :bordered="false" size="small" class="pm-list" :title="t('common.detail')">
        <NDataTable
          :columns="columns"
          :data="filtered"
          :loading="loading"
          :pagination="pagination"
          :row-key="rowKey"
          size="small"
          striped
        />
      </NCard>
    </div>
  </PageRegion>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, h } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NCard, NSpace, NInput, NSelect, NButton, NIcon, NTag,
  NDataTable, useMessage, type DataTableColumns,
} from 'naive-ui'
import { SearchOutline, AddOutline, RefreshOutline } from '@vicons/ionicons5'
import PageRegion from '@/components/PageRegion.vue'
import { listPacks, type PackItem, type PackType, type PackStatus } from '@/api/pack'

const { t } = useI18n()
const message = useMessage()

const keyword = ref('')
const packType = ref<PackType | null>(null)
const packStatus = ref<PackStatus | null>(null)
const loading = ref(false)
const items = ref<PackItem[]>([])

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
  { title: t('common.appName'), key: 'name', resizable: true, minWidth: 200 },
  { title: 'Type', key: 'type', width: 110, render: (row: PackItem) =>
      h(NTag, { type: 'info', size: 'small' }, () => row.type),
  },
  { title: t('common.detail'), key: 'status', width: 140, render: (row: PackItem) =>
      h(NTag, { type: statusTagType(row.status), size: 'small' }, () => row.status),
  },
  { title: 'Source', key: 'source', width: 110 },
  { title: 'Assets', key: 'asset_count', width: 90 },
  { title: 'Task', key: 'task_type', width: 120 },
  {
    title: t('common.detail'),
    key: 'actions',
    width: 180,
    render: (row: PackItem) =>
      h(NSpace, { size: 4 }, () => [
        h(NButton, { text: true, type: 'primary', size: 'tiny', onClick: () => viewPack(row) }, () => t('common.detail')),
        h(NButton, { text: true, type: 'warning', size: 'tiny', onClick: () => routePack(row) }, () => t('common.submit')),
      ]),
  },
])

onMounted(reload)

async function reload() {
  loading.value = true
  try {
    const page = await listPacks({ keyword: keyword.value, type: packType.value ?? undefined, status: packStatus.value ?? undefined })
    items.value = page.items
  } catch (e) {
    message.error(String(e))
  } finally {
    loading.value = false
  }
}

function openCreate() { message.info(t('common.create')) }
function viewPack(row: PackItem) { message.info(`${t('common.detail')}: ${row.name}`) }
function routePack(row: PackItem) { message.success(`${t('common.submit')}: ${row.name}`) }
</script>

<style scoped>
.pm-layout { display: flex; flex-direction: column; gap: 12px; padding: 12px; height: 100%; }
.pm-toolbar { flex-shrink: 0; }
.pm-list { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
</style>
