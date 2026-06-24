<template>
  <NSpace :wrap="true" align="center" style="margin-bottom: 12px">
    <NInput
      v-model:value="localKeyword"
      :placeholder="placeholder"
      clearable
      style="width: 280px"
      @keyup.enter="onSearch"
      @clear="onSearch"
    >
      <template #prefix>
        <NIcon><SearchOutline /></NIcon>
      </template>
    </NInput>
    <NButton type="primary" @click="onSearch">
      <template #icon>
        <NIcon><SearchOutline /></NIcon>
      </template>
      搜索
    </NButton>
    <NButton @click="onReset">
      <template #icon>
        <NIcon><RefreshOutline /></NIcon>
      </template>
      重置
    </NButton>
    <slot name="extra" />
  </NSpace>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { NSpace, NInput, NButton, NIcon } from 'naive-ui'
import { SearchOutline, RefreshOutline } from '@vicons/ionicons5'

interface Props {
  modelValue?: string
  placeholder?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  placeholder: '请输入搜索关键词'
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'search', value: string): void
  (e: 'reset'): void
}>()

const localKeyword = ref<string>(props.modelValue)

watch(() => props.modelValue, (v) => {
  localKeyword.value = v
})

function onSearch() {
  emit('update:modelValue', localKeyword.value)
  emit('search', localKeyword.value)
}

function onReset() {
  localKeyword.value = ''
  emit('update:modelValue', '')
  emit('reset')
}
</script>
