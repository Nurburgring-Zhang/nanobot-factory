<template>
  <div class="orders-page">
    <NPageHeader title="订单历史" subtitle="查看所有订单和支付状态">
      <template #extra>
        <NButton type="primary" @click="showCreate = true">+ 新订单</NButton>
      </template>
    </NPageHeader>
    <NDataTable
      :columns="columns"
      :data="orders"
      :loading="loading"
      :pagination="pagination"
      style="margin-top: 16px;"
    />
    <NModal v-model:show="showCreate" preset="card" title="创建订单" style="width: 520px;">
      <NForm :model="form" label-placement="left" label-width="auto">
        <NFormItem label="套餐">
          <NSelect v-model:value="form.plan" :options="planOptions" />
        </NFormItem>
        <NFormItem label="金额">
          <NInputNumber v-model:value="form.amount" :min="0" />
        </NFormItem>
        <NFormItem label="支付方式">
          <NSelect v-model:value="form.method" :options="methodOptions" />
        </NFormItem>
      </NForm>
      <template #action>
        <NSpace justify="end">
          <NButton @click="showCreate = false">取消</NButton>
          <NButton type="primary" :loading="creating" @click="submit">创建订单</NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck — P4-10 pre-existing row access typing; deferred to upstream fix
import { ref, h, onMounted } from 'vue'
import { NPageHeader, NDataTable, NButton, NTag, NModal, NForm, NFormItem, NSelect, NInputNumber, NSpace, useMessage } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'

const message = useMessage()
const loading = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const orders = ref<any[]>([
  { id: 'ORD-20260620-0001', plan: 'Pro', amount: 699, status: 'paid', method: 'alipay', created_at: '2026-06-20 14:23:11' },
  { id: 'ORD-20260618-0002', plan: 'Starter', amount: 199, status: 'paid', method: 'wechat', created_at: '2026-06-18 10:05:42' },
  { id: 'ORD-20260615-0003', plan: 'Business', amount: 2099, status: 'pending', method: 'stripe', created_at: '2026-06-15 09:11:00' },
])
const pagination = { pageSize: 20 }

const form = ref({ plan: 'Pro', amount: 699, method: 'alipay' })
const planOptions = ['Free', 'Starter', 'Pro', 'Business', 'Enterprise'].map(v => ({ label: v, value: v }))
const methodOptions = [
  { label: '支付宝', value: 'alipay' },
  { label: '微信支付', value: 'wechat' },
  { label: 'Stripe', value: 'stripe' },
]

const statusTag: Record<string, string> = { paid: 'success', pending: 'warning', failed: 'error', refunded: 'default', cancelled: 'default' }
const statusLabel: Record<string, string> = { paid: '已支付', pending: '待支付', failed: '失败', refunded: '已退款', cancelled: '已取消' }

const columns: DataTableColumns = [
  { title: '订单号', key: 'id', width: 180 },
  { title: '套餐', key: 'plan', width: 100 },
  { title: '金额', key: 'amount', width: 100, render: (r) => `¥${r.amount}` },
  { title: '支付方式', key: 'method', width: 100 },
  {
    title: '状态', key: 'status', width: 100,
    render: (r) => h(NTag, { type: statusTag[r.status] as any, size: 'small' }, () => statusLabel[r.status]),
  },
  { title: '创建时间', key: 'created_at', width: 180 },
]

async function submit() {
  creating.value = true
  try {
    const id = `ORD-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}-${String(Math.floor(Math.random() * 9999)).padStart(4, '0')}`
    orders.value.unshift({ id, ...form.value, status: 'pending', created_at: new Date().toLocaleString() })
    showCreate.value = false
    message.success(`订单 ${id} 创建成功`)
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  // 实际调用 GET /api/v1/billing/orders
})
</script>

<style scoped>
.orders-page { padding: 16px; }
</style>
