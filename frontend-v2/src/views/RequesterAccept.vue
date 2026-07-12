<template>
  <div class="requester-accept-view">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">{{ t('requesterAccept.t000') }} (Requester Acceptance)</NText>
          <NText depth="3" style="margin-left: 8px">
            {{ t('requesterAccept.t001') }} · {{ t('common.approve') }}/{{ t('common.decline') }} · {{ t('requesterAccept.t002') }}
          </NText>
        </div>
        <NSpace align="center">
          <NText depth="3">{{ t('requesterAccept.t003') }} ID:</NText>
          <NInput v-model:value="requesterId" placeholder="r001" size="small" style="width: 140px" />
          <ActionButton type="primary" :loading="loading" @click="loadAll">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ t('common.refresh') }}
          </ActionButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NAlert v-if="error" type="error" :show-icon="true" closable style="margin-bottom: 12px" @close="error = null">
      {{ error }}
    </NAlert>

    <NGrid :cols="3" :x-gap="12" :y-gap="12" style="margin-bottom: 12px">
      <NGi>
        <NCard size="small" :bordered="false">
          <NText depth="3" style="font-size: 11px">{{ t('requesterAccept.t004') }}</NText>
          <div class="kpi-value">
            <NText strong style="font-size: 24px">{{ pending.length }}</NText>
          </div>
        </NCard>
      </NGi>
      <NGi>
        <NCard size="small" :bordered="false">
          <NText depth="3" style="font-size: 11px">{{ t('requesterAccept.t005') }}</NText>
          <div class="kpi-value">
            <NText strong style="font-size: 24px; color: #18a058">{{ stats.accepted }}</NText>
          </div>
        </NCard>
      </NGi>
      <NGi>
        <NCard size="small" :bordered="false">
          <NText depth="3" style="font-size: 11px">{{ t('requesterAccept.t006') }}</NText>
          <div class="kpi-value">
            <NText strong style="font-size: 24px; color: #d03050">{{ stats.rejected }}</NText>
          </div>
        </NCard>
      </NGi>
    </NGrid>

    <div class="main-grid">
      <!-- 左: {{ t('requesterAccept.t007') }} -->
      <NCard title="待我验收" :bordered="false" class="left-pane">
        <NSpin :show="loading">
          <NEmpty v-if="!pending.length" description="暂无待验收" />
          <NList v-else hoverable clickable>
            <NListItem
              v-for="acc in pending"
              :key="acc.id"
              :class="{ active: selected?.id === acc.id }"
              @click="onSelect(acc)"
            >
              <NThing>
                <template #header>
                  <NSpace align="center" :size="6">
                    <NText strong>{{ acc.delivery_id }}</NText>
                    <NTag size="tiny" type="warning" :bordered="false">{{ t('requesterAccept.t008') }}</NTag>
                  </NSpace>
                </template>
                <template #description>
                  <NText depth="3" style="font-size: 11px">
                    {{ t('requesterAccept.t009') }} {{ acc.sampled_count }} · {{ t('requesterAccept.t010') }} {{ formatTime(acc.created_at) }}
                  </NText>
                </template>
              </NThing>
            </NListItem>
          </NList>
        </NSpin>

        <NDivider />

        <NText depth="3" style="font-size: 11px">{{ t('requesterAccept.t011') }}</NText>
        <NSpace vertical :size="6" style="margin-top: 6px">
          <NInput v-model:value="newDeliveryId" placeholder="delivery_id (如 d1)" size="small" />
          <NSelect v-model:value="newSampleRate" :options="sampleRateOpts" size="small" />
          <NButton block size="small" type="primary" :loading="creating" @click="onCreate">
            <template #icon><NIcon><AddOutline /></NIcon></template>
            {{ t('requesterAccept.t012') }}
          </NButton>
        </NSpace>
      </NCard>

      <!-- 中: {{ t('common.detail') }} -->
      <NCard :bordered="false" class="center-pane">
        <template #header>
          <NSpace align="center" justify="space-between" style="width: 100%">
            <NText strong>{{ selected?.delivery_id || t('requesterAccept.t013') }}</NText>
            <NTag v-if="selected" :type="statusType(selected.status)" :bordered="false">
              {{ statusLabel(selected.status) }}
            </NTag>
          </NSpace>
        </template>

        <NEmpty v-if="!selected" description="选择左侧记录进行验收" />

        <template v-else>
          <NGrid :cols="4" :x-gap="8" :y-gap="8">
            <NGi>
              <NCard size="small" :bordered="false">
                <NText depth="3" style="font-size: 11px">{{ t('requesterAccept.t014') }}</NText>
                <div class="kpi-value"><NText strong style="font-size: 20px">{{ selected.sampled_count }}</NText></div>
              </NCard>
            </NGi>
            <NGi>
              <NCard size="small" :bordered="false">
                <NText depth="3" style="font-size: 11px">{{ t('annotation.statusApproved') }}</NText>
                <div class="kpi-value"><NText strong style="font-size: 20px; color: #18a058">{{ selected.accepted_count }}</NText></div>
              </NCard>
            </NGi>
            <NGi>
              <NCard size="small" :bordered="false">
                <NText depth="3" style="font-size: 11px">{{ t('requesterAccept.t015') }}</NText>
                <div class="kpi-value"><NText strong style="font-size: 20px; color: #d03050">{{ selected.rejected_count }}</NText></div>
              </NCard>
            </NGi>
            <NGi>
              <NCard size="small" :bordered="false">
                <NText depth="3" style="font-size: 11px">{{ t('requesterAccept.t016') }}</NText>
                <div class="kpi-value">
                  <NText strong style="font-size: 20px">{{ ((selected.acceptance_rate || 0) * 100).toFixed(0) }}%</NText>
                </div>
              </NCard>
            </NGi>
          </NGrid>

          <NDivider />

          <NText depth="3" style="font-size: 12px">{{ t('requesterAccept.t017') }} (前 30 个)</NText>
          <NScrollbar style="max-height: 160px; margin-top: 6px">
            <NSpace :size="4" :wrap-item="false">
              <NTag
                v-for="aid in selected.sampled_assets.slice(0, 30)"
                :key="aid"
                size="small"
                :bordered="false"
              >
                {{ aid }}
              </NTag>
            </NSpace>
          </NScrollbar>

          <NDivider style="margin: 12px 0" />

          <template v-if="selected.status === 'pending'">
            <NForm label-placement="top" :model="form">
              <NFormItem label="备注">
                <NInput
                  v-model:value="form.comments"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 4 }"
                  placeholder="（可选）验收意见"
                />
              </NFormItem>
              <NSpace>
                <NButton type="success" :loading="submitting" @click="onSubmit('accepted')">
                  <template #icon><NIcon><CheckmarkCircleOutline /></NIcon></template>
                  {{ t('common.approve') }}
                </NButton>
                <NButton type="error" :loading="submitting" @click="onSubmit('rejected')">
                  <template #icon><NIcon><CloseCircleOutline /></NIcon></template>
                  {{ t('common.decline') }}
                </NButton>
                <NButton type="warning" :loading="submitting" @click="onRequestRevision">
                  <template #icon><NIcon><ArrowBackCircleOutline /></NIcon></template>
                  {{ t('requesterAccept.t018') }}
                </NButton>
              </NSpace>
            </NForm>
          </template>

          <template v-else>
            <NAlert :type="selected.status === 'accepted' ? 'success' : selected.status === 'rejected' ? 'error' : 'warning'" :show-icon="true">
              已 {{ statusLabel(selected.status) }} — {{ selected.comments || t('requesterAccept.t019') }}
              <div v-if="selected.updated_at" style="margin-top: 4px; font-size: 11px">
                {{ t('common.updatedAt') }}: {{ formatTime(selected.updated_at) }}
              </div>
            </NAlert>
          </template>
        </template>
      </NCard>

      <!-- 右: {{ t('menu.contextHistory') }} -->
      <NCard title="历史记录" :bordered="false" class="right-pane">
        <NEmpty v-if="!allAcceptances.length" description="暂无记录" />
        <NScrollbar v-else style="max-height: calc(100vh - 300px)">
          <NList>
            <NListItem v-for="acc in allAcceptances" :key="acc.id">
              <NThing>
                <template #header>
                  <NSpace :size="6">
                    <NText strong>{{ acc.delivery_id }}</NText>
                    <NTag size="tiny" :type="statusType(acc.status)" :bordered="false">{{ statusLabel(acc.status) }}</NTag>
                  </NSpace>
                </template>
                <template #description>
                  <NText depth="3" style="font-size: 11px">
                    {{ t('requesterAccept.t020') }} {{ acc.sampled_count }} · {{ t('requesterAccept.t021') }} {{ ((acc.acceptance_rate || 0) * 100).toFixed(0) }}%
                  </NText>
                  <div style="font-size: 10px; color: #999">{{ formatTime(acc.created_at) }}</div>
                </template>
              </NThing>
            </NListItem>
          </NList>
        </NScrollbar>
      </NCard>
    </div>
  </div>
</template>

<script setup lang="ts">import { useI18n } from 'vue-i18n'

const { t } = useI18n()

import { computed, onMounted, reactive, ref } from 'vue'
import {
  NCard, NSpace, NText, NTag, NIcon, NButton, NInput, NSelect, NInputNumber,
  NGrid, NGi, NAlert, NDivider, NEmpty, NList, NListItem, NThing,
  NScrollbar, NForm, NFormItem, useMessage,
} from 'naive-ui'
import {
  RefreshOutline, AddOutline, CheckmarkCircleOutline, CloseCircleOutline,
  ArrowBackCircleOutline,
} from '@vicons/ionicons5'
import ActionButton from '@/components/ActionButton.vue'
import {
  listPending, listAcceptances, createAcceptance, submitAcceptance,
  requestRevision, type AcceptanceRecord, type AcceptanceStatus,
} from '@/api/requester'
import { finalizeAndShare } from '@/api/delivery'

const message = useMessage()

const requesterId = ref('r001')
const pending = ref<AcceptanceRecord[]>([])
const allAcceptances = ref<AcceptanceRecord[]>([])
const selected = ref<AcceptanceRecord | null>(null)
const loading = ref(false)
const submitting = ref(false)
const creating = ref(false)
const error = ref<string | null>(null)

const newDeliveryId = ref('')
const newSampleRate = ref(0.05)

const sampleRateOpts = [
  { label: '5%', value: 0.05 },
  { label: '10%', value: 0.10 },
  { label: '20%', value: 0.20 },
]

const form = reactive({
  comments: '',
})

const stats = computed(() => {
  const accepted = allAcceptances.value.filter((a) => a.status === 'accepted').length
  const rejected = allAcceptances.value.filter((a) => a.status === 'rejected').length
  return { accepted, rejected }
})

function statusType(s: AcceptanceStatus): 'success' | 'warning' | 'error' | 'info' {
  if (s === 'accepted') return 'success'
  if (s === 'rejected') return 'error'
  if (s === 'needs_revision') return 'warning'
  return 'info'
}

function statusLabel(s: AcceptanceStatus): string {
  return { pending: t("requesterAccept.t022"), accepted: t("annotation.statusApproved"), rejected: t("requesterAccept.t023"), needs_revision: t("requesterAccept.t024") }[s] || s
}

function formatTime(iso: string): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch { return iso }
}

async function loadAll() {
  if (!requesterId.value.trim()) {
    message.warning(`${t('requesterAccept.t025')} ID`)
    return
  }
  loading.value = true
  error.value = null
  try {
    const [p, a] = await Promise.allSettled([
      listPending(requesterId.value),
      listAcceptances({ requester_id: requesterId.value }),
    ])
    if (p.status === 'fulfilled' && p.value.success) {
      pending.value = p.value.data.items || []
    } else {
      pending.value = []
    }
    if (a.status === 'fulfilled' && a.value.success) {
      allAcceptances.value = a.value.data.items || []
    } else {
      allAcceptances.value = []
    }
    // ${t('requesterAccept.t026')}
    if (pending.value.length && !selected.value) {
      onSelect(pending.value[0])
    }
  } catch (e) {
    error.value = (e as Error).message || t(`dataFlowTracker.loadFailed`)
  } finally {
    loading.value = false
  }
}

function onSelect(acc: AcceptanceRecord) {
  selected.value = acc
  form.comments = ''
}

async function onCreate() {
  if (!newDeliveryId.value.trim()) {
    message.warning(`${t('requesterAccept.t027')} delivery_id`)
    return
  }
  creating.value = true
  try {
    const resp = await createAcceptance({
      delivery_id: newDeliveryId.value.trim(),
      requester_id: requesterId.value,
      sample_rate: newSampleRate.value,
      seed: 42,
    })
    if (resp.success) {
      message.success(t("requesterAccept.t028"))
      newDeliveryId.value = ''
      selected.value = resp.data
      await loadAll()
    } else {
      throw new Error(resp.message || t("requesterAccept.t029"))
    }
  } catch (e) {
    message.error((e as Error).message || t("requesterAccept.t030"))
  } finally {
    creating.value = false
  }
}

async function onSubmit(status: 'accepted' | 'rejected') {
  if (!selected.value) return
  submitting.value = true
  try {
    const resp = await submitAcceptance(selected.value.id, {
      status,
      comments: form.comments,
      accepted_assets: status === 'accepted' ? selected.value.sampled_assets : [],
      rejected_assets: status === 'rejected' ? selected.value.sampled_assets : [],
    })
    if (resp.success) {
      message.success(status === 'accepted' ? t("annotation.statusApproved") : t("requesterAccept.t031"))
      selected.value = resp.data
      // ${t('requesterAccept.t032')} finalize-and-share
      if (status === 'accepted') {
        try {
          const fs = await finalizeAndShare({
            delivery_id: selected.value.delivery_id,
            owner_id: requesterId.value,
            expiry_hours: 72,
            max_downloads: 0,
            note: `Auto-shared after acceptance ${selected.value.id}`,
          })
          if (fs.success) {
            message.info(`${t('requesterAccept.t033')}, ${t('button.link')}: ${fs.data.share_url}`)
          }
        } catch {
          // ignore — ${t('requesterAccept.t034')}
        }
      }
      await loadAll()
    }
  } catch (e) {
    message.error((e as Error).message || t("requesterAccept.t035"))
  } finally {
    submitting.value = false
  }
}

async function onRequestRevision() {
  if (!selected.value) return
  if (!form.comments.trim()) {
    message.warning(t("requesterAccept.t036"))
    return
  }
  submitting.value = true
  try {
    const resp = await requestRevision(selected.value.id, {
      reason: form.comments,
    })
    if (resp.success) {
      message.success(t("requesterAccept.t037"))
      selected.value = resp.data
      await loadAll()
    }
  } catch (e) {
    message.error((e as Error).message || t("requesterAccept.t038"))
  } finally {
    submitting.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.requester-accept-view { padding: 16px; }
.header-card { margin-bottom: 12px; }
.main-grid {
  display: grid;
  grid-template-columns: 280px 1fr 360px;
  gap: 12px;
  align-items: start;
}
.left-pane { max-height: calc(100vh - 280px); overflow: auto; }
.center-pane {}
.right-pane { max-height: calc(100vh - 280px); overflow: auto; }
.kpi-value { margin: 4px 0; }
.active { background: #e6f0fa; }
</style>