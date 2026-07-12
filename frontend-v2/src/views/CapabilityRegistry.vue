<template>
  <PageRegion
    :label="t('nav.capabilities')"
    :description="t('common.detail')"
    region-class="capability-registry-root"
  >
    <div class="cr-layout">
      <NCard :bordered="false" size="small" class="cr-toolbar">
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
            v-model:value="category"
            :options="categoryOptions"
            :placeholder="t('common.all')"
            size="small"
            style="width: 200px"
            clearable
            @update:value="reload"
          />
          <NButton size="small" @click="reload">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ t('common.refresh') }}
          </NButton>
        </NSpace>
      </NCard>

      <div class="cr-body">
        <NCard :bordered="false" size="small" :title="t('common.detail')" class="cr-list">
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
import { SearchOutline, RefreshOutline } from '@vicons/ionicons5'
import PageRegion from '@/components/PageRegion.vue'
import { fetchCatalogue, type CapabilityItem, CAPABILITY_CATEGORIES } from '@/api/capabilities_v2'

const { t } = useI18n()
const message = useMessage()

const keyword = ref('')
const category = ref<string | null>(null)
const loading = ref(false)
const items = ref<CapabilityItem[]>([])

const categoryOptions = CAPABILITY_CATEGORIES.map((c) => ({ label: c, value: c }))

const pagination = { pageSize: 20 }

const rowKey = (row: CapabilityItem) => row.id

const filtered = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  let list = items.value
  if (k) list = list.filter((it) => it.name.toLowerCase().includes(k) || it.id.toLowerCase().includes(k))
  if (category.value) list = list.filter((it) => it.category === category.value)
  return list
})

const columns = computed<DataTableColumns<CapabilityItem>>(() => [
  { title: 'ID', key: 'id', resizable: true, minWidth: 200, fixed: 'left' },
  { title: t('common.appName'), key: 'name', resizable: true, minWidth: 200 },
  { title: 'Category', key: 'category', width: 130, render: (row: CapabilityItem) =>
      h(NTag, { type: 'info', size: 'small' }, () => row.category),
  },
  { title: t('common.detail'), key: 'description', resizable: true, minWidth: 280 },
  { title: 'Version', key: 'version', width: 100 },
  {
    title: t('common.detail'),
    key: 'actions',
    width: 140,
    render: (row: CapabilityItem) =>
      h(NButton, { text: true, type: 'primary', size: 'tiny', onClick: () => describe(row) }, () => t('common.detail')),
  },
])

onMounted(reload)

async function reload() {
  loading.value = true
  try {
    const cat = await fetchCatalogue()
    items.value = cat.items || []
  } catch (e) {
    message.error(String(e))
  } finally {
    loading.value = false
  }
}

function describe(row: CapabilityItem) {
  message.info(`${t('common.detail')}: ${row.id} v${row.version}`)
}
</script>

<style scoped>
.cr-layout { display: flex; flex-direction: column; gap: 12px; padding: 12px; height: 100%; }
.cr-toolbar { flex-shrink: 0; }
.cr-body { flex: 1; min-height: 0; }
.cr-list { height: 100%; overflow: hidden; display: flex; flex-direction: column; }
</style>
