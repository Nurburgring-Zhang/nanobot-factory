<template>
  <NPageHeader :title="'数据集管理'" :subtitle="'管理图片 / 编辑 / 视频 / 短剧 / 绘本 数据资产'">
    <template #extra>
      <NSpace>
        <NButton type="primary" disabled>+ 新建数据集</NButton>
        <NButton secondary disabled>导入</NButton>
      </NSpace>
    </template>
  </NPageHeader>
  <NEmpty
    description="W2 将集成 dataset_service 的真实数据模型与列表 / 过滤 / 上传流程"
    style="margin-top: 80px;"
  >
    <template #icon>
      <span style="font-size: 56px;">▤</span>
    </template>
  </NEmpty>
</template>

<script setup lang="ts">
import { NPageHeader, NSpace, NButton, NEmpty } from 'naive-ui'
</script>