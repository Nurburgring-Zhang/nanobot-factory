<template>
  <div class="page-root">
    <NCard title="全局搜索" :bordered="false">
      <SearchBar v-model="keyword" placeholder="搜索资产 / 数据集 / 标注 / 工作流" @search="onSearch" @reset="onReset">
        <template #extra>
          <NSelect v-model:value="typeFilter" :options="typeOptions" style="width: 160px" clearable placeholder="类型筛选" />
          <ActionButton type="primary" @click="onSearch">
            <template #icon><NIcon><SearchOutline /></NIcon></template>
            搜索
          </ActionButton>
        </template>
      </SearchBar>

      <NGrid :cols="3" :x-gap="12" :y-gap="12" responsive="screen">
        <NGi v-for="hit in rows" :key="hit.id">
          <NCard size="small" hoverable>
            <template #header>
              <NSpace align="center">
                <NTag :type="hitTypeTag(hit.type)">{{ hit.type }}</NTag>
                <span>{{ hit.title }}</span>
              </NSpace>
            </template>
            <div class="hit-snippet">{{ hit.snippet || '(无摘要)' }}</div>
            <template #footer>
              <NSpace justify="space-between" align="center">
                <span class="hit-score">score: {{ hit.score ?? '-' }}</span>
                <ActionButton size="tiny" @click="goDetail(hit)">查看</ActionButton>
              </NSpace>
            </template>
          </NCard>
        </NGi>
      </NGrid>

      <div v-if="!loading && rows.length === 0 && !error" style="margin-top: 24px">
        <NEmpty description="请输入关键词开始搜索" />
      </div>
      <NAlert v-if="error" type="error" style="margin-top: 12px">{{ error }}</NAlert>

      <div v-if="total > pageSize" style="margin-top: 12px; display: flex; justify-content: flex-end">
        <NPagination
          v-model:page="page"
          :page-size="pageSize"
          :item-count="total"
          show-size-picker
          :page-sizes="[10, 20, 50, 100]"
          @update:page="load"
          @update:page-size="(s: number) => { pageSize = s; page = 1; load() }"
        />
      </div>
    </NCard>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NCard, NGrid, NGi, NEmpty, NAlert, NTag, NSpace, NSelect, NIcon, NPagination, useMessage } from 'naive-ui'
import { SearchOutline } from '@vicons/ionicons5'
import { useRouter } from 'vue-router'
import SearchBar from '@/components/SearchBar.vue'
import ActionButton from '@/components/ActionButton.vue'
import { searchAll, type SearchHit } from '@/api/search'

const message = useMessage()
const router = useRouter()
const keyword = ref('')
const typeFilter = ref<SearchHit['type'] | null>(null)
const page = ref(1)
const pageSize = ref(20)
const rows = ref<SearchHit[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

const typeOptions = [
  { label: '资产', value: 'asset' },
  { label: '数据集', value: 'dataset' },
  { label: '标注', value: 'annotation' },
  { label: '工作流', value: 'workflow' }
]

function hitTypeTag(type: SearchHit['type']): 'info' | 'success' | 'warning' | 'error' {
  switch (type) {
    case 'asset': return 'info'
    case 'dataset': return 'success'
    case 'annotation': return 'warning'
    case 'workflow': return 'error'
    default: return 'info'
  }
}

async function load() {
  if (!keyword.value.trim()) { rows.value = []; total.value = 0; return }
  loading.value = true; error.value = null
  try {
    const res = await searchAll({ q: keyword.value, type: typeFilter.value ?? undefined, page: page.value, page_size: pageSize.value })
    rows.value = res.items; total.value = res.total
  } catch (e) {
    error.value = (e as Error).message || '搜索失败'; rows.value = []; total.value = 0
  } finally { loading.value = false }
}

function onSearch() { page.value = 1; load() }
function onReset() { keyword.value = ''; typeFilter.value = null; page.value = 1; rows.value = []; total.value = 0 }

function goDetail(hit: SearchHit) {
  const map: Record<SearchHit['type'], string> = {
    asset: '/asset-management',
    dataset: '/dataset-management',
    annotation: '/annotation-management',
    workflow: '/workflow-management'
  }
  router.push({ path: map[hit.type], query: { highlight: String(hit.id) } }).catch(() => undefined)
  message.info(`跳转到 ${hit.type} 详情`)
}

onMounted(() => { /* lazy load on first search */ })
</script>

<style scoped>
.page-root { padding: 16px; }
.hit-snippet { color: var(--n-text-color-3); font-size: 13px; min-height: 36px; }
.hit-score { font-size: 12px; color: var(--n-text-color-3); }
</style>
