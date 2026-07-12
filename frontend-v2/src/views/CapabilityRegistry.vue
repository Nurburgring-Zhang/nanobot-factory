<template>
  <PageRegion
    :label="t('nav.capabilities')"
    :description="t('common.detail')"
    region-class="capability-registry-root"
  >
    <div class="cr-layout">
      <NCard :bordered="false" size="small" class="cr-toolbar">
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
            v-model:value="category"
            :options="categoryOptions"
            :placeholder="t('common.all')"
            size="small"
            style="width: 200px"
            clearable
            @update:value="reload"
          />
          <NButton size="small" @click="reload" :loading="loading">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ t('common.refresh') }}
          </NButton>
        </NSpace>
      </NCard>

      <NCard :bordered="false" size="small" class="cr-list" :title="t('common.detail')">
        <NAlert v-if="error" type="error" :title="t('common.error')" closable @close="error = ''">
          {{ error }}
        </NAlert>
        <NEmpty v-else-if="!loading && filtered.length === 0" :description="t('common.empty')" style="margin-top: 60px">
          <template #icon><NIcon><CubeOutline /></NIcon></template>
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
      :title="detail?.name || detail?.id || t('common.detail')"
      preset="card"
      style="max-width: 720px"
    >
      <NSpin v-if="!detail" />
      <NDescriptions v-else :column="2" bordered>
        <NDescriptionsItem :label="'ID'">{{ detail.id }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('common.appName')">{{ detail.name }}</NDescriptionsItem>
        <NDescriptionsItem :label="'Category'">{{ detail.category }}</NDescriptionsItem>
        <NDescriptionsItem :label="'Version'">{{ detail.version }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('common.detail')" :span="2">{{ detail.description || '—' }}</NDescriptionsItem>
        <NDescriptionsItem :label="'Inputs'" :span="2">
          <NCode v-if="Object.keys(detail.inputs_schema || {}).length" :code="JSON.stringify(detail.inputs_schema, null, 2)" language="json" />
          <span v-else>—</span>
        </NDescriptionsItem>
        <NDescriptionsItem :label="'Outputs'" :span="2">
          <NCode v-if="Object.keys(detail.outputs_schema || {}).length" :code="JSON.stringify(detail.outputs_schema, null, 2)" language="json" />
          <span v-else>—</span>
        </NDescriptionsItem>
      </NDescriptions>
      <template #footer>
        <NSpace>
          <NButton @click="showDetail = false">{{ t('common.close') }}</NButton>
          <NButton type="primary" @click="invokeCap(detail!)" :loading="actionLoading">
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
  NCard, NSpace, NInput, NSelect, NButton, NIcon, NTag,
  NDataTable, NSpin, NAlert, NEmpty, NModal, NDescriptions, NDescriptionsItem, NCode,
  useMessage, type DataTableColumns,
} from 'naive-ui'
import { SearchOutline, RefreshOutline, CubeOutline } from '@vicons/ionicons5'
import PageRegion from '@/components/PageRegion.vue'
import { fetchCatalogue, invokeCapability, type CapabilityItem, CAPABILITY_CATEGORIES } from '@/api/capabilities_v2'

const { t } = useI18n()
const message = useMessage()

const keyword = ref('')
const category = ref<string | null>(null)
const loading = ref(false)
const actionLoading = ref(false)
const error = ref('')
const items = ref<CapabilityItem[]>([])

const showDetail = ref(false)
const detail = ref<CapabilityItem | null>(null)

const categoryOptions = CAPABILITY_CATEGORIES.map((c) => ({ label: c, value: c }))

const pagination = { pageSize: 25 }
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
    title: t('common.actions'), key: 'actions', width: 140, fixed: 'right',
    render: (row: CapabilityItem) =>
      h(NSpace, { size: 4 }, () => [
        h(NButton, { text: true, type: 'primary', size: 'tiny', onClick: () => viewDetail(row) }, () => t('common.detail')),
      ]),
  },
])

onMounted(reload)

async function reload() {
  loading.value = true
  error.value = ''
  try {
    const cat = await fetchCatalogue()
    items.value = cat.items || []
  } catch (e) {
    error.value = String(e)
    message.error(String(e))
  } finally {
    loading.value = false
  }
}

async function viewDetail(row: CapabilityItem) {
  showDetail.value = true
  detail.value = row
}

async function invokeCap(row: CapabilityItem) {
  actionLoading.value = true
  try {
    await invokeCapability({ capability_id: row.id, inputs: {} })
    message.success(`invoked: ${row.id}`)
  } catch (e) {
    message.error(String(e))
  } finally {
    actionLoading.value = false
  }
}
</script>

<style scoped>
.cr-layout { display: flex; flex-direction: column; gap: 12px; padding: 12px; height: 100%; }
.cr-toolbar { flex-shrink: 0; }
.cr-list { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
</style>
