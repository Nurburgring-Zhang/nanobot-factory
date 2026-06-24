<template>
  <NPageHeader :title="'标注工作台'" :subtitle="'对接 annotation_service 引擎'">
  </NPageHeader>
  <NEmpty description="W2 将接入任务分配 / Canvas 标注 / 快捷键 / 进度同步" style="margin-top: 80px;">
    <template #icon>
      <span style="font-size: 56px;">✎</span>
    </template>
  </NEmpty>
</template>

<script setup lang="ts">
import { NPageHeader, NEmpty } from 'naive-ui'
</script>