<template>
  <div class="character-manager">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between">
        <div>
          <NText strong style="font-size: 18px">角色管理</NText>
          <NText depth="3" style="margin-left: 8px">上传参考图 + 锁定一致性</NText>
        </div>
        <NButton type="primary" @click="openCreate">
          <template #icon><NIcon><AddOutline /></NIcon></template>
          新建角色
        </NButton>
      </NSpace>
    </NCard>

    <NGrid :cols="3" :x-gap="12" :y-gap="12" responsive="screen" :item-responsive="true">
      <NGi v-for="c in characters" :key="c.character_id" span="1 m:1 l:1">
        <NCard hoverable>
          <NSpace vertical size="small">
            <NSpace align="center" justify="space-between">
              <NText strong>{{ c.name }}</NText>
              <NTag size="small" :type="c.locked ? 'warning' : 'default'">{{ c.locked ? '已锁定' : '未锁定' }}</NTag>
            </NSpace>
            <NImage :src="c.reference_url" object-fit="cover" height="160" width="100%" preview-disabled />
            <NText depth="3" style="font-size: 12px">{{ c.description || '(无描述)' }}</NText>
            <NSpace size="small">
              <NTag v-for="t in c.tags || []" :key="t" size="tiny">{{ t }}</NTag>
            </NSpace>
            <NSpace>
              <NButton size="small" :type="c.locked ? 'warning' : 'default'" @click="toggleLock(c.character_id)">
                {{ c.locked ? '解锁' : '锁定' }}
              </NButton>
              <NButton size="small" @click="checkConsistency(c.character_id)">一致性检查</NButton>
              <NButton size="small" type="error" ghost @click="onDelete(c.character_id)">删除</NButton>
            </NSpace>
            <NAlert v-if="consistencyResults[c.character_id]" :type="consistencyResults[c.character_id].ok ? 'success' : 'warning'" style="margin-top: 8px">
              一致性: {{ (consistencyResults[c.character_id].score * 100).toFixed(1) }}% ({{ consistencyResults[c.character_id].ok ? 'OK' : '需修复' }})
            </NAlert>
          </NSpace>
        </NCard>
      </NGi>
    </NGrid>

    <NEmpty v-if="!characters.length" description="还没有角色,点击右上角新建" />

    <ModalForm v-model:show="createShow" title="新建角色" v-model="createForm" :rules="createRules" @submit="onCreate">
      <template #default="{ form: f }">
        <NFormItem label="角色 ID" path="character_id"><NInput v-model:value="(f as any).character_id" placeholder="hero, wizard, ..." /></NFormItem>
        <NFormItem label="名称" path="name"><NInput v-model:value="(f as any).name" /></NFormItem>
        <NFormItem label="参考图 URL" path="reference_url"><NInput v-model:value="(f as any).reference_url" placeholder="/characters/hero.png" /></NFormItem>
        <NFormItem label="描述" path="description"><NInput v-model:value="(f as any).description" type="textarea" :rows="2" /></NFormItem>
      </template>
    </ModalForm>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { NCard, NSpace, NText, NButton, NIcon, NImage, NTag, NEmpty, NGrid, NGi, NAlert, NFormItem, NInput, useMessage } from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
import ModalForm from '@/components/ModalForm.vue'

const message = useMessage()

interface Character {
  character_id: string
  name: string
  reference_url: string
  description?: string
  tags?: string[]
  locked?: boolean
}

const characters = ref<Character[]>([])
const consistencyResults = ref<Record<string, { score: number; ok: boolean }>>({})

const createShow = ref(false)
const createForm = reactive({ character_id: '', name: '', reference_url: '', description: '' })
const createRules = {
  character_id: { required: true, message: '请输入角色 ID', trigger: 'blur' },
  name: { required: true, message: '请输入名称', trigger: 'blur' },
  reference_url: { required: true, message: '请输入参考图 URL', trigger: 'blur' }
}

async function load() {
  // Pull from localStorage (proxy for the asset_service character pool when W1 is up).
  const raw = localStorage.getItem('iter-characters')
  if (raw) characters.value = JSON.parse(raw)
  if (!characters.value.length) {
    // seed with 2 demo characters
    characters.value = [
      { character_id: 'hero', name: 'Hero', reference_url: '/c/hero.png', description: '勇者,穿皮甲', tags: ['protagonist', 'human'], locked: true },
      { character_id: 'wizard', name: 'Wizard', reference_url: '/c/wizard.png', description: '老巫师,长白胡子', tags: ['mentor'], locked: false }
    ]
    localStorage.setItem('iter-characters', JSON.stringify(characters.value))
  }
}
function persist() { localStorage.setItem('iter-characters', JSON.stringify(characters.value)) }

function openCreate() {
  Object.assign(createForm, { character_id: '', name: '', reference_url: '', description: '' })
  createShow.value = true
}
async function onCreate() {
  characters.value.push({ ...createForm, tags: [], locked: false })
  persist()
  createShow.value = false
  message.success('角色已创建')
}
function toggleLock(id: string) {
  const c = characters.value.find(c => c.character_id === id)
  if (c) { c.locked = !c.locked; persist() }
}
function checkConsistency(id: string) {
  // Stub: real impl would call /api/v1/assets/characters/{id}/consistency_check (W1).
  const score = 0.7 + Math.random() * 0.3
  consistencyResults.value[id] = { score, ok: score >= 0.85 }
  message.info(`${id} 一致性: ${(score * 100).toFixed(1)}%`)
}
function onDelete(id: string) {
  if (!window.confirm(`确认删除 ${id} ?`)) return
  characters.value = characters.value.filter(c => c.character_id !== id)
  persist()
}

onMounted(load)
</script>

<style scoped>
.character-manager { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
</style>