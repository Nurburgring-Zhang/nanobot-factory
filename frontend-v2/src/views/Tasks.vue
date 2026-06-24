<template>
  <NPageHeader :title="'任务队列'" :subtitle="'Celery + Redis 任务编排'"></NPageHeader>
  <NEmpty description="W2 将接入 celery_orchestrator 实时队列 / 重试 / 优先级" style="margin-top: 80px;">
    <template #icon>
      <span style="font-size: 56px;">☰</span>
    </template>
  </NEmpty>
</template>

<script setup lang="ts">
import { NPageHeader, NEmpty } from 'naive-ui'
</script>