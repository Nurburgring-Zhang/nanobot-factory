<template>
  <PageRegion
    :label="t('nav.collection')"
    :description="t('common.detail')"
    region-class="collection-center-root"
  >
    <div class="cc-layout">
      <NCard :bordered="false" size="small" class="cc-toolbar">
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
          <NButton size="small" @click="reload">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ t('common.refresh') }}
          </NButton>
        </NSpace>
      </NCard>

      <div class="cc-body">
        <NCard :bordered="false" size="small" :title="t('common.detail')" class="cc-list">
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
  NCard, NSpace, NInput, NSelect, NButton, NIcon, NTag,
  NDataTable, useMessage, type DataTableColumns,
} from 'naive-ui'
import { SearchOutline, AddOutline, RefreshOutline } from '@vicons/ionicons5'
import PageRegion from '@/components/PageRegion.vue'
import { listSources, type RssFeed, type CrawlerJob } from '@/api/collection'

const { t } = useI18n()
const message = useMessage()

const keyword = ref('')
const sourceType = ref<string | null>(null)
const loading = ref(false)
const rssItems = ref<RssFeed[]>([])
const crawlerItems = ref<CrawlerJob[]>([])

const sourceTypeOptions = [
  { label: 'RSS', value: 'rss' },
  { label: 'Crawler', value: 'crawler' },
]

const pagination = { pageSize: 20 }

const items = computed(() => {
  if (sourceType.value === 'rss') return rssItems.value
  if (sourceType.value === 'crawler') return crawlerItems.value
  return [...rssItems.value, ...crawlerItems.value]
})

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  let list: Array<RssFeed | CrawlerJob> = items.value
  if (k) list = list.filter((it) => it.name.toLowerCase().includes(k))
  return list
})

const columns = computed<DataTableColumns<RssFeed | CrawlerJob>>(() => [
  { title: t('common.appName'), key: 'name', resizable: true, minWidth: 200 },
  { title: 'URL', key: 'url', resizable: true, minWidth: 280 },
  { title: t('common.detail'), key: 'status', width: 100, render: (row: RssFeed | CrawlerJob) =>
      h(NTag, { type: row.status === 'active' || row.status === 'running' ? 'success' : 'default', size: 'small' }, () => row.status),
  },
  {
    title: t('common.detail'),
    key: 'actions',
    width: 160,
    render: (row: RssFeed | CrawlerJob) =>
      h(NSpace, { size: 4 }, () => [
        h(NButton, { text: true, type: 'primary', size: 'tiny', onClick: () => editItem(row) }, () => t('common.edit')),
        h(NButton, { text: true, type: 'error', size: 'tiny', onClick: () => removeItem(row) }, () => t('common.delete')),
      ]),
  },
])

onMounted(reload)

async function reload() {
  loading.value = true
  try {
    const sources = await listSources()
    rssItems.value = sources.rss || []
    crawlerItems.value = sources.crawler || []
  } catch (e) {
    message.error(String(e))
  } finally {
    loading.value = false
  }
}

function openCreate() { message.info(t('common.create')) }
function editItem(row: RssFeed | CrawlerJob) { message.info(`${t('common.edit')}: ${row.name}`) }
function removeItem(row: RssFeed | CrawlerJob) { message.warning(`${t('common.delete')}: ${row.name}`) }
</script>

<style scoped>
.cc-layout { display: flex; flex-direction: column; gap: 12px; padding: 12px; height: 100%; }
.cc-toolbar { flex-shrink: 0; }
.cc-body { flex: 1; min-height: 0; }
.cc-list { height: 100%; overflow: hidden; display: flex; flex-direction: column; }
</style>
