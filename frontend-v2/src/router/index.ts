import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

// 12 module routes — lazy-loaded for code splitting
const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true, title: '登录' }
  },
  {
    path: '/',
    component: () => import('@/layouts/DefaultLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '仪表盘', icon: 'gauge' }
      },
      {
        path: 'dataset',
        name: 'dataset',
        component: () => import('@/views/Dataset.vue'),
        meta: { title: '数据集', icon: 'database' }
      },
      {
        path: 'annotation',
        name: 'annotation',
        component: () => import('@/views/Annotation.vue'),
        meta: { title: '标注', icon: 'edit' }
      },
      {
        path: 'review',
        name: 'review',
        component: () => import('@/views/Review.vue'),
        meta: { title: '审核', icon: 'check' }
      },
      {
        path: 'scoring',
        name: 'scoring',
        component: () => import('@/views/Scoring.vue'),
        meta: { title: '评分', icon: 'star' }
      },
      {
        path: 'workflows',
        name: 'workflows',
        component: () => import('@/views/Workflows.vue'),
        meta: { title: '工作流', icon: 'flow' }
      },
      {
        path: 'engines',
        name: 'engines',
        component: () => import('@/views/Engines.vue'),
        meta: { title: '引擎', icon: 'cube' }
      },
      {
        path: 'tasks',
        name: 'tasks',
        component: () => import('@/views/Tasks.vue'),
        meta: { title: '任务', icon: 'queue' }
      },
      {
        path: 'users',
        name: 'users',
        component: () => import('@/views/Users.vue'),
        meta: { title: '用户', icon: 'people' }
      },
      {
        path: 'billing',
        name: 'billing',
        component: () => import('@/views/Billing.vue'),
        meta: { title: '计费', icon: 'card' }
      },
      {
        path: 'monitoring',
        name: 'monitoring',
        component: () => import('@/views/Monitoring.vue'),
        meta: { title: '监控', icon: 'pulse' }
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/views/Settings.vue'),
        meta: { title: '设置', icon: 'gear' }
      },
      // ===== 12 业务模块路由 (P3-7-W2) — 对接 12 个微服务 =====
      {
        path: 'user-management',
        name: 'user-management',
        component: () => import('@/views/UserManagement.vue'),
        meta: { title: '用户管理', icon: 'people' }
      },
      {
        path: 'asset-management',
        name: 'asset-management',
        component: () => import('@/views/AssetManagement.vue'),
        meta: { title: '资产管理', icon: 'image' }
      },
      {
        path: 'annotation-management',
        name: 'annotation-management',
        component: () => import('@/views/AnnotationManagement.vue'),
        meta: { title: '标注管理', icon: 'edit' }
      },
      {
        path: 'cleaning-management',
        name: 'cleaning-management',
        component: () => import('@/views/CleaningManagement.vue'),
        meta: { title: '清洗管理', icon: 'sparkles' }
      },
      {
        path: 'scoring-management',
        name: 'scoring-management',
        component: () => import('@/views/ScoringManagement.vue'),
        meta: { title: '评分管理', icon: 'star' }
      },
      {
        path: 'dataset-management',
        name: 'dataset-management',
        component: () => import('@/views/DatasetManagement.vue'),
        meta: { title: '数据集管理', icon: 'database' }
      },
      {
        path: 'evaluation-management',
        name: 'evaluation-management',
        component: () => import('@/views/EvaluationManagement.vue'),
        meta: { title: '评测管理', icon: 'speedometer' }
      },
      {
        path: 'agent-management',
        name: 'agent-management',
        component: () => import('@/views/AgentManagement.vue'),
        meta: { title: '智能体管理', icon: 'hardware-chip' }
      },
      {
        path: 'workflow-management',
        name: 'workflow-management',
        component: () => import('@/views/WorkflowManagement.vue'),
        meta: { title: '工作流管理', icon: 'git-network' }
      },
      {
        path: 'notification-management',
        name: 'notification-management',
        component: () => import('@/views/NotificationManagement.vue'),
        meta: { title: '通知管理', icon: 'notifications' }
      },
      {
        path: 'search-management',
        name: 'search-management',
        component: () => import('@/views/SearchManagement.vue'),
        meta: { title: '全局搜索', icon: 'search' }
      },
      {
        path: 'canvas-designer',
        name: 'canvas-designer',
        component: () => import('@/views/CanvasDesigner.vue'),
        meta: { title: '画布设计器', icon: 'canvas' }
      },
      // ===== P4-6-W2 workflow_service dag_v2 + director studio =====
      {
        path: 'workflow/visual-editor',
        name: 'workflow-visual-editor',
        component: () => import('@/views/workflow/VisualEditor.vue'),
        meta: { title: 'DAG 可视化编辑器', icon: 'git-network' }
      },
      {
        path: 'workflow/operator-market',
        name: 'workflow-operator-market',
        component: () => import('@/views/workflow/OperatorMarket.vue'),
        meta: { title: '算子市场', icon: 'apps' }
      },
      {
        path: 'workflow/director-studio',
        name: 'workflow-director-studio',
        component: () => import('@/views/workflow/DirectorStudio.vue'),
        meta: { title: '三模块导演台', icon: 'film' }
      },
      {
        path: 'workflow/run-monitor',
        name: 'workflow-run-monitor',
        component: () => import('@/views/workflow/RunMonitor.vue'),
        meta: { title: '工作流运行监控', icon: 'pulse' }
      },
      // ===== P4-10 商业化能力 (W2) — 合同/发票/CRM/工单 =====
      {
        path: 'pricing',
        name: 'pricing',
        component: () => import('@/views/billing/Pricing.vue'),
        meta: { title: '套餐定价', icon: 'pricetags' }
      },
      {
        path: 'orders',
        name: 'orders',
        component: () => import('@/views/billing/Orders.vue'),
        meta: { title: '订单历史', icon: 'receipt' }
      },
      {
        path: 'invoices',
        name: 'invoices',
        component: () => import('@/views/billing/Invoices.vue'),
        meta: { title: '发票管理', icon: 'document-text' }
      },
      {
        path: 'contracts',
        name: 'contracts',
        component: () => import('@/views/contracts/Contracts.vue'),
        meta: { title: '合同管理', icon: 'document' }
      },
      {
        path: 'crm',
        name: 'crm',
        component: () => import('@/views/crm/Customers.vue'),
        meta: { title: '客户管理', icon: 'people' }
      },
      {
        path: 'tickets',
        name: 'tickets',
        component: () => import('@/views/tickets/Tickets.vue'),
        meta: { title: '工单系统', icon: 'help-circle' }
      },
      // ===== P4-8-W2 extended frontend: 8 业务 view + Skill/Obsidian/Lineage =====
      {
        path: 'skills',
        name: 'skills',
        component: () => import('@/views/skills/Marketplace.vue'),
        meta: { title: 'Skill 市场', icon: 'puzzle' }
      },
      {
        path: 'skills/orchestrator',
        name: 'skills-orchestrator',
        component: () => import('@/views/skills/Orchestrator.vue'),
        meta: { title: 'Skill 编排', icon: 'flow' }
      },
      {
        path: 'obsidian/graph',
        name: 'obsidian-graph',
        component: () => import('@/views/obsidian/KnowledgeGraph.vue'),
        meta: { title: '知识图谱', icon: 'graph' }
      },
      {
        path: 'obsidian/wiki',
        name: 'obsidian-wiki',
        component: () => import('@/views/obsidian/WikiList.vue'),
        meta: { title: 'Wiki 列表', icon: 'book' }
      },
      {
        path: 'obsidian/wiki/new',
        name: 'obsidian-wiki-new',
        component: () => import('@/views/obsidian/WikiEdit.vue'),
        meta: { title: '新建 Wiki', icon: 'book' }
      },
      {
        path: 'obsidian/wiki/:slug',
        name: 'obsidian-wiki-edit',
        component: () => import('@/views/obsidian/WikiEdit.vue'),
        meta: { title: 'Wiki 编辑', icon: 'book' }
      },
      {
        path: 'assets/storyboard',
        name: 'assets-storyboard',
        component: () => import('@/views/assets/StoryboardEditor.vue'),
        meta: { title: '分镜编辑器', icon: 'film' }
      },
      {
        path: 'workflow/visual',
        name: 'workflow-visual',
        component: () => import('@/views/workflow/VisualEditor.vue'),
        meta: { title: '工作流可视化', icon: 'flow' }
      },
      {
        path: 'agent/multimodal',
        name: 'agent-multimodal',
        component: () => import('@/views/agent/MultimodalChat.vue'),
        meta: { title: '多模态对话', icon: 'chat' }
      },
      {
        path: 'billing/dashboard',
        name: 'billing-dashboard',
        component: () => import('@/views/billing/Dashboard.vue'),
        meta: { title: '计费仪表盘', icon: 'card' }
      },
      {
        path: 'lineage',
        name: 'lineage',
        component: () => import('@/views/lineage/Graph.vue'),
        meta: { title: '数据血缘', icon: 'graph' }
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Auth guard — runs before every navigation
router.beforeEach((to) => {
  const auth = useAuthStore()
  const requiresAuth = to.matched.some((r) => r.meta?.requiresAuth)

  if (requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && auth.isAuthenticated) {
    return { name: 'dashboard' }
  }
  return true
})

export default router