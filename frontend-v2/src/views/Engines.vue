<template>
  <NPageHeader :title="'引擎管理'" :subtitle="'注册 / 上线 / 下线 64 个数据生产引擎'"></NPageHeader>
  <NEmpty description="W2 将集成引擎注册表 / 健康检查 / 资源占用监控" style="margin-top: 80px;">
    <template #icon>
      <span style="font-size: 56px;">◆</span>
    </template>
  </NEmpty>
</template>

<script setup lang="ts">
import { NPageHeader, NEmpty } from 'naive-ui'
</script>