<template>
  <div class="billing-dashboard">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">Billing Dashboard (P4-10 整合)</NText>
          <NText depth="3" style="margin-left: 8px">
            12 维度用量 · 套餐对比 · 订单 / 发票 / 合同 / 工单 一站式入口
          </NText>
        </div>
        <NSpace>
          <NTag :type="planTag" size="large" :bordered="false">{{ currentPlan.name }} 套餐</NTag>
          <NButton type="primary" @click="gotoPricing">升级套餐</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <!-- 12-dimension usage grid -->
    <NGrid :cols="4" :x-gap="12" :y-gap="12" style="margin-bottom: 16px">
      <NGi v-for="(d, i) in usageDims" :key="i">
        <NCard :bordered="false" size="small" class="dim-card">
          <NText depth="3" style="font-size: 11px">{{ d.label }}</NText>
          <div class="dim-value">
            <NText strong style="font-size: 22px">{{ formatNum(d.used) }}</NText>
            <NText depth="3" style="font-size: 12px"> / {{ formatNum(d.quota) }} {{ d.unit }}</NText>
          </div>
          <NProgress
            type="line"
            :percentage="Math.min(100, (d.used / Math.max(1, d.quota)) * 100)"
            :status="d.used / Math.max(1, d.quota) > 0.9 ? 'error' : d.used / Math.max(1, d.quota) > 0.7 ? 'warning' : 'success'"
            :show-indicator="false"
            :height="6"
          />
          <NText depth="3" style="font-size: 10px">花费 ¥{{ d.cost.toFixed(2) }}</NText>
        </NCard>
      </NGi>
    </NGrid>

    <div class="dash-grid">
      <!-- Plan comparison -->
      <NCard title="套餐对比" :bordered="false" class="col-plans">
        <NGrid :cols="3" :x-gap="8">
          <NGi v-for="p in plans" :key="p.id">
            <NCard size="small" :class="['plan-card', { recommended: p.recommended }]">
              <NSpace align="center" justify="space-between">
                <NText strong style="font-size: 14px">{{ p.name }}</NText>
                <NTag v-if="p.recommended" type="success" size="tiny">推荐</NTag>
              </NSpace>
              <div class="plan-price">
                <NText strong style="font-size: 24px">¥{{ p.price }}</NText>
                <NText depth="3" style="font-size: 12px">/ {{ p.period }}</NText>
              </div>
              <NList size="small" style="margin-top: 8px">
                <NListItem v-for="(f, i) in p.features" :key="i">
                  <NText style="font-size: 12px">✓ {{ f }}</NText>
                </NListItem>
              </NList>
              <NButton
                size="small"
                :type="p.recommended ? 'primary' : 'default'"
                block
                :disabled="p.id === currentPlan.id"
                style="margin-top: 8px"
                @click="onUpgrade(p)"
              >{{ p.id === currentPlan.id ? '当前套餐' : '升级到此套餐' }}</NButton>
            </NCard>
          </NGi>
        </NGrid>
      </NCard>

      <!-- Entry cards -->
      <NCard title="业务入口" :bordered="false" class="col-entries">
        <NGrid :cols="2" :x-gap="8" :y-gap="8">
          <NGi v-for="(e, i) in entryCards" :key="i">
            <NCard size="small" hoverable class="entry-card" @click="goto(e.route)">
              <span class="entry-icon">{{ e.icon }}</span>
              <div>
                <NText strong style="font-size: 13px">{{ e.title }}</NText>
                <NText depth="3" style="font-size: 11px; display: block">{{ e.desc }}</NText>
              </div>
            </NCard>
          </NGi>
        </NGrid>
      </NCard>
    </div>

    <!-- Recent activity -->
    <NCard title="近期活动" :bordered="false" style="margin-top: 16px">
      <NList>
        <NListItem v-for="(a, i) in recentActivity" :key="i">
          <NSpace align="center" justify="space-between" style="width: 100%">
            <div>
              <NText strong style="font-size: 13px">{{ a.title }}</NText>
              <NText depth="3" style="font-size: 11px; margin-left: 8px">{{ a.time }}</NText>
            </div>
            <NTag :type="a.type === 'payment' ? 'success' : a.type === 'usage' ? 'info' : 'warning'" size="small">
              {{ a.type === 'payment' ? '支付' : a.type === 'usage' ? '用量' : '告警' }}
            </NTag>
          </NSpace>
        </NListItem>
      </NList>
    </NCard>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NCard, NSpace, NText, NTag, NButton, NGrid, NGi, NProgress, NList, NListItem, useMessage
} from 'naive-ui'

const router = useRouter()
const message = useMessage()

interface UsageDim { key: string; label: string; used: number; quota: number; unit: string; cost: number }

const usageDims = ref<UsageDim[]>([
  { key: 'img-gen', label: '图片生成', used: 12_400, quota: 50_000, unit: '张', cost: 248 },
  { key: 'vid-gen', label: '视频生成', used: 86, quota: 200, unit: '条', cost: 1200 },
  { key: 'aud-gen', label: '音频/TTS', used: 3_200, quota: 20_000, unit: '次', cost: 64 },
  { key: 'llm-tokens', label: 'LLM Tokens', used: 18_500_000, quota: 100_000_000, unit: 'tok', cost: 185 },
  { key: 'storage', label: '存储用量', used: 412, quota: 1024, unit: 'GB', cost: 41.2 },
  { key: 'bandwidth', label: 'CDN 流量', used: 680, quota: 2000, unit: 'GB', cost: 136 },
  { key: 'workflow-runs', label: '工作流运行', used: 4_200, quota: 10_000, unit: '次', cost: 0 },
  { key: 'skill-calls', label: 'Skill 调用', used: 8_900, quota: 30_000, unit: '次', cost: 89 },
  { key: 'mcp-calls', label: 'MCP 调用', used: 1_200, quota: 5_000, unit: '次', cost: 24 },
  { key: 'agent-sessions', label: 'Agent 会话', used: 320, quota: 1000, unit: '次', cost: 320 },
  { key: 'multimodal', label: '多模态理解', used: 5_400, quota: 20_000, unit: '次', cost: 270 },
  { key: 'vector-rag', label: 'RAG 检索', used: 12_000, quota: 50_000, unit: '次', cost: 60 },
])

const plans = ref([
  { id: 'free', name: '免费版', price: 0, period: '月', recommended: false, features: ['1k 图片/月', '10 视频/月', '5 GB 存储', '社区支持'] },
  { id: 'pro', name: '专业版', price: 999, period: '月', recommended: true, features: ['50k 图片/月', '200 视频/月', '1 TB 存储', '邮件支持', 'Skill 市场', 'RAG 索引'] },
  { id: 'enterprise', name: '企业版', price: 4999, period: '月', recommended: false, features: ['无限用量', 'SLA 99.99%', '专属客户经理', '私有部署', 'SSO', '审计日志'] },
])

const currentPlan = ref(plans.value[1])

const planTag = computed<'success' | 'warning' | 'info'>(() => {
  return currentPlan.value.id === 'enterprise' ? 'warning' : currentPlan.value.id === 'pro' ? 'success' : 'info'
})

const entryCards = [
  { icon: '🧾', title: '订单历史', desc: '查看历史订单与状态', route: '/orders' },
  { icon: '📃', title: '发票管理', desc: '申请 / 导出 / 重开发票', route: '/invoices' },
  { icon: '📜', title: '合同管理', desc: '电子合同 / 服务协议', route: '/contracts' },
  { icon: '👥', title: '客户管理', desc: 'CRM · 客户档案', route: '/crm' },
  { icon: '🎫', title: '工单系统', desc: '提交 / 跟踪 工单', route: '/tickets' },
  { icon: '💎', title: '套餐定价', desc: '所有可用套餐', route: '/pricing' },
]

const recentActivity = ref([
  { title: 'Skill 安装: deep-research v2.0.0', time: '2026-06-24 10:30', type: 'usage' },
  { title: '本月已消耗 ¥2,623.50', time: '2026-06-24 09:15', type: 'usage' },
  { title: '发票 #INV-2026-006 已开具', time: '2026-06-23 16:00', type: 'payment' },
  { title: '工作流运行 #wf-8932 失败', time: '2026-06-23 14:22', type: 'warning' },
  { title: '存储用量超过 80%', time: '2026-06-22 12:08', type: 'warning' },
  { title: '订单 #ORD-2026-004 已支付', time: '2026-06-21 18:30', type: 'payment' },
])

function formatNum(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 10_000) return (n / 10_000).toFixed(1) + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

function onUpgrade(p: any) {
  if (p.id === currentPlan.value.id) return
  message.success(`已切换到 ${p.name} 套餐 (演示)`)
  currentPlan.value = p
}

function gotoPricing() { router.push({ name: 'pricing' }) }
function goto(route: string) { router.push(route) }

onMounted(() => {
  // Optionally load from backend
})
</script>

<style scoped>
.billing-dashboard { padding: 0; }
.header-card { margin-bottom: 12px; }
.dim-card { min-height: 110px; }
.dim-value { margin: 4px 0 8px; }
.dash-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.plan-card { transition: all 0.2s; }
.plan-card.recommended { border-color: #18a058; }
.plan-price { margin: 4px 0; }
.entry-card {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.entry-card:hover { background: #f0f8ff; transform: translateY(-1px); }
.entry-icon { font-size: 28px; }
</style>
