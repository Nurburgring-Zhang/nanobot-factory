<template>
  <NPageHeader :title="'系统设置'" :subtitle="'平台配置 / API 密钥 / 第三方集成'"></NPageHeader>
  <NEmpty description="W2 将集成配置中心 / 密钥管理 / 功能开关" style="margin-top: 80px;">
    <template #icon>
      <span style="font-size: 56px;">⚙</span>
    </template>
  </NEmpty>
</template>

<script setup lang="ts">
import { NPageHeader, NEmpty } from 'naive-ui'
</script>