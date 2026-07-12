<template>
  <PageRegion
    :label="t('nav.delivery')"
    :description="t('common.detail')"
    region-class="delivery-root"
  >
    <div class="dl-layout">
      <NCard :bordered="false" size="small" class="dl-toolbar">
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
          <NButton size="small" @click="reload" :loading="loading">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ t('common.refresh') }}
          </NButton>
        </NSpace>
      </NCard>

      <NCard :bordered="false" size="small" class="dl-list" :title="t('common.detail')">
        <NAlert v-if="error" type="error" :title="t('common.error')" closable @close="error = ''">
          {{ error }}
        </NAlert>
        <NEmpty v-else-if="!loading && items.length === 0" :description="t('common.empty')" style="margin-top: 60px">
          <template #icon><NIcon><ArchiveOutline /></NIcon></template>
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
        <NDescriptionsItem :label="'Format'">{{ detail.format }}</NDescriptionsItem>
        <NDescriptionsItem :label="'Version'">{{ detail.dataset_version }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('common.detail')">
          <NTag :type="statusTagType(detail.status)" size="small">{{ detail.status }}</NTag>
        </NDescriptionsItem>
        <NDescriptionsItem :label="'Reviewer'">{{ detail.reviewer || '—' }}</NDescriptionsItem>
        <NDescriptionsItem :label="'Comments'">{{ detail.comments || '—' }}</NDescriptionsItem>
      </NDescriptions>
      <template #footer>
        <NSpace>
          <NButton @click="showDetail = false">{{ t('common.close') }}</NButton>
          <NButton
            v-if="detail?.status === 'draft' || detail?.status === 'rejected'"
            type="primary"
            @click="transition(detail!, 'submit')"
            :loading="actionLoading"
          >{{ t('common.submit') }}</NButton>
          <NButton
            v-if="detail?.status === 'in_review'"
            type="success"
            @click="transition(detail!, 'approve')"
            :loading="actionLoading"
          >{{ t('common.approve') }}</NButton>
          <NButton
            v-if="detail?.status === 'in_review'"
            type="warning"
            @click="transition(detail!, 'reject')"
            :loading="actionLoading"
          >{{ t('common.reject') }}</NButton>
          <NButton
            v-if="detail?.status === 'approved'"
            type="primary"
            @click="transition(detail!, 'finalize')"
            :loading="actionLoading"
          >{{ t('common.submit') }}</NButton>
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
import { SearchOutline, AddOutline, RefreshOutline, ArchiveOutline } from '@vicons/ionicons5'
import PageRegion from '@/components/PageRegion.vue'
import { listDeliveries, type DeliveryItem, type DeliveryStatus } from '@/api/delivery'

const { t } = useI18n()
const message = useMessage()

const keyword = ref('')
const status = ref<DeliveryStatus | null>(null)
const loading = ref(false)
const actionLoading = ref(false)
const error = ref('')
const items = ref<DeliveryItem[]>([])

const showDetail = ref(false)
const detail = ref<DeliveryItem | null>(null)

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
const rowKey = (row: DeliveryItem) => row.id

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
  { title: t('common.appName'), key: 'name', resizable: true, minWidth: 220, fixed: 'left' },
  { title: 'Format', key: 'format', width: 110 },
  { title: 'Version', key: 'dataset_version', width: 130 },
  { title: t('common.detail'), key: 'status', width: 120, render: (row: DeliveryItem) =>
      h(NTag, { type: statusTagType(row.status), size: 'small' }, () => row.status),
  },
  { title: 'Reviewer', key: 'reviewer', width: 140 },
  {
    title: t('common.actions'), key: 'actions', width: 220, fixed: 'right',
    render: (row: DeliveryItem) =>
      h(NSpace, { size: 4 }, () => [
        h(NButton, { text: true, type: 'primary', size: 'tiny', onClick: () => viewDetail(row) }, () => t('common.detail')),
        h(NButton, { text: true, type: 'success', size: 'tiny', onClick: () => transition(row, 'submit'), loading: actionLoading.value }, () => t('common.submit')),
      ]),
  },
])

onMounted(reload)

async function reload() {
  loading.value = true
  error.value = ''
  try {
    const page = await listDeliveries({ q: keyword.value })
    items.value = (page.data as unknown as DeliveryItem[]) || []
  } catch (e) {
    error.value = String(e)
    message.error(String(e))
  } finally {
    loading.value = false
  }
}

async function viewDetail(row: DeliveryItem) {
  showDetail.value = true
  detail.value = row
}

async function transition(row: DeliveryItem, action: 'submit' | 'approve' | 'reject' | 'finalize') {
  actionLoading.value = true
  try {
    message.success(`${action}: ${row.name}`)
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
.dl-layout { display: flex; flex-direction: column; gap: 12px; padding: 12px; height: 100%; }
.dl-toolbar { flex-shrink: 0; }
.dl-list { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
</style>
