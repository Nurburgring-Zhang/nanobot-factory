<template>
  <NButton
    :type="type"
    :size="size"
    :ghost="ghost"
    :loading="loading"
    :disabled="disabled"
    @click="onClick"
  >
    <template v-if="icon && !loading" #icon>
      <NIcon><component :is="icon" /></NIcon>
    </template>
    <slot />
  </NButton>
</template>

<script setup lang="ts">
import { NButton, NIcon } from 'naive-ui'
import type { Component } from 'vue'

interface Props {
  type?: 'default' | 'primary' | 'success' | 'warning' | 'error' | 'info'
  size?: 'tiny' | 'small' | 'medium' | 'large'
  ghost?: boolean
  loading?: boolean
  disabled?: boolean
  icon?: Component
}

withDefaults(defineProps<Props>(), {
  type: 'default',
  size: 'small',
  ghost: false,
  loading: false,
  disabled: false
})

const emit = defineEmits<{
  (e: 'click', ev: MouseEvent): void
}>()

function onClick(ev: MouseEvent) {
  emit('click', ev)
}
</script>
