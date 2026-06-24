<template>
  <NLayout has-sider style="height: 100vh">
    <NLayoutSider
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="240"
      :native-scrollbar="false"
      show-trigger
    >
      <div class="sidebar-brand">
        <span class="brand-text">智影</span>
        <span class="brand-sub">nanobot-factory</span>
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
      <NLayoutHeader bordered class="layout-header">
        <div class="header-title">{{ pageTitle }}</div>
        <div class="header-user">
          <NSpace align="center">
            <NTag v-if="auth.user" type="info" size="small" round>
              {{ auth.user.role }}
            </NTag>
            <span v-if="auth.user" class="username">{{ auth.user.username }}</span>
            <NButton size="small" tertiary @click="onLogout">退出登录</NButton>
          </NSpace>
        </div>
      </NLayoutHeader>
      <NLayoutContent
        content-style="padding: 24px;"
        :native-scrollbar="false"
      >
        <RouterView />
      </NLayoutContent>
    </NLayout>
  </NLayout>
</template>

<script setup lang="ts">
import { computed, h } from 'vue'
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
  type MenuOption
} from 'naive-ui'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const menuOptions: MenuOption[] = [
  { label: () => h(RouterLink, { to: '/' }, () => '仪表盘'), key: 'dashboard', icon: () => h('span', { class: 'menu-icon' }, '◈') },
  { label: () => h(RouterLink, { to: '/dataset' }, () => '数据集'), key: 'dataset', icon: () => h('span', { class: 'menu-icon' }, '▤') },
  { label: () => h(RouterLink, { to: '/annotation' }, () => '标注'), key: 'annotation', icon: () => h('span', { class: 'menu-icon' }, '✎') },
  { label: () => h(RouterLink, { to: '/review' }, () => '审核'), key: 'review', icon: () => h('span', { class: 'menu-icon' }, '✓') },
  { label: () => h(RouterLink, { to: '/scoring' }, () => '评分'), key: 'scoring', icon: () => h('span', { class: 'menu-icon' }, '★') },
  { label: () => h(RouterLink, { to: '/workflows' }, () => '工作流'), key: 'workflows', icon: () => h('span', { class: 'menu-icon' }, '⇄') },
  { label: () => h(RouterLink, { to: '/engines' }, () => '引擎'), key: 'engines', icon: () => h('span', { class: 'menu-icon' }, '◆') },
  { label: () => h(RouterLink, { to: '/tasks' }, () => '任务'), key: 'tasks', icon: () => h('span', { class: 'menu-icon' }, '☰') },
  { label: () => h(RouterLink, { to: '/users' }, () => '用户'), key: 'users', icon: () => h('span', { class: 'menu-icon' }, '☷') },
  { label: () => h(RouterLink, { to: '/billing' }, () => '计费'), key: 'billing', icon: () => h('span', { class: 'menu-icon' }, '☼') },
  { label: () => h(RouterLink, { to: '/monitoring' }, () => '监控'), key: 'monitoring', icon: () => h('span', { class: 'menu-icon' }, '◉') },
  { label: () => h(RouterLink, { to: '/settings' }, () => '设置'), key: 'settings', icon: () => h('span', { class: 'menu-icon' }, '⚙') }
]
// === Business submenu: 12 业务模块 (P3-7-W2) ===
const businessSubmenu: MenuOption = {
  type: 'group',
  label: '业务模块',
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
  label: 'P4-8 能力',
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
  return typeof meta === 'string' ? meta : 'nanobot-factory'
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
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.brand-text {
  font-size: 22px;
  font-weight: 700;
  color: #2080f0;
  letter-spacing: 4px;
}
.brand-sub {
  font-size: 11px;
  color: #888;
  margin-top: 2px;
}
.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 56px;
  background: #fff;
}
.header-title {
  font-size: 16px;
  font-weight: 600;
}
.header-user {
  display: flex;
  align-items: center;
  gap: 12px;
}
.username {
  font-size: 13px;
  color: #555;
}
.menu-icon {
  display: inline-block;
  width: 20px;
  text-align: center;
  color: #2080f0;
  font-size: 16px;
}
</style>