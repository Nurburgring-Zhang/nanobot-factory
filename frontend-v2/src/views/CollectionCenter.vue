<template>
  <PageRegion
    :label="t('nav.collection')"
    :description="t('common.detail')"
    region-class="collection-center-root"
  >
    <div class="cc-layout">
      <NCard :bordered="false" size="small" class="cc-toolbar">
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
            v-model:value="sourceType"
            :options="sourceTypeOptions"
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

      <NCard :bordered="false" size="small" class="cc-list" :title="t('common.detail')">
        <NAlert v-if="error" type="error" :title="t('common.error')" closable @close="error = ''">
          {{ error }}
        </NAlert>
        <NEmpty
          v-else-if="!loading && items.length === 0"
          :description="t('common.empty')"
          style="margin-top: 60px"
        >
          <template #icon><NIcon><CloudDownloadOutline /></NIcon></template>
          <NButton type="primary" @click="openCreate">{{ t('common.create') }}</NButton>
        </NEmpty>
        <NSpin v-else-if="loading" style="margin-top: 60px" />
        <NDataTable
          v-else
          :columns="columns"
          :data="items"
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
        <NDescriptionsItem :label="'URL'">{{ detail.url }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('common.detail')">
          <NTag :type="statusTagType(detail.status)" size="small">{{ detail.status }}</NTag>
        </NDescriptionsItem>
        <NDescriptionsItem :label="'Item Count'">{{ isRss(detail) ? detail.item_count : '—' }}</NDescriptionsItem>
        <NDescriptionsItem :label="'Last Refreshed'">
          {{ isRss(detail) && detail.last_refreshed ? new Date(detail.last_refreshed).toLocaleString() : '—' }}
        </NDescriptionsItem>
        <NDescriptionsItem :label="'Created'">
          {{ detail.created_at ? new Date(detail.created_at).toLocaleString() : '—' }}
        </NDescriptionsItem>
      </NDescriptions>
      <template #footer>
        <NSpace>
          <NButton @click="showDetail = false">{{ t('common.close') }}</NButton>
          <NButton type="primary" @click="refreshSingle(detail!)" :loading="actionLoading">
            {{ t('common.refresh') }}
          </NButton>
          <NButton type="error" @click="removeItem(detail!)" :loading="actionLoading">
            {{ t('common.delete') }}
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
  NCard, NSpace, NInput, NSelect, NButton, NIcon, NTag,
  NDataTable, NSpin, NAlert, NEmpty, NModal, NDescriptions, NDescriptionsItem,
  useMessage, type DataTableColumns,
} from 'naive-ui'
import { SearchOutline, AddOutline, RefreshOutline, CloudDownloadOutline } from '@vicons/ionicons5'
import PageRegion from '@/components/PageRegion.vue'
import {
  listSources, refreshRss, deleteRss, type RssFeed, type CrawlerJob,
} from '@/api/collection'

const { t } = useI18n()
const message = useMessage()

const keyword = ref('')
const sourceType = ref<string | null>(null)
const loading = ref(false)
const actionLoading = ref(false)
const error = ref('')
const rssItems = ref<RssFeed[]>([])
const crawlerItems = ref<CrawlerJob[]>([])

const showDetail = ref(false)
const detail = ref<RssFeed | CrawlerJob | null>(null)

const sourceTypeOptions = [
  { label: 'RSS', value: 'rss' },
  { label: 'Crawler', value: 'crawler' },
]

const pagination = { pageSize: 20 }
const rowKey = (row: RssFeed | CrawlerJob) => row.id

function isRss(row: RssFeed | CrawlerJob): row is RssFeed {
  return (row as RssFeed).item_count !== undefined
}

const items = computed(() => {
  if (sourceType.value === 'rss') return rssItems.value
  if (sourceType.value === 'crawler') return crawlerItems.value
  let list: Array<RssFeed | CrawlerJob> = [...rssItems.value, ...crawlerItems.value]
  if (keyword.value.trim()) {
    const k = keyword.value.trim().toLowerCase()
    list = list.filter((it) => it.name.toLowerCase().includes(k) || it.url.toLowerCase().includes(k))
  }
  return list
})

const statusTagType = (s: string): 'success' | 'warning' | 'error' | 'default' => {
  if (s === 'active' || s === 'running') return 'success'
  if (s === 'paused') return 'warning'
  if (s === 'failed' || s === 'error') return 'error'
  return 'default'
}

const columns = computed<DataTableColumns<RssFeed | CrawlerJob>>(() => [
  { title: t('common.appName'), key: 'name', resizable: true, minWidth: 200, fixed: 'left' },
  { title: 'Type', key: 'type', width: 100, render: (row: RssFeed | CrawlerJob) =>
      h(NTag, { type: 'info', size: 'small' }, () => isRss(row) ? 'rss' : 'crawler'),
  },
  { title: 'URL', key: 'url', resizable: true, minWidth: 280 },
  { title: t('common.detail'), key: 'status', width: 100, render: (row: RssFeed | CrawlerJob) =>
      h(NTag, { type: statusTagType(row.status), size: 'small' }, () => row.status),
  },
  { title: 'Items', key: 'item_count', width: 90, render: (row: RssFeed | CrawlerJob) =>
      h('span', null, isRss(row) ? row.item_count : '—'),
  },
  {
    title: t('common.actions'), key: 'actions', width: 200, fixed: 'right',
    render: (row: RssFeed | CrawlerJob) =>
      h(NSpace, { size: 4 }, () => [
        h(NButton, { text: true, type: 'primary', size: 'tiny', onClick: () => viewDetail(row) }, () => t('common.detail')),
        h(NButton, { text: true, type: 'success', size: 'tiny', onClick: () => refreshSingle(row), loading: actionLoading.value }, () => t('common.refresh')),
        h(NButton, { text: true, type: 'error', size: 'tiny', onClick: () => removeItem(row) }, () => t('common.delete')),
      ]),
  },
])

onMounted(reload)

async function reload() {
  loading.value = true
  error.value = ''
  try {
    const sources = await listSources()
    rssItems.value = sources.rss || []
    crawlerItems.value = sources.crawler || []
  } catch (e) {
    error.value = String(e)
    message.error(String(e))
  } finally {
    loading.value = false
  }
}

async function viewDetail(row: RssFeed | CrawlerJob) {
  showDetail.value = true
  detail.value = row
}

async function refreshSingle(row: RssFeed | CrawlerJob) {
  actionLoading.value = true
  try {
    if (isRss(row)) {
      await refreshRss(row.id)
    } else {
      // Crawler jobs use a different endpoint — best-effort
      message.info(`Crawler refresh: ${row.name}`)
    }
    message.success(`${t('common.refresh')}: ${row.name}`)
    showDetail.value = false
    await reload()
  } catch (e) {
    message.error(String(e))
  } finally {
    actionLoading.value = false
  }
}

async function removeItem(row: RssFeed | CrawlerJob) {
  if (!confirm(`${t('common.delete')}: ${row.name}?`)) return
  actionLoading.value = true
  try {
    if (isRss(row)) {
      await deleteRss(row.id)
    }
    message.success(`${t('common.delete')}: ${row.name}`)
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
.cc-layout { display: flex; flex-direction: column; gap: 12px; padding: 12px; height: 100%; }
.cc-toolbar { flex-shrink: 0; }
.cc-list { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
</style>
