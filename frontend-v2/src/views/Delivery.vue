<template>
  <PageRegion
    :label="t('nav.delivery')"
    :description="t('common.detail')"
    region-class="delivery-root"
  >
    <div class="dl-layout">
      <NCard :bordered="false" size="small" class="dl-toolbar">
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
            v-model:value="status"
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

      <NCard :bordered="false" size="small" class="dl-list" :title="t('common.detail')">
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
import { listDeliveries, type DeliveryItem, type DeliveryStatus } from '@/api/delivery'

const { t } = useI18n()
const message = useMessage()

const keyword = ref('')
const status = ref<DeliveryStatus | null>(null)
const loading = ref(false)
const items = ref<DeliveryItem[]>([])

const statusOptions: Array<{ label: string; value: DeliveryStatus }> = [
  { label: 'draft', value: 'draft' },
  { label: 'submitted', value: 'submitted' },
  { label: 'in_review', value: 'in_review' },
  { label: 'approved', value: 'approved' },
  { label: 'rejected', value: 'rejected' },
  { label: 'delivered', value: 'delivered' },
  { label: 'archived', value: 'archived' },
]

const pagination = { pageSize: 20 }

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  let list = items.value
  if (k) list = list.filter((it: DeliveryItem) => it.name.toLowerCase().includes(k))
  if (status.value) list = list.filter((it: DeliveryItem) => it.status === status.value)
  return list
})

const statusTagType = (s: DeliveryStatus): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  switch (s) {
    case 'approved':
    case 'delivered': return 'success'
    case 'submitted':
    case 'in_review': return 'warning'
    case 'rejected': return 'error'
    case 'draft': return 'info'
    default: return 'default'
  }
}

const columns = computed<DataTableColumns<DeliveryItem>>(() => [
  { title: t('common.appName'), key: 'name', resizable: true, minWidth: 220 },
  { title: 'Format', key: 'format', width: 110 },
  { title: 'Version', key: 'dataset_version', width: 130 },
  { title: t('common.detail'), key: 'status', width: 120, render: (row: DeliveryItem) =>
      h(NTag, { type: statusTagType(row.status), size: 'small' }, () => row.status),
  },
  { title: 'Reviewer', key: 'reviewer', width: 140 },
  {
    title: t('common.detail'),
    key: 'actions',
    width: 180,
    render: (row: DeliveryItem) =>
      h(NSpace, { size: 4 }, () => [
        h(NButton, { text: true, type: 'primary', size: 'tiny', onClick: () => viewItem(row) }, () => t('common.detail')),
        h(NButton, { text: true, type: 'warning', size: 'tiny', onClick: () => shareItem(row) }, () => t('common.submit')),
      ]),
  },
])

onMounted(reload)

async function reload() {
  loading.value = true
  try {
    const page = await listDeliveries({ q: keyword.value })
    items.value = (page.data as unknown as DeliveryItem[]) || []
  } catch (e) {
    message.error(String(e))
  } finally {
    loading.value = false
  }
}

function openCreate() { message.info(t('common.create')) }
function viewItem(row: DeliveryItem) { message.info(`${t('common.detail')}: ${row.name}`) }
function shareItem(row: DeliveryItem) { message.success(`${t('common.submit')}: ${row.name}`) }
</script>

<style scoped>
.dl-layout { display: flex; flex-direction: column; gap: 12px; padding: 12px; height: 100%; }
.dl-toolbar { flex-shrink: 0; }
.dl-list { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
</style>
