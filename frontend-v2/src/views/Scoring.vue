<template>
  <NPageHeader :title="'评分 / 评测'" :subtitle="'对接 scoring_service'"></NPageHeader>
  <NEmpty description="W2 将集成打分模板 / 多维评分 / 模型评测对比" style="margin-top: 80px;">
    <template #icon>
      <span style="font-size: 56px;">★</span>
    </template>
  </NEmpty>
</template>

<script setup lang="ts">
import { NPageHeader, NEmpty } from 'naive-ui'
</script>