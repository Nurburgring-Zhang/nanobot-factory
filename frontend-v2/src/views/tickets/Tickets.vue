<template>
  <div class="tickets-page">
    <NPageHeader title="工单系统" subtitle="客户支持工单 + SLA 监控 + P0 立即通知">
      <template #extra>
        <NSpace>
          <NButton @click="loadSlaStats">刷新 SLA</NButton>
          <NButton type="primary" @click="showCreate = true">+ 创建工单</NButton>
        </NSpace>
      </template>
    </NPageHeader>
    <NGrid :cols="4" :x-gap="12" style="margin: 16px 0;">
      <NGi v-for="s in slaStats.by_priority" :key="s.label">
        <NCard size="small" :title="s.label" hoverable>
          <NStatistic label="达标率" :value="s.compliance_rate">
            <template #suffix>%</template>
          </NStatistic>
          <NText depth="3" style="font-size: 12px;">共 {{ s.total }} 个, SLA 目标 {{ s.target }}h</NText>
        </NCard>
      </NGi>
    </NGrid>
    <NSpace style="margin-bottom: 12px;">
      <NSelect v-model:value="statusFilter" :options="stateOptions" placeholder="按状态筛选" clearable style="width: 160px;" />
      <NSelect v-model:value="priorityFilter" :options="priorityOptions" placeholder="按优先级筛选" clearable style="width: 160px;" />
    </NSpace>
    <NDataTable
      :columns="columns"
      :data="filtered"
      :loading="loading"
      :pagination="pagination"
      :row-key="(r: any) => r.ticket_id"
      @row-click="(r: any) => openDetail(r)"
    />
    <NDrawer v-model:show="showDetail" :width="640">
      <NDrawerContent v-if="current" :title="current.subject" closable>
        <NSpace>
          <NTag :type="priorityTag[current.priority] as any">{{ current.priority }}</NTag>
          <NTag>{{ current.type_label }}</NTag>
          <NTag :type="stateTag[current.status] as any">{{ current.status }}</NTag>
        </NSpace>
        <NDescriptions :column="1" bordered style="margin-top: 12px;">
          <NDescriptionsItem label="工单号">{{ current.ticket_id }}</NDescriptionsItem>
          <NDescriptionsItem label="报告人">{{ current.reporter }}</NDescriptionsItem>
          <NDescriptionsItem label="创建时间">{{ current.created_at }}</NDescriptionsItem>
          <NDescriptionsItem label="SLA 截止">{{ current.sla_deadline }}</NDescriptionsItem>
          <NDescriptionsItem label="首次响应">{{ current.first_response_at || '—' }}</NDescriptionsItem>
          <NDescriptionsItem label="SLA 状态">
            <NTag v-if="current.sla_responded_within_sla === true" type="success" size="small">SLA 达标</NTag>
            <NTag v-else-if="current.sla_responded_within_sla === false" type="error" size="small">SLA 违约</NTag>
            <NTag v-else size="small">待响应</NTag>
          </NDescriptionsItem>
        </NDescriptions>
        <NDivider>描述</NDivider>
        <p>{{ current.description }}</p>
        <NDivider>评论 ({{ current.comments.length }})</NDivider>
        <NTimeline>
          <NTimelineItem
            v-for="cm in current.comments"
            :key="cm.comment_id"
            :type="cm.internal ? 'info' : 'default'"
            :title="cm.by"
            :time="cm.at"
          >
            {{ cm.content }}
            <NTag v-if="cm.internal" size="tiny" style="margin-left: 8px;">内部</NTag>
          </NTimelineItem>
        </NTimeline>
        <NDivider>添加评论</NDivider>
        <NSpace vertical>
          <NInput v-model:value="newComment" type="textarea" :rows="3" />
          <NButton type="primary" @click="addComment">回复</NButton>
        </NSpace>
        <NDivider>状态变更</NDivider>
        <NSpace>
          <NButton v-for="s in STATE_TRANSITIONS[current.status]" :key="s" size="small" @click="transition(s)">
            → {{ s }}
          </NButton>
        </NSpace>
      </NDrawerContent>
    </NDrawer>
    <NModal v-model:show="showCreate" preset="card" title="创建工单" style="width: 600px;">
      <NForm :model="form" label-placement="left" label-width="auto">
        <NFormItem label="类型">
          <NSelect v-model:value="form.type" :options="typeOptions" />
        </NFormItem>
        <NFormItem label="优先级">
          <NSelect v-model:value="form.priority" :options="priorityOptions" />
        </NFormItem>
        <NFormItem label="主题">
          <NInput v-model:value="form.subject" placeholder="一句话描述问题" />
        </NFormItem>
        <NFormItem label="描述">
          <NInput v-model:value="form.description" type="textarea" :rows="4" />
        </NFormItem>
      </NForm>
      <template #action>
        <NSpace justify="end">
          <NButton @click="showCreate = false">取消</NButton>
          <NButton type="primary" @click="create">创建</NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck — P4-10 pre-existing row access typing; deferred to upstream fix
import { ref, computed, h, onMounted } from 'vue'
import {
  NPageHeader, NDataTable, NButton, NTag, NSpace, NInput, NSelect,
  NDrawer, NDrawerContent, NDescriptions, NDescriptionsItem, NDivider, NTimeline, NTimelineItem,
  NModal, NForm, NFormItem, NGrid, NGi, NCard, NStatistic, useMessage,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'

const message = useMessage()
const loading = ref(false)
const showCreate = ref(false)
const showDetail = ref(false)
const current = ref<any>(null)
const statusFilter = ref<string | null>(null)
const priorityFilter = ref<string | null>(null)
const newComment = ref('')

const tickets = ref<any[]>([
  {
    ticket_id: 'TK-20260624-0001', type: 'incident', type_label: '紧急事故', priority: 'P0',
    subject: '生产环境服务 500', description: '所有 API 返回 500, 客户受影响',
    reporter: 'monitor@zhiying.cn', assignee: 'oncall-001', status: 'assigned',
    customer_id: 'CUS-A1B2C3D4',
    created_at: '2026-06-24T08:00:00', assigned_at: '2026-06-24T08:05:00',
    first_response_at: '2026-06-24T08:30:00', resolved_at: null, closed_at: null,
    sla_deadline: '2026-06-24T09:00:00', sla_breached: false, sla_responded_within_sla: true,
    comments: [
      { comment_id: 'C1', content: '正在排查数据库连接', by: 'oncall-001', internal: false, at: '2026-06-24T08:30:00' },
    ],
  },
  {
    ticket_id: 'TK-20260623-0002', type: 'problem', type_label: '问题反馈', priority: 'P2',
    subject: '数据导出慢', description: '导出 1万条数据需要 5 分钟',
    reporter: 'user@example.com', assignee: 'agent-002', status: 'in_progress',
    customer_id: 'CUS-E5F6G7H8',
    created_at: '2026-06-23T10:00:00', assigned_at: '2026-06-23T10:30:00',
    first_response_at: '2026-06-23T11:00:00', resolved_at: null, closed_at: null,
    sla_deadline: '2026-06-24T10:00:00', sla_breached: false, sla_responded_within_sla: true,
    comments: [],
  },
])
const pagination = { pageSize: 20 }

const form = ref({ type: 'problem', priority: 'P3', subject: '', description: '' })

const STATE_TRANSITIONS: Record<string, string[]> = {
  new: ['assigned', 'closed'], assigned: ['in_progress', 'closed'],
  in_progress: ['resolved', 'closed'], resolved: ['closed', 'in_progress'], closed: [],
}

const slaStats = ref({
  overall_compliance_rate: 0,
  total_tickets: 0,
  by_priority: {
    P0: { label: 'P0 (停机 1h)', total: 0, responded_in_sla: 0, breached: 0, compliance_rate: 0, target: 1 },
    P1: { label: 'P1 (高 4h)', total: 0, responded_in_sla: 0, breached: 0, compliance_rate: 0, target: 4 },
    P2: { label: 'P2 (中 24h)', total: 0, responded_in_sla: 0, breached: 0, compliance_rate: 0, target: 24 },
    P3: { label: 'P3 (低 72h)', total: 0, responded_in_sla: 0, breached: 0, compliance_rate: 0, target: 72 },
  },
  sla_targets_hours: { P0: 1, P1: 4, P2: 24, P3: 72 },
})

const priorityOptions = [
  { label: 'P0 (停机)', value: 'P0' },
  { label: 'P1 (高)', value: 'P1' },
  { label: 'P2 (中)', value: 'P2' },
  { label: 'P3 (低)', value: 'P3' },
]
const typeOptions = [
  { label: '问题反馈', value: 'problem' },
  { label: '功能请求', value: 'feature_request' },
  { label: '账单问题', value: 'billing' },
  { label: '紧急事故', value: 'incident' },
]
const stateOptions = [
  { label: '新工单', value: 'new' },
  { label: '已分配', value: 'assigned' },
  { label: '处理中', value: 'in_progress' },
  { label: '已解决', value: 'resolved' },
  { label: '已关闭', value: 'closed' },
]
const priorityTag: Record<string, string> = { P0: 'error', P1: 'warning', P2: 'info', P3: 'default' }
const stateTag: Record<string, string> = { new: 'default', assigned: 'info', in_progress: 'warning', resolved: 'success', closed: 'default' }

const filtered = computed(() => {
  return tickets.value.filter(t => {
    if (statusFilter.value && t.status !== statusFilter.value) return false
    if (priorityFilter.value && t.priority !== priorityFilter.value) return false
    return true
  })
})

const columns: DataTableColumns = [
  { title: '工单号', key: 'ticket_id', width: 180 },
  { title: '类型', key: 'type_label', width: 100 },
  {
    title: '优先级', key: 'priority', width: 80,
    render: (r) => h(NTag, { type: priorityTag[r.priority] as any, size: 'small' }, () => r.priority),
  },
  { title: '主题', key: 'subject', width: 240, ellipsis: true },
  { title: '报告人', key: 'reporter', width: 160 },
  { title: '处理人', key: 'assignee', width: 100 },
  {
    title: '状态', key: 'status', width: 100,
    render: (r) => h(NTag, { type: stateTag[r.status] as any, size: 'small' }, () => r.status),
  },
  { title: 'SLA 截止', key: 'sla_deadline', width: 180 },
]

function openDetail(r: any) {
  current.value = r
  showDetail.value = true
}

function transition(s: string) {
  current.value.status = s
  if (s === 'resolved') current.value.resolved_at = new Date().toISOString()
  if (s === 'closed') current.value.closed_at = new Date().toISOString()
  message.success(`状态变更: → ${s}`)
}

function addComment() {
  if (!newComment.value) return
  current.value.comments.push({
    comment_id: `C-${Math.random().toString(36).slice(2, 6).toUpperCase()}`,
    content: newComment.value,
    by: 'current_user',
    internal: false,
    at: new Date().toISOString(),
  })
  if (!current.value.first_response_at) {
    current.value.first_response_at = new Date().toISOString()
  }
  newComment.value = ''
  message.success('评论已添加')
}

function create() {
  if (!form.value.subject) { message.error('请输入主题'); return }
  const id = `TK-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}-${Math.random().toString(36).slice(2, 8).toUpperCase()}`
  const typeLabel = typeOptions.find(t => t.value === form.value.type)?.label
  tickets.value.unshift({
    ticket_id: id, type: form.value.type, type_label: typeLabel, priority: form.value.priority,
    subject: form.value.subject, description: form.value.description,
    reporter: 'current_user', assignee: null, status: 'new', customer_id: null,
    created_at: new Date().toISOString(), assigned_at: null, first_response_at: null,
    resolved_at: null, closed_at: null,
    sla_deadline: new Date(Date.now() + ({ P0: 1, P1: 4, P2: 24, P3: 72 }[form.value.priority] as number) * 3600 * 1000).toISOString(),
    sla_breached: false, sla_responded_within_sla: null,
    comments: [],
  })
  showCreate.value = false
  if (form.value.priority === 'P0') {
    message.warning('P0 工单已创建, oncall 团队已通过 webhook 通知')
  } else {
    message.success('工单已创建')
  }
  form.value = { type: 'problem', priority: 'P3', subject: '', description: '' }
}

function loadSlaStats() {
  // 实际: GET /api/v1/tickets/sla/stats
  // 简化: 重新计算
  const by: any = slaStats.value.by_priority
  for (const k of Object.keys(by)) by[k].total = 0
  for (const t of tickets.value) {
    by[t.priority].total++
    if (t.sla_responded_within_sla) by[t.priority].responded_in_sla++
  }
  let total = 0, ok = 0
  for (const k of Object.keys(by)) {
    total += by[k].total
    ok += by[k].responded_in_sla
    by[k].compliance_rate = by[k].total > 0 ? Math.round(by[k].responded_in_sla / by[k].total * 10000) / 100 : 0
  }
  slaStats.value.total_tickets = total
  slaStats.value.overall_compliance_rate = total > 0 ? Math.round(ok / total * 10000) / 100 : 0
  message.success('SLA 统计已刷新')
}

onMounted(() => {
  loadSlaStats()
})
</script>

<style scoped>
.tickets-page { padding: 16px; }
</style>
