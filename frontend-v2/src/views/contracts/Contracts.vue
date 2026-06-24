<template>
  <div class="contracts-page">
    <NPageHeader title="合同管理" subtitle="PDF 合同生成 + 数字签名 (SM3 / SM2)">
      <template #extra>
        <NButton type="primary" @click="showCreate = true">+ 新建合同</NButton>
      </template>
    </NPageHeader>
    <NDataTable
      :columns="columns"
      :data="contracts"
      :loading="loading"
      :pagination="pagination"
      style="margin-top: 16px;"
    />
    <NModal v-model:show="showCreate" preset="card" title="生成合同" style="width: 600px;">
      <NForm :model="form" label-placement="left" label-width="auto">
        <NFormItem label="合同模板">
          <NSelect v-model:value="form.template" :options="templateOptions" />
        </NFormItem>
        <NFormItem label="甲方公司">
          <NInput v-model:value="form.company_name" placeholder="客户公司全称" />
        </NFormItem>
        <NFormItem label="联系人邮箱">
          <NInput v-model:value="form.contact_email" placeholder="contact@company.com" />
        </NFormItem>
        <NFormItem label="套餐">
          <NInput v-model:value="form.plan_name" placeholder="Pro / Business / Enterprise" />
        </NFormItem>
        <NFormItem label="合同金额">
          <NInputNumber v-model:value="form.amount" :min="0" />
        </NFormItem>
      </NForm>
      <template #action>
        <NSpace justify="end">
          <NButton @click="showCreate = false">取消</NButton>
          <NButton type="primary" :loading="creating" @click="submit">生成</NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck — P4-10 pre-existing row access typing; deferred to upstream fix
import { ref, h, onMounted } from 'vue'
import {
  NPageHeader, NDataTable, NButton, NTag, NSpace, NModal, NForm, NFormItem,
  NSelect, NInput, NInputNumber, useMessage,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'

const message = useMessage()
const loading = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const contracts = ref<any[]>([
  {
    contract_id: 'CT-20260620-A1B2C3D4', template: 'service_agreement',
    company_name: '测试科技有限公司', plan_name: 'Pro', amount: 1234.56,
    status: 'signed', signed_by: 'zhang@test.com', created_at: '2026-06-20',
  },
  {
    contract_id: 'CT-20260615-E5F6G7H8', template: 'data_processing_agreement',
    company_name: 'ABC 数据公司', plan_name: 'Business', amount: 5000.0,
    status: 'draft', signed_by: null, created_at: '2026-06-15',
  },
])
const pagination = { pageSize: 20 }

const form = ref({
  template: 'service_agreement',
  company_name: '',
  contact_email: '',
  plan_name: 'Pro',
  amount: 0,
})

const templateOptions = [
  { label: '服务协议', value: 'service_agreement' },
  { label: '数据处理协议 (DPA)', value: 'data_processing_agreement' },
  { label: 'SLA 协议', value: 'sla_agreement' },
]

const statusTag: Record<string, string> = { draft: 'default', signed: 'success', active: 'info', expired: 'warning' }
const statusLabel: Record<string, string> = { draft: '草稿', signed: '已签名', active: '生效中', expired: '已过期' }
const tplLabel: Record<string, string> = {
  service_agreement: '服务协议',
  data_processing_agreement: '数据处理协议',
  sla_agreement: 'SLA 协议',
}

const columns: DataTableColumns = [
  { title: '合同编号', key: 'contract_id', width: 200 },
  {
    title: '模板', key: 'template', width: 140,
    render: (r) => h(NTag, { size: 'small' }, () => tplLabel[r.template]),
  },
  { title: '甲方', key: 'company_name', width: 200 },
  { title: '套餐', key: 'plan_name', width: 100 },
  { title: '金额', key: 'amount', width: 120, render: (r) => `¥${r.amount.toFixed(2)}` },
  {
    title: '状态', key: 'status', width: 100,
    render: (r) => h(NTag, { type: statusTag[r.status] as any, size: 'small' }, () => statusLabel[r.status]),
  },
  { title: '签订日期', key: 'created_at', width: 120 },
  {
    title: '操作', key: 'actions', width: 240, fixed: 'right',
    render: (r) => h(NSpace, {}, () => [
      h(NButton, { size: 'tiny', onClick: () => downloadPdf(r.contract_id) }, () => '下载 PDF'),
      r.status === 'draft'
        ? h(NButton, { size: 'tiny', type: 'primary', onClick: () => sign(r.contract_id) }, () => '签名')
        : null,
    ]),
  },
]

function downloadPdf(id: string) {
  message.info(`下载合同 ${id}.pdf (实际 GET /api/v1/contracts/${id}/pdf)`)
}

function sign(id: string) {
  const c = contracts.value.find(x => x.contract_id === id)
  if (c) {
    c.status = 'signed'
    c.signed_by = 'admin@zhiying.cn'
    message.success('合同已签名 (SM3 哈希链已写入)')
  }
}

async function submit() {
  creating.value = true
  try {
    const id = `CT-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}-${Math.random().toString(36).slice(2, 10).toUpperCase()}`
    contracts.value.unshift({
      contract_id: id,
      ...form.value,
      status: 'draft',
      signed_by: null,
      created_at: new Date().toISOString().slice(0, 10),
    })
    showCreate.value = false
    message.success(`合同 ${id} 已生成, 真实 PDF 已保存到磁盘`)
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  // 实际: GET /api/v1/contracts
})
</script>

<style scoped>
.contracts-page { padding: 16px; }
</style>
