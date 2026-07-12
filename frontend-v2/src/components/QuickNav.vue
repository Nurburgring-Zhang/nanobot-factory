<template>
  <div class="quick-nav" :class="{ 'is-collapsed': quickNav.collapsed }">
    <!-- Sidebar toggle row -->
    <div class="quick-nav__head">
      <NButton
        size="small"
        quaternary
        :aria-label="toggleLabel"
        :title="toggleLabel"
        @click="onToggle"
      >
        <template #icon>
          <NIcon>
            <component :is="quickNav.collapsed ? ChevronForwardOutline : ChevronBackOutline" />
          </NIcon>
        </template>
        <span v-if="!quickNav.collapsed" class="quick-nav__head-text">
          {{ headText }}
        </span>
      </NButton>
      <NButton
        v-if="!quickNav.collapsed"
        size="tiny"
        quaternary
        :title="addFavoriteLabel"
        :aria-label="addFavoriteLabel"
        @click="onAddCurrentToFavorites"
      >
        <template #icon>
          <NIcon><StarOutline /></NIcon>
        </template>
      </NButton>
    </div>

    <!-- Collapsed view: just the toggle -->
    <div v-if="quickNav.collapsed" class="quick-nav__collapsed">
      <NButton
        size="small"
        quaternary
        :title="expandLabel"
        :aria-label="expandLabel"
        @click="onToggle"
      >
        <template #icon>
          <NIcon><ChevronForwardOutline /></NIcon>
        </template>
      </NButton>
    </div>

    <div v-else class="quick-nav__body">
      <!-- Favorites -->
      <section class="quick-nav__section">
        <header class="quick-nav__section-head">
          <span class="quick-nav__section-title">
            <NIcon size="14"><StarOutline /></NIcon>
            {{ favoritesLabel }}
            <NTag size="tiny" :bordered="false">{{ quickNav.favorites.length }}</NTag>
          </span>
        </header>
        <ul v-if="quickNav.favorites.length" class="quick-nav__items" role="list">
          <li
            v-for="fav in quickNav.sortedFavorites"
            :key="`fav:${fav.path}`"
            class="quick-nav__item"
          >
            <RouterLink
              :to="fav.path"
              class="quick-nav__link"
              active-class="is-active"
              @click="onVisit(fav.path, fav.title, fav.icon)"
            >
              <span class="quick-nav__icon" aria-hidden="true">{{ fav.icon || '★' }}</span>
              <span class="quick-nav__title">{{ fav.title }}</span>
            </RouterLink>
            <NButton
              size="tiny"
              quaternary
              :title="unstarLabel"
              :aria-label="unstarLabel"
              class="quick-nav__action"
              @click="onUnfavorite(fav.path)"
            >
              <template #icon>
                <NIcon><Star /></NIcon>
              </template>
            </NButton>
          </li>
        </ul>
        <div v-else class="quick-nav__empty">{{ favoritesEmptyText }}</div>
      </section>

      <!-- Recent -->
      <section class="quick-nav__section">
        <header class="quick-nav__section-head">
          <span class="quick-nav__section-title">
            <NIcon size="14"><TimeOutline /></NIcon>
            {{ recentLabel }}
            <NTag size="tiny" :bordered="false">{{ quickNav.recent.length }}</NTag>
          </span>
          <NButton
            v-if="quickNav.recent.length"
            size="tiny"
            quaternary
            :title="clearRecentLabel"
            @click="onClearRecent"
          >
            {{ clearText }}
          </NButton>
        </header>
        <ul v-if="quickNav.topRecent.length" class="quick-nav__items" role="list">
          <li
            v-for="r in quickNav.topRecent"
            :key="`recent:${r.path}`"
            class="quick-nav__item"
          >
            <RouterLink
              :to="r.path"
              class="quick-nav__link"
              active-class="is-active"
              @click="onVisit(r.path, r.title, r.icon)"
            >
              <span class="quick-nav__icon" aria-hidden="true">{{ r.icon || '◦' }}</span>
              <span class="quick-nav__title">{{ r.title }}</span>
            </RouterLink>
            <NButton
              size="tiny"
              quaternary
              :title="starLabel"
              :aria-label="starLabel"
              class="quick-nav__action"
              @click="onFavorite(r)"
            >
              <template #icon>
                <NIcon><StarOutline /></NIcon>
              </template>
            </NButton>
          </li>
        </ul>
        <div v-else class="quick-nav__empty">{{ recentEmptyText }}</div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NIcon, NTag } from 'naive-ui'
import {
  ChevronBackOutline,
  ChevronForwardOutline,
  Star,
  StarOutline,
  TimeOutline,
} from '@vicons/ionicons5'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useQuickNavStore, type NavItem } from '@/stores/quicknav'

/**
 * QuickNav.vue (P17-D3)
 *
 * Left sidebar complement to DefaultLayout. Shows:
 *   - Toggle to collapse/expand the panel (state persisted)
 *   - Favorites list (user-starred routes)
 *   - Recent list (auto-tracked by App.vue from router navigation)
 *
 * The toggle here is *additive* — DefaultLayout's NLayoutSider
 * remains the primary navigation. This component slots in beside it
 * as a quick-access panel.
 */

const route = useRoute()
const router = useRouter()
const quickNav = useQuickNavStore()
const { locale } = useI18n()

const isZh = computed<boolean>(() => (locale.value || '').toLowerCase().startsWith('zh'))
const t = (en: string, zh: string): string => (isZh.value ? zh : en)

const toggleLabel = computed<string>(() =>
  quickNav.collapsed
    ? t('Expand quick navigation', '展开快速导航')
    : t('Collapse quick navigation', '收起快速导航'),
)
const expandLabel = computed<string>(() => t('Expand', '展开'))
const headText = computed<string>(() => t('Quick Navigation', '快速导航'))
const favoritesLabel = computed<string>(() => t('Favorites', '收藏'))
const recentLabel = computed<string>(() => t('Recent', '最近'))
const favoritesEmptyText = computed<string>(() =>
  t('No favorites yet — star any page', '还没有收藏 — 给任意页面加星标'),
)
const recentEmptyText = computed<string>(() =>
  t('No recent pages — start navigating', '最近还没记录 — 开始浏览吧'),
)
const clearRecentLabel = computed<string>(() => t('Clear recent', '清除最近'))
const clearText = computed<string>(() => t('Clear', '清除'))
const starLabel = computed<string>(() => t('Add to favorites', '加入收藏'))
const unstarLabel = computed<string>(() => t('Remove from favorites', '取消收藏'))
const addFavoriteLabel = computed<string>(() =>
  t('Star current page', '收藏当前页'),
)

function onToggle() {
  quickNav.toggleCollapsed()
}

function onVisit(path: string, title: string, icon?: string) {
  quickNav.trackVisit({ path, title, icon, hint: title })
}

function onFavorite(item: NavItem) {
  quickNav.toggleFavorite({
    path: item.path,
    title: item.title,
    icon: item.icon,
    hint: item.hint ?? item.title,
  })
}

function onUnfavorite(path: string) {
  quickNav.removeFavorite(path)
}

function onClearRecent() {
  quickNav.clearRecent()
}

function onAddCurrentToFavorites() {
  const meta = route.meta as { title?: unknown } | undefined
  const title = typeof meta?.title === 'string' ? meta.title : (route.name as string) || route.path
  quickNav.addFavorite({
    path: route.path,
    title,
    icon: '★',
    hint: title,
  })
  // Avoid unused-import false positives on RouterLink (used in template)
  void RouterLink
  void router
}
</script>

<style scoped>
.quick-nav {
  display: flex;
  flex-direction: column;
  background: var(--app-surface, #fff);
  border-right: 1px solid var(--app-border, rgba(0, 0, 0, 0.06));
  height: 100%;
  width: 240px;
  transition: width 0.18s ease;
  overflow: hidden;
}
.quick-nav.is-collapsed {
  width: 56px;
}

.quick-nav__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  border-bottom: 1px solid var(--app-border, rgba(0, 0, 0, 0.06));
}
.quick-nav__head-text {
  font-size: 12px;
  font-weight: 600;
  margin-left: 4px;
  color: var(--app-muted, #767676);
}
.quick-nav__collapsed {
  display: flex;
  justify-content: center;
  padding: 8px 0;
}

.quick-nav__body {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 8px 0;
}

.quick-nav__section {
  margin-bottom: 14px;
}
.quick-nav__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px 4px 12px;
}
.quick-nav__section-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: var(--app-muted, #767676);
}

.quick-nav__items {
  list-style: none;
  margin: 0;
  padding: 0;
}
.quick-nav__item {
  display: flex;
  align-items: center;
  padding: 0 6px;
  border-radius: 4px;
  margin: 0 4px;
}
.quick-nav__item:hover {
  background: var(--app-border, rgba(0, 0, 0, 0.04));
}
.quick-nav__link {
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 6px;
  text-decoration: none;
  color: var(--app-fg, #333);
  font-size: 12px;
  border-radius: 4px;
  overflow: hidden;
}
.quick-nav__link.is-active {
  background: var(--app-border, rgba(10, 93, 194, 0.10));
  color: var(--app-primary, #0a5dc2);
  font-weight: 600;
}
.quick-nav__icon {
  display: inline-block;
  width: 16px;
  text-align: center;
  color: var(--app-primary, #0a5dc2);
}
.quick-nav__title {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.quick-nav__action {
  flex: 0 0 auto;
  opacity: 0.6;
}
.quick-nav__action:hover {
  opacity: 1;
}

.quick-nav__empty {
  font-size: 11px;
  color: var(--app-muted, #767676);
  padding: 6px 12px;
  font-style: italic;
}
</style>