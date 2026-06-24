<template>
  <div class="iter-studio">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between">
        <div>
          <NText strong style="font-size: 18px">迭代创作工作室</NText>
          <NText depth="3" style="margin-left: 8px">多轮对话 + A/B 测试 + 一致性工作流</NText>
        </div>
        <NSpace>
          <NSelect v-model:value="filterProject" :options="projectOptions" placeholder="选择项目" clearable style="width: 220px" />
          <NButton type="primary" @click="openCreate">
            <template #icon><NIcon><AddOutline /></NIcon></template>
            新建会话
          </NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <div class="studio-grid">
      <!-- LEFT: prompt editor + history -->
      <NCard title="会话列表" :bordered="false" class="col-left">
        <NEmpty v-if="!sessions.length" description="还没有会话,点击右上角新建" />
        <NList v-else bordered hoverable>
          <NListItem v-for="s in sessions" :key="s.session_id" class="session-item" @click="selectSession(s.session_id)">
            <NThing>
              <template #header>
                <NSpace align="center">
                  <NText strong>{{ s.title }}</NText>
                  <NTag size="small" :type="stateTagType(s.state)">{{ stateLabel(s.state) }}</NTag>
                </NSpace>
              </template>
              <template #description>
                <NText depth="3" style="font-size: 12px">{{ s.session_id }} · {{ s.modality }}</NText>
              </template>
              <template #header-extra>
                <NText depth="3" style="font-size: 12px">{{ formatTime(s.updated_at) }}</NText>
              </template>
            </NThing>
          </NListItem>
        </NList>
      </NCard>

      <!-- CENTER: prompt editor + versions + A/B -->
      <NCard :bordered="false" class="col-center">
        <NEmpty v-if="!current" description="从左侧选择一个会话,或在右上角新建" />
        <template v-else>
          <NSpace vertical size="medium">
            <NSpace align="center">
              <NText strong>{{ current.title }}</NText>
              <NTag :type="stateTagType(current.state)">{{ stateLabel(current.state) }}</NText>
              <NText depth="3" style="font-size: 12px">{{ current.session_id }}</NText>
            </NSpace>

            <NInput
              v-model:value="iterText"
              type="textarea"
              :rows="4"
              placeholder="输入下一轮 prompt,例如: a knight with glowing sword on a stormy cliff"
            />
            <NSpace>
              <NButton type="primary" :loading="iterating" :disabled="!iterText" @click="onIterate">
                <template #icon><NIcon><RefreshOutline /></NIcon></template>
                迭代 (新增版本)
              </NButton>
              <NButton @click="openAB" :disabled="current.prompt_versions.length === 0">启动 A/B 测试</NButton>
              <NButton @click="onFinalize" :disabled="current.state === 'final'">完成会话</NButton>
              <NButton @click="onDiscard" type="error" ghost :disabled="current.state === 'discarded'">废弃</NButton>
            </NSpace>

            <NDivider title-placement="left">版本历史</NDivider>
            <NTimeline>
              <NTimelineItem
                v-for="(pv, idx) in current.prompt_versions"
                :key="pv.version_id"
                :type="idx === current.prompt_versions.length - 1 ? 'success' : 'default'"
                :title="`v${idx + 1}`"
                :time="formatTime(pv.created_at)"
              >
                <NSpace vertical size="small">
                  <NText>{{ pv.text }}</NText>
                  <NText v-if="pv.note" depth="3" style="font-size: 12px">note: {{ pv.note }}</NText>
                  <NButton v-if="current.best_variant_id === pv.version_id" size="tiny" type="success" ghost>最佳变体</NButton>
                </NSpace>
              </NTimelineItem>
            </NTimeline>

            <NDivider title-placement="left">A/B 测试</NDivider>
            <NEmpty v-if="!current.ab_tests?.length" size="small" description="还没有 A/B 测试" />
            <NCard v-for="ab in current.ab_tests || []" :key="ab.ab_id" size="small" :title="`ab ${ab.ab_id}`">
              <NSpace vertical size="small">
                <NText depth="3" style="font-size: 12px">状态: {{ ab.status }} · 变体数: {{ ab.variants.length }}</NText>
                <NGrid :cols="3" :x-gap="8">
                  <NGi v-for="v in ab.variants" :key="v.version_id">
                    <NCard size="small" :title="v.note || v.version_id.slice(0,6)">
                      <NSpace vertical size="small">
                        <NText style="font-size: 12px">{{ v.text }}</NText>
                        <NTag size="small">score: {{ ab.scores[v.version_id]?.toFixed?.(2) ?? '-' }}</NTag>
                        <NButton size="tiny" :type="ab.winner_variant_id === v.version_id ? 'success' : 'default'" :disabled="!ab.scores[v.version_id]" @click="scoreABInline(ab.ab_id, v.version_id, ab)">
                          评分
                        </NButton>
                      </NSpace>
                    </NCard>
                  </NGi>
                </NGrid>
                <NSpace>
                  <NButton size="small" @click="pickBestInline(ab.ab_id)">选最佳</NButton>
                  <NButton size="small" @click="randomScoreAB(ab)">随机评分(演示)</NButton>
                </NSpace>
              </NSpace>
            </NCard>
          </NSpace>
        </template>
      </NCard>

      <!-- RIGHT: feedback + assets -->
      <NCard title="生成结果 + 反馈" :bordered="false" class="col-right">
        <NEmpty v-if="!current" description="—" />
        <template v-else>
          <NSpace vertical size="medium">
            <NText strong>资产 ({{ current.assets?.length || 0 }})</NText>
            <NGrid :cols="2" :x-gap="6" :y-gap="6">
              <NGi v-for="a in current.assets || []" :key="a.asset_id">
                <NCard size="small" hoverable>
                  <NSpace vertical size="small">
                    <NTag size="tiny">{{ a.modality }}</NTag>
                    <NImage v-if="a.modality === 'image'" :src="a.url" object-fit="cover" height="80" />
                    <NText v-else style="font-size: 12px">{{ a.url }}</NText>
                    <NText depth="3" style="font-size: 11px">{{ a.asset_id }}</NText>
                    <NRate :default-value="0" size="small" @update:value="(v: number) => submitFeedback(v, a.asset_id)" />
                  </NSpace>
                </NCard>
              </NGi>
            </NGrid>

            <NDivider title-placement="left">反馈</NDivider>
            <NList v-if="current.feedback?.length">
              <NListItem v-for="f in current.feedback || []" :key="f.feedback_id">
                <NThing>
                  <template #header>
                    <NSpace>
                      <NTag size="small" :type="f.rating >= 4 ? 'success' : f.rating >= 2 ? 'warning' : 'error'">★ {{ f.rating }}</NTag>
                      <NText depth="3" style="font-size: 12px">{{ formatTime(f.created_at) }}</NText>
                    </NSpace>
                  </template>
                  <template #description>{{ f.text || '(无文本反馈)' }}</template>
                </NThing>
              </NListItem>
            </NList>
            <NEmpty v-else size="small" description="还没有反馈" />
            <NInput v-model:value="fbText" type="textarea" :rows="2" placeholder="补充文字反馈..." />
            <NButton @click="submitFeedback(3)" size="small" :disabled="!current">提交文字反馈</NButton>
          </NSpace>
        </template>
      </NCard>
    </div>

    <ModalForm v-model:show="createShow" title="新建迭代会话" v-model="createForm" :rules="createRules" @submit="onCreate">
      <template #default="{ form: f }">
        <NFormItem label="标题" path="title"><NInput v-model:value="(f as any).title" /></NFormItem>
        <NFormItem label="项目" path="project_id"><NInput v-model:value="(f as any).project_id" placeholder="project-id" /></NFormItem>
        <NFormItem label="模态" path="modality">
          <NSelect v-model:value="(f as any).modality" :options="modalityOptions" />
        </NFormItem>
        <NFormItem label="初始 Prompt" path="initial_prompt">
          <NInput v-model:value="(f as any).initial_prompt" type="textarea" :rows="3" />
        </NFormItem>
      </template>
    </ModalForm>

    <ModalForm v-model:show="abShow" title="启动 A/B 测试" v-model="abForm" :rules="abRules" @submit="onStartAB">
      <template #default="{ form: f }">
        <NFormItem label="变体 A"><NInput v-model:value="(f as any).a" /></NFormItem>
        <NFormItem label="变体 B"><NInput v-model:value="(f as any).b" /></NFormItem>
        <NFormItem label="变体 C (可选)"><NInput v-model:value="(f as any).c" /></NFormItem>
      </template>
    </ModalForm>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch, computed } from 'vue'
import {
  NCard, NSpace, NText, NButton, NIcon, NInput, NSelect, NTag, NList, NListItem, NThing,
  NEmpty, NTimeline, NTimelineItem, NDivider, NGrid, NGi, NImage, NRate, NFormItem, useMessage
} from 'naive-ui'
import { AddOutline, RefreshOutline } from '@vicons/ionicons5'
import ModalForm from '@/components/ModalForm.vue'
import {
  listSessions, getSession, createSession, iterateSession,
  addFeedback, startAB, scoreAB, pickBest, finalizeSession, discardSession,
  type IterativeSession
} from '@/api/iteration'

const message = useMessage()
const sessions = ref<IterativeSession[]>([])
const current = ref<IterativeSession | null>(null)
const iterText = ref('')
const iterating = ref(false)
const fbText = ref('')
const filterProject = ref<string | null>(null)

const projectOptions = computed(() => {
  const ids = Array.from(new Set(sessions.value.map(s => s.project_id)))
  return ids.map(id => ({ label: id, value: id }))
})

const modalityOptions = [
  { label: '图像', value: 'image' },
  { label: '视频', value: 'video' },
  { label: '音频', value: 'audio' }
]

const createShow = ref(false)
const createForm = reactive({ title: '', project_id: 'project-default', modality: 'image', initial_prompt: '' })
const createRules = {
  project_id: { required: true, message: '请输入项目 ID', trigger: 'blur' },
  initial_prompt: { required: true, message: '请输入初始 prompt', trigger: 'blur' }
}

const abShow = ref(false)
const abForm = reactive({ a: '', b: '', c: '' })
const abRules = {}

function stateLabel(s: string) {
  return { draft: '草稿', review: '审阅中', final: '已完成', discarded: '已废弃' }[s] || s
}
function stateTagType(s: string): 'default' | 'info' | 'success' | 'warning' | 'error' {
  return ({ draft: 'info', review: 'warning', final: 'success', discarded: 'default' } as any)[s] || 'default'
}
function formatTime(t?: string) {
  if (!t) return '-'
  return t.slice(0, 16).replace('T', ' ')
}

async function load() {
  const res = await listSessions({ project_id: filterProject.value || undefined })
  sessions.value = res.items
  if (current.value) {
    const fresh = sessions.value.find(s => s.session_id === current.value!.session_id)
    if (fresh) current.value = fresh
  }
}
async function selectSession(id: string) {
  current.value = await getSession(id)
}
function openCreate() {
  Object.assign(createForm, { title: '', project_id: 'project-default', modality: 'image', initial_prompt: '' })
  createShow.value = true
}
async function onCreate() {
  const created = await createSession({
    owner_id: 'demo-user',
    project_id: createForm.project_id,
    modality: createForm.modality,
    initial_prompt: createForm.initial_prompt,
    title: createForm.title || `session-${Date.now()}`
  })
  message.success('已创建会话')
  createShow.value = false
  await load()
  await selectSession(created.session_id)
}
async function onIterate() {
  if (!current.value || !iterText.value) return
  iterating.value = true
  try {
    await iterateSession(current.value.session_id, { text: iterText.value })
    iterText.value = ''
    message.success('已新增版本')
    await load()
    await selectSession(current.value.session_id)
  } finally { iterating.value = false }
}
async function submitFeedback(rating: number, asset_id?: string) {
  if (!current.value) return
  await addFeedback(current.value.session_id, { rating, text: fbText.value || undefined, asset_id })
  fbText.value = ''
  message.success('已记录反馈')
  await load()
  await selectSession(current.value.session_id)
}
function openAB() {
  Object.assign(abForm, { a: '', b: '', c: '' })
  abShow.value = true
}
async function onStartAB() {
  if (!current.value) return
  const variants = [abForm.a, abForm.b, abForm.c].filter(Boolean).map(text => ({ text }))
  if (variants.length < 2) { message.warning('至少需要 2 个变体'); return }
  await startAB(current.value.session_id, {
    parent_prompt_version_id: current.value.prompt_versions[current.value.prompt_versions.length - 1].version_id,
    variants
  })
  abShow.value = false
  message.success('A/B 已启动')
  await selectSession(current.value.session_id)
}
async function scoreABInline(abId: string, versionId: string, ab: any) {
  if (!current.value) return
  const newScores = { ...ab.scores, [versionId]: 0.9 }
  await scoreAB(current.value.session_id, abId, { scores: newScores })
  await selectSession(current.value.session_id)
}
async function pickBestInline(abId: string) {
  if (!current.value) return
  await pickBest(current.value.session_id, abId)
  message.success('已选出最佳变体')
  await load()
  await selectSession(current.value.session_id)
}
async function randomScoreAB(ab: any) {
  if (!current.value) return
  const scores: Record<string, number> = {}
  ab.variants.forEach((v: any, i: number) => { scores[v.version_id] = Math.random() })
  await scoreAB(current.value.session_id, ab.ab_id, { scores })
  await pickBestInline(ab.ab_id)
}
async function onFinalize() { if (!current.value) return; await finalizeSession(current.value.session_id); message.success('会话已完成'); await load(); await selectSession(current.value.session_id) }
async function onDiscard() { if (!current.value) return; await discardSession(current.value.session_id); message.warning('会话已废弃'); await load(); await selectSession(current.value.session_id) }

watch(filterProject, () => { load() })
onMounted(load)
</script>

<style scoped>
.iter-studio { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.studio-grid {
  display: grid;
  grid-template-columns: 320px 1fr 360px;
  gap: 12px;
  align-items: start;
}
.col-left, .col-center, .col-right { min-height: 480px; }
.session-item { cursor: pointer; }
</style>