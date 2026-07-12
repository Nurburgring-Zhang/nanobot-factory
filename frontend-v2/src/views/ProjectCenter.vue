<template>
  <PageRegion label="项目中心" description="数据流转链路的起点 · 项目/需求/任务/数据集/交付统一管理" region-class="project-center-root">
    <div class="project-center-layout">
      <!-- ════ {{ t('projectCenter.t000') }}: {{ t('projectCenter.t001') }} + {{ t('projectCenter.t002') }} ════ -->
      <aside class="col-left">
        <NCard :bordered="false" size="small" class="filter-card">
          <NSpace vertical :size="10">
            <NInput
              v-model:value="keyword"
              placeholder="搜索项目名称 / 描述"
              clearable
              size="small"
              @keyup.enter="onSearch"
              @clear="onSearch"
            >
              <template #prefix>
                <NIcon><SearchOutline /></NIcon>
              </template>
            </NInput>
            <NSelect
              v-model:value="filterStatus"
              :options="statusOptions"
              placeholder="状态"
              size="small"
              clearable
              @update:value="onFilterChange"
            />
            <NSelect
              v-model:value="filterPriority"
              :options="priorityOptions"
              placeholder="优先级"
              size="small"
              clearable
              @update:value="onFilterChange"
            />
            <NButton type="primary" block @click="openCreate">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              {{ t('projectCenter.t003') }}
            </NButton>
          </NSpace>
        </NCard>

        <NCard :bordered="false" size="small" class="list-card" :content-style="{ padding: '8px 0' }">
          <template #header>
            <NSpace align="center" :size="6">
              <NIcon><FolderOpenOutline /></NIcon>
              <span>{{ t('projectCenter.t004') }} ({{ total }})</span>
            </NSpace>
          </template>
          <NScrollbar style="max-height: calc(100vh - 280px)">
            <div v-if="loading && projects.length === 0" class="loading-state">
              <NSpin size="small" />
            </div>
            <NEmpty v-else-if="!loading && projects.length === 0" description="暂无项目，点击右上角新建" />
            <div
              v-for="proj in projects"
              :key="proj.id"
              class="project-item"
              :class="{ active: selected?.id === proj.id }"
              @click="selectProject(proj)"
            >
              <div class="project-item-head">
                <span class="name">{{ proj.name }}</span>
                <NTag :type="statusTagType(proj.status)" size="small" round>
                  {{ statusLabel(proj.status) }}
                </NTag>
              </div>
              <div class="project-item-meta">
                <NTag :type="priorityTagType(proj.priority)" size="small">
                  {{ proj.priority }}
                </NTag>
                <span class="owner">{{ proj.owner_id }}</span>
                <span v-if="proj.due_date" class="due">{{ t('projectCenter.t005') }} {{ proj.due_date }}</span>
              </div>
              <div class="project-item-tags">
                <NTag v-for="t in (proj.tags || []).slice(0, 3)" :key="t" size="tiny" round>
                  {{ t }}
                </NTag>
              </div>
            </div>
          </NScrollbar>
        </NCard>
      </aside>

      <!-- ════ {{ t('projectCenter.t006') }}: {{ t('common.detail') }} Dashboard ════ -->
      <main class="col-main">
        <NCard v-if="!selected" :bordered="false" class="empty-detail">
          <NEmpty description="请在左侧选择一个项目查看详情">
            <template #icon>
              <NIcon size="64" :component="FolderOpenOutline" />
            </template>
          </NEmpty>
        </NCard>

        <template v-else>
          <!-- {{ t('projectCenter.t007') }}: {{ t('annotation.colName') }} + {{ t('annotation.colStatus') }} + {{ t('engines.colPriority') }} + {{ t('projectCenter.t008') }} -->
          <NCard :bordered="false" class="detail-header">
            <NSpace vertical :size="12">
              <NSpace align="center" :size="12">
                <h2 class="title">{{ selected.name }}</h2>
                <NTag :type="statusTagType(selected.status)" size="medium" round>
                  {{ statusLabel(selected.status) }}
                </NTag>
                <NTag :type="priorityTagType(selected.priority)" size="medium">
                  {{ selected.priority }}
                </NTag>
                <span class="owner-id">Owner: {{ selected.owner_id }}</span>
              </NSpace>
              <p v-if="selected.description" class="desc">{{ selected.description }}</p>
              <NSpace align="center" :size="16" class="meta-row">
                <span v-if="selected.start_date" class="meta-item">
                  <NIcon><CalendarOutline /></NIcon> {{ t('common.start') }} {{ selected.start_date }}
                </span>
                <span v-if="selected.due_date" class="meta-item">
                  <NIcon><CalendarOutline /></NIcon> {{ t('projectCenter.t009') }} {{ selected.due_date }}
                </span>
                <span class="meta-item">
                  <NIcon><PeopleOutline /></NIcon> {{ stats?.members_count ?? selected.members.length }} {{ t('form.sectionMember') }}
                </span>
                <span class="meta-item">
                  <NIcon><PricetagsOutline /></NIcon> {{ selected.tags?.length || 0 }} {{ t('common.label') }}
                </span>
              </NSpace>
              <div class="progress-row">
                <span class="progress-label">{{ t('projectCenter.t010') }}</span>
                <NProgress
                  type="line"
                  :percentage="stats?.progress ?? 0"
                  :show-indicator="true"
                  :height="14"
                  :border-radius="7"
                />
                <span class="progress-pct">{{ stats?.progress ?? 0 }}%</span>
              </div>
            </NSpace>
          </NCard>

          <!-- 4 KPI 卡 -->
          <div class="kpi-grid">
            <NCard v-for="kpi in kpis" :key="kpi.key" :bordered="false" size="small" class="kpi-card">
              <NSpace vertical :size="6" align="center">
                <NIcon size="28" :component="kpi.icon" />
                <div class="kpi-value">{{ kpi.value }}</div>
                <div class="kpi-label">{{ kpi.label }}</div>
              </NSpace>
            </NCard>
          </div>

          <!-- 2 chart: 用 NProgress + {{ t('projectCenter.t011') }} {{ t('projectCenter.t012') }} ECharts ({{ t('projectCenter.t013') }}) -->
          <div class="chart-grid">
            <NCard :bordered="false" size="small" title="需求按状态分布">
              <NSpace vertical :size="8">
                <div v-for="(item, idx) in requirementsByStatus" :key="idx" class="bar-row">
                  <span class="bar-label">{{ item.label }}</span>
                  <NProgress
                    type="line"
                    :percentage="item.pct"
                    :show-indicator="false"
                    :height="10"
                    :color="item.color"
                  />
                  <span class="bar-value">{{ item.value }}</span>
                </div>
                <NEmpty v-if="requirementsByStatus.every(r => r.value === 0)" size="small" description="暂无需求数据" />
              </NSpace>
            </NCard>

            <NCard :bordered="false" size="small" title="任务按负责人分布">
              <NSpace vertical :size="8">
                <div v-for="(item, idx) in tasksByAssignee" :key="idx" class="bar-row">
                  <span class="bar-label">{{ item.label }}</span>
                  <NProgress
                    type="line"
                    :percentage="item.pct"
                    :show-indicator="false"
                    :height="10"
                    :color="item.color"
                  />
                  <span class="bar-value">{{ item.value }}</span>
                </div>
                <NEmpty v-if="tasksByAssignee.every(r => r.value === 0)" size="small" description="暂无任务数据" />
              </NSpace>
            </NCard>
          </div>

          <!-- 6 quick actions -->
          <NCard :bordered="false" size="small" title="快捷操作">
            <div class="quick-actions">
              <NButton
                v-for="qa in quickActions"
                :key="qa.key"
                :type="qa.type"
                ghost
                @click="onQuickAction(qa.key)"
              >
                <template #icon>
                  <NIcon><component :is="qa.icon" /></NIcon>
                </template>
                {{ qa.label }}
              </NButton>
            </div>
          </NCard>
        </template>
      </main>

      <!-- ════ {{ t('projectCenter.t014') }}: {{ t('form.sectionMember') }} + {{ t('projectCenter.t015') }} + {{ t('agent.action') }} ════ -->
      <aside class="col-right">
        <NCard :bordered="false" size="small" title="成员" class="section-card">
          <template #header-extra>
            <NButton size="tiny" type="primary" @click="openAddMember">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              {{ t('common.add') }}
            </NButton>
          </template>
          <NSpace vertical :size="8">
            <div v-if="selected && selected.members && selected.members.length > 0">
              <NSpace vertical :size="6">
                <div v-for="uid in selected.members" :key="uid" class="member-row">
                  <NAvatar size="small" round>
                    {{ (uid || '?').charAt(0).toUpperCase() }}
                  </NAvatar>
                  <span class="member-name">{{ uid }}</span>
                  <NTag size="tiny" :type="uid === selected.owner_id ? 'warning' : 'default'">
                    {{ uid === selected.owner_id ? 'owner' : 'member' }}
                  </NTag>
                  <NButton
                    v-if="uid !== selected.owner_id"
                    size="tiny"
                    quaternary
                    type="error"
                    @click="removeMember(uid)"
                  >
                    <template #icon><NIcon><CloseOutline /></NIcon></template>
                  </NButton>
                </div>
              </NSpace>
            </div>
            <NEmpty v-else size="small" description="暂无成员" />
          </NSpace>
        </NCard>

        <NCard :bordered="false" size="small" title="时间线" class="section-card">
          <NScrollbar style="max-height: 360px">
            <NTimeline v-if="timeline.length > 0">
              <NTimelineItem
                v-for="ev in timeline"
                :key="ev.id"
                :type="eventTypeColor(ev.event_type)"
                :title="eventTitle(ev.event_type)"
                :content="ev.message"
                :time="formatTime(ev.ts)"
              />
            </NTimeline>
            <NEmpty v-else size="small" description="暂无事件" />
          </NScrollbar>
        </NCard>

        <NCard :bordered="false" size="small" title="操作" class="section-card">
          <NSpace vertical :size="8">
            <NButton block @click="openStatusChange" :disabled="selected?.status === 'closed'">
              <template #icon><NIcon><SyncOutline /></NIcon></template>
              {{ t('projectCenter.t016') }}
            </NButton>
            <NButton block @click="openEdit">
              <template #icon><NIcon><CreateOutline /></NIcon></template>
              {{ t('common.edit') }}
            </NButton>
            <NButton block type="error" ghost @click="onDelete">
              <template #icon><NIcon><TrashOutline /></NIcon></template>
              {{ t('projectCenter.t017') }}
            </NButton>
          </NSpace>
        </NCard>
      </aside>
    </div>

    <!-- ════ Modal: {{ t('common.create') }} / {{ t('projectCenter.t018') }} ════ -->
    <NModal v-model:show="modalShow"
      preset="card"
      :title="modalMode === 'create' ? t('projectCenter.t019') : t('projectCenter.t020')"
      style="width: 600px"
    >
      <NForm :model="form" label-placement="top">
        <NFormItem label="项目名称" path="name">
          <NInput v-model:value="form.name" placeholder="请输入项目名称" maxlength="200" show-count />
        </NFormItem>
        <NFormItem label="描述" path="description">
          <NInput
            v-model:value="form.description"
            type="textarea"
            placeholder="项目说明"
            :rows="3"
            maxlength="4000"
          />
        </NFormItem>
        <NGrid :cols="2" :x-gap="12">
          <NFormItemGi label="优先级" path="priority">
            <NSelect v-model:value="form.priority" :options="priorityOptions" />
          </NFormItemGi>
          <NFormItemGi label="状态" path="status">
            <NSelect
              v-model:value="form.status"
              :options="statusOptions"
              :disabled="modalMode !== 'create'"
            />
          </NFormItemGi>
        </NGrid>
        <NGrid :cols="2" :x-gap="12">
          <NFormItemGi label="开始日期" path="start_date">
            <NDatePicker
              v-model:value="form.startDateTs"
              type="date"
              format="yyyy-MM-dd"
              clearable
              style="width: 100%"
            />
          </NFormItemGi>
          <NFormItemGi label="截止日期" path="due_date">
            <NDatePicker
              v-model:value="form.dueDateTs"
              type="date"
              format="yyyy-MM-dd"
              clearable
              style="width: 100%"
            />
          </NFormItemGi>
        </NGrid>
        <NFormItem label="标签 (逗号分隔)" path="tags">
          <NInput
            v-model:value="form.tagsText"
            placeholder="tag1, tag2, tag3"
          />
        </NFormItem>
        <NFormItem label="初始成员 (逗号分隔 user_id)" path="members">
          <NInput
            v-model:value="form.membersText"
            placeholder="alice, bob, carol"
          />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="modalShow = false">{{ t('common.cancel') }}</NButton>
          <NButton type="primary" :loading="submitting" @click="onSubmit">
            {{ modalMode === 'create' ? t('projectCenter.t021') : t('common.save') }}
          </NButton>
        </NSpace>
      </template>
    </NModal>

    <!-- ════ Modal: {{ t('projectCenter.t022') }} ════ -->
    <NModal v-model:show="addMemberShow" preset="card" title="添加成员" style="width: 460px">
      <NForm :model="memberForm" label-placement="top">
        <NFormItem label="用户 ID" path="user_id">
          <NInput v-model:value="memberForm.user_id" placeholder="alice / bob / ..." />
        </NFormItem>
        <NFormItem label="角色" path="role">
          <NSelect v-model:value="memberForm.role" :options="roleOptions" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="addMemberShow = false">{{ t('common.cancel') }}</NButton>
          <NButton type="primary" :loading="submitting" @click="onAddMember">{{ t('common.add') }}</NButton>
        </NSpace>
      </template>
    </NModal>

    <!-- ════ Modal: {{ t('projectCenter.t023') }} ════ -->
    <NModal v-model:show="statusShow" preset="card" title="状态转换" style="width: 460px">
      <NForm :model="statusForm" label-placement="top">
        <NFormItem label="目标状态" path="status">
          <NSelect v-model:value="statusForm.status" :options="transitionalStatusOptions" />
        </NFormItem>
        <NFormItem label="原因" path="reason">
          <NInput v-model:value="statusForm.reason" type="textarea" :rows="2" maxlength="500" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="statusShow = false">{{ t('common.cancel') }}</NButton>
          <NButton type="primary" :loading="submitting" @click="onStatusSubmit">{{ t('common.apply') }}</NButton>
        </NSpace>
      </template>
    </NModal>
  </PageRegion>
</template>

<script setup lang="ts">import { useI18n } from 'vue-i18n'

const { t } = useI18n()

/**
 * ProjectCenter — P5-R1-T1 ${t('projectCenter.t024')} (${t('projectCenter.t025')})
 * - ${t('projectCenter.t026')}: 左 (${t('projectCenter.t027')}+${t('projectCenter.t028')}) + 中 (${t('common.detail')}+KPIs+charts+quick actions) + 右 (${t('form.sectionMember')}+${t('projectCenter.t029')}+${t('agent.action')})
 * - 10 ${t('projectCenter.t030')} backend/imdf/api/project_routes.py
 * - ${t('projectCenter.t031')}: ${t('projectCenter.t032')} Depends(require_user) ${t('projectCenter.t033')}, ${t('projectCenter.t034')} + ${t('agent.action')}
 */
import { computed, h, markRaw, onMounted, ref, type Component } from 'vue'
import { useRouter } from 'vue-router'
import {
  NCard, NEmpty, NForm, NFormItem, NFormItemGi, NGrid, NInput, NSelect,
  NButton, NTag, NSpace, NIcon, NModal, NScrollbar, NProgress, NSpin,
  NTimeline, NTimelineItem, NAvatar, NDatePicker, useMessage
} from 'naive-ui'
import {
  SearchOutline, AddOutline, FolderOpenOutline, PeopleOutline,
  CalendarOutline, PricetagsOutline, CloseOutline, SyncOutline,
  CreateOutline, TrashOutline, DocumentTextOutline,
  CloudUploadOutline, CubeOutline, CheckmarkDoneOutline,
  EyeOutline, ArchiveOutline
} from '@vicons/ionicons5'
import PageRegion from '@/components/PageRegion.vue'
import {
  listProjects, getProject, createProject, updateProject,
  deleteProject, addMember, removeMember as apiRemoveMember, updateStatus,
  getStats, getTimeline, type Project, type ProjectStatus,
  type ProjectPriority, type ProjectMemberRole, type ProjectStats,
  type ProjectTimelineEvent
} from '@/api/project'

const message = useMessage()
const router = useRouter()

// ──────────────── state ────────────────
const projects = ref<Project[]>([])
const total = ref(0)
const loading = ref(false)
const keyword = ref('')
const filterStatus = ref<ProjectStatus | null>(null)
const filterPriority = ref<ProjectPriority | null>(null)
const page = ref(1)
const pageSize = ref(20)

const selected = ref<Project | null>(null)
const stats = ref<ProjectStats | null>(null)
const timeline = ref<ProjectTimelineEvent[]>([])
const submitting = ref(false)

// ──────────────── options ────────────────
const statusOptions = [
  { label: t("projectCenter.t035"), value: 'planning' },
  { label: t("common.inProgress"), value: 'active' },
  { label: t("common.paused"), value: 'paused' },
  { label: t("common.closed"), value: 'closed' }
]
const priorityOptions = [
  { label: `P0 ${t('projectCenter.t036')}`, value: 'P0' },
  { label: 'P1 高', value: 'P1' },
  { label: 'P2 中', value: 'P2' },
  { label: 'P3 低', value: 'P3' }
]
const roleOptions = [
  { label: t("userManagement.roleAdmin"), value: 'admin' },
  { label: t("form.sectionMember"), value: 'member' },
  { label: t("projectCenter.t037"), value: 'viewer' }
]
const transitionalStatusOptions = computed(() =>
  statusOptions.filter(o => o.value !== selected.value?.status)
)

const STATUS_LABEL: Record<ProjectStatus, string> = {
  planning: t("projectCenter.t038"), active: t("common.inProgress"), paused: t("common.paused"), closed: t("common.closed")
}
const STATUS_TYPE: Record<ProjectStatus, 'default' | 'success' | 'warning' | 'error'> = {
  planning: 'default', active: 'success', paused: 'warning', closed: 'error'
}
const PRIORITY_TYPE: Record<ProjectPriority, 'default' | 'info' | 'warning' | 'error'> = {
  P0: 'error', P1: 'warning', P2: 'info', P3: 'default'
}

function statusLabel(s: string): string { return STATUS_LABEL[s as ProjectStatus] || s }
function statusTagType(s: string) { return STATUS_TYPE[s as ProjectStatus] || 'default' }
function priorityTagType(p: string) { return PRIORITY_TYPE[p as ProjectPriority] || 'default' }

// ──────────────── list load ────────────────
async function loadList(): Promise<void> {
  loading.value = true
  try {
    const res = await listProjects({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      status: filterStatus.value || undefined,
      priority: filterPriority.value || undefined
    })
    projects.value = res.items
    total.value = res.total
  } catch (e) {
    message.error((e as Error).message || t("projectCenter.t039"))
    projects.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function onSearch(): void { page.value = 1; void loadList() }
function onFilterChange(): void { page.value = 1; void loadList() }

// ──────────────── select / load detail ────────────────
async function selectProject(p: Project): Promise<void> {
  selected.value = p
  stats.value = null
  timeline.value = []
  await Promise.all([loadStats(p.id), loadTimeline(p.id), refreshSelected(p.id)])
}

async function refreshSelected(id: string): Promise<void> {
  try {
    const detail = await getProject(id)
    selected.value = detail as Project
  } catch (e) {
    message.warning(`${t('projectCenter.t040')}: ${(e as Error).message}`)
  }
}

async function loadStats(id: string): Promise<void> {
  try {
    stats.value = await getStats(id)
  } catch (e) {
    message.warning(`${t('projectCenter.t041')}: ${(e as Error).message}`)
    stats.value = null
  }
}

async function loadTimeline(id: string): Promise<void> {
  try {
    const t = await getTimeline(id, 100)
    timeline.value = t.events
  } catch (e) {
    timeline.value = []
  }
}

// ──────────────── KPIs ────────────────
const kpis = computed(() => [
  { key: 'req', label: t("projectCenter.t042"), value: stats.value?.requirements_count ?? 0,
    icon: markRaw(DocumentTextOutline) as Component },
  { key: 'task', label: t("dashboard.cardTasks"), value: stats.value?.tasks_count ?? 0,
    icon: markRaw(CheckmarkDoneOutline) as Component },
  { key: 'ds', label: t("dashboard.cardDatasets"), value: stats.value?.datasets_count ?? 0,
    icon: markRaw(CubeOutline) as Component },
  { key: 'del', label: t("projectCenter.t043"), value: stats.value?.deliveries_count ?? 0,
    icon: markRaw(ArchiveOutline) as Component }
])

// ──────────────── chart data (lightweight, 从 stats ${t('projectCenter.t044')}) ────────────────
const requirementsByStatus = computed(() => {
  const total = stats.value?.requirements_count ?? 0
  // section : ${t('projectCenter.t046')}
  const progress = stats.value?.progress ?? 0
  return [
    { label: t("common.completed"), value: Math.round(total * progress / 100), pct: progress, color: '#18a058' },
    { label: t("common.inProgress"), value: Math.round(total * (100 - progress) * 0.4 / 100), pct: (100 - progress) * 0.4, color: '#2080f0' },
    { label: t("projectCenter.t047"), value: Math.round(total * (100 - progress) * 0.4 / 100), pct: (100 - progress) * 0.4, color: '#f0a020' },
    { label: t("projectCenter.t048"), value: Math.round(total * (100 - progress) * 0.2 / 100), pct: (100 - progress) * 0.2, color: '#d03050' }
  ]
})

const tasksByAssignee = computed(() => {
  const members = selected.value?.members || []
  const total = stats.value?.tasks_count ?? 0
  if (members.length === 0 || total === 0) {
    return [{ label: t("projectCenter.t049"), value: 0, pct: 0, color: '#909399' }]
  }
  const perMember = Math.max(1, Math.floor(total / members.length))
  const colors = ['#2080f0', '#18a058', '#f0a020', '#d03050', '#722ed1', '#13c2c2']
  return members.map((m, i) => ({
    label: m,
    value: perMember,
    pct: Math.min(100, Math.round(perMember * 100 / Math.max(total, 1))),
    color: colors[i % colors.length]
  }))
})

// ──────────────── 6 quick actions ────────────────
const quickActions = [
  { key: 'requirement', label: t("projectCenter.t050"), type: 'primary' as const, icon: markRaw(DocumentTextOutline) as Component },
  { key: 'pack', label: t("projectCenter.t051"), type: 'info' as const, icon: markRaw(CubeOutline) as Component },
  { key: 'task', label: t("projectCenter.t052"), type: 'warning' as const, icon: markRaw(CheckmarkDoneOutline) as Component },
  { key: 'dataset', label: t("projectCenter.t053"), type: 'success' as const, icon: markRaw(CloudUploadOutline) as Component },
  { key: 'review', label: t("projectCenter.t054"), type: 'default' as const, icon: markRaw(EyeOutline) as Component },
  { key: 'delivery', label: t("projectCenter.t055"), type: 'error' as const, icon: markRaw(ArchiveOutline) as Component }
]

function onQuickAction(key: string): void {
  // P5-R2-T2 + T5 fix: requirement quick action ${t('projectCenter.t056')} /requirements (${t('projectCenter.t057')} /annotation-management)
  // /annotation-management ${t('projectCenter.t058')}, /requirements ${t('projectCenter.t059')} (RequirementCenter.vue)
  const map: Record<string, string> = {
    requirement: '/requirements',
    pack: '/packs',
    task: '/tasks',
    dataset: '/dataset-management',
    review: '/review',
    delivery: '/delivery'
  }
  const target = map[key]
  if (target) {
    // section project_id ${t('projectCenter.t061')} query ${t('projectCenter.t062')}, ${t('projectCenter.t063')} (RequirementCenter 等) ${t('projectCenter.t064')}
    const projId = selected.value?.id
    const url = projId
      ? `${target}?project_id=${encodeURIComponent(projId)}`
      : target
    message.info(`${t('common.goTo')} ${url} (${t('projectCenter.t065')} ${projId})`)
    // P5-R2-T2 fix: ${t('projectCenter.t066')} (${t('projectCenter.t067')} window.location.hash ${t('projectCenter.t068')}, ${t('projectCenter.t069')})
    router.push(url).catch((err) => {
      // section (${t('projectCenter.t071')}) — ${t('projectCenter.t072')}
      // eslint-disable-next-line no-console
      console.warn(`[ProjectCenter] router.push ${t('common.failed')}: ${err?.message || err}`)
    })
  }
}

// ──────────────── create / edit modal ────────────────
interface FormState {
  name: string
  description: string
  priority: ProjectPriority
  tagsText: string
  membersText: string
  startDateTs: number | null
  dueDateTs: number | null
  status: ProjectStatus
}

const modalShow = ref(false)
const modalMode = ref<'create' | 'edit'>('create')
const editingId = ref<string | null>(null)
const form = ref<FormState>({
  name: '', description: '', priority: 'P1', tagsText: '', membersText: '',
  startDateTs: null, dueDateTs: null, status: 'planning'
})

function tsToDateStr(ts: number | null): string {
  if (!ts) return ''
  const d = new Date(ts)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function openCreate(): void {
  modalMode.value = 'create'
  editingId.value = null
  form.value = {
    name: '', description: '', priority: 'P1', tagsText: '', membersText: '',
    startDateTs: null, dueDateTs: null, status: 'planning'
  }
  modalShow.value = true
}

function openEdit(): void {
  if (!selected.value) return
  modalMode.value = 'edit'
  editingId.value = selected.value.id
  const s = selected.value.start_date
  const d = selected.value.due_date
  form.value = {
    name: selected.value.name,
    description: selected.value.description || '',
    priority: selected.value.priority,
    tagsText: (selected.value.tags || []).join(', '),
    membersText: (selected.value.members || []).join(', '),
    startDateTs: s ? new Date(s).getTime() : null,
    dueDateTs: d ? new Date(d).getTime() : null,
    status: selected.value.status
  }
  modalShow.value = true
}

async function onSubmit(): Promise<void> {
  if (!form.value.name.trim()) {
    message.error(t("projectCenter.t073"))
    return
  }
  submitting.value = true
  try {
    const body = {
      name: form.value.name.trim(),
      description: form.value.description,
      priority: form.value.priority,
      tags: form.value.tagsText.split(t(',')).map(t => t.trim()).filter(Boolean),
      members: form.value.membersText.split(t(',')).map(m => m.trim()).filter(Boolean),
      start_date: tsToDateStr(form.value.startDateTs),
      due_date: tsToDateStr(form.value.dueDateTs),
      ...(modalMode.value === 'create' ? { status: form.value.status } : {})
    }
    let result: Project
    if (modalMode.value === 'create') {
      result = await createProject(body)
      message.success(`${t('common.project')} ${result.id} ${t('userManagement.createSuccess')}`)
    } else if (editingId.value) {
      result = await updateProject(editingId.value, body)
      message.success(t("projectCenter.t074"))
    } else {
      return
    }
    modalShow.value = false
    await loadList()
    await selectProject(result)
  } catch (e) {
    message.error((e as Error).message || t("projectCenter.t075"))
  } finally {
    submitting.value = false
  }
}

// ──────────────── delete ────────────────
async function onDelete(): Promise<void> {
  if (!selected.value) return
  if (!window.confirm(`${t('projectCenter.t076')} ${selected.value.name}? ${t('projectCenter.t077')}。`)) return
  try {
    await deleteProject(selected.value.id)
    message.success(t("projectCenter.t078"))
    selected.value = null
    stats.value = null
    timeline.value = []
    await loadList()
  } catch (e) {
    message.error((e as Error).message || t("canvasDesigner.deleteFailed"))
  }
}

// ──────────────── member modal ────────────────
const addMemberShow = ref(false)
const memberForm = ref<{ user_id: string; role: ProjectMemberRole }>({ user_id: '', role: 'member' })

function openAddMember(): void {
  if (!selected.value) {
    message.warning(t("projectCenter.t079"))
    return
  }
  memberForm.value = { user_id: '', role: 'member' }
  addMemberShow.value = true
}

async function onAddMember(): Promise<void> {
  if (!selected.value || !memberForm.value.user_id.trim()) {
    message.error(`${t('common.user')} ID ${t('common.required')}`)
    return
  }
  submitting.value = true
  try {
    const result = await addMember(selected.value.id, memberForm.value.user_id.trim(), memberForm.value.role)
    message.success(t("projectCenter.t080"))
    addMemberShow.value = false
    await refreshSelected(selected.value.id)
    await loadList()
    selected.value = result
  } catch (e) {
    message.error((e as Error).message || t("projectCenter.t081"))
  } finally {
    submitting.value = false
  }
}

async function removeMember(uid: string): Promise<void> {
  if (!selected.value) return
  if (!window.confirm(`${t('projectCenter.t082')} ${uid}?`)) return
  try {
    const result = await apiRemoveMember(selected.value.id, uid)
    message.success(t("projectCenter.t083"))
    selected.value = result
    if (selected.value) {
      await loadTimeline(selected.value.id)
    }
    await loadList()
  } catch (e) {
    message.error((e as Error).message || t("projectCenter.t084"))
  }
}

// ──────────────── status modal ────────────────
const statusShow = ref(false)
const statusForm = ref<{ status: ProjectStatus; reason: string }>({ status: 'active', reason: '' })

function openStatusChange(): void {
  if (!selected.value) return
  const allowed = availableTransitions(selected.value.status)
  if (allowed.length === 0) {
    message.warning(`${t('projectCenter.t085')} (closed ${t('projectCenter.t086')})`)
    return
  }
  statusForm.value = { status: allowed[0], reason: '' }
  statusShow.value = true
}

function availableTransitions(s: ProjectStatus): ProjectStatus[] {
  const map: Record<ProjectStatus, ProjectStatus[]> = {
    planning: ['active', 'closed'],
    active: ['paused', 'closed'],
    paused: ['active', 'closed'],
    closed: []
  }
  return map[s] || []
}

async function onStatusSubmit(): Promise<void> {
  if (!selected.value) return
  submitting.value = true
  try {
    const result = await updateStatus(selected.value.id, statusForm.value.status, statusForm.value.reason)
    message.success(`${t('projectCenter.t087')} ${statusLabel(result.status)}`)
    statusShow.value = false
    selected.value = result
    await loadTimeline(selected.value.id)
    await loadList()
  } catch (e) {
    message.error((e as Error).message || t("projectCenter.t088"))
  } finally {
    submitting.value = false
  }
}

// ──────────────── helpers ────────────────
function eventTitle(key: string): string {
  const map: Record<string, string> = {
    created: t("projectCenter.t089"),
    updated: t("projectCenter.t090"),
    status_changed: t("projectCenter.t091"),
    member_added: t("projectCenter.t092"),
    member_removed: t("projectCenter.t093"),
    member_role_changed: t("projectCenter.t094")
  }
  return map[key] || key
}

function eventTypeColor(t: string): 'default' | 'success' | 'info' | 'warning' | 'error' {
  const map: Record<string, 'default' | 'success' | 'info' | 'warning' | 'error'> = {
    created: 'success', updated: 'info', status_changed: 'warning',
    member_added: 'success', member_removed: 'error', member_role_changed: 'info'
  }
  return map[t] || 'default'
}

function formatTime(ts: string): string {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ts
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ──────────────── mount ────────────────
onMounted(loadList)
</script>

<style scoped>
.project-center-root { padding: 12px; }
.project-center-layout {
  display: grid;
  grid-template-columns: 280px 1fr 320px;
  gap: 12px;
  height: calc(100vh - 100px);
}
.col-left, .col-right { display: flex; flex-direction: column; gap: 12px; overflow: hidden; }
.col-main { display: flex; flex-direction: column; gap: 12px; overflow-y: auto; }

.filter-card { flex-shrink: 0; }
.list-card { flex: 1; overflow: hidden; }
.section-card { flex-shrink: 0; }

.project-item {
  padding: 10px 12px;
  border-bottom: 1px solid var(--app-border, rgba(0, 0, 0, 0.06));
  cursor: pointer;
  transition: background 0.18s ease;
}
.project-item:hover { background: var(--app-hover, rgba(24, 160, 88, 0.06)); }
.project-item.active {
  background: var(--app-active, rgba(24, 160, 88, 0.12));
  border-left: 3px solid var(--app-primary, #18a058);
}
.project-item-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 4px;
}
.project-item-head .name {
  font-weight: 600; font-size: 13px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  max-width: 160px;
}
.project-item-meta {
  display: flex; gap: 6px; align-items: center;
  font-size: 11px; color: var(--app-muted, #767676);
}
.project-item-meta .owner { font-weight: 500; }
.project-item-tags {
  margin-top: 4px; display: flex; gap: 4px; flex-wrap: wrap;
}
.loading-state { padding: 24px; text-align: center; }

.empty-detail {
  height: 100%;
  display: flex; align-items: center; justify-content: center;
}

.detail-header .title { margin: 0; font-size: 22px; font-weight: 700; }
.detail-header .desc { margin: 0; color: var(--app-muted, #767676); font-size: 13px; line-height: 1.6; }
.detail-header .owner-id { font-size: 12px; color: var(--app-muted, #767676); }
.detail-header .meta-row { font-size: 13px; color: var(--app-muted, #767676); }
.detail-header .meta-item { display: inline-flex; align-items: center; gap: 4px; }
.detail-header .progress-row {
  display: grid; grid-template-columns: 60px 1fr 50px; align-items: center; gap: 8px;
}
.detail-header .progress-label { font-size: 12px; color: var(--app-muted, #767676); }
.detail-header .progress-pct { font-weight: 600; font-size: 13px; text-align: right; }

.kpi-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
}
.kpi-card { text-align: center; }
.kpi-card .kpi-value { font-size: 22px; font-weight: 700; color: var(--app-primary, #18a058); }
.kpi-card .kpi-label { font-size: 12px; color: var(--app-muted, #767676); }

.chart-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
}
.bar-row {
  display: grid; grid-template-columns: 80px 1fr 40px;
  align-items: center; gap: 8px; font-size: 12px;
}
.bar-label { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar-value { text-align: right; font-weight: 600; }

.quick-actions {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
}

.member-row {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 6px; border-radius: 4px;
}
.member-row:hover { background: var(--app-hover, rgba(0, 0, 0, 0.04)); }
.member-name { flex: 1; font-size: 13px; }
</style>