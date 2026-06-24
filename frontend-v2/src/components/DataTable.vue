<template>
  <NDataTable
    :columns="columns"
    :data="data"
    :loading="loading"
    :pagination="mergedPagination"
    :row-key="(row: T) => rowKey(row)"
    :bordered="false"
    :stripe="true"
    flex-height
    style="margin-top: 12px"
    @update:page="onPageChange"
    @update:page-size="onPageSizeChange"
  >
    <template v-if="$slots.empty && isEmpty" #empty>
      <slot name="empty" />
    </template>
  </NDataTable>
  <NAlert v-if="error" type="error" :show-icon="true" style="margin-top: 12px">
    {{ error }}
  </NAlert>
</template>

<script setup lang="ts" generic="T extends Record<string, unknown>">
import { computed } from 'vue'
import { NDataTable, NAlert, type DataTableColumns, type PaginationProps } from 'naive-ui'

interface Props {
  columns: DataTableColumns<T>
  data: T[]
  loading?: boolean
  error?: string | null
  total: number
  page?: number
  pageSize?: number
  rowKey: (row: T) => string | number
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  error: null,
  page: 1,
  pageSize: 20
})

const emit = defineEmits<{
  (e: 'update:page', value: number): void
  (e: 'update:pageSize', value: number): void
  (e: 'refresh'): void
}>()

const isEmpty = computed(() => !props.loading && props.data.length === 0)

const mergedPagination = computed<PaginationProps>(() => ({
  page: props.page,
  pageSize: props.pageSize,
  itemCount: props.total,
  showSizePicker: true,
  pageSizes: [10, 20, 50, 100],
  showQuickJumper: true,
  prefix: ({ itemCount }) => `共 ${itemCount} 条`
}))

function onPageChange(page: number) {
  emit('update:page', page)
  emit('refresh')
}

function onPageSizeChange(pageSize: number) {
  emit('update:pageSize', pageSize)
  emit('update:page', 1)
  emit('refresh')
}
</script>
