<!--
  P4-7-W2: frontend-v2/src/views/multimodal/EmbedStudio.vue
  Multimodal embedding studio — generate images/videos/audio via
  CrossModalGeneration and preview 4 candidates.
-->
<template>
  <NPageHeader title="跨模态生成工作室" subtitle="文本 + 参考图 → 图 / 视频 / 音频 (4 候选)">
    <template #extra>
      <NTag :type="providers.length ? 'success' : 'default'">{{ providers.length || 0 }} providers</NTag>
    </template>
  </NPageHeader>

  <NGrid :cols="3" :x-gap="16" :y-gap="16" style="margin-top: 16px;">
    <NGi :span="1">
      <NCard title="输入">
        <NSpace vertical>
          <NFormItem label="文本 prompt">
            <NInput v-model:value="form.text" type="textarea" placeholder="a robot painting the sunset, oil on canvas" />
          </NFormItem>
          <NFormItem label="目标模态">
            <NSelect v-model:value="form.target" :options="targetOptions" />
          </NFormItem>
          <NFormItem label="Provider">
            <NSelect v-model:value="form.provider" :options="providerOptions" placeholder="默认 (按优先级)" />
          </NFormItem>
          <NFormItem label="参考图 URL (1-3 张)">
            <NInput v-model:value="refUrl1" placeholder="ref image 1" />
            <NInput v-model:value="refUrl2" placeholder="ref image 2" style="margin-top: 6px;" />
            <NInput v-model:value="refUrl3" placeholder="ref image 3" style="margin-top: 6px;" />
          </NFormItem>
          <NFormItem label="候选数 n (1-4)">
            <NInputNumber v-model:value="n" :min="1" :max="4" />
          </NFormItem>
          <NButton type="primary" :loading="loading" @click="onGenerate">生成</NButton>
          <NAlert v-if="errMsg" type="error" :title="errMsg" />
        </NSpace>
      </NCard>
    </NGi>

    <NGi :span="2">
      <NCard :title="`候选 (${candidates.length})`">
        <NEmpty v-if="!candidates.length && !loading" description="点击生成查看候选" />
        <NGrid :cols="2" :x-gap="12" :y-gap="12">
          <NGi v-for="(c, i) in candidates" :key="i">
            <NCard size="small">
              <template #header>{{ i + 1 }}. {{ c.modality }}</template>
              <NImage v-if="c.modality === 'image'" :src="c.url" :preview-disabled="false" object-fit="cover" />
              <video v-else-if="c.modality === 'video'" :src="c.url" controls style="width: 100%;"></video>
              <audio v-else-if="c.modality === 'audio'" :src="c.url" controls style="width: 100%;"></audio>
              <pre v-else style="white-space: pre-wrap;">{{ c.url }}</pre>
              <div style="margin-top: 6px; font-size: 12px;">
                <NTag size="small">{{ c.mime }}</NTag>
                <span v-if="c.width"> · {{ c.width }}x{{ c.height }}</span>
                <span v-if="c.duration_sec"> · {{ c.duration_sec }}s</span>
                <span v-if="c.seed"> · seed={{ c.seed }}</span>
              </div>
            </NCard>
          </NGi>
        </NGrid>
      </NCard>
    </NGi>
  </NGrid>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { NAlert, NButton, NCard, NEmpty, NFormItem, NGi, NGrid, NImage, NInput, NInputNumber, NPageHeader, NSelect, NSpace, NTag } from 'naive-ui'
import { multimodalApi, type GenerateResponse, type GenerationCandidate, type MediaItem } from '../../api/multimodal'

const targetOptions = [
  { label: '图 (image)', value: 'image' },
  { label: '视频 (video)', value: 'video' },
  { label: '音频 (audio)', value: 'audio' },
  { label: '文 (text)', value: 'text' },
]

const form = reactive<{ text: string; target: 'image' | 'video' | 'audio' | 'text'; provider?: string }>({
  text: 'a cat astronaut, ultra-detailed, soft lighting',
  target: 'image',
  provider: undefined,
})

const refUrl1 = ref('stub://image/ref1.jpg')
const refUrl2 = ref('')
const refUrl3 = ref('')
const n = ref(4)
const candidates = ref<GenerationCandidate[]>([])
const providers = ref<Array<{ name: string; loaded: boolean }>>([])
const providerOptions = ref<Array<{ label: string; value: string }>>([])
const loading = ref(false)
const errMsg = ref('')

onMounted(async () => {
  try {
    const r = await multimodalApi.providers()
    providers.value = r.data.providers
    providerOptions.value = r.data.providers.map((p) => ({ label: `${p.name}${p.loaded ? '' : ' (stub)'}`, value: p.name }))
  } catch {
    providers.value = []
  }
})

async function onGenerate() {
  errMsg.value = ''
  loading.value = true
  candidates.value = []
  try {
    const refs: MediaItem[] = [refUrl1.value, refUrl2.value, refUrl3.value]
      .filter((s) => s && s.trim())
      .map((url) => ({ url }))
    const r = await multimodalApi.generate({
      text: form.text,
      target: form.target,
      ref_images: refs,
      provider: form.provider,
      params: { n: n.value },
    })
    candidates.value = r.data.candidates
  } catch (e: unknown) {
    errMsg.value = (e as Error)?.message || String(e)
  } finally {
    loading.value = false
  }
}
</script>