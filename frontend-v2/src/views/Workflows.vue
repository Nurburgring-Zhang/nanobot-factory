<template>
  <div class="workflows">
    <NPageHeader :title="'工作流编排'" :subtitle="'基于 Vue Flow 的可视化引擎编排'"></NPageHeader>
    <NCard class="flow-card" title="示例工作流">
      <div class="flow-host">
        <VueFlow
          v-model:nodes="nodes"
          v-model:edges="edges"
          :default-viewport="{ zoom: 1, x: 0, y: 0 }"
          :fit-view-on-init="true"
        >
          <template #node-default="{ data }">
            <div class="node-default">{{ data.label }}</div>
          </template>
          <Background pattern-color="#aaa" :gap="16" />
          <Controls />
          <MiniMap />
        </VueFlow>
      </div>
    </NCard>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { NPageHeader, NCard } from 'naive-ui'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

// Vue Flow options — minimal demo for W1; W2 will load workflow templates from backend
const nodes = ref([
  { id: '1', type: 'input', position: { x: 60, y: 80 }, data: { label: '源数据' } },
  { id: '2', position: { x: 240, y: 80 }, data: { label: '清洗' } },
  { id: '3', position: { x: 420, y: 80 }, data: { label: '标注' } },
  { id: '4', position: { x: 600, y: 80 }, data: { label: '审核' } },
  { id: '5', type: 'output', position: { x: 780, y: 80 }, data: { label: '入库' } }
])

const edges = ref([
  { id: 'e1-2', source: '1', target: '2', animated: true },
  { id: 'e2-3', source: '2', target: '3' },
  { id: 'e3-4', source: '3', target: '4' },
  { id: 'e4-5', source: '4', target: '5' }
])
</script>

<style scoped>
.workflows {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: calc(100vh - 104px);
}
.flow-card {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.flow-host {
  flex: 1;
  min-height: 480px;
  width: 100%;
}
.node-default {
  padding: 8px 12px;
  border-radius: 4px;
  background: #fff;
  border: 1px solid #2080f0;
  font-size: 13px;
  color: #2080f0;
}
</style>