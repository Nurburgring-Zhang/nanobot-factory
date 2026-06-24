<template>
  <NPageHeader :title="'监控 / 告警'" :subtitle="'Prometheus + Grafana 嵌入视图'"></NPageHeader>
  <NEmpty description="W2 将集成可观测性仪表盘 / 告警阈值 / 日志检索" style="margin-top: 80px;">
    <template #icon>
      <span style="font-size: 56px;">◉</span>
    </template>
  </NEmpty>
</template>

<script setup lang="ts">
import { NPageHeader, NEmpty } from 'naive-ui'
</script>