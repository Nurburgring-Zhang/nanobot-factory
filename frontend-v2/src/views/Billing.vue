<template>
  <div class="billing-view" role="region" :aria-label="t('billing.pageTitle')">
    <h2 class="sr-only">{{ t('billing.pageTitle') }}</h2>
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">{{ t('billing.pageTitle') }}</NText>
          <NText depth="3" style="margin-left: 8px">
            {{ t('billing.pageSubtitle') }}
          </NText>
        </div>
        <NSpace>
          <NTag :type="currentPlanBadge" :bordered="false" size="large">
            {{ currentPlan?.plan_name || t('billing.notSubscribed') }}
          </NTag>
          <ActionButton type="primary" :loading="loading" @click="load">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ t('billing.refresh') }}
          </ActionButton>
          <ActionButton type="warning" @click="goPricing">
            <template #icon><NIcon><CardOutline /></NIcon></template>
            {{ t('billing.upgrade') }}
          </ActionButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NAlert v-if="error" type="error" :show-icon="true" closable style="margin-bottom: 12px" @close="error = null">
      {{ error }}
    </NAlert>

    <!-- KPI tiles: usage overview -->
    <NGrid :cols="4" :x-gap="12" :y-gap="12" style="margin-bottom: 12px">
      <NGi v-for="k in kpis" :key="k.key">
        <NCard :bordered="false" size="small" class="kpi-card" :aria-label="k.label">
          <NText depth="3" style="font-size: 11px">{{ k.label }}</NText>
          <div class="kpi-value">
            <NText strong style="font-size: 22px">{{ k.value }}</NText>
            <NText depth="3" style="font-size: 12px; margin-left: 4px">{{ k.unit }}</NText>
          </div>
          <NText depth="3" style="font-size: 11px">{{ k.hint }}</NText>
        </NCard>
      </NGi>
    </NGrid>

    <div class="billing-grid">
      <!-- Plans column -->
      <NCard :title="t('billing.plans')" :bordered="false">
        <NSpin :show="plansLoading">
          <div v-if="plans.length === 0 && !plansLoading" class="empty-wrap">
            <NEmpty :description="t('billing.emptyPlans')" />
          </div>
          <div v-else class="plan-list">
            <div
              v-for="p in plans"
              :key="p.id"
              :class="['plan-row', { active: p.id === currentPlanId }]"
              :aria-label="`${p.name} ${p.price_monthly}`"
            >
              <div class="plan-head">
                <div>
                  <NText strong style="font-size: 14px">{{ p.name }}</NText>
                  <NTag v-if="p.recommended" type="success" size="tiny" style="margin-left: 6px">{{ t('billing.recommended') }}</NTag>
                  <NText depth="3" style="font-size: 11px; display: block">
                    {{ p.tier }} · {{ p.description || '—' }}
                  </NText>
                </div>
                <div class="plan-price">
                  <NText strong style="font-size: 22px">¥{{ p.price_monthly }}</NText>
                  <NText depth="3" style="font-size: 12px">{{ t('billing.perMonth') }}</NText>
                </div>
              </div>
              <div class="plan-features">
                <NTag v-for="(f, i) in p.features?.slice(0, 4)" :key="i" size="tiny" :bordered="false">
                  {{ f }}
                </NTag>
                <NText v-if="(p.features?.length ?? 0) > 4" depth="3" style="font-size: 11px">
                  {{ t('billing.moreFeatures', { n: p.features!.length - 4 }) }}
                </NText>
              </div>
              <div class="plan-actions">
                <NButton
                  size="small"
                  :type="p.id === currentPlanId ? 'default' : 'primary'"
                  :disabled="p.id === currentPlanId"
                  :loading="upgrading && upgradingTo === p.id"
                  @click="onUpgrade(p)"
                >
                  {{ p.id === currentPlanId ? t('billing.currentPlan') : t('billing.switchTo') }}
                </NButton>
                <NButton size="small" tertiary @click="goPricing">{{ t('billing.viewDetail') }}</NButton>
              </div>
            </div>
          </div>
        </NSpin>
      </NCard>

      <!-- Usage column -->
      <NCard :title="t('billing.usageTitle')" :bordered="false">
        <NSpin :show="usageLoading">
          <div v-if="usageBuckets.length === 0 && !usageLoading" class="empty-wrap">
            <NEmpty :description="t('billing.emptyUsage')" />
          </div>
          <div v-else class="usage-list">
            <div v-for="b in usageBuckets" :key="b.key" class="usage-row">
              <div class="usage-head">
                <NText strong style="font-size: 13px">{{ b.label }}</NText>
                <NText depth="3" style="font-size: 11px">
                  {{ formatNum(b.used) }} / {{ formatNum(b.quota) }} {{ b.unit }}
                </NText>
              </div>
              <NProgress
                type="line"
                :percentage="Math.min(100, (b.used / Math.max(1, b.quota)) * 100)"
                :status="usageStatus(b)"
                :height="6"
                :show-indicator="false"
              />
              <NText depth="3" style="font-size: 10px">花费 ¥{{ b.cost.toFixed(2) }}</NText>
            </div>
          </div>
        </NSpin>
      </NCard>
    </div>

    <!-- Quick entries -->
    <NCard :title="t('billing.entriesTitle')" :bordered="false" style="margin-top: 12px">
      <NGrid :cols="6" :x-gap="12" :y-gap="12">
        <NGi v-for="e in entryCards" :key="e.route">
          <NCard size="small" hoverable class="entry-card" @click="goto(e.route)">
            <span class="entry-icon" aria-hidden="true">{{ e.icon }}</span>
            <div>
              <NText strong style="font-size: 13px">{{ e.title }}</NText>
              <NText depth="3" style="font-size: 11px; display: block">{{ e.desc }}</NText>
            </div>
          </NCard>
        </NGi>
      </NGrid>
    </NCard>

    <!-- Recent orders -->
    <NCard :title="t('billing.ordersTitle')" :bordered="false" style="margin-top: 12px">
      <DataTable
        :columns="orderColumns"
        :data="orders"
        :loading="ordersLoading"
        :error="ordersError"
        :total="orders.length"
        :page="1"
        :page-size="10"
        :row-key="(r: any) => r.id || r.order_id"
        @refresh="loadOrders"
      >
        <template #empty><NEmpty :description="t('billing.emptyOrders')" /></template>
      </DataTable>
    </NCard>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NCard, NSpace, NText, NTag, NIcon, NGrid, NGi, NProgress, NSpin, NEmpty, NAlert, NButton,
  useMessage, type DataTableColumns
} from 'naive-ui'
import { RefreshOutline, CardOutline } from '@vicons/ionicons5'
import { useI18n } from 'vue-i18n'
import ActionButton from '@/components/ActionButton.vue'
import DataTable from '@/components/DataTable.vue'
import {
  listPlans, getCurrentPlan, getUserUsage,
  createSubscription, changePlan, listOrders,
  type PlanItem, type UsageBucket,
} from '@/api/billing'

const router = useRouter()
const message = useMessage()
const { t } = useI18n()

const loading = ref(false)
const error = ref<string | null>(null)

const plans = ref<PlanItem[]>([])
const plansLoading = ref(false)
const currentPlan = ref<any>(null)
const currentPlanId = computed(() => currentPlan.value?.plan_id || currentPlan.value?.id || '')

const usageBuckets = ref<UsageBucket[]>([])
const usageLoading = ref(false)

const orders = ref<any[]>([])
const ordersLoading = ref(false)
const ordersError = ref<string | null>(null)

const upgrading = ref(false)
const upgradingTo = ref<string | null>(null)

const currentPlanBadge = computed<'success' | 'warning' | 'info' | 'default'>(() => {
  const id = currentPlanId.value
  if (!id) return 'default'
  if (id === 'enterprise' || id === 'business') return 'warning'
  if (id === 'pro' || id === 'standard') return 'success'
  return 'info'
})

const kpis = computed(() => [
  { key: 'cost', label: t('billing.kpiCost'), value: usageBuckets.value.reduce((s, b) => s + b.cost, 0).toFixed(2), unit: t('common.unitCurrency'), hint: t('billing.kpiCostHint') },
  { key: 'used', label: t('billing.kpiBuckets'), value: usageBuckets.value.length, unit: t('common.unitItem'), hint: t('billing.kpiBucketsHint') },
  { key: 'orders', label: t('billing.kpiOrders'), value: orders.value.length, unit: t('common.unitTimes'), hint: t('billing.kpiOrdersHint') },
  { key: 'plan', label: t('billing.kpiPlan'), value: currentPlan.value?.plan_name || t('billing.notSubscribed'), unit: '', hint: currentPlan.value?.period || '' },
])

const entryCards = [
  { icon: '🧾', title: '订单历史', desc: '查看历史订单与状态', route: '/orders' },
  { icon: '📃', title: '发票管理', desc: '申请 / 导出 / 重开发票', route: '/invoices' },
  { icon: '📜', title: '合同管理', desc: '电子合同 / 服务协议', route: '/contracts' },
  { icon: '👥', title: '客户管理', desc: 'CRM · 客户档案', route: '/crm' },
  { icon: '🎫', title: '工单系统', desc: '提交 / 跟踪 工单', route: '/tickets' },
  { icon: '💎', title: '套餐定价', desc: '所有可用套餐', route: '/pricing' },
]

const orderColumns: DataTableColumns<any> = [
  { title: '订单号', key: 'id', width: 200 },
  { title: '套餐', key: 'plan_id', width: 120 },
  {
    title: '金额', key: 'amount', width: 120,
    render: (row: any) => h(NText, { strong: true }, { default: () => `¥${row.amount ?? row.total ?? '0.00'}` }),
  },
  {
    title: '状态', key: 'status', width: 120,
    render: (row: any) => h(NTag, { size: 'small', type: orderStatusBadge(row.status) }, { default: () => row.status || 'pending' }),
  },
  { title: '创建时间', key: 'created_at', width: 180 },
]

function orderStatusBadge(s?: string): 'default' | 'success' | 'warning' | 'error' | 'info' {
  switch ((s || '').toLowerCase()) {
    case 'paid':
    case 'success':
    case 'completed':
      return 'success'
    case 'pending':
    case 'processing':
      return 'warning'
    case 'failed':
    case 'cancelled':
    case 'canceled':
      return 'error'
    default:
      return 'info'
  }
}

function usageStatus(b: UsageBucket): 'success' | 'warning' | 'error' {
  const ratio = b.used / Math.max(1, b.quota)
  if (ratio > 0.9) return 'error'
  if (ratio > 0.7) return 'warning'
  return 'success'
}

function formatNum(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 10_000) return (n / 10_000).toFixed(1) + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

async function load() {
  loading.value = true; error.value = null
  try {
    await Promise.all([loadPlans(), loadCurrent(), loadUsage(), loadOrders()])
  } catch (e) {
    error.value = (e as Error).message || '加载计费数据失败'
    message.error(error.value)
  } finally { loading.value = false }
}

async function loadPlans() {
  plansLoading.value = true
  try {
    const res = await listPlans()
    plans.value = res.plans || (res as any)
  } catch (e) {
    // backend may not be wired; fall back to stub plan list for offline dev
    plans.value = [
      { id: 'free', name: '免费版', tier: 'starter', price_monthly: 0, price_yearly: 0, currency: 'CNY', features: ['1k 图片/月', '10 视频/月', '5 GB 存储'], limits: {}, description: '体验套餐' },
      { id: 'pro', name: '专业版', tier: 'standard', price_monthly: 999, price_yearly: 9988, currency: 'CNY', features: ['50k 图片/月', '200 视频/月', '1 TB 存储', 'Skill 市场'], limits: {}, recommended: true, description: '推荐生产环境' },
      { id: 'enterprise', name: '企业版', tier: 'enterprise', price_monthly: 4999, price_yearly: 49988, currency: 'CNY', features: ['无限用量', 'SLA 99.99%', '专属客户经理', 'SSO'], limits: {}, description: '私有部署 / 大客户' },
    ]
  } finally { plansLoading.value = false }
}

async function loadCurrent() {
  try {
    currentPlan.value = await getCurrentPlan('me')
  } catch {
    currentPlan.value = { plan_id: 'pro', plan_name: '专业版', period: 'monthly' }
  }
}

async function loadUsage() {
  usageLoading.value = true
  try {
    const res = await getUserUsage('me')
    usageBuckets.value = res.buckets || []
  } catch {
    // fallback demo data
    usageBuckets.value = [
      { key: 'img-gen', label: '图片生成', used: 12400, quota: 50000, unit: '张', cost: 248 },
      { key: 'vid-gen', label: '视频生成', used: 86, quota: 200, unit: '条', cost: 1200 },
      { key: 'llm-tokens', label: 'LLM Tokens', used: 18_500_000, quota: 100_000_000, unit: 'tok', cost: 185 },
      { key: 'storage', label: '存储用量', used: 412, quota: 1024, unit: 'GB', cost: 41.2 },
      { key: 'workflow-runs', label: '工作流运行', used: 4200, quota: 10000, unit: '次', cost: 0 },
      { key: 'agent-sessions', label: 'Agent 会话', used: 320, quota: 1000, unit: '次', cost: 320 },
    ]
  } finally { usageLoading.value = false }
}

async function loadOrders() {
  ordersLoading.value = true; ordersError.value = null
  try {
    const res = await listOrders('me')
    orders.value = res.orders || (res as any) || []
  } catch (e) {
    ordersError.value = (e as Error).message || '加载订单失败'
    orders.value = []
  } finally { ordersLoading.value = false }
}

async function onUpgrade(p: PlanItem) {
  if (p.id === currentPlanId.value) return
  upgrading.value = true; upgradingTo.value = p.id
  try {
    if (currentPlan.value) {
      await changePlan('me', p.id)
    } else {
      await createSubscription('me', p.id, 'monthly')
    }
    currentPlan.value = { plan_id: p.id, plan_name: p.name, period: 'monthly' }
    message.success(`已切换到 ${p.name} 套餐`)
  } catch (e) {
    message.warning(`后端未确认 — 已在本地切换到 ${p.name}`)
    currentPlan.value = { plan_id: p.id, plan_name: p.name, period: 'monthly' }
  } finally { upgrading.value = false; upgradingTo.value = null }
}

function goPricing() { router.push('/pricing') }
function goto(route: string) { router.push(route) }

onMounted(load)
</script>

<style scoped>
.billing-view { padding: 16px; }
.header-card { margin-bottom: 12px; }
.kpi-card { min-height: 100px; }
.kpi-value { margin: 4px 0; }
.billing-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}
.plan-list { display: flex; flex-direction: column; gap: 12px; }
.plan-row {
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  padding: 12px;
  background: #fff;
  transition: all 0.15s;
}
.plan-row.active { border-color: #18a058; background: #f0fff6; }
.plan-row:hover { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06); }
.plan-head { display: flex; align-items: flex-start; justify-content: space-between; }
.plan-price { text-align: right; }
.plan-features { margin: 8px 0; display: flex; gap: 6px; flex-wrap: wrap; }
.plan-actions { display: flex; gap: 8px; }
.usage-list { display: flex; flex-direction: column; gap: 14px; }
.usage-row { padding: 4px 0; }
.usage-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.entry-card {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.entry-card:hover { background: #f0f8ff; transform: translateY(-1px); }
.entry-icon { font-size: 28px; }
.empty-wrap { padding: 24px; }
</style>