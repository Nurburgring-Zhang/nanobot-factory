<template>
  <NModal
    :show="show"
    :title="title"
    :preset="undefined"
    :mask-closable="false"
    :closable="true"
    style="width: 520px"
    @update:show="(v: boolean) => emit('update:show', v)"
  >
    <NCard :title="title" :bordered="false" size="small">
      <NForm ref="formRef" :model="form" :rules="rules" label-placement="top">
        <slot :form="form" />
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="onCancel">取消</NButton>
          <NButton type="primary" :loading="submitting" @click="onSubmit">
            {{ submitText }}
          </NButton>
        </NSpace>
      </template>
    </NCard>
  </NModal>
</template>

<script setup lang="ts" generic="T extends Record<string, unknown>">
import { ref, watch } from 'vue'
import { NModal, NCard, NForm, NButton, NSpace, type FormInst, type FormRules } from 'naive-ui'

interface Props {
  show: boolean
  title: string
  modelValue: T
  rules?: FormRules
  submitText?: string
  submitting?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  rules: () => ({}),
  submitText: '保存',
  submitting: false
})

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'update:modelValue', value: T): void
  (e: 'submit', value: T): void
  (e: 'cancel'): void
}>()

const formRef = ref<FormInst | null>(null)
const form = ref<T>({ ...props.modelValue })

watch(
  () => props.modelValue,
  (v) => {
    form.value = { ...v }
  },
  { deep: true }
)

function onCancel() {
  emit('cancel')
  emit('update:show', false)
}

async function onSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
    emit('update:modelValue', { ...form.value })
    emit('submit', { ...form.value })
  } catch {
    // validation errors handled by Naive UI
  }
}
</script>
