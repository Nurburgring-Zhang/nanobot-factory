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
      :collapsed="ui.sidebarCollapsed"
      @update:collapsed="(v: boolean) => ui.setSidebarCollapsed(v)"
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
        :collapsed="ui.sidebarCollapsed"
        @update:value="onMenuSelect"
      />
    </NLayoutSider>
    <!-- P17-D3: Quick navigation panel (favorites + recent) -->
    <QuickNav v-if="showQuickNav" class="layout-quicknav" />
    <NLayout>
      <NLayoutHeader bordered class="layout-header" role="banner">
        <Topbar :page-title="pageTitle" />
      </NLayoutHeader>
      <NLayoutContent
        content-style="padding: 24px;"
        :native-scrollbar="false"
      >
        <main id="main" tabindex="-1" role="main" :aria-label="pageTitle">
          <!-- Suspense + Skeleton fallback for lazy-loaded routes -->
          <RouterView v-slot="{ Component }">
            <Suspense>
              <component :is="Component" v-if="Component" />
              <template #fallback>
                <SkeletonLoader variant="block" />
              </template>
            </Suspense>
          </RouterView>
        </main>
      </NLayoutContent>
    </NLayout>
  </NLayout>
</template>

<script setup lang="ts">
import { computed, h, type Component } from 'vue'
import { useRouter, useRoute, RouterLink, RouterView } from 'vue-router'
import {
  NLayout,
  NLayoutSider,
  NLayoutHeader,
  NLayoutContent,
  NMenu,
  type MenuOption
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { useUiStore } from '@/stores/ui'
import { useSkipLink } from '@/utils/skipLink'
import QuickNav from '@/components/QuickNav.vue'
import Topbar from '@/components/Topbar.vue'
import SkeletonLoader from '@/components/SkeletonLoader.vue'

const router = useRouter()
const route = useRoute()
const ui = useUiStore()
const { t } = useI18n()
const { focusMain } = useSkipLink()

// P17-D3: QuickNav is opt-in via env (defaults to visible). This lets
// us hide it on small screens or for demo deployments without code
// changes. Set VITE_DISABLE_QUICKNAV=true to suppress.
const showQuickNav = computed<boolean>(() => {
  try {
    const flag = (import.meta.env.VITE_DISABLE_QUICKNAV ?? '') as string
    return flag !== 'true'
  } catch {
    return true
  }
})

function onSkip(): void {
  focusMain()
}

// ============================================================
// P20-O: Sidebar menu groups
//   - main:   top-level nav (12 base modules)
//   - v5:     V5 core UI (canvas, command, project, requirement,
//             dataset, pack, annotation, qc, delivery, agent)
//   - biz:    12 业务模块
//   - p48:    P4-8 能力 (skills / obsidian / storyboard / lineage / etc.)
//   - flow:   P5 数据流转链路
// ============================================================

const _void: Component = (() => null) as unknown as Component // helper type for h()

const menuOptions: MenuOption[] = [
  // === Top-level: 12 modules ===
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

// === V5 Core UI submenu — 9/12 V5 core pages (P20-O) ===
// canvas / command / project / requirement / dataset / pack /
// annotation / qc / delivery / agent (alias for agent-management).
const v5CoreUiSubmenu: MenuOption = {
  type: 'group',
  label: () => h('span', null, { default: () => 'V5 Core UI' }),
  key: 'v5core',
  children: [
    { label: () => h(RouterLink, { to: '/canvas' }, () => 'Infinite Canvas'), key: 'infinite-canvas', icon: () => h('span', { class: 'menu-icon' }, 'C') },
    { label: () => h(RouterLink, { to: '/command' }, () => 'Command Center'), key: 'command-center', icon: () => h('span', { class: 'menu-icon' }, 'M') },
    { label: () => h(RouterLink, { to: '/projects' }, () => '项目中心'), key: 'ProjectCenter', icon: () => h('span', { class: 'menu-icon' }, '◰') },
    { label: () => h(RouterLink, { to: '/requirements' }, () => '需求中心'), key: 'requirements', icon: () => h('span', { class: 'menu-icon' }, 'R') },
    { label: () => h(RouterLink, { to: '/dataset-management' }, () => 'Dataset Hub'), key: 'dataset-management', icon: () => h('span', { class: 'menu-icon' }, 'D') },
    { label: () => h(RouterLink, { to: '/packs' }, () => '数据包管理'), key: 'packs', icon: () => h('span', { class: 'menu-icon' }, '⬢') },
    { label: () => h(RouterLink, { to: '/annotation-workbench' }, () => 'Annotation Workbench'), key: 'annotation-workbench', icon: () => h('span', { class: 'menu-icon' }, 'A') },
    { label: () => h(RouterLink, { to: '/internal-qc' }, () => 'Internal QC'), key: 'internal-qc', icon: () => h('span', { class: 'menu-icon' }, 'Q') },
    { label: () => h(RouterLink, { to: '/delivery' }, () => 'Delivery'), key: 'delivery', icon: () => h('span', { class: 'menu-icon' }, 'Y') },
    { label: () => h(RouterLink, { to: '/agent-management' }, () => 'Agent'), key: 'agent-management', icon: () => h('span', { class: 'menu-icon' }, 'B') }
  ]
}
menuOptions.push(v5CoreUiSubmenu)

// === Business submenu: 12 业务模块 ===
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
    { label: () => h(RouterLink, { to: '/evaluation-management' }, () => '评测管理'), key: 'evaluation-management', icon: () => h('span', { class: 'menu-icon' }, 'E') },
    { label: () => h(RouterLink, { to: '/workflow-management' }, () => '工作流管理'), key: 'workflow-management', icon: () => h('span', { class: 'menu-icon' }, 'W') },
    { label: () => h(RouterLink, { to: '/notification-management' }, () => '通知管理'), key: 'notification-management', icon: () => h('span', { class: 'menu-icon' }, 'M') },
    { label: () => h(RouterLink, { to: '/search-management' }, () => '全局搜索'), key: 'search-management', icon: () => h('span', { class: 'menu-icon' }, 'Q') },
    { label: () => h(RouterLink, { to: '/canvas-designer' }, () => '画布设计器'), key: 'canvas-designer', icon: () => h('span', { class: 'menu-icon' }, 'P') }
  ]
}
menuOptions.push(businessSubmenu)

// === P4-8 能力: Skills / Obsidian / Storyboard / Workflow / Multimodal / Billing / Lineage ===
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

// === P5-R1 数据流转链路 (T1-T6) ===
const dataflowSubmenu: MenuOption = {
  type: 'group',
  label: () => h('span', null, { default: () => '数据流转链路' }),
  key: 'dataflow',
  children: [
    { label: () => h(RouterLink, { to: '/collection' }, () => '采集中心'), key: 'collection', icon: () => h('span', { class: 'menu-icon' }, '⬇') },
    { label: () => h(RouterLink, { to: '/requester-accept' }, () => '需求方验收'), key: 'requester-accept', icon: () => h('span', { class: 'menu-icon' }, '🤝') }
  ]
}
menuOptions.push(dataflowSubmenu)

const activeMenuKey = computed<string>(() => (route.name as string) || 'dashboard')

const pageTitle = computed<string>(() => {
  const meta = route.meta?.title
  return typeof meta === 'string' ? meta : t('nav.dashboard')
})

function onMenuSelect(key: string) {
  router.push({ name: key })
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
  color: var(--app-primary, #0a5dc2);
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
.menu-icon {
  display: inline-block;
  width: 20px;
  text-align: center;
  color: var(--app-primary, #0a5dc2);
  font-size: 16px;
}

/* P17-D3: QuickNav slots beside the primary NLayoutSider. It sizes
   itself (240px / 56px collapsed) and inherits the surface colour
   tokens so dark mode is automatic. */
.layout-quicknav {
  height: 100vh;
  flex: 0 0 auto;
}
</style>
