<template>
  <div class="global-search">
    <NButton
      class="global-search__trigger"
      size="small"
      tertiary
      :aria-label="triggerLabel"
      @click="onOpen"
    >
      <template #icon>
        <NIcon><SearchOutline /></NIcon>
      </template>
      <span class="global-search__trigger-text">{{ placeholderText }}</span>
      <span class="global-search__trigger-kbd" aria-hidden="true">
        {{ kbdHint }}
      </span>
    </NButton>

    <NModal
      v-model:show="uiStore.searchPaletteOpen"
      :mask-closable="true"
      :bordered="false"
      :auto-focus="true"
      preset="card"
      class="global-search__modal"
      :style="{ width: '720px', maxWidth: '92vw' }"
      :title="modalTitle"
      transform-origin="center"
    >
      <div class="global-search__body">
        <div class="global-search__input-row">
          <NIcon class="global-search__input-icon" aria-hidden="true">
            <SearchOutline />
          </NIcon>
          <NInput
            ref="inputRef"
            v-model:value="query"
            :placeholder="inputPlaceholder"
            clearable
            autofocus
            size="large"
            :input-props="{ 'aria-label': inputPlaceholder }"
            @input="onInput"
            @keydown="onKeyDown"
          />
          <NButton size="small" quaternary @click="onClose">
            {{ closeText }}
          </NButton>
        </div>

        <!-- Domain filter chips -->
        <div class="global-search__chips">
          <NTag
            v-for="d in DOMAINS"
            :key="d.key"
            size="small"
            :bordered="false"
            :type="selectedDomains.has(d.key) ? 'primary' : 'default'"
            :checkable="true"
            :checked="selectedDomains.has(d.key)"
            class="global-search__chip"
            @update:checked="(v: boolean) => toggleDomain(d.key, v)"
          >
            <span class="global-search__chip-dot" :style="{ background: d.color }" aria-hidden="true" />
            {{ d.label }}
            <span v-if="results && results.counts[d.key]" class="global-search__chip-count">
              {{ results.counts[d.key] }}
            </span>
          </NTag>
        </div>

        <NSpin :show="loading">
          <div class="global-search__results">
            <template v-if="!query.trim()">
              <NEmpty :description="emptyHint">
                <template #extra>
                  <NText depth="3" style="font-size: 12px">
                    {{ hintSubText }}
                  </NText>
                </template>
              </NEmpty>
            </template>

            <template v-else-if="error">
              <NAlert type="error" :show-icon="true" :title="errorTitle">
                {{ error }}
              </NAlert>
            </template>

            <template v-else-if="results && results.hits.length === 0">
              <NEmpty :description="noResultsText">
                <template #extra>
                  <NText depth="3" style="font-size: 12px">
                    {{ noResultsHint }}
                  </NText>
                </template>
              </NEmpty>
            </template>

            <template v-else-if="results">
              <div
                v-for="group in groupedResults"
                :key="group.domain"
                class="global-search__group"
              >
                <div class="global-search__group-head">
                  <span class="global-search__group-title">
                    {{ group.domainTitle }}
                  </span>
                  <NTag size="tiny" :bordered="false">
                    {{ group.hits.length }}
                  </NTag>
                </div>
                <ul class="global-search__items" role="listbox">
                  <li
                    v-for="hit in group.hits"
                    :key="`${hit.domain}:${hit.id}`"
                    class="global-search__item"
                    :class="{ 'is-active': isActive(hit) }"
                    role="option"
                    :aria-selected="isActive(hit)"
                    @mouseenter="activeIndex = hitIndex(hit)"
                    @click="onSelect(hit)"
                  >
                    <div class="global-search__item-row">
                      <span
                        class="global-search__item-dot"
                        :style="{ background: domainColor(hit.domain) }"
                        aria-hidden="true"
                      />
                      <span class="global-search__item-title">{{ hit.title }}</span>
                      <span class="global-search__item-domain">
                        {{ domainShort(hit.domain) }}
                      </span>
                      <NTag size="tiny" :bordered="false" type="info">
                        {{ Math.round((hit.score || 0) * 100) }}%
                      </NTag>
                    </div>
                    <div v-if="hit.snippet" class="global-search__item-snippet">
                      {{ hit.snippet }}
                    </div>
                  </li>
                </ul>
              </div>
              <div v-if="results.elapsed_ms !== undefined" class="global-search__foot">
                {{ results.total }} {{ hitsText }} · {{ results.elapsed_ms }} ms
              </div>
            </template>
          </div>
        </NSpin>
      </div>

      <template #footer>
        <div class="global-search__footer">
          <span class="global-search__hint">
            <kbd>↑</kbd><kbd>↓</kbd> {{ navigateText }}
            <kbd>↵</kbd> {{ openText }}
            <kbd>Esc</kbd> {{ closeText }}
          </span>
          <span class="global-search__credit">
            {{ backendLabel }}
          </span>
        </div>
      </template>
    </NModal>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  NAlert, NButton, NEmpty, NIcon, NInput, NModal, NSpin, NTag, NText,
} from 'naive-ui'
import { SearchOutline } from '@vicons/ionicons5'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useUiStore } from '@/stores/ui'
import { useQuickNavStore } from '@/stores/quicknav'
import {
  searchGlobal,
  type GlobalDomain,
  type GlobalHit,
  type GlobalSearchResponse,
} from '@/api/search'

/**
 * GlobalSearch.vue (P17-D3)
 *
 * Top-bar trigger button + Ctrl/⌘+K palette. Debounced query →
 * GET /api/v1/search/global. Results grouped by domain with:
 *  - keyboard navigation (↑/↓, Enter to open, Esc to close)
 *  - domain filter chips
 *  - domain-coloured dots and tags
 *  - score percentage chip
 *
 * The trigger button is what lives in the DefaultLayout header. The
 * modal body lives at root level so z-index doesn't get trapped.
 */

const router = useRouter()
const uiStore = useUiStore()
const quickNav = useQuickNavStore()
const { locale } = useI18n()

const isZh = computed<boolean>(() => (locale.value || '').toLowerCase().startsWith('zh'))
const t = (en: string, zh: string): string => (isZh.value ? zh : en)

const triggerLabel = computed<string>(() => t('Search (Ctrl+K)', '搜索 (Ctrl+K)'))
const placeholderText = computed<string>(() => t('Search…', '搜索…'))
const modalTitle = computed<string>(() => t('Global Search', '全局搜索'))
const inputPlaceholder = computed<string>(() =>
  t('Search datasets, projects, users, assets, agents, workflows…',
    '搜索数据集、项目、用户、资产、智能体、工作流…'),
)
const kbdHint = computed<string>(() => 'Ctrl K')
const closeText = computed<string>(() => t('Close', '关闭'))
const emptyHint = computed<string>(() => t('Type to search across all domains', '输入关键字跨域搜索'))
const hintSubText = computed<string>(() => t('Try: test, prod, dataset, alice', '试试:test, prod, dataset, alice'))
const noResultsText = computed<string>(() => t('No matches', '没有匹配结果'))
const noResultsHint = computed<string>(() => t('Try a different keyword or remove filters', '换个关键字或移除过滤'))
const errorTitle = computed<string>(() => t('Search failed', '搜索失败'))
const hitsText = computed<string>(() => t('hits', '条结果'))
const navigateText = computed<string>(() => t('Navigate', '选择'))
const openText = computed<string>(() => t('Open', '打开'))
const backendLabel = computed<string>(() => t('Powered by /api/v1/search/global', '由 /api/v1/search/global 提供'))

interface DomainSpec {
  key: GlobalDomain
  label: string
  color: string
  short: string
}

const DOMAINS: DomainSpec[] = [
  { key: 'dataset', label: '数据集', color: '#0a5dc2', short: 'DS' },
  { key: 'project', label: '项目', color: '#157a3e', short: 'PJ' },
  { key: 'user', label: '用户', color: '#c87f0d', short: 'USR' },
  { key: 'asset', label: '资产', color: '#5e3aa8', short: 'AST' },
  { key: 'agent', label: '智能体', color: '#d03050', short: 'AGT' },
  { key: 'workflow', label: '工作流', color: '#0a8c8c', short: 'WF' },
]

const domainColor = (d: GlobalDomain): string => {
  return DOMAINS.find((x) => x.key === d)?.color ?? '#666'
}

const domainShort = (d: GlobalDomain): string => {
  return DOMAINS.find((x) => x.key === d)?.short ?? d.toUpperCase()
}

const query = ref<string>('')
const loading = ref<boolean>(false)
const error = ref<string>('')
const results = ref<GlobalSearchResponse | null>(null)
const activeIndex = ref<number>(0)
const selectedDomains = ref<Set<GlobalDomain>>(new Set())
const inputRef = ref<InstanceType<typeof NInput> | null>(null)

let debounceHandle: ReturnType<typeof setTimeout> | null = null
let lastFetchSeq = 0

function onOpen() {
  uiStore.openSearchPalette()
  nextTick(() => {
    const input = (inputRef.value as unknown as { focus?: () => void } | null)
    if (input && typeof input.focus === 'function') input.focus()
  })
}

function onClose() {
  uiStore.closeSearchPalette()
  query.value = ''
  results.value = null
  error.value = ''
  activeIndex.value = 0
}

function toggleDomain(d: GlobalDomain, on: boolean) {
  if (on) {
    selectedDomains.value.add(d)
  } else {
    selectedDomains.value.delete(d)
  }
  // Trigger re-render (Set mutation isn't reactive in Vue 3 unless wrapped)
  selectedDomains.value = new Set(selectedDomains.value)
  if (query.value.trim()) runSearch()
}

const groupedResults = computed<Array<{ domain: GlobalDomain; domainTitle: string; hits: GlobalHit[] }>>(() => {
  if (!results.value) return []
  const groups = new Map<GlobalDomain, GlobalHit[]>()
  for (const h of results.value.hits) {
    if (!groups.has(h.domain)) groups.set(h.domain, [])
    groups.get(h.domain)!.push(h)
  }
  const out: Array<{ domain: GlobalDomain; domainTitle: string; hits: GlobalHit[] }> = []
  for (const spec of DOMAINS) {
    const list = groups.get(spec.key)
    if (!list || list.length === 0) continue
    out.push({ domain: spec.key, domainTitle: spec.label, hits: list })
  }
  return out
})

const flatHits = computed<GlobalHit[]>(() => {
  return groupedResults.value.flatMap((g) => g.hits)
})

function hitIndex(hit: GlobalHit): number {
  return flatHits.value.findIndex(
    (h) => h.domain === hit.domain && String(h.id) === String(hit.id),
  )
}

function isActive(hit: GlobalHit): boolean {
  return hitIndex(hit) === activeIndex.value
}

function onInput(_v: string) {
  if (debounceHandle) clearTimeout(debounceHandle)
  debounceHandle = setTimeout(() => {
    runSearch()
  }, 220)
}

async function runSearch() {
  const q = query.value.trim()
  if (!q) {
    results.value = null
    error.value = ''
    return
  }
  loading.value = true
  error.value = ''
  const seq = ++lastFetchSeq
  try {
    const domains = selectedDomains.value.size > 0
      ? Array.from(selectedDomains.value)
      : undefined
    const res = await searchGlobal({ q, top_k: 4, domains })
    if (seq !== lastFetchSeq) return
    results.value = res
    activeIndex.value = 0
  } catch (e) {
    if (seq !== lastFetchSeq) return
    error.value = (e as Error).message || 'search failed'
    results.value = null
  } finally {
    if (seq === lastFetchSeq) loading.value = false
  }
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    onClose()
    return
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    const max = flatHits.value.length - 1
    if (max < 0) return
    activeIndex.value = (activeIndex.value + 1) > max ? 0 : activeIndex.value + 1
    return
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    const max = flatHits.value.length - 1
    if (max < 0) return
    activeIndex.value = (activeIndex.value - 1) < 0 ? max : activeIndex.value - 1
    return
  }
  if (e.key === 'Enter') {
    e.preventDefault()
    const hit = flatHits.value[activeIndex.value]
    if (hit) onSelect(hit)
  }
}

function onSelect(hit: GlobalHit) {
  const path = hit.url || `/${hit.domain}/${hit.id}`
  quickNav.trackVisit({
    path,
    title: hit.title,
    icon: domainShort(hit.domain),
    hint: `${hit.domain_title} · ${hit.title}`,
  })
  void router.push(path)
  onClose()
}

watch(
  () => uiStore.searchPaletteOpen,
  (open) => {
    if (open) {
      nextTick(() => {
        const input = (inputRef.value as unknown as { focus?: () => void } | null)
        if (input && typeof input.focus === 'function') input.focus()
      })
    }
  },
)

onBeforeUnmount(() => {
  if (debounceHandle) clearTimeout(debounceHandle)
})

defineExpose({
  open: onOpen,
  close: onClose,
  runSearch,
})
</script>

<style scoped>
.global-search {
  display: inline-flex;
  align-items: center;
}
.global-search__trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 200px;
  justify-content: flex-start;
  color: var(--app-muted, #767676);
}
.global-search__trigger-text {
  font-size: 12px;
  flex: 1 1 auto;
  text-align: left;
}
.global-search__trigger-kbd {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--app-border, rgba(0, 0, 0, 0.06));
  color: var(--app-muted, #767676);
  letter-spacing: 0.5px;
}

.global-search__body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.global-search__input-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.global-search__input-icon {
  color: var(--app-muted, #767676);
}

.global-search__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.global-search__chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.global-search__chip-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.global-search__chip-count {
  margin-left: 4px;
  font-size: 10px;
  color: var(--app-muted, #767676);
}

.global-search__results {
  min-height: 200px;
  max-height: 56vh;
  overflow-y: auto;
}

.global-search__group {
  margin-bottom: 12px;
}
.global-search__group-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  border-bottom: 1px solid var(--app-border, rgba(0, 0, 0, 0.06));
}
.global-search__group-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-muted, #767676);
}

.global-search__items {
  list-style: none;
  margin: 4px 0 0 0;
  padding: 0;
}
.global-search__item {
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.12s ease;
}
.global-search__item:hover,
.global-search__item.is-active {
  background: var(--app-border, rgba(10, 93, 194, 0.08));
}
.global-search__item-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.global-search__item-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.global-search__item-title {
  flex: 1 1 auto;
  font-size: 13px;
  color: var(--app-fg, #333);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.global-search__item-domain {
  font-size: 10px;
  color: var(--app-muted, #767676);
  letter-spacing: 0.5px;
}
.global-search__item-snippet {
  font-size: 11px;
  color: var(--app-muted, #767676);
  margin-top: 2px;
  margin-left: 16px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.global-search__foot {
  font-size: 11px;
  color: var(--app-muted, #767676);
  text-align: right;
  margin-top: 8px;
}

.global-search__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  color: var(--app-muted, #767676);
}
.global-search__hint kbd {
  display: inline-block;
  padding: 1px 5px;
  margin: 0 2px;
  font-size: 10px;
  font-family: monospace;
  background: var(--app-border, rgba(0, 0, 0, 0.06));
  border-radius: 3px;
  color: var(--app-fg, #333);
}
</style>