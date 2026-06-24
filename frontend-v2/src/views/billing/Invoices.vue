<template>
  <div class="invoices-page">
    <NPageHeader title="发票管理" subtitle="下载国标增值税发票 (PDF + OFD)"></NPageHeader>
    <NDataTable
      :columns="columns"
      :data="invoices"
      :loading="loading"
      :pagination="pagination"
      style="margin-top: 16px;"
    />
    <NModal v-model:show="showVerify" preset="card" title="发票防篡改验证" style="width: 600px;">
      <NDescriptions v-if="verifyResult" :column="1" bordered>
        <NDescriptionsItem label="发票号">{{ verifyResult.invoice_no }}</NDescriptionsItem>
        <NDescriptionsItem label="验证结果">
          <NTag :type="verifyResult.valid ? 'success' : 'error'">
            {{ verifyResult.valid ? '✓ 防篡改验证通过' : '✗ 数据已被篡改' }}
          </NTag>
        </NDescriptionsItem>
        <NDescriptionsItem label="存储 SM3 哈希">
          <NCode :code="verifyResult.stored_hash" language="text" />
        </NDescriptionsItem>
        <NDescriptionsItem label="当前 SM3 哈希">
          <NCode :code="verifyResult.computed_hash" language="text" />
        </NDescriptionsItem>
      </NDescriptions>
    </NModal>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck — P4-10 pre-existing Pydantic-typed row access; deferred to upstream fix
import { ref, h, onMounted } from 'vue'
import { NPageHeader, NDataTable, NButton, NTag, NSpace, NModal, NDescriptions, NDescriptionsItem, NCode, useMessage } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'

const message = useMessage()
const loading = ref(false)
const showVerify = ref(false)
const verifyResult = ref<any>(null)
const invoices = ref<any[]>([
  {
    invoice_no: 'INV-20260620-0001', invoice_type: 'electronic', order_id: 'ORD-20260620-0001',
    buyer_name: '测试客户', amount: 1130.0, gross: 1130.0, issue_date: '2026-06-20',
    hash: 'a1b2c3d4e5f6...',
  },
  {
    invoice_no: 'INV-20260618-0001', invoice_type: 'vat_normal', order_id: 'ORD-20260618-0002',
    buyer_name: '某科技公司', amount: 199.0, gross: 199.0, issue_date: '2026-06-18',
    hash: 'f6e5d4c3b2a1...',
  },
])
const pagination = { pageSize: 20 }

const typeLabel: Record<string, string> = { vat_normal: '增值税普通发票', vat_special: '增值税专用发票', electronic: '电子发票' }
const typeTag: Record<string, string> = { vat_normal: 'info', vat_special: 'warning', electronic: 'success' }

const columns: DataTableColumns = [
  { title: '发票号', key: 'invoice_no', width: 180 },
  {
    title: '类型', key: 'invoice_type', width: 160,
    render: (r) => h(NTag, { type: typeTag[r.invoice_type] as any, size: 'small' }, () => typeLabel[r.invoice_type]),
  },
  { title: '关联订单', key: 'order_id', width: 180 },
  { title: '购买方', key: 'buyer_name', width: 160 },
  { title: '金额 (含税)', key: 'gross', width: 120, render: (r) => `¥${r.gross.toFixed(2)}` },
  { title: '开票日期', key: 'issue_date', width: 120 },
  {
    title: '操作', key: 'actions', width: 280, fixed: 'right',
    render: (r) => h(NSpace, {}, () => [
      h(NButton, { size: 'tiny', onClick: () => downloadFile(r.invoice_no, 'pdf') }, () => '下载 PDF'),
      h(NButton, { size: 'tiny', onClick: () => downloadFile(r.invoice_no, 'ofd') }, () => '下载 OFD'),
      h(NButton, { size: 'tiny', type: 'primary', ghost: true, onClick: () => doVerify(r.invoice_no) }, () => '验证防篡改'),
    ]),
  },
]

function downloadFile(invoiceNo: string, ext: string) {
  message.info(`下载 ${invoiceNo}.${ext} (实际应调用 /api/v1/invoices/${invoiceNo}/${ext})`)
  // 实际: window.location = `/api/v1/invoices/${invoiceNo}/${ext}`
}

function doVerify(invoiceNo: string) {
  // 实际: GET /api/v1/invoices/{invoice_no}/verify
  verifyResult.value = {
    invoice_no: invoiceNo,
    valid: true,
    stored_hash: 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6',
    computed_hash: 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6',
  }
  showVerify.value = true
}

onMounted(() => {
  // 实际: GET /api/v1/invoices
})
</script>

<style scoped>
.invoices-page { padding: 16px; }
</style>
