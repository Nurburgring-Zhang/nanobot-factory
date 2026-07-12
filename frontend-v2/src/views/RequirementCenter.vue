<template>
  <div class="requirement-center">
    <!-- {{ t('requirementCenter.t000') }} -->
    <div class="rc-toolbar">
      <SearchBar
        v-model="keyword"
        placeholder="搜索需求标题/描述/责任人"
        @search="onSearch"
        @reset="onReset"
      >
        <template #extra>
          <PermissionGuard :roles="['admin', 'engineer']">
            <ActionButton type="primary" @click="openCreate">
              <template #icon><NIcon><AddOutline /></NIcon></template>
              {{ t('requirementCenter.t001') }}
            </ActionButton>
          </PermissionGuard>
        </template>
      </SearchBar>

      <!-- {{ t('requirementCenter.t002') }} -->
      <div class="rc-filters">
        <NSpace :size="8" align="center" wrap>
          <span class="filter-label">{{ t('common.project') }}:</span>
          <NSelect
            v-model:value="filterProjectId"
            :options="projectOptions"
            placeholder="全部项目"
            clearable
            filterable
            style="width: 180px"
            @update:value="onFilterChange"
          />
          <span class="filter-label">{{ t('annotation.colType') }}:</span>
          <NSelect
            v-model:value="filterType"
            :options="typeOptions"
            placeholder="全部类型"
            clearable
            style="width: 140px"
            @update:value="onFilterChange"
          />
          <span class="filter-label">{{ t('annotation.colStatus') }}:</span>
          <NSelect
            v-model:value="filterStatus"
            :options="statusOptions"
            placeholder="全部状态"
            clearable
            style="width: 140px"
            @update:value="onFilterChange"
          />
          <span class="filter-label">{{ t('engines.colPriority') }}:</span>
          <NSelect
            v-model:value="filterPriority"
            :options="priorityOptions"
            placeholder="全部优先级"
            clearable
            style="width: 120px"
            @update:value="onFilterChange"
          />
        </NSpace>
      </div>
    </div>

    <!-- {{ t('requirementCenter.t003') }} -->
    <div class="rc-3col">
      <!-- 左: {{ t('requirementCenter.t004') }} 280px -->
      <div class="rc-col-left">
        <NCard :bordered="false" size="small" class="rc-list-card" content-style="padding: 8px;">
          <template #header>
            <NSpace align="center" justify="space-between" style="width: 100%">
              <span class="card-title">{{ t('requirementCenter.t005') }} ({{ total }})</span>
              <NButton quaternary size="tiny" @click="load" :loading="loading">
                <template #icon><NIcon><RefreshOutline /></NIcon></template>
              </NButton>
            </NSpace>
          </template>
          <NEmpty v-if="!loading && rows.length === 0" description="暂无需求" />
          <div v-else class="rc-list-scroll">
            <div
              v-for="row in rows"
              :key="row.id"
              class="rc-list-item"
              :class="{ active: row.id === selectedId }"
              @click="onSelect(row)"
              role="button"
              tabindex="0"
              @keydown.enter="onSelect(row)"
            >
              <div class="rc-li-header">
                <NTag :type="priorityType(row.priority)" size="small" round>{{ row.priority }}</NTag>
                <NTag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</NTag>
              </div>
              <div class="rc-li-title">{{ row.title }}</div>
              <div class="rc-li-meta">
                <span class="rc-li-type">{{ typeLabel(row.type) }}</span>
                <span v-if="row.project_id" class="rc-li-project" :title="t('common.project') + ' ' + row.project_id">
                  📁 {{ truncateProject(row.project_id) }}
                </span>
              </div>
              <div class="rc-li-footer">
                <span v-if="row.owner">👤 {{ row.owner }}</span>
                <span v-if="row.due_date">📅 {{ row.due_date }}</span>
              </div>
            </div>
          </div>
          <!-- {{ t('requirementCenter.t006') }} -->
          <div class="rc-pagination">
            <NPagination
              v-model:page="page"
              v-model:page-size="pageSize"
              :item-count="total"
              :page-sizes="[10, 20, 50]"
              show-size-picker
              size="small"
            />
          </div>
        </NCard>
      </div>

      <!-- 中: {{ t('common.detail') }} 1fr -->
      <div class="rc-col-center">
        <NCard :bordered="false" size="small" content-style="padding: 16px;" v-if="selected">
          <!-- {{ t('requirementCenter.t007') }}: {{ t('form.title') }} + {{ t('requirementCenter.t008') }} + {{ t('requirementCenter.t009') }} + {{ t('requirementCenter.t010') }} -->
          <div class="rc-detail-header">
            <div class="rc-detail-titles">
              <h2 class="rc-detail-title">{{ selected.title }}</h2>
              <NSpace :size="6" align="center">
                <NTag :type="statusType(selected.status)" round>{{ statusLabel(selected.status) }}</NTag>
                <NTag :type="priorityType(selected.priority)" round>{{ selected.priority }}</NTag>
                <NTag v-if="selected.qc_status" :type="qcType(selected.qc_status)" size="small">
                  QC: {{ qcLabel(selected.qc_status) }}
                </NTag>
                <NTag v-if="selected.project_id" type="info" size="small">
                  📁 {{ t('common.project') }} {{ truncateProject(selected.project_id) }}
                </NTag>
              </NSpace>
            </div>
            <div class="rc-progress-ring">
              <NProgress
                type="circle"
                :percentage="stats ? stats.progress : 0"
                :stroke-width="8"
                :width="80"
              />
            </div>
          </div>

          <!-- 5 {{ t('requirementCenter.t011') }} -->
          <div class="rc-status-flow">
            <NSteps :current="stats ? stats.current_step + 1 : 1" size="small" status="process">
              <NStep title="草稿" description="draft" />
              <NStep title="待处理" description="open" />
              <NStep title="进行中" description="in_progress" />
              <NStep title="审核中" description="review" />
              <NStep title="已完成" description="done" />
              <NStep title="已关闭" description="closed" />
            </NSteps>
          </div>

          <!-- {{ t('common.description') }} + {{ t('requirementCenter.t012') }} -->
          <NDivider />
          <div class="rc-section">
            <h4 class="rc-section-title">{{ t('common.description') }}</h4>
            <p class="rc-desc">{{ selected.description || '(无)' }}</p>
          </div>
          <div class="rc-section">
            <h4 class="rc-section-title">{{ t('requirementCenter.t013') }}</h4>
            <p class="rc-desc">{{ selected.acceptance_criteria || '(无)' }}</p>
          </div>
          <div class="rc-section rc-meta-grid">
            <div class="rc-meta-item">
              <span class="rc-meta-key">{{ t('annotation.colType') }}</span>
              <span class="rc-meta-val">{{ typeLabel(selected.type) }}</span>
            </div>
            <div class="rc-meta-item">
              <span class="rc-meta-key">{{ t('requirementCenter.t014') }}</span>
              <span class="rc-meta-val">{{ selected.owner || '—' }}</span>
            </div>
            <div class="rc-meta-item">
              <span class="rc-meta-key">{{ t('form.dueDate') }}</span>
              <span class="rc-meta-val">{{ selected.due_date || '—' }}</span>
            </div>
            <div class="rc-meta-item">
              <span class="rc-meta-key">{{ t('form.creator') }}</span>
              <span class="rc-meta-val">{{ selected.created_by || '—' }}</span>
            </div>
            <div class="rc-meta-item">
              <span class="rc-meta-key">{{ t('requirementCenter.t015') }}</span>
              <span class="rc-meta-val">{{ selected.delivery_id || '—' }}</span>
            </div>
            <div class="rc-meta-item">
              <span class="rc-meta-key">{{ t('requirementCenter.t016') }}</span>
              <span class="rc-meta-val">{{ selected.pack_id || '—' }}</span>
            </div>
          </div>

          <!-- {{ t('requirementCenter.t017') }} -->
          <NDivider />
          <NSpace :size="8" align="center">
            <PermissionGuard :roles="['admin', 'engineer']">
              <NButton type="primary" size="small" @click="onDecomposePreview(selected)" :loading="previewing">
                <template #icon><NIcon><GitNetworkOutline /></NIcon></template>
                {{ t('requirementCenter.t018') }}
              </NButton>
              <NButton type="warning" size="small" @click="onDecompose(selected)" :loading="decomposing">
                <template #icon><NIcon><LayersOutline /></NIcon></template>
                {{ t('requirementCenter.t019') }}
              </NButton>
              <NButton size="small" @click="openReassign(selected)">
                <template #icon><NIcon><SyncOutline /></NIcon></template>
                {{ t('requirementCenter.t020') }}
              </NButton>
            </PermissionGuard>
            <NButton size="small" quaternary @click="onStatsRefresh(selected)">
              <template #icon><NIcon><RefreshOutline /></NIcon></template>
              {{ t('requirementCenter.t021') }}
            </NButton>
          </NSpace>
        </NCard>

        <NCard v-else :bordered="false" size="small" class="rc-empty">
          <NEmpty description="从左侧选择一条需求查看详情" />
        </NCard>
      </div>

      <!-- 右: {{ t('requirementCenter.t022') }} / {{ t('requirementCenter.t023') }} 320px -->
      <div class="rc-col-right">
        <NCard :bordered="false" size="small" content-style="padding: 12px;" v-if="stats">
          <template #header>
            <span class="card-title">{{ t('requirementCenter.t024') }}</span>
          </template>

          <!-- {{ t('requirementCenter.t025') }} -->
          <div class="rc-stat-row">
            <div class="rc-stat-cell">
              <div class="rc-stat-val">{{ stats.tasks_count }}</div>
              <div class="rc-stat-key">{{ t('requirementCenter.t026') }}</div>
            </div>
            <div class="rc-stat-cell success">
              <div class="rc-stat-val">{{ stats.approved_count }}</div>
              <div class="rc-stat-key">{{ t('annotation.statusApproved') }}</div>
            </div>
            <div class="rc-stat-cell warn">
              <div class="rc-stat-val">{{ stats.in_progress_count }}</div>
              <div class="rc-stat-key">{{ t('common.inProgress') }}</div>
            </div>
            <div class="rc-stat-cell danger">
              <div class="rc-stat-val">{{ stats.rejected_count }}</div>
              <div class="rc-stat-key">{{ t('annotation.statusRejected') }}</div>
            </div>
          </div>

          <NDivider />

          <!-- {{ t('requirementCenter.t027') }} -->
          <h4 class="rc-section-title">{{ t('requirementCenter.t028') }} ({{ stats.task_tree.length }})</h4>
          <NEmpty v-if="stats.task_tree.length === 0" size="small" description="暂无子任务" />
          <div v-else class="rc-task-tree">
            <div v-for="t in stats.task_tree" :key="t.id" class="rc-task-item">
              <NTag :type="taskStatusType(t.status)" size="small">{{ taskStatusLabel(t.status) }}</NTag>
              <span class="rc-task-title">{{ t.title }}</span>
              <span class="rc-task-meta">
                <span v-if="t.assignee">👤 {{ t.assignee }}</span>
                <span v-if="t.estimated_hours">⏱ {{ t.estimated_hours }}h</span>
              </span>
            </div>
          </div>

          <!-- 按 assignee {{ t('requirementCenter.t029') }} -->
          <NDivider />
          <h4 class="rc-section-title">{{ t('requirementCenter.t030') }}</h4>
          <div v-if="Object.keys(stats.assignee_breakdown).length === 0" class="rc-muted">
            {{ t('requirementCenter.t031') }}
          </div>
          <div v-else class="rc-assignee-list">
            <div
              v-for="(count, uid) in stats.assignee_breakdown"
              :key="uid"
              class="rc-assignee-item"
            >
              <span class="rc-assignee-name">{{ uid }}</span>
              <NTag size="small">{{ count }} 个</NTag>
            </div>
          </div>

          <!-- Packs 数 -->
          <NDivider />
          <NSpace align="center" justify="space-between">
            <span class="rc-section-title">{{ t('requirementCenter.t032') }}</span>
            <NTag type="info" round>{{ stats.packs_count }}</NTag>
          </NSpace>
        </NCard>

        <NCard v-else :bordered="false" size="small" class="rc-empty">
          <NEmpty description="选择需求后展示统计与任务树" />
        </NCard>
      </div>
    </div>

    <!-- {{ t('requirementCenter.t033') }} Modal -->
    <ModalForm
      v-model:show="createShow"
      title="新建需求"
      v-model="createForm"
      :rules="createRules"
      :submitting="createSubmitting"
      @submit="onCreate"
    >
      <template #default="{ form: f }">
        <NFormItem label="标题" path="title">
          <NInput v-model:value="(f as RequirementCreate).title" placeholder="需求标题" />
        </NFormItem>
        <NFormItem label="类型" path="type">
          <NSelect v-model:value="(f as RequirementCreate).type" :options="typeOptions" />
        </NFormItem>
        <NFormItem label="优先级" path="priority">
          <NSelect v-model:value="(f as RequirementCreate).priority" :options="priorityOptions" />
        </NFormItem>
        <NFormItem label="关联项目" path="project_id">
          <NSelect
            v-model:value="(f as RequirementCreate).project_id"
            :options="projectOptions"
            placeholder="选择关联项目 (ProjectCenter)"
            filterable
            clearable
          />
        </NFormItem>
        <NFormItem label="责任人" path="owner">
          <NInput v-model:value="(f as RequirementCreate).owner" placeholder="user_id 或邮箱" />
        </NFormItem>
        <NFormItem label="描述" path="description">
          <NInput
            v-model:value="(f as RequirementCreate).description"
            type="textarea"
            placeholder="详细描述"
            :autosize="{ minRows: 3, maxRows: 6 }"
          />
        </NFormItem>
        <NFormItem label="验收标准" path="acceptance_criteria">
          <NInput
            v-model:value="(f as RequirementCreate).acceptance_criteria"
            type="textarea"
            placeholder="验收标准"
            :autosize="{ minRows: 2, maxRows: 4 }"
          />
        </NFormItem>
        <NFormItem label="截止日期" path="due_date">
          <NDatePicker
            v-model:value="dueDateTs"
            type="date"
            placeholder="选择日期"
            clearable
            @update:value="onDueDateChange"
          />
        </NFormItem>
      </template>
    </ModalForm>

    <!-- {{ t('requirementCenter.t034') }} Modal -->
    <NModal v-model:show="previewShow" preset="card" title="拆解预览" style="width: 720px">
      <NEmpty v-if="!previewData" description="正在加载..." />
      <div v-else>
        <NSpace align="center" style="margin-bottom: 12px">
          <NTag type="info">{{ t('requirementCenter.t035') }}: {{ previewData.complexity }}</NTag>
          <NTag type="success">{{ t('requirementCenter.t036') }}: {{ previewData.estimated_hours }}h</NTag>
          <NTag>{{ t('requirementCenter.t037') }} {{ previewData.task_count }} {{ t('requirementCenter.t038') }}</NTag>
        </NSpace>
        <NList bordered>
          <NListItem v-for="(task, idx) in previewData.tasks" :key="idx">
            <NThing :title="task.title">
              <template #header-extra>
                <NTag size="small">{{ task.estimated_hours }}h</NTag>
              </template>
              <template #description>
                <span class="muted">{{ t('requirementCenter.t039') }}: {{ task.acceptance_criteria }}</span>
              </template>
            </NThing>
          </NListItem>
        </NList>
      </div>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="previewShow = false">{{ t('common.close') }}</NButton>
          <NButton type="primary" :loading="decomposing" @click="onConfirmDecompose">
            {{ t('requirementCenter.t040') }}
          </NButton>
        </NSpace>
      </template>
    </NModal>

    <!-- {{ t('requirementCenter.t041') }} Modal -->
    <NModal v-model:show="reassignShow" preset="card" title="重派任务" style="width: 480px">
      <NFormItem label="选择重派策略">
        <NRadioGroup v-model:value="reassignStrategy">
          <NSpace vertical>
            <NRadio value="by_skill">{{ t('requirementCenter.t042') }} (by_skill)</NRadio>
            <NRadio value="by_workload">{{ t('requirementCenter.t043') }} (by_workload)</NRadio>
            <NRadio value="random">{{ t('requirementCenter.t044') }} (random)</NRadio>
            <NRadio value="hybrid">{{ t('requirementCenter.t045') }} (hybrid) — {{ t('common.recommended') }}</NRadio>
          </NSpace>
        </NRadioGroup>
      </NFormItem>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="reassignShow = false">{{ t('common.cancel') }}</NButton>
          <NButton type="primary" :loading="reassigning" @click="onConfirmReassign">
            {{ t('requirementCenter.t046') }}
          </NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<script setup lang="ts">import { useI18n } from 'vue-i18n'

const { t } = useI18n()

import { ref, reactive, computed, onMounted, h } from 'vue'
import {
  NCard, NEmpty, NSpace, NSelect, NButton, NInput, NInputNumber, NTag, NDivider,
  NProgress, NSteps, NStep, NList, NListItem, NThing, NModal, NFormItem,
  NRadioGroup, NRadio, NPagination, NDatePicker, NIcon, useMessage
} from 'naive-ui'
import {
  AddOutline, RefreshOutline, GitNetworkOutline, LayersOutline, SyncOutline
} from '@vicons/ionicons5'
import SearchBar from '@/components/SearchBar.vue'
import ActionButton from '@/components/ActionButton.vue'
import ModalForm from '@/components/ModalForm.vue'
import PermissionGuard from '@/components/PermissionGuard.vue'
import {
  listRequirements, createRequirement,
  decomposePreview, decomposeRequirement, reassignTasks,
  getRequirementStats,
  type RequirementItem, type RequirementCreate, type RequirementStats,
  type DecomposePreview, type ReassignStrategy
} from '@/api/requirement'

const message = useMessage()

// ── ${t('requirementCenter.t047')}/${t('requirementCenter.t048')} ─────────────────────────────────────
const keyword = ref('')
const page = ref(1)
const pageSize = ref(20)
const filterProjectId = ref<string | null>(null)
const filterType = ref<string | null>(null)
const filterStatus = ref<string | null>(null)
const filterPriority = ref<string | null>(null)
const loading = ref(false)

const rows = ref<RequirementItem[]>([])
const total = ref(0)
const selected = ref<RequirementItem | null>(null)
const selectedId = ref<string | null>(null)
const stats = ref<RequirementStats | null>(null)

// ── ${t('menu.dropdownOptions')} ─────────────────────────────────────
const typeOptions = [
  { label: t("requirementCenter.t049"), value: 'general' },
  { label: t("requirementCenter.t050"), value: 'feature' },
  { label: t("requirementCenter.t051"), value: 'bug' },
  { label: t("requirementCenter.t052"), value: 'improvement' },
]
const statusOptions = [
  { label: t("common.draft"), value: 'draft' },
  { label: t("common.pending"), value: 'open' },
  { label: t("common.inProgress"), value: 'in_progress' },
  { label: t("requirementCenter.t053"), value: 'review' },
  { label: t("common.completed"), value: 'done' },
  { label: t("common.closed"), value: 'closed' },
]
const priorityOptions = [
  { label: `P0 (${t('requirementCenter.t054')})`, value: 'critical' },
  { label: 'P1 (高)', value: 'high' },
  { label: 'P2 (中)', value: 'medium' },
  { label: 'P3 (低)', value: 'low' },
]
// section — 从 project_id ${t('requirementCenter.t056')}, ${t('requirementCenter.t057')}
const projectOptions = computed(() => {
  // section rows ${t('requirementCenter.t059')} project_id ${t('requirementCenter.t060')}
  // section /api/projects/ ${t('requirementCenter.t062')}
  const ids = new Set<string>()
  for (const r of rows.value) {
    if (r.project_id) ids.add(r.project_id)
  }
  if (filterProjectId.value && !ids.has(filterProjectId.value)) {
    ids.add(filterProjectId.value)
  }
  return Array.from(ids).map((id) => ({ label: id, value: id }))
})

// ── ${t('requirementCenter.t063')} ─────────────────────────────────
function statusLabel(s: string): string {
  const map: Record<string, string> = {
    draft: t("common.draft"), open: t("common.pending"), in_progress: t("common.inProgress"),
    review: t("requirementCenter.t064"), done: t("common.completed"), closed: t("common.closed"),
  }
  return map[s] || s
}
function statusType(s: string): 'default' | 'info' | 'success' | 'warning' | 'error' {
  const map: Record<string, 'default' | 'info' | 'success' | 'warning' | 'error'> = {
    draft: 'default', open: 'info', in_progress: 'warning',
    review: 'warning', done: 'success', closed: 'default',
  }
  return (map[s] || 'default') as any
}
function priorityType(p: string): 'error' | 'warning' | 'info' | 'default' {
  if (p === 'P0' || p === 'critical') return 'error'
  if (p === 'P1' || p === 'high') return 'warning'
  if (p === 'P2' || p === 'medium') return 'info'
  return 'default'
}
function qcLabel(q: string): string {
  const map: Record<string, string> = {
    not_started: t("common.notStarted"), in_progress: t("common.inProgress"), passed: t("common.approve"), failed: t("common.failed"),
  }
  return map[q] || q
}
function qcType(q: string): 'default' | 'info' | 'success' | 'error' {
  if (q === 'passed') return 'success'
  if (q === 'failed') return 'error'
  if (q === 'in_progress') return 'info'
  return 'default'
}
function typeLabel(key: string): string {
  const map: Record<string, string> = {
    data_annotation: t("requirementCenter.t065"), data_collection: t("requirementCenter.t066"),
    data_cleaning: t("menu.sidebarCleaningManagement"), model_evaluation: t("requirementCenter.t067"),
    data_augmentation: t("requirementCenter.t068"), quality_review: t("requirementCenter.t069"),
    general: t("requirementCenter.t070"), feature: t("requirementCenter.t071"), bug: t("requirementCenter.t072"), improvement: t("requirementCenter.t073"),
  }
  return map[key] || key
}
function taskStatusLabel(s: string): string {
  const map: Record<string, string> = {
    pending: t("requirementCenter.t074"), assigned: t("requirementCenter.t075"), in_progress: t("common.inProgress"),
    submitted: t("requirementCenter.t076"), approved: t("annotation.statusApproved"), rejected: t("annotation.statusRejected"), blocked: t("requirementCenter.t077"),
  }
  return map[s] || s
}
function taskStatusType(s: string): 'default' | 'info' | 'success' | 'warning' | 'error' {
  if (s === 'approved') return 'success'
  if (s === 'rejected') return 'error'
  if (s === 'in_progress') return 'warning'
  if (s === 'assigned') return 'info'
  return 'default'
}
function truncateProject(id: string | null | undefined): string {
  if (!id) return ''
  return id.length > 16 ? id.slice(0, 14) + '…' : id
}

// ── ${t('requirementCenter.t078')} ─────────────────────────────────
async function load() {
  loading.value = true
  try {
    const res = await listRequirements({
      project_id: filterProjectId.value || undefined,
      status: (filterStatus.value || undefined) as any,
      type: filterType.value || undefined,
      priority: filterPriority.value || undefined,
      keyword: keyword.value || undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    rows.value = res.items
    total.value = res.total
  } catch (e) {
    rows.value = []
    total.value = 0
    message.error(`${t('requirementCenter.t079')}: ${(e as Error).message || ''}`)
  } finally {
    loading.value = false
  }
}
function onSearch() { page.value = 1; void load() }
function onReset() {
  keyword.value = ''
  filterProjectId.value = null
  filterType.value = null
  filterStatus.value = null
  filterPriority.value = null
  page.value = 1
  void load()
}
function onFilterChange() { page.value = 1; void load() }

// section import { watch } from 'vue'
import { watch } from 'vue'
watch([page, pageSize], () => { void load() })

// ── ${t('requirementCenter.t081')} & ${t('common.detail')} ─────────────────────────────────
async function onSelect(row: RequirementItem) {
  selected.value = row
  selectedId.value = row.id
  await refreshStats(row.id)
}

async function refreshStats(reqId: string) {
  try {
    const s = await getRequirementStats(reqId)
    stats.value = s
  } catch (e) {
    stats.value = null
    message.error(`${t('requirementCenter.t082')}: ${(e as Error).message || ''}`)
  }
}
async function onStatsRefresh(row: RequirementItem) {
  await refreshStats(row.id)
  message.success(t("requirementCenter.t083"))
}

// ── ${t('common.create')} ─────────────────────────────────
const createShow = ref(false)
const createSubmitting = ref(false)
const dueDateTs = ref<number | null>(null)
const createForm = reactive<RequirementCreate>({
  title: '',
  type: 'general',
  priority: 'medium',
  description: '',
  acceptance_criteria: '',
  owner: '',
  project_id: undefined,
  due_date: '',
})
const createRules = {
  title: { required: true, message: t("form.placeholderTitle"), trigger: 'blur' },
}

function openCreate() {
  Object.assign(createForm, {
    title: '', type: 'general', priority: 'medium',
    description: '', acceptance_criteria: '', owner: '',
    project_id: undefined, due_date: '',
  } as RequirementCreate)
  dueDateTs.value = null
  createShow.value = true
}
function onDueDateChange(ts: number | null) {
  if (ts) {
    const d = new Date(ts)
    createForm.due_date = d.toISOString().slice(0, 10)
  } else {
    createForm.due_date = ''
  }
}
async function onCreate(payload: RequirementCreate) {
  createSubmitting.value = true
  try {
    const created = await createRequirement(payload)
    message.success(`${t('requirementCenter.t084')} : ${created.id}`)
    createShow.value = false
    await load()
    if (created) onSelect(created)
  } catch (e) {
    message.error(`${t('requirementCenter.t085')}: ${(e as Error).message || ''}`)
  } finally {
    createSubmitting.value = false
  }
}

// ── ${t('requirementCenter.t086')} & ${t('requirementCenter.t087')} ─────────────────────────────────
const previewShow = ref(false)
const previewData = ref<DecomposePreview | null>(null)
const previewing = ref(false)
const decomposing = ref(false)
let previewTarget: RequirementItem | null = null

async function onDecomposePreview(row: RequirementItem) {
  previewTarget = row
  previewing.value = true
  previewShow.value = true
  previewData.value = null
  try {
    previewData.value = await decomposePreview(row.id)
  } catch (e) {
    message.error(`${t('requirementCenter.t088')}: ${(e as Error).message || ''}`)
    previewShow.value = false
  } finally {
    previewing.value = false
  }
}
async function onConfirmDecompose() {
  if (!previewTarget) return
  decomposing.value = true
  try {
    const res = await decomposeRequirement(previewTarget.id)
    message.success(`${t('requirementCenter.t089')} ${res.task_count} ${t('requirementCenter.t090')}`)
    previewShow.value = false
    await refreshStats(previewTarget.id)
  } catch (e) {
    message.error(`${t('requirementCenter.t091')}: ${(e as Error).message || ''}`)
  } finally {
    decomposing.value = false
  }
}
async function onDecompose(row: RequirementItem) {
  await onDecomposePreview(row)
}

// ── ${t('requirementCenter.t092')} ─────────────────────────────────
const reassignShow = ref(false)
const reassignStrategy = ref<ReassignStrategy>('hybrid')
const reassigning = ref(false)
let reassignTarget: RequirementItem | null = null

function openReassign(row: RequirementItem) {
  reassignTarget = row
  reassignStrategy.value = 'hybrid'
  reassignShow.value = true
}
async function onConfirmReassign() {
  if (!reassignTarget) return
  reassigning.value = true
  try {
    const res = await reassignTasks(reassignTarget.id, { strategy: reassignStrategy.value })
    message.success(`${t('requirementCenter.t093')} ${res.reassigned_count} ${t('requirementCenter.t094')} (${res.strategy})`)
    reassignShow.value = false
    await refreshStats(reassignTarget.id)
  } catch (e) {
    message.error(`${t('requirementCenter.t095')}: ${(e as Error).message || ''}`)
  } finally {
    reassigning.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.requirement-center {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 56px - 48px);
  gap: 8px;
}
.rc-toolbar {
  flex-shrink: 0;
}
.rc-filters {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--app-surface-2, #f7f7f7);
  border-radius: 6px;
}
.filter-label {
  font-size: 13px;
  color: var(--app-muted, #666);
}
.rc-3col {
  flex: 1 1 auto;
  display: grid;
  grid-template-columns: 280px 1fr 320px;
  gap: 8px;
  min-height: 0;
}
.rc-col-left,
.rc-col-center,
.rc-col-right {
  min-height: 0;
  overflow: auto;
}
.rc-list-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.rc-list-scroll {
  max-height: calc(100vh - 320px);
  overflow-y: auto;
}
.rc-list-item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
  border: 1px solid transparent;
  transition: background-color 0.12s, border-color 0.12s;
}
.rc-list-item:hover {
  background-color: var(--app-hover, rgba(10, 93, 194, 0.06));
}
.rc-list-item.active {
  background-color: var(--app-active, rgba(10, 93, 194, 0.12));
  border-color: var(--app-primary, #0a5dc2);
}
.rc-li-header {
  display: flex;
  gap: 4px;
  margin-bottom: 4px;
}
.rc-li-title {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 4px;
  line-height: 1.4;
  word-break: break-word;
}
.rc-li-meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--app-muted, #666);
  margin-bottom: 4px;
}
.rc-li-footer {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--app-muted, #888);
}
.rc-pagination {
  display: flex;
  justify-content: center;
  padding: 8px 0;
}
.card-title {
  font-size: 14px;
  font-weight: 600;
}
.rc-detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}
.rc-detail-titles {
  flex: 1 1 auto;
}
.rc-detail-title {
  margin: 0 0 8px 0;
  font-size: 20px;
  font-weight: 700;
}
.rc-status-flow {
  margin: 16px 0;
}
.rc-section {
  margin-bottom: 12px;
}
.rc-section-title {
  margin: 0 0 6px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-muted, #666);
}
.rc-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
}
.rc-meta-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px 16px;
  padding: 12px;
  background: var(--app-surface-2, #f7f7f7);
  border-radius: 6px;
}
.rc-meta-item {
  display: flex;
  flex-direction: column;
  font-size: 12px;
}
.rc-meta-key {
  color: var(--app-muted, #888);
  font-size: 11px;
}
.rc-meta-val {
  font-weight: 500;
}
.rc-stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
}
.rc-stat-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 4px;
  border-radius: 4px;
  background: var(--app-surface-2, #f7f7f7);
}
.rc-stat-cell.success {
  background: rgba(34, 197, 94, 0.1);
}
.rc-stat-cell.warn {
  background: rgba(245, 158, 11, 0.1);
}
.rc-stat-cell.danger {
  background: rgba(239, 68, 68, 0.1);
}
.rc-stat-val {
  font-size: 18px;
  font-weight: 700;
}
.rc-stat-key {
  font-size: 11px;
  color: var(--app-muted, #888);
}
.rc-task-tree {
  max-height: 240px;
  overflow-y: auto;
}
.rc-task-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  border-bottom: 1px solid var(--app-border, rgba(0, 0, 0, 0.06));
  font-size: 12px;
}
.rc-task-item:last-child {
  border-bottom: none;
}
.rc-task-title {
  flex: 1 1 auto;
  word-break: break-word;
}
.rc-task-meta {
  font-size: 11px;
  color: var(--app-muted, #888);
  display: flex;
  gap: 6px;
}
.rc-assignee-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.rc-assignee-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  padding: 4px 8px;
  background: var(--app-surface-2, #f7f7f7);
  border-radius: 4px;
}
.rc-muted {
  color: var(--app-muted, #888);
  font-size: 12px;
}
.rc-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
.muted {
  color: var(--app-muted, #888);
  font-size: 12px;
}
</style>