<template>
  <div class="page-root dataflow-tracker">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">{{ t('dataFlowTracker.pageTitle') }}</NText>
          <NText depth="3" style="margin-left: 8px">
            {{ t('dataFlowTracker.pageSubtitle', { count: snapshot?.total_events ?? 0 }) }}
          </NText>
        </div>
        <NSpace>
          <ActionButton type="primary" :loading="loading" @click="load">
            <template #icon><NIcon><RefreshOutline /></NIcon></template>
            {{ t('dataFlowTracker.refresh') }}
          </ActionButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NAlert v-if="error" type="error" closable style="margin-bottom: 12px" @close="error = ''">
      {{ error }}
    </NAlert>

    <NCard :bordered="false" :title="t('dataFlowTracker.filterByProject')" size="small" style="margin-bottom: 12px">
      <NSpace align="center" :wrap-item="false">
        <NInput
          v-model:value="filterProject"
          :placeholder="t('dataFlowTracker.filterPlaceholder')"
          clearable
          @keyup.enter="load"
          style="width: 320px"
        />
        <NButton type="primary" @click="load">{{ t('dataFlowTracker.apply') }}</NButton>
        <NButton @click="onClearFilter">{{ t('dataFlowTracker.clear') }}</NButton>
      </NSpace>
    </NCard>

    <!-- Stage pipeline -->
    <NCard :bordered="false" :title="t('dataFlowTracker.pipelineTitle')" style="margin-bottom: 12px">
      <div class="pipeline">
        <div
          v-for="(node, idx) in (snapshot?.stages || [])"
          :key="node.stage"
          class="stage"
          :style="{ borderColor: node.color }"
        >
          <div class="stage-label">{{ node.label }}</div>
          <div class="stage-count">{{ node.event_count }}</div>
          <div class="stage-time" :title="node.last_event_at">
            {{ node.last_event_at ? formatTime(node.last_event_at) : '—' }}
          </div>
          <div v-if="idx < (snapshot?.stages?.length ?? 0) - 1" class="arrow" :style="{ color: node.color }">→</div>
        </div>
      </div>
    </NCard>

    <NGrid :x-gap="12" :y-gap="12" cols="3" item-responsive responsive="screen">
      <NGi span="3 m:1 l:1">
        <NCard :bordered="false" :title="t('dataFlowTracker.domainEventsTitle')">
          <div v-for="node in (snapshot?.stages || [])" :key="node.stage" class="dist-row">
            <NSpace align="center" justify="space-between" :wrap-item="false" style="margin-bottom: 4px">
              <NSpace align="center" :wrap-item="false">
                <div class="dist-color" :style="{ backgroundColor: node.color }" />
                <NText style="font-size: 12px">{{ node.label }}</NText>
              </NSpace>
              <NText depth="3" style="font-size: 12px">{{ node.event_count }}</NText>
            </NSpace>
            <NProgress
              type="line"
              :percentage="node.event_count > 0 ? Math.min(100, node.event_count * 20) : 0"
              :show-indicator="false"
              :height="6"
              :color="node.color"
            />
          </div>
        </NCard>
      </NGi>
      <NGi span="3 m:2 l:2">
        <NCard :bordered="false" :title="t('dataFlowTracker.timelineTitle', { count: snapshot?.timeline.length ?? 0 })">
          <NEmpty v-if="!snapshot || snapshot.timeline.length === 0" :description="t('dataFlowTracker.noEvents')" />
          <NTimeline v-else>
            <NTimelineItem
              v-for="ev in snapshot.timeline"
              :key="ev.id"
              :type="(ev.stage === 'delivery' || ev.stage === 'acceptance') ? 'success' : (ev.stage === 'qc' || ev.stage === 'review') ? 'warning' : 'info'"
              :title="ev.subject"
              :content="`actor=${ev.actor} · project=${ev.project_id || '—'} · pack=${ev.pack_id || '—'} · delivery=${ev.delivery_id || '—'}`"
              :time="formatTime(ev.created_at)"
            />
          </NTimeline>
        </NCard>
      </NGi>
    </NGrid>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NAlert,
  NButton,
  NCard,
  NEmpty,
  NGrid,
  NGi,
  NIcon,
  NInput,
  NProgress,
  NSpace,
  NTag,
  NText,
  NTimeline,
  NTimelineItem,
  useMessage,
} from 'naive-ui'
import { RefreshOutline } from '@vicons/ionicons5'
import { fetchSnapshot, type FlowSnapshot } from '@/api/dataflow'
import ActionButton from '@/components/ActionButton.vue'

const { t } = useI18n()
const message = useMessage()

const loading = ref(false)
const error = ref('')
const snapshot = ref<FlowSnapshot | null>(null)
const filterProject = ref<string>('')

const formatTime = (s: string) => {
  if (!s) return ''
  const d = new Date(s)
  if (Number.isNaN(d.valueOf())) return s
  return d.toLocaleString('zh-CN', { hour12: false })
}

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    const params = filterProject.value ? { project_id: filterProject.value } : {}
    snapshot.value = await fetchSnapshot(params)
  } catch (e) {
    error.value = (e as Error).message || t('dataFlowTracker.loadFailed')
  } finally {
    loading.value = false
  }
}

const onClearFilter = () => {
  filterProject.value = ''
  load()
}

onMounted(load)
</script>

<style scoped>
.page-root { padding: 16px; }
.header-card { margin-bottom: 12px; }

.pipeline {
  display: flex;
  align-items: stretch;
  flex-wrap: wrap;
  gap: 0;
  width: 100%;
  margin-top: 8px;
}

.stage {
  position: relative;
  flex: 1;
  min-width: 110px;
  padding: 12px 14px;
  border: 2px solid;
  border-radius: 8px;
  background: var(--surface-1, #fff);
  margin-right: 6px;
}
.stage-label { font-weight: 600; font-size: 13px; }
.stage-count { font-size: 22px; font-weight: bold; line-height: 1.2; }
.stage-time { font-size: 11px; color: var(--text-3, #777); }
.arrow {
  position: absolute;
  right: -14px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 18px;
  z-index: 2;
}
.dist-row { margin-bottom: 14px; }
.dist-color {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 6px;
}
</style>
