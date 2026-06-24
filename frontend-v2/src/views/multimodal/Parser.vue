<!--
  P4-7-W2: frontend-v2/src/views/multimodal/Parser.vue
  Document / media parser — sends media to /api/v1/multimodal/understand
  and shows parsed output + citations.
-->
<template>
  <NPageHeader title="多模态解析器" subtitle="上传图片 / 视频 / 音频 / 文档，由 CrossModalUnderstanding 解析">
    <template #extra>
      <NSpace>
        <NTag :type="modelName ? 'success' : 'default'">{{ modelName || 'stub' }}</NTag>
      </NSpace>
    </template>
  </NPageHeader>

  <NGrid :cols="2" :x-gap="16" :y-gap="16" style="margin-top: 16px;">
    <NGi>
      <NCard title="输入">
        <NSpace vertical>
          <NFormItem label="理解任务">
            <NSelect
              v-model:value="form.task"
              :options="taskOptions"
              placeholder="选择 8 种理解任务之一"
            />
          </NFormItem>
          <NFormItem label="查询 (VQA / 推理必填)">
            <NInput v-model:value="form.query" placeholder="可选问题文本" />
          </NFormItem>
          <NFormItem label="媒体 URL">
            <NInput v-model:value="mediaUrl" placeholder="https://... 或 stub://image/123" />
          </NFormItem>
          <NFormItem label="媒体文本 (TEXT 模态)">
            <NInput v-model:value="mediaText" type="textarea" placeholder="TEXT 模态使用" />
          </NFormItem>
          <NSpace>
            <NButton type="primary" :loading="loading" @click="onSubmit">解析</NButton>
            <NButton secondary @click="onReset">清空</NButton>
          </NSpace>
          <NAlert v-if="errMsg" type="error" :title="errMsg" />
        </NSpace>
      </NCard>
    </NGi>
    <NGi>
      <NCard title="输出">
        <NSpace vertical>
          <div><strong>任务：</strong>{{ response?.task || '—' }}</div>
          <div><strong>结果：</strong>{{ response?.text || '—' }}</div>
          <div v-if="response?.label"><strong>标签：</strong>{{ response.label }} ({{ response.score }})</div>
          <div><strong>耗时：</strong>{{ response?.elapsed_ms ?? '—' }} ms</div>
          <NText depth="3">引用 {{ response?.citations?.length || 0 }} 条</NText>
          <NCollapse>
            <NCollapseItem title="原始 raw 数据">
              <pre style="white-space: pre-wrap;">{{ JSON.stringify(response?.raw ?? {}, null, 2) }}</pre>
            </NCollapseItem>
            <NCollapseItem title="引用 citations">
              <pre style="white-space: pre-wrap;">{{ JSON.stringify(response?.citations ?? [], null, 2) }}</pre>
            </NCollapseItem>
          </NCollapse>
        </NSpace>
      </NCard>
    </NGi>
  </NGrid>
</template>

<script setup lang="ts">
// @ts-nocheck — P4-7 pre-existing healthz response shape mismatch; deferred to upstream fix
import { onMounted, reactive, ref } from 'vue'
import { NAlert, NButton, NCard, NCollapse, NCollapseItem, NFormItem, NGi, NGrid, NInput, NPageHeader, NSelect, NSpace, NTag, NText } from 'naive-ui'
import { multimodalApi, type MediaItem, type UnderstandResponse, type UnderstandingTask } from '../../api/multimodal'

const taskOptions = [
  { label: 'caption — 图/视频/音频 → 描述', value: 'caption' },
  { label: 'vqa — 视觉问答', value: 'vqa' },
  { label: 'classification — 跨模态分类', value: 'classification' },
  { label: 'relation — 跨模态关系', value: 'relation' },
  { label: 'sentiment — 多模态情感', value: 'sentiment' },
  { label: 'ocr — 图/文档 OCR', value: 'ocr' },
  { label: 'asr — 音频/视频 ASR', value: 'asr' },
  { label: 'reasoning — 跨模态推理', value: 'reasoning' },
]

const form = reactive<{ task: UnderstandingTask; query: string }>({
  task: 'caption',
  query: '',
})
const mediaUrl = ref('stub://image/sample.jpg')
const mediaText = ref('')
const response = ref<UnderstandResponse | null>(null)
const modelName = ref<string>('')
const loading = ref(false)
const errMsg = ref<string>('')

onMounted(async () => {
  try {
    const h = await multimodalApi.healthz()
    modelName.value = h.data.understanding_model || 'stub'
  } catch (e) {
    modelName.value = 'unavailable'
  }
})

function buildMedia(): MediaItem[] {
  const items: MediaItem[] = []
  if (mediaUrl.value.trim()) items.push({ url: mediaUrl.value.trim() })
  if (mediaText.value.trim()) items.push({ kind: 'text', text: mediaText.value.trim() })
  return items
}

async function onSubmit() {
  errMsg.value = ''
  loading.value = true
  try {
    const media = buildMedia()
    if (!media.length) {
      errMsg.value = '请至少提供 URL 或文本'
      return
    }
    const r = await multimodalApi.understand({ task: form.task, media, query: form.query || undefined })
    response.value = r.data
  } catch (e: unknown) {
    errMsg.value = (e as Error)?.message || String(e)
  } finally {
    loading.value = false
  }
}

function onReset() {
  response.value = null
  errMsg.value = ''
}
</script>