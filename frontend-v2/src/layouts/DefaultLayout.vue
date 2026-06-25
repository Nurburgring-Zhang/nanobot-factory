<template>
  <NLayout has-sider style="height: 100vh">
    <!-- WCAG 2.4.1 Bypass Blocks: skip-link for keyboard users -->
    <a class="skip-link" href="#main" @click.prevent="onSkip">
      {{ t('nav.skipToMain') }}
    </a>

    <NLayoutSider
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="240"
      :native-scrollbar="false"
      show-trigger
      role="navigation"
      :aria-label="t('nav.dashboard')"
    >
      <div class="sidebar-brand">
        <span class="brand-text">{{ t('common.appName') }}</span>
        <span class="brand-sub">{{ t('common.appSubName') }}</span>
      </div>
      <NMenu
        :options="menuOptions"
        :value="activeMenuKey"
        :collapsed-width="64"
        :collapsed-icon-size="20"
        :indent="18"
        @update:value="onMenuSelect"
      />
    </NLayoutSider>
    <NLayout>
      <NLayoutHeader bordered class="layout-header" role="banner">
        <h1 class="header-title">{{ pageTitle }}</h1>
        <div class="header-user">
          <NSpace align="center" :size="12">
            <!-- Locale switcher (P6-4 P1: minimal selector) -->
            <NButton
              class="locale-toggle"
              size="small"
              quaternary
              :title="localeTooltip"
              :aria-label="localeTooltip"
              @click="onToggleLocale"
            >
              <template #icon>
                <span class="locale-toggle-label" aria-hidden="true">{{ localeShortLabel }}</span>
              </template>
            </NButton>
            <NButton
              class="theme-toggle"
              size="small"
              quaternary
              :title="themeTooltip"
              :aria-label="themeTooltip"
              @click="onToggleTheme"
            >
              <template #icon>
                <NIcon size="18">
                  <component :is="themeIcon" />
                </NIcon>
              </template>
              <span class="theme-toggle-label">{{ themeShortLabel }}</span>
            </NButton>
            <NTag v-if="auth.user" type="info" size="small" round>
              {{ auth.user.role }}
            </NTag>
            <span v-if="auth.user" class="username">{{ auth.user.username }}</span>
            <NButton size="small" tertiary @click="onLogout">{{ t('nav.logout') }}</NButton>
          </NSpace>
        </div>
      </NLayoutHeader>
      <NLayoutContent
        content-style="padding: 24px;"
        :native-scrollbar="false"
      >
        <main id="main" tabindex="-1" role="main" :aria-label="pageTitle">
          <RouterView />
        </main>
      </NLayoutContent>
    </NLayout>
  </NLayout>
</template>

<script setup lang="ts">
import { computed, h, markRaw, type Component } from 'vue'
import { useRouter, useRoute, RouterLink, RouterView } from 'vue-router'
import {
  NLayout,
  NLayoutSider,
  NLayoutHeader,
  NLayoutContent,
  NMenu,
  NSpace,
  NButton,
  NTag,
  NIcon,
  type MenuOption
} from 'naive-ui'
import {
  SunnyOutline,
  MoonOutline,
  DesktopOutline
} from '@vicons/ionicons5'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { useLocaleStore } from '@/stores/locale'
import { useSkipLink } from '@/utils/skipLink'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const themeStore = useThemeStore()
const localeStore = useLocaleStore()
const { t } = useI18n()
const { focusMain } = useSkipLink()

/**
 * Map theme mode → ionicon component.
 * Use markRaw so Vue doesn't try to make the icon reactive (icons are static).
 */
const themeIcon = computed<Component>(() => {
  const map: Record<'light' | 'dark' | 'auto', Component> = {
    light: markRaw(SunnyOutline),
    dark: markRaw(MoonOutline),
    auto: markRaw(DesktopOutline)
  }
  return map[themeStore.mode] ?? markRaw(SunnyOutline)
})

const themeShortLabel = computed<string>(() => {
  const map: Record<'light' | 'dark' | 'auto', string> = {
    light: localeStore.current === 'zh-CN' ? '浅色' : 'Light',
    dark: localeStore.current === 'zh-CN' ? '深色' : 'Dark',
    auto: localeStore.current === 'zh-CN' ? '自动' : 'Auto'
  }
  return map[themeStore.mode] ?? (localeStore.current === 'zh-CN' ? '浅色' : 'Light')
})

const themeTooltip = computed<string>(() => {
  const next: Record<'light' | 'dark' | 'auto', string> = {
    light: localeStore.current === 'zh-CN' ? '当前:浅色 · 点击切换为深色' : 'Light · click for Dark',
    dark: localeStore.current === 'zh-CN' ? '当前:深色 · 点击切换为自动' : 'Dark · click for Auto',
    auto: localeStore.current === 'zh-CN' ? '当前:自动 (跟随系统) · 点击切换为浅色' : 'Auto (system) · click for Light'
  }
  return next[themeStore.mode] ?? (localeStore.current === 'zh-CN' ? '切换主题' : 'Toggle theme')
})

const localeShortLabel = computed<string>(() => {
  return localeStore.current === 'zh-CN' ? '中' : 'EN'
})

const localeTooltip = computed<string>(() => {
  return localeStore.current === 'zh-CN'
    ? '当前:简体中文 · 点击切换为 English'
    : 'Current: English · click for 简体中文'
})

function onToggleTheme(): void {
  themeStore.cycle()
}

function onToggleLocale(): void {
  void localeStore.toggle()
}

function onSkip(): void {
  focusMain()
}

const menuOptions: MenuOption[] = [
  { label: () => h(RouterLink, { to: '/' }, () => t('nav.dashboard')), key: 'dashboard', icon: () => h('span', { class: 'menu-icon' }, '◈') },
  { label: () => h(RouterLink, { to: '/dataset' }, () => t('nav.dataset')), key: 'dataset', icon: () => h('span', { class: 'menu-icon' }, '▤') },
  { label: () => h(RouterLink, { to: '/annotation' }, () => t('nav.annotation')), key: 'annotation', icon: () => h('span', { class: 'menu-icon' }, '✎') },
  { label: () => h(RouterLink, { to: '/review' }, () => t('nav.review')), key: 'review', icon: () => h('span', { class: 'menu-icon' }, '✓') },
  { label: () => h(RouterLink, { to: '/scoring' }, () => t('nav.scoring')), key: 'scoring', icon: () => h('span', { class: 'menu-icon' }, '★') },
  { label: () => h(RouterLink, { to: '/workflows' }, () => t('nav.workflows')), key: 'workflows', icon: () => h('span', { class: 'menu-icon' }, '⇄') },
  { label: () => h(RouterLink, { to: '/engines' }, () => t('nav.engines')), key: 'engines', icon: () => h('span', { class: 'menu-icon' }, '◆') },
  { label: () => h(RouterLink, { to: '/tasks' }, () => t('nav.tasks')), key: 'tasks', icon: () => h('span', { class: 'menu-icon' }, '☰') },
  { label: () => h(RouterLink, { to: '/users' }, () => t('nav.users')), key: 'users', icon: () => h('span', { class: 'menu-icon' }, '☷') },
  { label: () => h(RouterLink, { to: '/billing' }, () => t('nav.billing')), key: 'billing', icon: () => h('span', { class: 'menu-icon' }, '☼') },
  { label: () => h(RouterLink, { to: '/monitoring' }, () => t('nav.monitoring')), key: 'monitoring', icon: () => h('span', { class: 'menu-icon' }, '◉') },
  { label: () => h(RouterLink, { to: '/settings' }, () => t('nav.settings')), key: 'settings', icon: () => h('span', { class: 'menu-icon' }, '⚙') }
]
// === Business submenu: 12 业务模块 (P3-7-W2) ===
const businessSubmenu: MenuOption = {
  type: 'group',
  label: () => h('span', null, { default: () => '业务模块' }),
  key: 'biz',
  children: [
    { label: () => h(RouterLink, { to: '/user-management' }, () => '用户管理'), key: 'user-management', icon: () => h('span', { class: 'menu-icon' }, 'U') },
    { label: () => h(RouterLink, { to: '/asset-management' }, () => '资产管理'), key: 'asset-management', icon: () => h('span', { class: 'menu-icon' }, 'A') },
    { label: () => h(RouterLink, { to: '/annotation-management' }, () => '标注管理'), key: 'annotation-management', icon: () => h('span', { class: 'menu-icon' }, 'N') },
    { label: () => h(RouterLink, { to: '/cleaning-management' }, () => '清洗管理'), key: 'cleaning-management', icon: () => h('span', { class: 'menu-icon' }, 'C') },
    { label: () => h(RouterLink, { to: '/scoring-management' }, () => '评分管理'), key: 'scoring-management', icon: () => h('span', { class: 'menu-icon' }, 'S') },
    { label: () => h(RouterLink, { to: '/dataset-management' }, () => '数据集管理'), key: 'dataset-management', icon: () => h('span', { class: 'menu-icon' }, 'D') },
    { label: () => h(RouterLink, { to: '/evaluation-management' }, () => '评测管理'), key: 'evaluation-management', icon: () => h('span', { class: 'menu-icon' }, 'E') },
    { label: () => h(RouterLink, { to: '/agent-management' }, () => '智能体管理'), key: 'agent-management', icon: () => h('span', { class: 'menu-icon' }, 'B') },
    { label: () => h(RouterLink, { to: '/workflow-management' }, () => '工作流管理'), key: 'workflow-management', icon: () => h('span', { class: 'menu-icon' }, 'W') },
    { label: () => h(RouterLink, { to: '/notification-management' }, () => '通知管理'), key: 'notification-management', icon: () => h('span', { class: 'menu-icon' }, 'M') },
    { label: () => h(RouterLink, { to: '/search-management' }, () => '全局搜索'), key: 'search-management', icon: () => h('span', { class: 'menu-icon' }, 'Q') },
    { label: () => h(RouterLink, { to: '/canvas-designer' }, () => '画布设计器'), key: 'canvas-designer', icon: () => h('span', { class: 'menu-icon' }, 'P') }
  ]
}
menuOptions.push(businessSubmenu)

// === P4-8-W2 新增菜单组: Skills / Obsidian / Storyboard / Workflow / Multimodal / Billing / Lineage ===
const skillsSubmenu: MenuOption = {
  type: 'group',
  label: () => h('span', null, { default: () => 'P4-8 能力' }),
  key: 'p48',
  children: [
    { label: () => h(RouterLink, { to: '/skills' }, () => 'Skill 市场'), key: 'skills', icon: () => h('span', { class: 'menu-icon' }, '◇') },
    { label: () => h(RouterLink, { to: '/skills/orchestrator' }, () => 'Skill 编排'), key: 'skills-orchestrator', icon: () => h('span', { class: 'menu-icon' }, '⬡') },
    { label: () => h(RouterLink, { to: '/obsidian/graph' }, () => '知识图谱'), key: 'obsidian-graph', icon: () => h('span', { class: 'menu-icon' }, '◉') },
    { label: () => h(RouterLink, { to: '/obsidian/wiki' }, () => 'Wiki 列表'), key: 'obsidian-wiki', icon: () => h('span', { class: 'menu-icon' }, '✎') },
    { label: () => h(RouterLink, { to: '/assets/storyboard' }, () => '分镜编辑器'), key: 'assets-storyboard', icon: () => h('span', { class: 'menu-icon' }, '🎬') },
    { label: () => h(RouterLink, { to: '/workflow/visual' }, () => '工作流可视化'), key: 'workflow-visual', icon: () => h('span', { class: 'menu-icon' }, '⇄') },
    { label: () => h(RouterLink, { to: '/agent/multimodal' }, () => '多模态对话'), key: 'agent-multimodal', icon: () => h('span', { class: 'menu-icon' }, '💬') },
    { label: () => h(RouterLink, { to: '/billing/dashboard' }, () => '计费仪表盘'), key: 'billing-dashboard', icon: () => h('span', { class: 'menu-icon' }, '💰') },
    { label: () => h(RouterLink, { to: '/lineage' }, () => '数据血缘'), key: 'lineage', icon: () => h('span', { class: 'menu-icon' }, '🕸') },
  ]
}
menuOptions.push(skillsSubmenu)

const activeMenuKey = computed<string>(() => (route.name as string) || 'dashboard')

const pageTitle = computed<string>(() => {
  const meta = route.meta?.title
  return typeof meta === 'string' ? meta : t('nav.dashboard')
})

function onMenuSelect(key: string) {
  router.push({ name: key })
}

function onLogout() {
  auth.logout()
  router.replace({ name: 'login' })
}
</script>

<style scoped>
.sidebar-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 18px 12px 14px 12px;
  border-bottom: 1px solid var(--app-border, rgba(255, 255, 255, 0.08));
}
.brand-text {
  font-size: 22px;
  font-weight: 700;
  color: #2080f0;
  letter-spacing: 4px;
}
.brand-sub {
  font-size: 11px;
  color: var(--app-muted, #767676);
  margin-top: 2px;
}
.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 56px;
  background: var(--app-surface, #fff);
  color: var(--app-fg, #333);
  transition: background-color 0.18s ease, color 0.18s ease;
}
.header-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}
.header-user {
  display: flex;
  align-items: center;
  gap: 12px;
}
.username {
  font-size: 13px;
  color: var(--app-muted, #767676);
}
.menu-icon {
  display: inline-block;
  width: 20px;
  text-align: center;
  color: #2080f0;
  font-size: 16px;
}
.theme-toggle,
.locale-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.theme-toggle-label,
.locale-toggle-label {
  font-size: 12px;
  margin-left: 2px;
  color: var(--app-muted, #767676);
}
.locale-toggle-label {
  font-weight: 600;
  letter-spacing: 0.5px;
}
</style>