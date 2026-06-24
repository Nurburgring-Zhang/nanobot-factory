<template>
  <NPageHeader :title="'用户管理'" :subtitle="'RBAC + SSO + GDPR'"></NPageHeader>
  <NEmpty description="W2 将集成 user_service 的增删改查 + RBAC 矩阵 + 审计日志" style="margin-top: 80px;">
    <template #icon>
      <span style="font-size: 56px;">☷</span>
    </template>
  </NEmpty>
</template>

<script setup lang="ts">
import { NPageHeader, NEmpty } from 'naive-ui'
</script>