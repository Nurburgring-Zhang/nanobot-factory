<template>
  <NPageHeader :title="'审核 / QA'" :subtitle="'对接 review_service'"></NPageHeader>
  <NEmpty description="W2 将集成审核队列 / 评分卡 / 通过 / 驳回流" style="margin-top: 80px;">
    <template #icon>
      <span style="font-size: 56px;">✓</span>
    </template>
  </NEmpty>
</template>

<script setup lang="ts">
import { NPageHeader, NEmpty } from 'naive-ui'
</script>