<!--
  P4-7-W2: frontend-v2/src/views/multimodal/SearchRAG.vue
  MultimodalRAG — index media, then search by text or by image.
-->
<template>
  <NPageHeader title="跨模态 RAG" subtitle="向 MultimodalRAG 索引多模态媒体，再以文本 / 图查询">
    <template #extra>
      <NTag>{{ indexedCount }} items indexed</NTag>
    </template>
  </NPageHeader>

  <NTabs type="line" animated style="margin-top: 16px;">
    <NTabPane name="index" tab="1. 索引">
      <NCard title="向 RAG 添加媒体">
        <NSpace vertical>
          <NFormItem label="媒体 URL (一行一条)">
            <NInput v-model:value="indexUrls" type="textarea" :rows="4" placeholder="stub://image/a.jpg&#10;stub://doc/report.pdf" />
          </NFormItem>
          <NSpace>
            <NButton type="primary" :loading="indexing" @click="onIndex">索引</NButton>
            <NButton secondary @click="onClearIndex">清空</NButton>
          </NSpace>
          <NText v-if="lastIndexMsg">{{ lastIndexMsg }}</NText>
        </NSpace>
      </NCard>
    </NTabPane>

    <NTabPane name="search" tab="2. 检索">
      <NCard title="RAG 检索">
        <NSpace vertical>
          <NFormItem label="查询文本">
            <NInput v-model:value="queryText" placeholder="a robot painting the sunset" />
          </NFormItem>
          <NFormItem label="或查询 URL (image/video/audio/document)">
            <NInput v-model:value="queryUrl" placeholder="stub://image/query.jpg" />
          </NFormItem>
          <NFormItem label="top_k">
            <NInputNumber v-model:value="topK" :min="1" :max="20" />
          </NFormItem>
          <NButton type="primary" :loading="searching" @click="onSearch">检索</NButton>
          <NAlert v-if="errMsg" type="error" :title="errMsg" />
          <NList bordered v-if="hits.length">
            <NListItem v-for="(h, i) in hits" :key="i">
              <NThing :title="`Hit ${i + 1}`" :description="(h as any).chunk?.slice(0, 200)">
                score: {{ (h as any).score }}
              </NThing>
            </NListItem>
          </NList>
        </NSpace>
      </NCard>
    </NTabPane>
  </NTabs>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { NAlert, NButton, NCard, NFormItem, NInput, NInputNumber, NList, NListItem, NPageHeader, NSpace, NTabPane, NTabs, NTag, NText, NThing } from 'naive-ui'
import { multimodalApi } from '../../api/multimodal'

const indexUrls = ref('stub://image/sample1.jpg\nstub://doc/sample2.pdf')
const queryText = ref('a robot painting the sunset')
const queryUrl = ref('')
const topK = ref(5)
const indexedCount = ref(0)
const hits = ref<Array<Record<string, unknown>>>([])
const indexing = ref(false)
const searching = ref(false)
const errMsg = ref('')
const lastIndexMsg = ref('')

async function onIndex() {
  errMsg.value = ''
  indexing.value = true
  try {
    const urls = indexUrls.value.split('\n').map((s) => s.trim()).filter(Boolean)
    const media = urls.map((url) => ({ url }))
    const r = await multimodalApi.ragIndex({ media })
    indexedCount.value += r.data.indexed
    lastIndexMsg.value = `Indexed ${r.data.indexed} items`
  } catch (e: unknown) {
    errMsg.value = (e as Error)?.message || String(e)
  } finally {
    indexing.value = false
  }
}

function onClearIndex() {
  indexedCount.value = 0
  lastIndexMsg.value = ''
}

async function onSearch() {
  errMsg.value = ''
  hits.value = []
  searching.value = true
  try {
    const req: { query?: string; media?: { url: string }; top_k: number } = { top_k: topK.value }
    if (queryText.value.trim()) req.query = queryText.value.trim()
    if (queryUrl.value.trim()) req.media = { url: queryUrl.value.trim() }
    if (!req.query && !req.media) {
      errMsg.value = '请填写查询文本或 URL'
      return
    }
    const r = await multimodalApi.ragSearch(req)
    hits.value = r.data.hits
  } catch (e: unknown) {
    errMsg.value = (e as Error)?.message || String(e)
  } finally {
    searching.value = false
  }
}
</script>