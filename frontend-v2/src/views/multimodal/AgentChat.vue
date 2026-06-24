<!--
  P4-7-W2: frontend-v2/src/views/multimodal/AgentChat.vue
  MultimodalAgent — chat with the multimodal agent; attach any media,
  agent picks tools, returns text + tool calls + memory_ids.
-->
<template>
  <NPageHeader title="多模态 Agent" subtitle="输入文本 + 任意模态媒体，Agent 自动选择工具">
    <template #extra>
      <NSpace>
        <NTag :type="tools.length ? 'success' : 'default'">{{ tools.length }} tools</NTag>
        <NTag>{{ sessionId }}</NTag>
      </NSpace>
    </NPageHeader>

  <NGrid :cols="3" :x-gap="16" :y-gap="16" style="margin-top: 16px;">
    <NGi :span="1">
      <NCard title="输入">
        <NSpace vertical>
          <NFormItem label="prompt">
            <NInput v-model:value="prompt" type="textarea" :rows="4" placeholder="请描述这张图并搜索相似内容" />
          </NFormItem>
          <NFormItem label="媒体 URL">
            <NInput v-model:value="mediaUrl" placeholder="stub://image/upload.jpg" />
          </NFormItem>
          <NFormItem label="session_id">
            <NInput v-model:value="sessionId" />
          </NFormItem>
          <NFormItem>
            <NCheckbox v-model:checked="saveMemory">保存到 MemoryPalace</NCheckbox>
          </NFormItem>
          <NButton type="primary" :loading="loading" @click="onInvoke">调用</NButton>
          <NAlert v-if="errMsg" type="error" :title="errMsg" />
        </NSpace>
      </NCard>

      <NCard title="可用工具" style="margin-top: 16px;">
        <NList>
          <NListItem v-for="t in tools" :key="t.name">
            <NThing :title="t.name" :description="t.description" />
          </NListItem>
        </NList>
      </NCard>
    </NGi>

    <NGi :span="2">
      <NCard title="Agent 输出">
        <NSpace vertical>
          <div><strong>request_id:</strong> {{ response?.request_id }}</div>
          <div><strong>text:</strong> <pre style="white-space: pre-wrap;">{{ response?.text }}</pre></div>
          <div><strong>tool_calls:</strong></div>
          <NList bordered>
            <NListItem v-for="(tc, i) in response?.tool_calls || []" :key="i">
              <NThing :title="tc.tool" :description="JSON.stringify(tc.result).slice(0, 300)">
                args: {{ JSON.stringify(tc.args) }}
              </NThing>
            </NListItem>
          </NList>
          <div v-if="response?.memory_ids?.length">
            <strong>memory_ids:</strong>
            <NTag v-for="m in response.memory_ids" :key="m" style="margin-right: 6px;">{{ m }}</NTag>
          </div>
          <div><strong>elapsed_ms:</strong> {{ response?.elapsed_ms }}</div>
        </NSpace>
      </NCard>
    </NGi>
  </NGrid>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NAlert, NButton, NCard, NCheckbox, NFormItem, NGi, NGrid, NInput, NList, NListItem, NPageHeader, NSpace, NTag, NThing } from 'naive-ui'
import { multimodalApi, type AgentInvokeResponse } from '../../api/multimodal'

const prompt = ref('请描述这张图')
const mediaUrl = ref('stub://image/upload.jpg')
const sessionId = ref('session-' + Math.random().toString(36).slice(2, 8))
const saveMemory = ref(true)
const response = ref<AgentInvokeResponse | null>(null)
const tools = ref<Array<{ name: string; description: string }>>([])
const loading = ref(false)
const errMsg = ref('')

onMounted(async () => {
  try {
    const r = await multimodalApi.agentTools()
    tools.value = r.data.tools
  } catch (e: unknown) {
    errMsg.value = (e as Error)?.message || String(e)
  }
})

async function onInvoke() {
  errMsg.value = ''
  loading.value = true
  response.value = null
  try {
    const r = await multimodalApi.agentInvoke({
      prompt: prompt.value,
      media: mediaUrl.value.trim() ? [{ url: mediaUrl.value.trim() }] : [],
      session_id: sessionId.value,
      save_to_memory: saveMemory.value,
    })
    response.value = r.data
  } catch (e: unknown) {
    errMsg.value = (e as Error)?.message || String(e)
  } finally {
    loading.value = false
  }
}
</script>