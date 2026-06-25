# P6-4 Actions — 修复优先级 + 工作量估算 + 实施路径

**审计日期**: 2026-06-24
**目标**: 将 nanobot-factory frontend-v2 从 B+ (75/100) 提升到 A- (90/100)
**总投入**: 4-6 周 (1 人 + 1 审)

---

## 一、优先级矩阵 (P0/P1/P2/P3)

### 1.1 P0 (今日必修 — 阻塞上线)

| ID | 项 | 文件 | 工作量 | 风险 |
| :-: | --- | --- | ---: | --- |
| P0-1 | **补 `@vicons/ionicons5` 依赖** | `package.json` | 5 min | **生产部署 npm ci 必失败** |
| P0-2 | **11 个 stub view 接入真实后端** | Annotation/Billing/Dataset/Engines/Monitoring/Review/Scoring/Settings/Tasks/Users/Workflows | 1-2d | 占位文案违反"商业级"要求 |
| P0-3 | **暗色模式切换 UI + Pinia store** | stores/theme.ts (新) + App.vue + DefaultLayout.vue | 3h | 用户基础体验 |
| P0-4 | **ErrorBoundary + 全局 catch** | App.vue + errorHandler in main.ts | 2h | 任何 view 崩溃白屏 |

**P0 总投入**: 2.5-3.5 人天

### 1.2 P1 (本周必修 — 商业级必备)

| ID | 项 | 文件 | 工作量 | 影响 |
| :-: | --- | --- | ---: | --- |
| P1-1 | **i18n (vue-i18n + zh-CN/en-US)** | locales/zh-CN.ts + en-US.ts + main.ts | 1d | 国际化能力 |
| P1-2 | **i18n 文本抽离 (52 view)** | 全部 view | 2-3d | 工作量大但机械 |
| P1-3 | **a11y 全量改造 (52 view)** | 全部 view + skip-link + focus-visible | 2-3d | WCAG AA 不达标 |
| P1-4 | **WCAG AA 对比度修复** | App.vue + 占位色 #aaa → #767676 | 0.5d | 标准合规 |
| P1-5 | **vitest 单元测试 (12 关键 view)** | tests/unit/ | 1-2d | 回归保障 |
| P1-6 | **SSO + 2FA** | Login.vue + auth.ts | 2-3d | 企业级认证 |
| P1-7 | **404/500 页面** | views/NotFound.vue + Error.vue (新) | 0.5d | 错误体验 |

**P1 总投入**: 9-13 人天 (~2 周)

### 1.3 P2 (下周 — UX 提升)

| ID | 项 | 文件 | 工作量 | 价值 |
| :-: | --- | --- | ---: | --- |
| P2-1 | **⌘K 命令面板** | components/CommandPalette.vue (新) + stores/command.ts | 0.5-1d | 对标 Linear/Vercel |
| P2-2 | **Playwright E2E (登录 + 3 流程)** | tests/e2e/ + playwright.config.ts | 1-2d | 关键路径覆盖 |
| P2-3 | **DataTable 列控制 + 多选** | components/DataTable.vue 增强 | 1d | 数据表能力 |
| P2-4 | **Lighthouse 跑通 + 优化** | package.json 加 lighthouse-ci | 1d | 性能可见 |
| P2-5 | **Lighthouse 优化 (vendor 拆分)** | vite.config.ts + 按需 import | 0.5-1d | FCP/LCP 提升 |
| P2-6 | **响应式适配 (mobile/tablet)** | 48 view @media | 3-5d | 移动体验 |
| P2-7 | **Open Graph + favicon 完整** | index.html + public/* | 0.5d | 分享卡片 |

**P2 总投入**: 7.5-11.5 人天 (~2 周)

### 1.4 P3 (迭代 — 长期能力)

| ID | 项 | 文件 | 工作量 | 战略价值 |
| :-: | --- | --- | ---: | --- |
| P3-1 | **Design token 体系 (CSS vars)** | assets/theme.css + tokens.ts | 1d | 视觉一致性 |
| P3-2 | **品牌色 + Logo SVG + brand kit** | public/logo.svg + brand/* | 1d | 品牌识别 |
| P3-3 | **字体本地化 (Inter + JetBrains Mono)** | public/fonts/ + assets/fonts.css | 0.5d | 跨平台一致 |
| P3-4 | **lucide-vue-next 替换图标** | 52 view + DefaultLayout.vue | 1-2d | 图标标准化 |
| P3-5 | **8 点栅格 + 5 级圆角 + 5 级阴影** | assets/tokens.css | 0.5d | 视觉一致 |
| P3-6 | **3 级动效 (100/200/300ms)** | assets/motion.css | 0.5d | 动效一致 |
| P3-7 | **虚拟列表 (NVirtualList)** | DataTable.vue + 大数据 view | 0.5d | 性能 |
| P3-8 | **拖拽上传** | AssetManagement + MultimodalChat | 1d | 输入效率 |
| P3-9 | **数据导出 (CSV/Excel/PDF)** | 工具栏组件 | 1d | 数据导出 |
| P3-10 | **视图切换 (List/Board/Calendar)** | TaskManagement 等 | 1-2 周 | 数据展示 |
| P3-11 | **实时协作 (Yjs + WebSocket)** | stores/collab.ts (新) | 2-4 周 | 多人协作 |
| P3-12 | **AI Copilot (Inline AI)** | components/AICopilot.vue | 1-2 周 | AI 集成 |
| P3-13 | **Webhook 事件流** | views/Events.vue (新) | 1-2 周 | 集成能力 |

**P3 总投入**: 8-15 周 (持续)

---

## 二、实施路径 (4 周冲刺)

### Week 1: P0 + P1 启动 (今日 + 5d)

```
Day 1 (今日): P0-1 + P0-3 + P0-4 (依赖 + 暗色 + ErrorBoundary)
Day 2-3: P0-2 (11 stub view 接后端)
Day 4: P1-1 + P1-4 (i18n 框架 + WCAG 修复)
Day 5: P1-3 启动 (a11y 改造)
```

**交付**: vue-tsc 0 error + vite build + 无 stub view + 暗色模式 + ErrorBoundary

### Week 2: P1 主体 (i18n + a11y + 测试)

```
Day 1-2: P1-2 (i18n 文本抽离)
Day 3: P1-3 (a11y 全量完成)
Day 4-5: P1-5 (vitest 单测)
```

**交付**: i18n zh-CN/en-US 切换 + WCAG AA 达标 + 12 view 单测

### Week 3: P1 + P2 启动 (UX 提升)

```
Day 1-2: P1-6 (SSO + 2FA)
Day 3: P2-1 (⌘K 命令面板)
Day 4: P2-3 (DataTable 增强)
Day 5: P2-4 + P2-5 (Lighthouse 优化)
```

**交付**: SSO 登录 + ⌘K + 列控制 + Lighthouse 90+

### Week 4: P2 主体 + P3 启动 (打磨)

```
Day 1-2: P2-2 (Playwright E2E)
Day 3: P2-6 启动 (响应式 mobile/tablet)
Day 4-5: P3-1 + P3-2 (Design token + 品牌色)
```

**交付**: E2E 3 流程 + 移动适配 + 品牌色上线

### Week 5+: P3 长期 (持续)

```
P3-3 字体 → P3-4 图标 → P3-5 间距圆角 → P3-6 动效 → P3-7 虚拟列表
P3-8 拖拽上传 → P3-9 数据导出 → P3-10 视图切换 → P3-11 实时协作
```

---

## 三、详细实施清单

### P0-1: @vicons/ionicons5 依赖 (5 min)

**文件**: `frontend-v2/package.json`

```jsonc
{
  "dependencies": {
    // ... 现有依赖 ...
    "@vicons/ionicons5": "^0.12.0"
  }
}
```

**验证**:
```bash
cd frontend-v2
npm install
npm run build  # 必须成功
```

**风险**: 0 (lock 文件会自动更新)

---

### P0-2: 11 个 stub view 接入 (1-2d)

**目标 view**:
- Annotation.vue (13 行 → 200+ 行)
- Billing.vue (12 行 → 200+ 行)
- Dataset.vue (22 行 → 200+ 行)
- Engines.vue (12 行 → 200+ 行)
- Monitoring.vue (12 行 → 200+ 行)
- Review.vue (12 行 → 200+ 行)
- Scoring.vue (12 行 → 200+ 行)
- Settings.vue (12 行 → 200+ 行)
- Tasks.vue (12 行 → 200+ 行)
- Users.vue (12 行 → 200+ 行)
- Workflows.vue (76 行 → 200+ 行)

**实施模板** (以 Annotation.vue 为例):

```vue
<template>
  <div class="page-root">
    <NCard title="标注工作台" :bordered="false">
      <SearchBar v-model="keyword" placeholder="搜索任务ID/标注员"
                 @search="onSearch" @reset="onReset">
        <template #extra>
          <PermissionGuard :roles="['admin', 'annotator']">
            <ActionButton type="primary" @click="openCreate">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              新建任务
            </ActionButton>
          </PermissionGuard>
        </template>
      </SearchBar>

      <DataTable
        :columns="columns"
        :data="rows"
        :loading="loading"
        :error="error"
        :total="total"
        v-model:page="page"
        v-model:page-size="pageSize"
        :row-key="(r: AnnotationTask) => r.id"
        @refresh="load"
      >
        <template #empty>
          <NEmpty description="暂无标注任务" />
        </template>
      </DataTable>
    </NCard>

    <ModalForm
      v-model:show="modalShow"
      :title="editingId ? '编辑任务' : '新建任务'"
      v-model="form"
      :rules="rules"
      :submitting="submitting"
      @submit="onSubmit"
    >
      <template #default="{ form: f }">
        <NFormItem label="任务ID" path="task_id">
          <NInput v-model:value="(f as AnnotationCreate).task_id" />
        </NFormItem>
        <NFormItem label="资产ID" path="asset_id">
          <NInput v-model:value="(f as AnnotationCreate).asset_id" />
        </NFormItem>
        <NFormItem label="标注员" path="annotator">
          <NSelect v-model:value="(f as AnnotationCreate).annotator" :options="userOptions" filterable />
        </NFormItem>
        <NFormItem label="标签集" path="labels">
          <NInput v-model:value="(f as AnnotationCreate).labels" placeholder="逗号分隔" />
        </NFormItem>
        <NFormItem label="优先级" path="priority">
          <NSelect v-model:value="(f as AnnotationCreate).priority" :options="priorityOptions" />
        </NFormItem>
      </template>
    </ModalForm>
  </div>
</template>

<script setup lang="ts">
import { h, onMounted, ref, reactive } from 'vue'
import {
  NCard, NEmpty, NFormItem, NInput, NSelect, NIcon,
  NTag, NSpace, useMessage, type DataTableColumns, type FormRules
} from 'naive-ui'
import { AddOutline, CreateOutline, TrashOutline, PlayOutline } from '@vicons/ionicons5'
import SearchBar from '@/components/SearchBar.vue'
import DataTable from '@/components/DataTable.vue'
import ActionButton from '@/components/ActionButton.vue'
import ModalForm from '@/components/ModalForm.vue'
import PermissionGuard from '@/components/PermissionGuard.vue'
import {
  listTasks, createTask, updateTask, deleteTask,
  type AnnotationTask, type AnnotationCreate
} from '@/api/annotation'

const message = useMessage()
const keyword = ref('')
const page = ref(1)
const pageSize = ref(20)
const rows = ref<AnnotationTask[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

const modalShow = ref(false)
const editingId = ref<string | number | null>(null)
const submitting = ref(false)
const form = reactive<AnnotationCreate>({
  task_id: '', asset_id: '', annotator: '', labels: '', priority: 'normal'
})

const priorityOptions = [
  { label: 'P0 紧急', value: 'p0' },
  { label: 'P1 高', value: 'p1' },
  { label: 'P2 中', value: 'p2' },
  { label: 'P3 低', value: 'p3' },
  { label: 'normal', value: 'normal' },
]

const userOptions = ref<Array<{ label: string; value: string }>>([])

const rules: FormRules = {
  task_id: { required: true, message: '请输入任务ID', trigger: 'blur' },
  asset_id: { required: true, message: '请输入资产ID', trigger: 'blur' },
  annotator: { required: true, message: '请选择标注员', trigger: 'change' },
}

const columns: DataTableColumns<AnnotationTask> = [
  { title: '任务ID', key: 'task_id', width: 160 },
  { title: '资产ID', key: 'asset_id', width: 160 },
  {
    title: '标注员', key: 'annotator', width: 100,
    render: (row) => h(NTag, { size: 'small' }, { default: () => row.annotator })
  },
  {
    title: '优先级', key: 'priority', width: 80,
    render: (row) => {
      const color = row.priority === 'p0' ? 'error' : row.priority === 'p1' ? 'warning' : 'info'
      return h(NTag, { size: 'small', type: color }, { default: () => row.priority })
    }
  },
  {
    title: '状态', key: 'status', width: 100,
    render: (row) => {
      const color = row.status === 'completed' ? 'success' : row.status === 'in_progress' ? 'warning' : 'default'
      return h(NTag, { size: 'small', type: color }, { default: () => row.status })
    }
  },
  { title: '创建时间', key: 'created_at', width: 180 },
  {
    title: '操作', key: 'actions', width: 240,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(PermissionGuard, { roles: ['admin', 'annotator'] }, {
          default: () => h(ActionButton, { icon: PlayOutline, onClick: () => onStart(row) }, { default: () => '开始' })
        }),
        h(PermissionGuard, { roles: ['admin', 'annotator'] }, {
          default: () => h(ActionButton, { icon: CreateOutline, onClick: () => openEdit(row) }, { default: () => '编辑' })
        }),
        h(PermissionGuard, { roles: ['admin'] }, {
          default: () => h(ActionButton, { type: 'error', icon: TrashOutline, onClick: () => onDelete(row) }, { default: () => '删除' })
        }),
      ]
    })
  },
]

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await listTasks({ page: page.value, page_size: pageSize.value, keyword: keyword.value })
    rows.value = res.items
    total.value = res.total
  } catch (e) {
    error.value = (e as Error).message || '加载任务列表失败'
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function onSearch() { page.value = 1; load() }
function onReset() { keyword.value = ''; page.value = 1; load() }

function openCreate() {
  editingId.value = null
  Object.assign(form, { task_id: '', asset_id: '', annotator: '', labels: '', priority: 'normal' } as AnnotationCreate)
  modalShow.value = true
}

function openEdit(row: AnnotationTask) {
  editingId.value = row.id
  Object.assign(form, {
    task_id: row.task_id, asset_id: row.asset_id,
    annotator: row.annotator, labels: row.labels?.join(',') ?? '', priority: row.priority
  } as AnnotationCreate)
  modalShow.value = true
}

async function onSubmit(payload: AnnotationCreate) {
  submitting.value = true
  try {
    const body = { ...payload, labels: payload.labels?.split(',').map(s => s.trim()).filter(Boolean) }
    if (editingId.value !== null) {
      await updateTask(editingId.value, body)
      message.success('更新成功')
    } else {
      await createTask(body)
      message.success('创建成功')
    }
    modalShow.value = false
    await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  } finally {
    submitting.value = false
  }
}

async function onStart(row: AnnotationTask) {
  try {
    // TODO: 调用启动标注 API
    message.success(`任务 ${row.task_id} 已启动`)
  } catch (e) {
    message.error((e as Error).message || '启动失败')
  }
}

async function onDelete(row: AnnotationTask) {
  if (!window.confirm(`确认删除任务 ${row.task_id} ?`)) return
  try {
    await deleteTask(row.id)
    message.success('删除成功')
    await load()
  } catch (e) {
    message.error((e as Error).message || '删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.page-root { padding: 16px; }
</style>
```

**注意**: 11 个 view 的实际 CRUD 字段需要参考后端 API (api/annotation.ts 等)。

---

### P0-3: 暗色模式 (3h)

**新文件**: `src/stores/theme.ts`

```typescript
import { defineStore } from 'pinia'

type ThemeMode = 'light' | 'dark' | 'auto'

export const useThemeStore = defineStore('theme', {
  state: () => ({
    mode: 'light' as ThemeMode,
    resolved: 'light' as 'light' | 'dark'
  }),

  actions: {
    init() {
      const saved = localStorage.getItem('theme') as ThemeMode | null
      if (saved) this.mode = saved
      this.apply()
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        if (this.mode === 'auto') this.apply()
      })
    },

    setMode(mode: ThemeMode) {
      this.mode = mode
      this.apply()
    },

    toggle() {
      this.mode = this.resolved === 'light' ? 'dark' : 'light'
      this.apply()
    },

    apply() {
      const resolved = this.mode === 'auto'
        ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
        : this.mode
      this.resolved = resolved
      document.documentElement.dataset.theme = resolved
      localStorage.setItem('theme', this.mode)
    }
  }
})
```

**新文件**: `src/assets/theme.css` (CSS vars)

```css
:root,
[data-theme="light"] {
  --bg-default: #ffffff;
  --bg-subtle: #fafafa;
  --bg-muted: #f5f7fa;
  --text-primary: #18181b;
  --text-secondary: #52525b;
  --text-tertiary: #71717a;
  --text-placeholder: #767676; /* WCAG AA: 4.54:1 */
  --border-default: #e4e4e7;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 2px 6px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
}

[data-theme="dark"] {
  --bg-default: #0a0a0a;
  --bg-subtle: #18181b;
  --bg-muted: #27272a;
  --text-primary: #fafafa;
  --text-secondary: #d4d4d8;
  --text-tertiary: #a1a1aa;
  --text-placeholder: #a1a1aa;
  --border-default: #27272a;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.30);
  --shadow-md: 0 2px 6px rgba(0,0,0,0.40), 0 1px 2px rgba(0,0,0,0.30);
}
```

**修改**: `src/main.ts`

```typescript
import { useThemeStore } from './stores/theme'

const app = createApp(App)
app.use(pinia)
app.use(router)

// Init theme before mount
const themeStore = useThemeStore()
themeStore.init()
```

**修改**: `src/App.vue`

```vue
<template>
  <NConfigProvider
    :theme="themeStore.resolved === 'dark' ? darkTheme : null"
    :theme-overrides="themeOverrides"
    :date-locale="dateEnUS"
    :locale="enUS"
  >
    <!-- ... 原有 providers ... -->
  </NConfigProvider>
</template>

<script setup lang="ts">
import { useThemeStore } from '@/stores/theme'
const themeStore = useThemeStore()
// darkTheme 引入
import { darkTheme } from 'naive-ui'
</script>
```

**修改**: `src/layouts/DefaultLayout.vue`

```vue
<NButton size="small" tertiary @click="themeStore.toggle">
  {{ themeStore.resolved === 'dark' ? '☀' : '☾' }}
</NButton>
```

---

### P0-4: ErrorBoundary (2h)

**新文件**: `src/components/ErrorBoundary.vue`

```vue
<template>
  <template v-if="error">
    <NCard class="error-boundary" :bordered="false">
      <NEmpty size="large" description="页面渲染出错">
        <template #icon>
          <span style="font-size: 48px;">⚠</span>
        </template>
        <template #extra>
          <NSpace>
            <NButton type="primary" @click="reload">刷新页面</NButton>
            <NButton @click="reset">重置</NButton>
          </NSpace>
        </template>
      </NEmpty>
      <details v-if="error.stack" style="margin-top: 16px;">
        <summary>错误详情</summary>
        <pre>{{ error.stack }}</pre>
      </details>
    </NCard>
  </template>
  <slot v-else />
</template>

<script setup lang="ts">
import { onErrorCaptured, ref } from 'vue'
import { NCard, NEmpty, NButton, NSpace } from 'naive-ui'

const error = ref<Error | null>(null)

onErrorCaptured((err) => {
  error.value = err as Error
  console.error('[ErrorBoundary]', err)
  return false // 阻止传播
})

function reload() {
  window.location.reload()
}

function reset() {
  error.value = null
}
</script>
```

**修改**: `src/App.vue` 包裹 `<RouterView>`

```vue
<ErrorBoundary>
  <RouterView />
</ErrorBoundary>
```

**修改**: `src/main.ts` 全局错误处理

```typescript
app.config.errorHandler = (err, instance, info) => {
  console.error('[Vue Global Error]', err, info)
}
```

---

### P1-1: i18n 框架 (1d)

**安装**: `npm i vue-i18n@^9`

**新文件**: `src/locales/zh-CN.ts`

```typescript
export default {
  common: {
    save: '保存',
    cancel: '取消',
    confirm: '确认',
    delete: '删除',
    edit: '编辑',
    create: '新建',
    search: '搜索',
    reset: '重置',
    refresh: '刷新',
    loading: '加载中...',
    success: '操作成功',
    failed: '操作失败',
    yes: '是',
    no: '否',
  },
  menu: {
    dashboard: '仪表盘',
    dataset: '数据集',
    annotation: '标注',
    review: '审核',
    scoring: '评分',
    workflows: '工作流',
    engines: '引擎',
    tasks: '任务',
    users: '用户',
    billing: '计费',
    monitoring: '监控',
    settings: '设置',
  },
  // ... 后续 view 逐项抽离
}
```

**新文件**: `src/locales/en-US.ts`

```typescript
export default {
  common: {
    save: 'Save',
    cancel: 'Cancel',
    confirm: 'Confirm',
    delete: 'Delete',
    edit: 'Edit',
    create: 'Create',
    search: 'Search',
    reset: 'Reset',
    refresh: 'Refresh',
    loading: 'Loading...',
    success: 'Success',
    failed: 'Failed',
    yes: 'Yes',
    no: 'No',
  },
  menu: {
    dashboard: 'Dashboard',
    dataset: 'Datasets',
    annotation: 'Annotation',
    review: 'Review',
    scoring: 'Scoring',
    workflows: 'Workflows',
    engines: 'Engines',
    tasks: 'Tasks',
    users: 'Users',
    billing: 'Billing',
    monitoring: 'Monitoring',
    settings: 'Settings',
  },
}
```

**修改**: `src/main.ts`

```typescript
import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import enUS from './locales/en-US'

const i18n = createI18n({
  legacy: false,
  locale: localStorage.getItem('locale') || 'zh-CN',
  fallbackLocale: 'en-US',
  messages: { 'zh-CN': zhCN, 'en-US': enUS }
})

app.use(i18n)
```

**view 改造示例** (UserManagement.vue):

```vue
<template>
  <NCard :title="t('user.title')">
    <SearchBar v-model="keyword" :placeholder="t('user.searchPlaceholder')" />
    <!-- ... -->
  </NCard>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
</script>
```

---

### P1-3: a11y 全量改造 (2-3d)

**52 view 改造模板**:

```vue
<!-- 1. skip-link -->
<a href="#main-content" class="skip-link">跳转到主内容</a>

<!-- 2. icon-only button 加 aria-label -->
<NButton aria-label="删除用户" @click="onDelete">
  <Trash2 />
</NButton>

<!-- 3. 表单 label 关联 -->
<NFormItem label="用户名">
  <NInput aria-required="true" aria-describedby="username-help" />
</NFormItem>
<span id="username-help" class="form-help">3-20 字符</span>

<!-- 4. nav 标识 -->
<nav role="navigation" aria-label="主菜单">
  <RouterLink :aria-current="isActive ? 'page' : undefined">
    {{ menuTitle }}
  </RouterLink>
</nav>

<!-- 5. 表格 header 关联 -->
<table>
  <th id="col-id">ID</th>
  <td :headers="'col-id'">{{ item.id }}</td>
</table>

<!-- 6. live region -->
<div role="status" aria-live="polite" aria-atomic="true">
  {{ toast.message }}
</div>
```

**CSS focus-visible**:

```css
/* global.css */
:focus-visible {
  outline: 2px solid var(--brand-primary, #2080f0);
  outline-offset: 2px;
}

.skip-link {
  position: absolute;
  top: -40px;
  left: 8px;
  padding: 8px 16px;
  background: var(--bg-default);
  border: 1px solid var(--brand-primary);
  border-radius: 4px;
  z-index: 9999;
}
.skip-link:focus {
  top: 8px;
}
```

---

### P2-1: ⌘K 命令面板 (0.5-1d)

**新文件**: `src/components/CommandPalette.vue`

```vue
<template>
  <NModal v-model:show="store.open" preset="card" style="width: 640px" :mask-closable="true">
    <NInput
      ref="inputRef"
      v-model:value="store.keyword"
      placeholder="输入命令或搜索... (↑↓ 选择, Enter 执行, Esc 关闭)"
      size="large"
      autofocus
      @keydown="onKeydown"
    />
    <NDivider style="margin: 12px 0" />
    <NScrollbar style="max-height: 400px">
      <NList>
        <NListItem
          v-for="(item, i) in store.filtered"
          :key="item.id"
          :class="['cmd-item', { active: i === selectedIndex }]"
          @click="run(item)"
          @mouseenter="selectedIndex = i"
        >
          <NSpace align="center" :wrap-item="false">
            <span class="cmd-icon">{{ item.icon }}</span>
            <span>{{ item.title }}</span>
            <NTag size="tiny" :bordered="false">{{ item.section }}</NTag>
            <NTag v-if="item.shortcut" size="tiny" type="info">{{ item.shortcut }}</NTag>
          </NSpace>
        </NListItem>
      </NList>
    </NScrollbar>
  </NModal>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { NModal, NInput, NDivider, NScrollbar, NList, NListItem, NSpace, NTag } from 'naive-ui'
import { useCommandStore } from '@/stores/command'

const store = useCommandStore()
const inputRef = ref<InstanceType<typeof NInput> | null>(null)
const selectedIndex = ref(0)

watch(() => store.open, (open) => {
  if (open) {
    selectedIndex.value = 0
    nextTick(() => inputRef.value?.focus())
  }
})

watch(() => store.filtered, () => {
  selectedIndex.value = 0
})

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    selectedIndex.value = Math.min(selectedIndex.value + 1, store.filtered.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    selectedIndex.value = Math.max(selectedIndex.value - 1, 0)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const item = store.filtered[selectedIndex.value]
    if (item) run(item)
  } else if (e.key === 'Escape') {
    store.hide()
  }
}

function run(item: any) {
  store.record(item.title)
  item.action()
  store.hide()
}
</script>

<style scoped>
.cmd-item { cursor: pointer; padding: 8px 12px; }
.cmd-item.active { background: var(--bg-muted, #f5f7fa); }
.cmd-icon { display: inline-block; width: 24px; text-align: center; }
</style>
```

**main.ts 全局快捷键**:

```typescript
import { useCommandStore } from './stores/command'
document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k' && !e.shiftKey) {
    e.preventDefault()
    useCommandStore().show()
  }
})
```

**App.vue 挂载**:

```vue
<CommandPalette />
```

---

## 四、依赖清单 (待安装)

```bash
# P0
# @vicons/ionicons5 — 已存在 node_modules, 仅需 package.json 声明

# P1
npm i vue-i18n@^9
npm i -D vitest@^1 @vue/test-utils@^2 happy-dom@^13

# P2
npm i fuse.js@^7
npm i -D @playwright/test@^1.40
npm i -D @lhci/cli@^0.13  # Lighthouse CI

# P3
npm i lucide-vue-next@^0.300
npm i papaparse@^5 @types/papaparse
npm i jspdf@^2 html2canvas@^1  # PDF
npm i xlsx@^0.18  # Excel (按需)
npm i yjs@^13 y-websocket@^1  # 实时协作

# 字体本地化 (public/fonts/)
# Inter Variable — 从 https://github.com/rsms/inter/releases 下载
# JetBrains Mono Variable — 从 https://github.com/JetBrains/JetBrainsMono/releases
```

---

## 五、风险评估

| 风险 | 等级 | 缓解 |
| --- | :-: | --- |
| i18n 抽离文本工作量大 | 中 | 用脚本批量正则提取 + 人工 review |
| a11y 改造易破坏现有样式 | 中 | 每个 view PR + 视觉回归 |
| 11 stub view 接后端依赖后端 | **高** | 后端 API 不稳则先 mock (MSW) |
| Naive UI 暗色主题与默认样式冲突 | 中 | 用 CSS vars 覆盖 |
| Lighthouse 优化导致功能回归 | 中 | 每次构建跑 lighthouse-ci |
| Playwright CI 资源消耗 | 低 | 仅 3 个关键路径 + nightly |

---

## 六、度量指标

| KPI | 当前 | 目标 (4 周后) | 测量 |
| --- | --- | --- | --- |
| View 完成度 | 79% | 100% | 11 stub → 0 |
| TypeScript 严格模式 | ✓ | ✓ | vue-tsc --noEmit |
| Bundle gzip | 482 KB | < 350 KB | vite build 报告 |
| Lighthouse 评分 | ? | > 90 | LHCI |
| WCAG AA | 0% | 100% | axe-core 自动 + 人工 |
| 单元测试覆盖率 | 0% | > 60% | vitest --coverage |
| E2E 关键路径 | 0 | 3 | Playwright |
| i18n 覆盖 | 0% | 100% | 文本抽离 |
| 暗色模式 | ✗ | ✓ | 手动 toggle |
| ⌘K 命令面板 | ✗ | ✓ | ⌘K 触发 |

---

## 七、最终交付物 (4 周后)

✓ P0-P2 全部完成
✓ P3 完成 P3-1/P3-2/P3-3/P3-4 (基础打磨)
✓ 评分: B+ → **A- (90/100)**
✓ 商业级可用, 距离 Linear/Vercel 80% 体验
✓ 进入 P3 长期打磨期

---

## 附录: 一键实施脚本

```bash
# Week 1: P0
cd frontend-v2

# P0-1: 依赖
npm i @vicons/ionicons5

# 11 stub view 重写 (需要按 api/ 实际接口填充)
# 详见 P0-2 详细模板

# P0-3: 暗色
# 1. 新建 src/stores/theme.ts
# 2. 新建 src/assets/theme.css
# 3. 修改 src/main.ts (init)
# 4. 修改 src/App.vue (NConfigProvider theme)
# 5. 修改 src/layouts/DefaultLayout.vue (toggle button)

# P0-4: ErrorBoundary
# 新建 src/components/ErrorBoundary.vue
# 修改 src/App.vue (包裹 RouterView)

# Week 2: P1
npm i vue-i18n@^9
npm i -D vitest@^1 @vue/test-utils@^2 happy-dom@^13

# Week 3: P2
npm i fuse.js@^7
npm i -D @playwright/test@^1.40
npm i -D @lhci/cli@^0.13

# Week 4: 打磨
npm i lucide-vue-next@^0.300

# 验证
npm run type-check
npm run build
```

---

> 报告生成: 2026-06-24 15:30 (Asia/Shanghai)
> 总工作量: 4 周冲刺 (1 人 + 1 审)
> 预计评分: B+ (75) → A- (90)