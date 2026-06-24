<template>
  <div class="multi-agent-panel">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between">
        <div>
          <NText strong style="font-size: 18px">多 Agent 协同面板</NText>
          <NText depth="3" style="margin-left: 8px">Director 调度 6 个 Worker Agent 协同生成</NText>
        </div>
        <NSpace>
          <NTag :type="running ? 'warning' : 'success'">{{ running ? '运行中' : '空闲' }}</NTag>
          <NButton type="primary" :loading="running" @click="runDemo">演示脚本生成</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <div class="agents-grid">
      <NCard v-for="a in agents" :key="a.role" class="agent-card" hoverable>
        <NSpace vertical size="small">
          <NSpace align="center" justify="space-between">
            <NSpace align="center">
              <div :class="['agent-dot', roleStatusClass(a.role)]" />
              <NText strong>{{ a.name }}</NText>
            </NSpace>
            <NTag size="small" :type="roleStatusTag(a.role)">{{ roleStatusLabel(a.role) }}</NTag>
          </NSpace>
          <NText depth="3" style="font-size: 12px">{{ a.description }}</NText>
          <NSpace size="small">
            <NTag v-for="cap in a.capabilities" :key="cap" size="tiny" type="info">{{ cap }}</NTag>
          </NSpace>
          <NProgress
            v-if="roleProgress(a.role) > 0"
            :percentage="roleProgress(a.role)"
            :status="roleProgress(a.role) === 100 ? 'success' : 'default'"
            :show-indicator="false"
            size="small"
          />
        </NSpace>
      </NCard>
    </div>

    <NCard title="最近运行" :bordered="false" class="runs-card">
      <NEmpty v-if="!runs.length" description="尚无运行记录" />
      <NList v-else>
        <NListItem v-for="r in runs" :key="r.run_id">
          <NThing>
            <template #header>
              <NSpace align="center">
                <NText strong>{{ r.run_id }}</NText>
                <NTag size="small" :type="r.ok ? 'success' : 'error'">{{ r.ok ? '成功' : '失败' }}</NTag>
                <NText depth="3" style="font-size: 12px">资产 {{ r.asset_count }}</NText>
              </NSpace>
            </template>
            <template #description>
              <NSpace size="small">
                <NTag v-for="ar in r.agent_results" :key="ar.role" size="tiny" :type="ar.status === 'done' ? 'success' : 'error'">
                  {{ ar.role }}: {{ ar.status }}
                </NTag>
              </NSpace>
            </template>
            <template #header-extra>
              <NText depth="3" style="font-size: 12px">{{ formatTime(r.started_at) }}</NText>
            </template>
          </NThing>
        </NListItem>
      </NList>
    </NCard>

    <NCard v-if="lastReport" title="Blackboard (上次运行)" :bordered="false">
      <NSpace vertical size="small">
        <NText strong>storyboard scenes: {{ lastReport.storyboard.scenes?.length || 0 }}</NText>
        <NText strong>characters bound: {{ Object.keys(lastReport.character_state).length }}</NText>
        <NText strong>assets produced: {{ lastReport.asset_pool.length }}</NText>
        <NText strong>QA scored: {{ Object.keys(lastReport.qa_scores).length }}</NText>
        <NDivider title-placement="left">事件流 (最近 10 条)</NDivider>
        <NList>
          <NListItem v-for="(e, idx) in lastReport.events.slice(-10).reverse()" :key="idx">
            <NThing>
              <template #header>
                <NSpace>
                  <NTag size="tiny" type="info">{{ e.role }}</NTag>
                  <NTag size="tiny">{{ e.kind }}</NTag>
                </NSpace>
              </template>
              <template #description>
                <NText style="font-size: 12px">{{ JSON.stringify(e.payload).slice(0, 200) }}</NText>
              </template>
              <template #header-extra>
                <NText depth="3" style="font-size: 11px">{{ formatTime(e.created_at) }}</NText>
              </template>
            </NThing>
          </NListItem>
        </NList>
      </NSpace>
    </NCard>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NCard, NSpace, NText, NButton, NTag, NEmpty, NList, NListItem, NThing, NDivider, NProgress, useMessage } from 'naive-ui'
import { listAgents, multiGenerate, listRuns, type AgentInfo, type OrchestratorReport } from '@/api/iteration'

const message = useMessage()
const agents = ref<AgentInfo[]>([])
const runs = ref<{ run_id: string; started_at: string; ok: boolean; asset_count: number; agent_results: { role: string; status: string }[] }[]>([])
const lastReport = ref<OrchestratorReport | null>(null)
const running = ref(false)
const progress = ref<Record<string, number>>({})

function roleStatusClass(role: string): string {
  const p = progress.value[role]
  if (p === undefined || p === 0) return 'agent-dot--idle'
  if (p === 100) return 'agent-dot--done'
  return 'agent-dot--running'
}
function roleStatusTag(role: string): 'default' | 'info' | 'success' | 'warning' | 'error' {
  const p = progress.value[role]
  if (p === undefined || p === 0) return 'info'
  if (p === 100) return 'success'
  return 'warning'
}
function roleStatusLabel(role: string): string {
  const p = progress.value[role]
  if (p === undefined || p === 0) return 'idle'
  if (p === 100) return 'done'
  return 'running'
}
function roleProgress(role: string): number {
  return progress.value[role] ?? 0
}
function formatTime(t?: string) {
  if (!t) return '-'
  return t.slice(0, 16).replace('T', ' ')
}

async function loadAgents() {
  const res = await listAgents()
  agents.value = res.items
}
async function loadRuns() {
  const res = await listRuns(10)
  runs.value = res.items
}

async function runDemo() {
  running.value = true
  progress.value = {}
  const allRoles = ['director', 'storyboard', 'character', 'image', 'video', 'voice', 'qa']
  for (const role of allRoles) progress.value[role] = 50
  try {
    const report = await multiGenerate({
      brief: {
        script: 'Scene 1: a hero walks into a tavern.\n\nScene 2: the hero meets an old wizard.',
        characters: ['hero', 'wizard'],
        shots_per_scene: 1
      },
      character_pool: {
        hero: { character_id: 'hero', reference_url: '/c/hero.png' },
        wizard: { character_id: 'wizard', reference_url: '/c/wizard.png' }
      }
    })
    lastReport.value = report
    for (const ar of report.agent_results) progress.value[ar.role] = ar.status === 'done' ? 100 : 0
    message.success(`协同完成, 共 ${report.asset_pool.length} 个资产`)
    await loadRuns()
  } catch (e: any) {
    message.error(e.message || '生成失败')
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  await loadAgents()
  await loadRuns()
})
</script>

<style scoped>
.multi-agent-panel { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.agents-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.agent-card { min-height: 140px; }
.agent-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.agent-dot--idle { background: #d9d9d9; }
.agent-dot--running { background: #faad14; animation: pulse 1.2s infinite; }
.agent-dot--done { background: #52c41a; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
.runs-card { margin-top: 8px; }
</style>