<template>
  <div class="operator-market">
    <n-card title="Operator Marketplace" :bordered="false">
      <n-space vertical>
        <n-space>
          <n-input v-model:value="query" placeholder="Search operators..." clearable style="width: 280px" @update:value="reload" />
          <n-select v-model:value="category" :options="categoryOptions" placeholder="All categories" clearable style="width: 200px" @update:value="reload" />
          <n-tag :type="summary.total >= 200 ? 'success' : 'warning'">
            {{ summary.total }} operators
          </n-tag>
        </n-space>
        <n-grid :cols="4" :x-gap="12" :y-gap="12">
          <n-gi v-for="op in items" :key="op.id">
            <n-card size="small" hoverable :style="{ borderLeft: `4px solid ${op.color}` }">
              <template #header>
                <n-space align="center">
                  <span style="font-size: 18px">{{ op.icon }}</span>
                  <span>{{ op.name }}</span>
                </n-space>
              </template>
              <template #header-extra>
                <n-tag size="small" :type="tagFor(op.category)">{{ op.category }}</n-tag>
              </template>
              <div style="font-size: 12px; color: #666; min-height: 40px">{{ op.description }}</div>
              <n-space size="small" style="margin-top: 8px">
                <n-tag v-for="t in op.tags.slice(0, 4)" :key="t" size="tiny">{{ t }}</n-tag>
              </n-space>
              <template #footer>
                <n-space justify="space-between" align="center">
                  <span style="font-size: 11px; color: #888">v{{ op.latest }} · {{ op.version_count }} versions</span>
                  <n-button size="tiny" @click="showSchema(op.id)">schema</n-button>
                </n-space>
              </template>
            </n-card>
          </n-gi>
        </n-grid>
        <n-empty v-if="items.length === 0" description="No operators" />
      </n-space>
    </n-card>
    <n-modal v-model:show="showSchemaModal" preset="card" title="Operator schema" style="width: 600px">
      <pre v-if="schema" style="font-size: 12px; background: #f5f5f5; padding: 8px; border-radius: 4px;">{{ schemaText }}</pre>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { NCard, NSpace, NInput, NSelect, NTag, NGrid, NGi, NEmpty, NButton, NModal } from 'naive-ui'
import { listOperators, operatorSummary, operatorCategories, operatorSchema, type OperatorItem, type OperatorSchema } from '@/api/workflow_v2'

const items = ref<OperatorItem[]>([])
const summary = ref({ total: 0, per_category: {} as Record<string, number>, categories: [] as string[] })
const query = ref('')
const category = ref<string | null>(null)
const categoryOptions = ref<{ label: string, value: string }[]>([])
const schema = ref<OperatorSchema | null>(null)
const showSchemaModal = ref(false)

const schemaText = computed(() => JSON.stringify(schema.value, null, 2))

onMounted(async () => {
  await reload()
  summary.value = await operatorSummary()
  const cats = await operatorCategories()
  categoryOptions.value = cats.items.map(c => ({ label: `${c.name} (${c.count})`, value: c.name }))
})

async function reload() {
  items.value = (await listOperators(query.value, category.value || undefined)).items
}

async function showSchema(id: string) {
  try {
    schema.value = await operatorSchema(id)
    showSchemaModal.value = true
  } catch (e) { /* ignore */ }
}

function tagFor(c: string) {
  switch (c) {
    case 'cleaning': return 'success'
    case 'scoring': return 'warning'
    case 'annotation': return 'info'
    case 'editor': return 'error'
    case 'generator': return 'primary'
    case 'agent': return 'default'
    case 'evaluation': return 'success'
    case 'export': return 'warning'
    default: return 'default'
  }
}
</script>

<style scoped>
.operator-market { padding: 16px; }
</style>
