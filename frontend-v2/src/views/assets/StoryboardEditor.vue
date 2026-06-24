<template>
  <div class="storyboard-editor">
    <!-- Header -->
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">Storyboard Editor (P4-5/6 整合)</NText>
          <NText depth="3" style="margin-left: 8px">
            场景序列 · 多模态合成 · 18 generator + 39 视觉操作 · 实时预览
          </NText>
        </div>
        <NSpace>
          <NSelect v-model:value="stylePreset" :options="stylePresets" size="small" style="width: 160px" />
          <NButton size="small" @click="autoArrangeScenes">自动排序</NButton>
          <NButton size="small" type="primary" @click="renderAll" :loading="rendering">渲染全部</NButton>
          <NButton size="small" @click="exportProject">导出</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <div class="editor-grid">
      <!-- LEFT: scene list (drag reorder) -->
      <NCard title="场景列表" :bordered="false" size="small" class="col-left">
        <NButton size="tiny" block @click="addScene" dashed>+ 新增场景</NButton>
        <NScrollbar style="margin-top: 8px; max-height: 520px">
          <div
            v-for="(sc, i) in scenes"
            :key="sc.id"
            class="scene-item"
            :class="{ active: selectedId === sc.id }"
            draggable="true"
            @dragstart="dragSceneIdx = i"
            @dragover.prevent
            @drop="onSceneDrop(i)"
            @click="selectedId = sc.id"
          >
            <span class="scene-handle">⋮⋮</span>
            <div class="scene-info">
              <NText strong style="font-size: 13px">{{ i + 1 }}. {{ sc.title }}</NText>
              <NText depth="3" style="font-size: 11px">{{ sc.shots.length }} 镜头 · {{ sc.duration_sec }}s · {{ sc.aspect }}</NText>
              <NSpace style="margin-top: 4px">
                <NTag v-if="sc.hasImage" size="tiny" type="success">image</NTag>
                <NTag v-if="sc.hasVideo" size="tiny" type="info">video</NTag>
                <NTag v-if="sc.hasAudio" size="tiny" type="warning">audio</NTag>
                <NTag v-if="sc.voiceover" size="tiny" :bordered="false">🎙 VO</NTag>
              </NSpace>
            </div>
            <span class="scene-del" @click.stop="removeScene(sc.id)">×</span>
          </div>
        </NScrollbar>
      </NCard>

      <!-- CENTER: scene config -->
      <NCard :bordered="false" size="small" class="col-center">
        <NEmpty v-if="!selected" description="从左侧选择或新增场景" />
        <div v-else>
          <NSpace align="center" justify="space-between" style="margin-bottom: 12px">
            <NText strong style="font-size: 16px">{{ selected.title }}</NText>
            <NSpace>
              <NButton size="tiny" @click="addShot">+ 镜头</NButton>
              <NButton size="tiny" type="primary" @click="renderSelected" :loading="rendering">渲染此场景</NButton>
            </NSpace>
          </NSpace>

          <NGrid :cols="2" :x-gap="12" :y-gap="8">
            <NGi>
              <NText depth="3" style="font-size: 12px">场景标题</NText>
              <NInput v-model:value="selected.title" size="small" />
            </NGi>
            <NGi>
              <NText depth="3" style="font-size: 12px">时长 (秒)</NText>
              <NInputNumber v-model:value="selected.duration_sec" size="small" :min="1" :max="120" style="width: 100%" />
            </NGi>
            <NGi>
              <NText depth="3" style="font-size: 12px">画幅</NText>
              <NSelect v-model:value="selected.aspect" :options="aspectOptions" size="small" />
            </NGi>
            <NGi>
              <NText depth="3" style="font-size: 12px">背景音乐</NText>
              <NSelect v-model:value="selected.music" :options="musicOptions" size="small" filterable tag clearable />
            </NGi>
          </NGrid>

          <NDivider style="margin: 12px 0" title-placement="left">Prompt</NDivider>
          <NInput v-model:value="selected.prompt" type="textarea" :rows="3" placeholder="镜头描述 prompt..." />

          <NDivider style="margin: 12px 0" title-placement="left">镜头序列</NDivider>
          <NTimeline>
            <NTimelineItem
              v-for="(sh, idx) in selected.shots"
              :key="sh.id"
              :title="`Shot ${idx + 1}: ${sh.kind}`"
              :time="`${sh.duration_sec}s`"
            >
              <NGrid :cols="3" :x-gap="6">
                <NGi>
                  <NSelect v-model:value="sh.kind" :options="shotKinds" size="tiny" />
                </NGi>
                <NGi>
                  <NInputNumber v-model:value="sh.duration_sec" size="tiny" :min="0.5" :max="30" :step="0.5" style="width: 100%" />
                </NGi>
                <NGi>
                  <NButton size="tiny" tertiary @click="selected.shots.splice(idx, 1)">删除</NButton>
                </NGi>
              </NGrid>
              <NInput v-model:value="sh.prompt" type="textarea" :rows="2" size="tiny" placeholder="shot prompt..." style="margin-top: 4px" />
            </NTimelineItem>
          </NTimeline>

          <NDivider style="margin: 12px 0" title-placement="left">旁白 (Voiceover)</NDivider>
          <NSpace>
            <NTag :type="selected.voiceover ? 'success' : 'default'" @click="selected.voiceover = !selected.voiceover" style="cursor: pointer">
              {{ selected.voiceover ? '✓ 已启用' : '启用旁白' }}
            </NTag>
            <NSelect v-if="selected.voiceover" v-model:value="selected.voice" :options="voiceOptions" size="tiny" style="width: 180px" />
          </NSpace>
          <NInput v-if="selected.voiceover" v-model:value="selected.voiceover_text" type="textarea" :rows="2" size="small" placeholder="旁白文本..." style="margin-top: 6px" />

          <NDivider style="margin: 12px 0" title-placement="left">P4-6 视觉操作</NDivider>
          <NSpace>
            <NTag v-for="op in visualOps" :key="op" size="small" :bordered="false" :type="selected.appliedOps?.includes(op) ? 'success' : 'default'" @click="toggleOp(op)" style="cursor: pointer">
              {{ op }}
            </NTag>
          </NSpace>
        </div>
      </NCard>

      <!-- RIGHT: real-time preview -->
      <NCard :bordered="false" size="small" class="col-right" title="实时预览">
        <div class="preview-frame" :class="aspectClass">
          <NEmpty v-if="!selected" description="无场景" />
          <div v-else>
            <NImage
              v-if="selected.preview_url"
              :src="selected.preview_url"
              object-fit="cover"
              style="width: 100%; height: 100%"
              preview-disabled
            />
            <div v-else class="preview-placeholder">
              <span style="font-size: 48px">🎬</span>
              <NText depth="3">{{ selected.prompt || '点击 "渲染" 生成预览' }}</NText>
            </div>
          </div>
        </div>
        <NText v-if="selected" depth="3" style="font-size: 11px; display: block; margin-top: 8px">
          {{ selected.shots.length }} 镜头 · 总时长 {{ totalDuration(selected) }}s
        </NText>

        <NDivider style="margin: 12px 0" title-placement="left">角色库</NDivider>
        <NSpace>
          <NTag v-for="c in characters" :key="c.id" :bordered="false" :type="selected?.characterIds?.includes(c.id) ? 'success' : 'default'" @click="toggleCharacter(c.id)" style="cursor: pointer">
            {{ c.avatar }} {{ c.name }}
          </NTag>
        </NSpace>
      </NCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  NCard, NSpace, NText, NInput, NInputNumber, NSelect, NButton, NTag, NEmpty, NDivider,
  NTimeline, NTimelineItem, NGrid, NGi, NImage, NScrollbar, useMessage
} from 'naive-ui'
import { multimodalApi } from '@/api/multimodal'

const message = useMessage()

interface Shot { id: string; kind: 'wide' | 'medium' | 'closeup' | 'pan' | 'tilt' | 'zoom'; duration_sec: number; prompt: string }
interface Scene {
  id: string
  title: string
  duration_sec: number
  aspect: '16:9' | '9:16' | '1:1' | '4:3'
  prompt: string
  shots: Shot[]
  music?: string | null
  voiceover: boolean
  voice?: string
  voiceover_text?: string
  hasImage?: boolean
  hasVideo?: boolean
  hasAudio?: boolean
  preview_url?: string | null
  appliedOps?: string[]
  characterIds?: string[]
}

const scenes = ref<Scene[]>([])
const selectedId = ref<string>('')
const dragSceneIdx = ref<number | null>(null)
const rendering = ref(false)
const stylePreset = ref('cinematic')

const stylePresets = [
  { label: '电影感', value: 'cinematic' },
  { label: '动漫', value: 'anime' },
  { label: '水彩', value: 'watercolor' },
  { label: '3D 渲染', value: '3d' },
  { label: '写实', value: 'realistic' },
]
const aspectOptions = [
  { label: '16:9 横屏', value: '16:9' },
  { label: '9:16 竖屏', value: '9:16' },
  { label: '1:1 方图', value: '1:1' },
  { label: '4:3 经典', value: '4:3' },
]
const shotKinds = [
  { label: '全景 wide', value: 'wide' },
  { label: '中景 medium', value: 'medium' },
  { label: '特写 closeup', value: 'closeup' },
  { label: '平移 pan', value: 'pan' },
  { label: '俯仰 tilt', value: 'tilt' },
  { label: '推拉 zoom', value: 'zoom' },
]
const musicOptions = [
  { label: '无', value: '' },
  { label: '🎵 激昂', value: 'epic' },
  { label: '🎵 安静', value: 'ambient' },
  { label: '🎵 紧张', value: 'suspense' },
  { label: '🎵 欢快', value: 'happy' },
]
const voiceOptions = [
  { label: '中文女声', value: 'zh-female' },
  { label: '中文男声', value: 'zh-male' },
  { label: '英文女声', value: 'en-female' },
  { label: '英文男声', value: 'en-male' },
]
const visualOps = [
  'face_swap', 'style_transfer', 'color_grade', 'denoise', 'upscale_4x',
  'object_remove', 'bg_replace', 'motion_blur', 'lens_flare', 'vintage',
  'crop_reframe', 'rotate', 'mirror_h', 'mirror_v', 'brightness_up',
  'brightness_down', 'contrast_up', 'saturation_up', 'tilt_shift', 'vignette',
  'sharpen', 'gaussian_blur', 'pixelate', 'cartoon', 'sketch',
  'oil_paint', 'watercolor', 'cyberpunk', 'invert', 'sepia',
  'grayscale', 'hsv_shift', 'lut_cinematic', 'lut_vintage', 'lut_teal_orange',
  'frame_interpolation', 'super_resolution', 'audio_enhance', 'voice_clone', 'caption_burn',
]
const characters = ref([
  { id: 'c-hero', name: 'Hero', avatar: '🧙' },
  { id: 'c-villain', name: 'Villain', avatar: '🦹' },
  { id: 'c-sidekick', name: 'Sidekick', avatar: '🧝' },
  { id: 'c-narrator', name: 'Narrator', avatar: '📖' },
])

const selected = computed(() => scenes.value.find(s => s.id === selectedId.value) || null)

const aspectClass = computed(() => {
  const a = selected.value?.aspect
  if (a === '9:16') return 'aspect-tall'
  if (a === '1:1') return 'aspect-square'
  if (a === '4:3') return 'aspect-classic'
  return 'aspect-wide'
})

function uid(): string { return `s${Date.now()}_${Math.random().toString(36).slice(2, 6)}` }

function addScene() {
  const id = uid()
  const sc: Scene = {
    id,
    title: `场景 ${scenes.value.length + 1}`,
    duration_sec: 6,
    aspect: '16:9',
    prompt: '',
    shots: [{ id: uid(), kind: 'wide', duration_sec: 3, prompt: '' }],
    voiceover: false,
    hasImage: false,
    hasVideo: false,
    hasAudio: false,
    preview_url: null,
    appliedOps: [],
    characterIds: [],
  }
  scenes.value.push(sc)
  selectedId.value = id
}

function removeScene(id: string) {
  scenes.value = scenes.value.filter(s => s.id !== id)
  if (selectedId.value === id) selectedId.value = scenes.value[0]?.id || ''
}

function addShot() {
  if (!selected.value) return
  selected.value.shots.push({ id: uid(), kind: 'medium', duration_sec: 2, prompt: '' })
}

function toggleOp(op: string) {
  if (!selected.value) return
  const ops = selected.value.appliedOps || []
  if (ops.includes(op)) selected.value.appliedOps = ops.filter(x => x !== op)
  else selected.value.appliedOps = [...ops, op]
}

function toggleCharacter(id: string) {
  if (!selected.value) return
  const ids = selected.value.characterIds || []
  if (ids.includes(id)) selected.value.characterIds = ids.filter(x => x !== id)
  else selected.value.characterIds = [...ids, id]
}

function onSceneDrop(target: number) {
  if (dragSceneIdx.value === null || dragSceneIdx.value === target) return
  const arr = scenes.value
  const [moved] = arr.splice(dragSceneIdx.value, 1)
  arr.splice(target, 0, moved)
  dragSceneIdx.value = null
}

function autoArrangeScenes() {
  scenes.value.sort((a, b) => a.title.localeCompare(b.title, 'zh'))
  message.success('已按标题排序')
}

function totalDuration(sc: Scene): number {
  return sc.shots.reduce((s, x) => s + x.duration_sec, 0)
}

async function renderSelected() {
  if (!selected.value) return
  rendering.value = true
  try {
    const res = await multimodalApi.generate({
      text: `${stylePreset.value} style, ${selected.value.prompt || selected.value.title}`,
      target: 'image',
      params: { aspect: selected.value.aspect, ops: selected.value.appliedOps, characters: selected.value.characterIds },
    })
    const data = res.data
    if (data.candidates[0]) {
      selected.value.preview_url = data.candidates[0].url
      selected.value.hasImage = true
      message.success(`已渲染 ${data.candidates[0].modality} (${data.elapsed_ms}ms)`)
    }
  } catch (e: any) {
    // local SVG placeholder
    const seed = Math.floor(Math.random() * 1e9)
    selected.value.preview_url = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 450'><rect fill='%232080f0' width='800' height='450'/><text x='400' y='225' fill='white' font-size='32' text-anchor='middle' font-family='sans-serif'>${selected.value.title} · ${stylePreset.value}</text><text x='400' y='260' fill='white' font-size='14' text-anchor='middle' opacity='0.7'>seed ${seed}</text></svg>`)}`
    selected.value.hasImage = true
    message.warning(`后端生成暂未就绪, 已生成占位预览: ${e?.message || ''}`)
  } finally {
    rendering.value = false
  }
}

async function renderAll() {
  for (const sc of scenes.value) {
    selectedId.value = sc.id
    await renderSelected()
  }
}

function exportProject() {
  const project = {
    name: `storyboard-${Date.now()}`,
    style: stylePreset.value,
    scenes: scenes.value.map(sc => ({
      ...sc,
      total_duration: totalDuration(sc),
    })),
  }
  const blob = new Blob([JSON.stringify(project, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${project.name}.json`
  a.click()
  URL.revokeObjectURL(url)
  message.success('已导出 JSON')
}

onMounted(() => {
  // Seed with 2 demo scenes
  const s1: Scene = {
    id: uid(), title: '开场: 英雄登场', duration_sec: 6, aspect: '16:9',
    prompt: 'A lone hero walking into a rainy tavern, cinematic lighting',
    shots: [
      { id: uid(), kind: 'wide', duration_sec: 3, prompt: 'wide shot: tavern exterior at night, rain' },
      { id: uid(), kind: 'medium', duration_sec: 3, prompt: 'hero enters, door creaks' },
    ],
    voiceover: true, voice: 'zh-male', voiceover_text: '雨夜, 英雄踏入了小酒馆...',
    hasImage: false, hasVideo: false, hasAudio: true,
    appliedOps: ['color_grade', 'lut_cinematic'],
    characterIds: ['c-hero'],
  }
  const s2: Scene = {
    id: uid(), title: '冲突: 老巫师的任务', duration_sec: 8, aspect: '16:9',
    prompt: 'Old wizard offers a quest, magic swirls around the table',
    shots: [
      { id: uid(), kind: 'closeup', duration_sec: 3, prompt: 'closeup on the wizard face' },
      { id: uid(), kind: 'medium', duration_sec: 3, prompt: 'magical map unrolls' },
      { id: uid(), kind: 'wide', duration_sec: 2, prompt: 'hero accepts, stands up' },
    ],
    voiceover: true, voice: 'zh-male', voiceover_text: '接受我的委托, 冒险者...',
    hasImage: false, hasVideo: false, hasAudio: true,
    appliedOps: ['denoise', 'upscale_4x'],
    characterIds: ['c-hero', 'c-villain'],
  }
  scenes.value = [s1, s2]
  selectedId.value = s1.id
})
</script>

<style scoped>
.storyboard-editor { padding: 0; }
.header-card { margin-bottom: 12px; }
.editor-grid {
  display: grid;
  grid-template-columns: 280px 1fr 360px;
  gap: 12px;
  align-items: stretch;
}
.col-left, .col-center, .col-right { min-height: 600px; }
.scene-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border: 1px solid #e0e0e6;
  border-radius: 6px;
  margin-bottom: 6px;
  cursor: grab;
  background: #fff;
  transition: all 0.15s;
}
.scene-item:hover { background: #f5f5f7; }
.scene-item.active { background: #e6f0ff; border-color: #2080f0; }
.scene-handle { color: #aaa; font-size: 14px; }
.scene-info { flex: 1; min-width: 0; }
.scene-del {
  color: #d03050;
  font-size: 18px;
  cursor: pointer;
  padding: 0 4px;
}
.scene-del:hover { color: #ff6666; }
.preview-frame {
  position: relative;
  width: 100%;
  background: #000;
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.preview-frame.aspect-wide { aspect-ratio: 16/9; }
.preview-frame.aspect-tall { aspect-ratio: 9/16; max-width: 200px; margin: 0 auto; }
.preview-frame.aspect-square { aspect-ratio: 1/1; max-width: 320px; margin: 0 auto; }
.preview-frame.aspect-classic { aspect-ratio: 4/3; }
.preview-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px;
  text-align: center;
  color: #fff;
}
</style>
