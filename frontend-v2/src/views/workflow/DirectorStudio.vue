<template>
  <div class="director-studio">
    <n-card title="Three-Module Director Studio (Story → Visual → Assembly)" :bordered="false">
      <n-space vertical>
        <n-space>
          <n-input v-model:value="brief" placeholder="Input a creative brief (e.g. '1 minute beauty tutorial')" style="width: 480px" />
          <n-input-number v-model:value="shotCount" :min="3" :max="20" placeholder="shots" />
          <n-button type="primary" :loading="busy" @click="onRunFull">Run full pipeline</n-button>
        </n-space>
        <n-alert v-if="error" type="error" :title="error" />
        <n-alert v-if="lastSession && lastSession.state === 'succeeded'" type="success" :title="`Final cut: ${lastSession.final_cut_uri}`" />

        <n-grid v-if="lastSession" :cols="3" :x-gap="12">
          <n-gi>
            <n-card size="small" title="1. Story (LLM script-split)">
              <template #header-extra>
                <n-tag :type="stateTag(lastSession.story_state)">{{ lastSession.story_state }}</n-tag>
              </template>
              <n-button size="small" :loading="busy" :disabled="!lastSession" @click="onStepStory">Run story</n-button>
              <n-list>
                <n-list-item v-for="s in lastSession.shots" :key="s.shot_id">
                  <b>{{ s.title }}</b>
                  <div style="font-size: 12px; color: #666">{{ s.description }}</div>
                </n-list-item>
              </n-list>
            </n-card>
          </n-gi>
          <n-gi>
            <n-card size="small" title="2. Visual (image / video / voice)">
              <template #header-extra>
                <n-tag :type="stateTag(lastSession.visual_state)">{{ lastSession.visual_state }}</n-tag>
              </template>
              <n-button size="small" :loading="busy" :disabled="!lastSession || lastSession.story_state !== 'succeeded'" @click="onStepVisual">Run visual</n-button>
              <n-list>
                <n-list-item v-for="a in lastSession.assets" :key="a.uri">
                  <n-tag size="tiny" :type="kindTag(a.kind)">{{ a.kind }}</n-tag>
                  <span style="font-size: 12px">{{ a.uri }}</span>
                </n-list-item>
              </n-list>
            </n-card>
          </n-gi>
          <n-gi>
            <n-card size="small" title="3. Assembly (final cut)">
              <template #header-extra>
                <n-tag :type="stateTag(lastSession.assembly_state)">{{ lastSession.assembly_state }}</n-tag>
              </template>
              <n-button size="small" :loading="busy" :disabled="!lastSession || lastSession.visual_state !== 'succeeded'" @click="onStepAssembly">Run assembly</n-button>
              <div v-if="lastSession.final_cut_uri" style="margin-top: 12px">
                <n-tag type="success" size="large">{{ lastSession.final_cut_uri }}</n-tag>
              </div>
            </n-card>
          </n-gi>
        </n-grid>
      </n-space>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NCard, NSpace, NInput, NInputNumber, NButton, NAlert, NGrid, NGi, NList, NListItem, NTag } from 'naive-ui'
import { directorRun, createDirectorSession, runDirectorStory, runDirectorVisual, runDirectorAssembly, type DirectorSession } from '@/api/workflow_v2'

const brief = ref('1 minute beauty tutorial')
const shotCount = ref<number>(8)
const busy = ref(false)
const lastSession = ref<DirectorSession | null>(null)
const error = ref('')

async function onRunFull() {
  if (!brief.value) return
  busy.value = true
  error.value = ''
  try {
    lastSession.value = await directorRun(brief.value, shotCount.value)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || String(e)
  } finally {
    busy.value = false
  }
}

async function ensureSession() {
  if (lastSession.value) return lastSession.value
  lastSession.value = await createDirectorSession(brief.value, shotCount.value)
  return lastSession.value
}

async function onStepStory() {
  busy.value = true; error.value = ''
  try {
    const sess = await ensureSession()
    lastSession.value = await runDirectorStory(sess.session_id)
  } catch (e: any) { error.value = e?.response?.data?.detail || String(e) }
  finally { busy.value = false }
}

async function onStepVisual() {
  if (!lastSession.value) return
  busy.value = true; error.value = ''
  try {
    lastSession.value = await runDirectorVisual(lastSession.value.session_id)
  } catch (e: any) { error.value = e?.response?.data?.detail || String(e) }
  finally { busy.value = false }
}

async function onStepAssembly() {
  if (!lastSession.value) return
  busy.value = true; error.value = ''
  try {
    lastSession.value = await runDirectorAssembly(lastSession.value.session_id)
  } catch (e: any) { error.value = e?.response?.data?.detail || String(e) }
  finally { busy.value = false }
}

function stateTag(s: string) {
  if (s === 'succeeded') return 'success'
  if (s === 'failed') return 'error'
  if (s === 'running') return 'info'
  return 'default'
}
function kindTag(k: string) {
  if (k === 'image') return 'success'
  if (k === 'video') return 'info'
  if (k === 'voice') return 'warning'
  return 'default'
}
</script>

<style scoped>
.director-studio { padding: 16px; }
</style>
