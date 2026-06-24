<template>
  <div class="consistency-report">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between">
        <div>
          <NText strong style="font-size: 18px">一致性报告</NText>
          <NText depth="3" style="margin-left: 8px">5 轮自动重生成 + NSFW fallback + 增量重生成</NText>
        </div>
        <NSpace>
          <NInput v-model:value="newProjectId" placeholder="输入项目 ID 启动新一轮" style="width: 240px" />
          <NButton type="primary" :loading="running" :disabled="!newProjectId" @click="runNew">运行一致性 workflow</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NCard title="历史报告" :bordered="false">
      <NEmpty v-if="!reports.length" description="还没有一致性报告" />
      <NSpace v-else vertical size="large">
        <NCard v-for="r in reports" :key="r.started_at + r.project_id" hoverable>
          <NSpace vertical size="small">
            <NSpace align="center" justify="space-between">
              <NSpace>
                <NText strong>{{ r.project_id }}</NText>
                <NTag :type="r.passed ? 'success' : 'error'">{{ r.passed ? 'PASS' : 'FAIL' }}</NTag>
                <NTag type="info">资产 {{ r.asset_count }}</NTag>
                <NTag :type="r.fallback_used_count > 0 ? 'warning' : 'default'">fallback ×{{ r.fallback_used_count }}</NTag>
              </NSpace>
              <NText depth="3" style="font-size: 12px">{{ formatTime(r.started_at) }}</NText>
            </NSpace>

            <NGrid :cols="4" :x-gap="8">
              <NGi><NStatistic label="初始分数">{{ r.initial_avg_score.toFixed(2) }}</NStatistic></NGi>
              <NGi><NStatistic label="最终分数">{{ r.final_avg_score.toFixed(2) }}</NStatistic></NGi>
              <NGi><NStatistic label="Δ">{{ (r.delta >= 0 ? '+' : '') + r.delta.toFixed(2) }}</NStatistic></NGi>
              <NGi><NStatistic label="轮数">{{ r.rounds.length }}</NStatistic></NGi>
            </NGrid>

            <NProgress
              :percentage="Math.min(100, r.final_avg_score * 100)"
              :status="r.passed ? 'success' : 'warning'"
              :indicator-placement="'inside'"
            />

            <NDivider title-placement="left">每轮详情</NDivider>
            <NEmpty v-if="!r.rounds.length" size="small" description="无需重生成 (初始已达标)" />
            <NList v-else>
              <NListItem v-for="round in r.rounds" :key="round.round_no">
                <NThing>
                  <template #header>
                    <NSpace>
                      <NTag :type="round.fallback_used ? 'warning' : 'info'">round {{ round.round_no }}</NTag>
                      <NTag v-if="round.fallback_used" size="small" type="warning">fallback</NTag>
                      <NText style="font-size: 12px">Δ {{ (round.delta >= 0 ? '+' : '') + round.delta.toFixed(2) }}</NText>
                    </NSpace>
                  </template>
                  <template #description>
                    <NSpace size="small">
                      <NTag v-for="s in round.regenerated_shots" :key="s" size="tiny" type="default">{{ s }}</NTag>
                    </NSpace>
                  </template>
                  <template #header-extra>
                    <NText depth="3" style="font-size: 11px">{{ formatTime(round.finished_at) }}</NText>
                  </template>
                </NThing>
              </NListItem>
            </NList>
          </NSpace>
        </NCard>
      </NSpace>
    </NCard>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NCard, NSpace, NText, NButton, NInput, NTag, NEmpty, NList, NListItem, NThing, NGrid, NGi, NStatistic, NProgress, NDivider, useMessage } from 'naive-ui'
import { consistencyRun, listConsistencyReports, type ConsistencyReport } from '@/api/iteration'

const message = useMessage()
const reports = ref<ConsistencyReport[]>([])
const newProjectId = ref('')
const running = ref(false)

function formatTime(t?: string) { return t ? t.slice(0, 19).replace('T', ' ') : '-' }

async function load() {
  const res = await listConsistencyReports()
  reports.value = res.items
}

async function runNew() {
  if (!newProjectId.value) return
  running.value = true
  try {
    const report = await consistencyRun({
      project_id: newProjectId.value,
      brief: { script: 'Scene 1: a hero enters.\n\nScene 2: the hero meets a wizard.' },
      config: { target_score: 0.85, max_rounds: 5 }
    })
    message.success(`workflow 完成: ${report.passed ? 'PASS' : 'FAIL'}, final ${report.final_avg_score.toFixed(2)}`)
    newProjectId.value = ''
    await load()
  } catch (e: any) {
    message.error(e.message || 'workflow 失败')
  } finally {
    running.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.consistency-report { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
</style>