<template>
  <div class="pricing-page">
    <NPageHeader title="套餐定价" subtitle="选择适合您的数据生成服务套餐"></NPageHeader>
    <NSpin :show="loading" style="margin-top: 24px;">
      <NGrid :cols="5" :x-gap="16" responsive="screen" item-responsive>
        <NGi v-for="plan in plans" :key="plan.key" span="1">
          <NCard
            :title="plan.name"
            hoverable
            embedded
            :class="['plan-card', { recommended: plan.key === 'Pro' }]"
          >
            <template #header-extra>
              <NTag v-if="plan.key === 'Pro'" type="success" size="small">推荐</NTag>
            </template>
            <div class="plan-price">
              <span class="currency">¥</span>
              <span class="amount">{{ plan.price_monthly }}</span>
              <span class="period">/月</span>
            </div>
            <NUl>
              <NLi v-for="(f, i) in plan.features" :key="i">
                <NText depth="3">{{ f }}</NText>
              </NLi>
            </NUl>
            <template #action>
              <NButton
                type="primary"
                block
                :disabled="plan.key === currentPlan"
                @click="choosePlan(plan)"
              >
                {{ plan.key === currentPlan ? '当前套餐' : '选此套餐' }}
              </NButton>
            </template>
          </NCard>
        </NGi>
      </NGrid>
    </NSpin>
    <NModal v-model:show="showConfirm" preset="card" title="确认升级" style="width: 480px;">
      <p>您选择了 <b>{{ selectedPlan?.name }}</b> 套餐, 价格 ¥{{ selectedPlan?.price_monthly }}/月</p>
      <p style="color: #999; font-size: 12px;">点击确认将创建新订单, 并自动生成发票和合同.</p>
      <template #action>
        <NSpace justify="end">
          <NButton @click="showConfirm = false">取消</NButton>
          <NButton type="primary" @click="confirmUpgrade">确认升级</NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NPageHeader, NGrid, NGi, NCard, NButton, NTag, NUl, NLi, NText, NSpin, NSpace, NModal, useMessage } from 'naive-ui'

const message = useMessage()
const loading = ref(false)
const showConfirm = ref(false)
const selectedPlan = ref<any>(null)
const currentPlan = ref('Free')

// 5 套餐 (与 P4-10-W1 对齐)
const plans = ref([
  { key: 'Free', name: 'Free', price_monthly: 0, features: ['100 条数据/月', '1 用户', '社区支持', '5GB 存储'] },
  { key: 'Starter', name: 'Starter', price_monthly: 199, features: ['1000 条数据/月', '1000 次算子调用', '3 用户', '邮件支持', '50GB 存储'] },
  { key: 'Pro', name: 'Pro', price_monthly: 699, features: ['10000 条数据/月', '10000 次算子调用', '10 用户', '工单支持', '500GB 存储', 'API 访问'] },
  { key: 'Business', name: 'Business', price_monthly: 2099, features: ['100000 条数据/月', '100000 次算子调用', '50 用户', '优先支持 + SLA', '5TB 存储', 'SSO + 审计'] },
  { key: 'Enterprise', name: 'Enterprise', price_monthly: 0, features: ['定制', '专属客户经理', '白标', '私有化部署', '7x24 支持', '99.99% SLA'] },
])

function choosePlan(p: any) {
  selectedPlan.value = p
  showConfirm.value = true
}

function confirmUpgrade() {
  showConfirm.value = false
  message.success(`已创建 ${selectedPlan.value.name} 订单, 发票和合同将自动生成`)
  currentPlan.value = selectedPlan.value.key
}

onMounted(() => {
  // 实际应调用 /api/v1/billing/subscription
  // 简化: 假设当前为 Free
})
</script>

<style scoped>
.pricing-page { padding: 16px; }
.plan-card { height: 100%; }
.plan-card.recommended { border: 2px solid #18a058; }
.plan-price { text-align: center; margin: 12px 0; }
.plan-price .currency { font-size: 16px; color: #999; }
.plan-price .amount { font-size: 32px; font-weight: bold; color: #18a058; }
.plan-price .period { font-size: 14px; color: #999; margin-left: 4px; }
</style>
