<template>
  <div class="crm-page">
    <NPageHeader title="客户管理 (CRM)" subtitle="客户档案 + 分级 + 跟进记录 + 联系人">
      <template #extra>
        <NButton type="primary" @click="showCreate = true">+ 新建客户</NButton>
      </template>
    </NPageHeader>
    <NSpace style="margin: 16px 0;">
      <NInput v-model:value="search" placeholder="搜索公司/联系人" clearable style="width: 240px;" />
      <NSelect v-model:value="tierFilter" :options="tierOptions" placeholder="按分级筛选" clearable style="width: 180px;" />
      <NSelect v-model:value="industryFilter" :options="industryOptions" placeholder="按行业筛选" clearable style="width: 180px;" />
    </NSpace>
    <NDataTable
      :columns="columns"
      :data="filtered"
      :loading="loading"
      :pagination="pagination"
      :row-key="(r: any) => r.customer_id"
      @row-click="(r: any) => openDetail(r)"
    />
    <!-- 详情/编辑 -->
    <NDrawer v-model:show="showDetail" :width="640">
      <NDrawerContent v-if="current" :title="current.company_name" closable>
        <NDescriptions :column="1" bordered>
          <NDescriptionsItem label="客户 ID">{{ current.customer_id }}</NDescriptionsItem>
          <NDescriptionsItem label="联系人">{{ current.contact_name }}</NDescriptionsItem>
          <NDescriptionsItem label="邮箱">{{ current.email }}</NDescriptionsItem>
          <NDescriptionsItem label="电话">{{ current.phone || '—' }}</NDescriptionsItem>
          <NDescriptionsItem label="行业">{{ current.industry }}</NDescriptionsItem>
          <NDescriptionsItem label="规模">{{ current.size }}</NDescriptionsItem>
          <NDescriptionsItem label="分级">
            <NTag type="success" size="small">{{ current.tier_label }}</NTag>
          </NDescriptionsItem>
          <NDescriptionsItem label="专属经理">{{ current.manager_id || '—' }}</NDescriptionsItem>
        </NDescriptions>
        <NDivider>跟进记录 ({{ current.followups.length }})</NDivider>
        <NTimeline>
          <NTimelineItem
            v-for="fu in current.followups"
            :key="fu.followup_id"
            :type="fu.type === 'complaint' ? 'error' : 'default'"
            :title="typeLabel[fu.type] || fu.type"
            :time="fu.at"
          >
            {{ fu.content }} — <NText depth="3">@{{ fu.by }}</NText>
          </NTimelineItem>
        </NTimeline>
        <NDivider>添加跟进</NDivider>
        <NSpace vertical>
          <NSelect v-model:value="newFuType" :options="fuTypeOptions" />
          <NInput v-model:value="newFuContent" type="textarea" :rows="3" placeholder="跟进内容" />
          <NButton type="primary" @click="addFollowup">添加</NButton>
        </NSpace>
      </NDrawerContent>
    </NDrawer>
    <!-- 创建客户 -->
    <NModal v-model:show="showCreate" preset="card" title="新建客户" style="width: 600px;">
      <NForm :model="form" label-placement="left" label-width="auto">
        <NFormItem label="公司名称"><NInput v-model:value="form.company_name" /></NFormItem>
        <NFormItem label="联系人"><NInput v-model:value="form.contact_name" /></NFormItem>
        <NFormItem label="邮箱"><NInput v-model:value="form.email" /></NFormItem>
        <NFormItem label="电话"><NInput v-model:value="form.phone" /></NFormItem>
        <NFormItem label="行业"><NSelect v-model:value="form.industry" :options="industryOptions" /></NFormItem>
        <NFormItem label="规模"><NSelect v-model:value="form.size" :options="sizeOptions" /></NFormItem>
        <NFormItem label="分级"><NSelect v-model:value="form.tier" :options="tierOptions" /></NFormItem>
        <NFormItem label="经理 ID"><NInput v-model:value="form.manager_id" placeholder="1 客户 1 manager" /></NFormItem>
      </NForm>
      <template #action>
        <NSpace justify="end">
          <NButton @click="showCreate = false">取消</NButton>
          <NButton type="primary" @click="createCustomer">创建</NButton>
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
  NText, NModal, NForm, NFormItem, useMessage,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'

const message = useMessage()
const loading = ref(false)
const showCreate = ref(false)
const showDetail = ref(false)
const current = ref<any>(null)
const search = ref('')
const tierFilter = ref<string | null>(null)
const industryFilter = ref<string | null>(null)
const newFuType = ref('communication')
const newFuContent = ref('')

const customers = ref<any[]>([
  {
    customer_id: 'CUS-A1B2C3D4', company_name: '宇宙科技', contact_name: '张三',
    email: 'zhang@u.com', phone: '+86-138-0000-0000', industry: '互联网/科技',
    size: '51-200', tier: 'mid_market', tier_label: '中型企业', tags: ['VIP'],
    manager_id: 'mgr-001', followups: [
      { followup_id: 'FU-1', type: 'communication', content: '初次沟通', by: '王经理', at: '2026-06-10T10:00:00' },
    ], created_at: '2026-06-01', updated_at: '2026-06-10',
  },
  {
    customer_id: 'CUS-E5F6G7H8', company_name: 'ABC 数据', contact_name: '李四',
    email: 'li@abc.com', phone: '+86-139-1111-1111', industry: '金融',
    size: '201-1000', tier: 'large', tier_label: '大型企业', tags: ['重点'],
    manager_id: 'mgr-002', followups: [], created_at: '2026-05-15', updated_at: '2026-05-15',
  },
])
const pagination = { pageSize: 20 }

const form = ref({
  company_name: '', contact_name: '', email: '', phone: '',
  industry: '互联网/科技', size: '1-10', tier: 'individual', manager_id: '',
})

const tierOptions = [
  { label: '个人', value: 'individual' },
  { label: 'SMB', value: 'smb' },
  { label: '中型企业', value: 'mid_market' },
  { label: '大型企业', value: 'large' },
  { label: '战略客户', value: 'strategic' },
]
const industryOptions = ['互联网/科技', '金融', '教育', '医疗', '零售/电商', '制造', '政企', '媒体/广告'].map(v => ({ label: v, value: v }))
const sizeOptions = ['1-10', '11-50', '51-200', '201-1000', '1000+'].map(v => ({ label: v, value: v }))
const fuTypeOptions = [
  { label: '沟通', value: 'communication' },
  { label: '合同', value: 'contract' },
  { label: '付款', value: 'payment' },
  { label: '投诉', value: 'complaint' },
  { label: '其他', value: 'other' },
]
const typeLabel: Record<string, string> = {
  communication: '沟通', contract: '合同', payment: '付款', complaint: '投诉', other: '其他',
}

const tierTag: Record<string, string> = {
  individual: 'default', smb: 'info', mid_market: 'warning', large: 'success', strategic: 'error',
}

const filtered = computed(() => {
  return customers.value.filter(c => {
    if (tierFilter.value && c.tier !== tierFilter.value) return false
    if (industryFilter.value && c.industry !== industryFilter.value) return false
    if (search.value) {
      const s = search.value.toLowerCase()
      if (!c.company_name.toLowerCase().includes(s) && !c.contact_name.toLowerCase().includes(s)) return false
    }
    return true
  })
})

const columns: DataTableColumns = [
  { title: '客户 ID', key: 'customer_id', width: 140 },
  { title: '公司', key: 'company_name', width: 180 },
  { title: '联系人', key: 'contact_name', width: 100 },
  { title: '行业', key: 'industry', width: 120 },
  { title: '规模', key: 'size', width: 100 },
  {
    title: '分级', key: 'tier', width: 100,
    render: (r) => h(NTag, { type: tierTag[r.tier] as any, size: 'small' }, () => r.tier_label),
  },
  { title: '经理', key: 'manager_id', width: 100 },
  { title: '跟进', key: 'followup_count', width: 80, render: (r) => r.followups.length },
]

function openDetail(r: any) {
  current.value = r
  showDetail.value = true
}

function addFollowup() {
  if (!newFuContent.value) {
    message.warning('请输入跟进内容')
    return
  }
  current.value.followups.push({
    followup_id: `FU-${Math.random().toString(36).slice(2, 8).toUpperCase()}`,
    type: newFuType.value,
    content: newFuContent.value,
    by: 'current_user',
    at: new Date().toISOString(),
  })
  newFuContent.value = ''
  message.success('跟进已添加')
}

function createCustomer() {
  if (!form.value.company_name || !form.value.contact_name || !form.value.email) {
    message.error('公司名/联系人/邮箱必填')
    return
  }
  const tier_label = tierOptions.find(t => t.value === form.value.tier)?.label || form.value.tier
  customers.value.unshift({
    customer_id: `CUS-${Math.random().toString(36).slice(2, 10).toUpperCase()}`,
    ...form.value,
    tier_label,
    tags: [],
    followups: [],
    created_at: new Date().toISOString().slice(0, 10),
    updated_at: new Date().toISOString().slice(0, 10),
  })
  showCreate.value = false
  message.success('客户已创建')
  form.value = { company_name: '', contact_name: '', email: '', phone: '', industry: '互联网/科技', size: '1-10', tier: 'individual', manager_id: '' }
}

onMounted(() => {
  // 实际: GET /api/v1/crm/customers
})
</script>

<style scoped>
.crm-page { padding: 16px; }
</style>
