<template>
  <NPageHeader :title="'计费 / 用量'" :subtitle="'AI provider 调用量与计费报表'"></NPageHeader>
  <NEmpty description="W2 将接入 billing_service + AI provider 计费记录" style="margin-top: 80px;">
    <template #icon>
      <span style="font-size: 56px;">☼</span>
    </template>
  </NEmpty>
</template>

<script setup lang="ts">
import { NPageHeader, NEmpty } from 'naive-ui'
</script>