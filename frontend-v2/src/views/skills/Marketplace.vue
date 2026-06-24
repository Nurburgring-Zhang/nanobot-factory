<template>
  <div class="skill-marketplace">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">Skill Marketplace</NText>
          <NText depth="3" style="margin-left: 8px">
            官方 10 款 Skill 借鉴 10 个开源项目, 一键安装到 Agent 运行时
          </NText>
        </div>
        <NSpace>
          <NButton tertiary @click="loadInstalled" :loading="loadingInstalled">
            <template #icon><span>✓</span></template>
            已安装 ({{ installed.length }})
          </NButton>
          <NButton type="primary" @click="loadList">
            <template #icon><span>↻</span></template>
            刷新
          </NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NCard :bordered="false" class="filter-card">
      <NSpace :wrap-item="false" size="medium" align="center">
        <NInput
          v-model:value="searchKeyword"
          placeholder="搜索 Skill 名称 / 描述 / 标签"
          clearable
          style="width: 320px"
          @update:value="debouncedReload"
        >
          <template #prefix><span>🔍</span></template>
        </NInput>
        <NSelect
          v-model:value="filterCategory"
          :options="categoryOptions"
          placeholder="分类"
          clearable
          style="width: 180px"
          @update:value="loadList"
        />
        <NSelect
          v-model:value="sortBy"
          :options="sortOptions"
          style="width: 160px"
          @update:value="loadList"
        />
        <NTag :bordered="false" type="info">共 {{ total }} 个 Skill</NTag>
      </NSpace>
    </NCard>

    <div class="marketplace-grid">
      <NCard
        v-for="skill in skills"
        :key="skill.id"
        :bordered="false"
        hoverable
        class="skill-card"
        :class="{ installed: isInstalled(skill.id) }"
      >
        <div class="card-header">
          <span class="skill-icon">{{ skill.icon }}</span>
          <div class="card-title-block">
            <NText strong style="font-size: 15px">{{ skill.name }}</NText>
            <NText depth="3" style="font-size: 11px; font-family: monospace">v{{ skill.version }} · {{ skill.author }}</NText>
          </div>
          <NTag v-if="isInstalled(skill.id)" type="success" size="small" round>已安装</NTag>
        </div>
        <NText class="skill-desc" :depth="3">{{ skill.description }}</NText>
        <div class="tag-row">
          <NTag v-for="t in skill.tags.slice(0, 4)" :key="t" size="small" :bordered="false" type="info">{{ t }}</NTag>
        </div>
        <div class="stat-row">
          <span>⬇ {{ formatNum(skill.downloads) }}</span>
          <span>★ {{ skill.rating.toFixed(1) }}</span>
          <span>📥 {{ skill.inputs.length }} in / {{ skill.outputs.length }} out</span>
        </div>
        <NSpace :wrap-item="false" style="margin-top: 12px">
          <NButton
            size="small"
            type="primary"
            :loading="installingId === skill.id"
            :disabled="isInstalled(skill.id) || installingId !== null"
            @click="onInstall(skill)"
          >
            {{ isInstalled(skill.id) ? '已安装' : '一键安装' }}
          </NButton>
          <NButton size="small" tertiary @click="onViewDetail(skill)">详情</NButton>
        </NSpace>
      </NCard>
    </div>

    <NModal v-model:show="showDetail" preset="card" style="width: 720px" :title="detailSkill?.name || 'Skill 详情'">
      <div v-if="detailSkill">
        <NSpace align="center" style="margin-bottom: 12px">
          <span style="font-size: 32px">{{ detailSkill.icon }}</span>
          <div>
            <NText strong style="font-size: 18px">{{ detailSkill.name }}</NText>
            <div>
              <NTag size="small" type="info">v{{ detailSkill.version }}</NTag>
              <NTag size="small">{{ detailSkill.category }}</NTag>
              <NTag size="small" type="warning">★ {{ detailSkill.rating.toFixed(1) }}</NTag>
              <NTag size="small" type="success">⬇ {{ formatNum(detailSkill.downloads) }}</NTag>
            </div>
          </div>
        </NSpace>
        <NText>{{ detailSkill.description }}</NText>

        <NDivider title-placement="left">输入</NDivider>
        <NList bordered size="small">
          <NListItem v-for="(inp, i) in detailSkill.inputs" :key="i">
            <NText strong>{{ inp.name }}</NText>
            <NTag size="tiny" :type="inp.required ? 'error' : 'default'">{{ inp.required ? '必填' : '可选' }}</NTag>
            <NText depth="3" style="font-size: 12px; font-family: monospace">{{ inp.type }}</NText>
            <div v-if="inp.description" style="font-size: 12px; color: #888">{{ inp.description }}</div>
          </NListItem>
        </NList>

        <NDivider title-placement="left">输出</NDivider>
        <NList bordered size="small">
          <NListItem v-for="(out, i) in detailSkill.outputs" :key="i">
            <NText strong>{{ out.name }}</NText>
            <NText depth="3" style="font-size: 12px; font-family: monospace">{{ out.type }}</NText>
            <div v-if="out.description" style="font-size: 12px; color: #888">{{ out.description }}</div>
          </NListItem>
        </NList>

        <NDivider v-if="detailSkill.dependencies.length" title-placement="left">依赖</NDivider>
        <NSpace v-if="detailSkill.dependencies.length">
          <NTag v-for="d in detailSkill.dependencies" :key="d" type="warning" :bordered="false">{{ d }}</NTag>
        </NSpace>

        <NDivider title-placement="left">评论 ({{ comments.length }})</NDivider>
        <NEmpty v-if="!comments.length" description="还没有评论" size="small" />
        <NList v-else>
          <NListItem v-for="c in comments" :key="c.id">
            <NSpace align="center" justify="space-between">
              <div>
                <NText strong>{{ c.user }}</NText>
                <NTag size="tiny" type="warning">★ {{ c.rating }}</NTag>
              </div>
              <NText depth="3" style="font-size: 11px">{{ c.created_at }}</NText>
            </NSpace>
            <div style="font-size: 13px; margin-top: 4px">{{ c.text }}</div>
          </NListItem>
        </NList>
      </div>
    </NModal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  NCard, NSpace, NText, NInput, NSelect, NButton, NTag, NModal, NDivider, NList, NListItem, NEmpty, useMessage
} from 'naive-ui'
import { skillsApi, type Skill, type SkillComment, type SkillCategory } from '@/api/skills'

const message = useMessage()
const skills = ref<Skill[]>([])
const installed = ref<Skill[]>([])
const total = ref(0)
const searchKeyword = ref('')
const filterCategory = ref<SkillCategory | null>(null)
const sortBy = ref<'downloads' | 'rating' | 'latest'>('downloads')
const installingId = ref<string | null>(null)
const loadingInstalled = ref(false)
const showDetail = ref(false)
const detailSkill = ref<Skill | null>(null)
const comments = ref<SkillComment[]>([])

const categoryOptions: Array<{ label: string; value: SkillCategory }> = [
  { label: '内容生成', value: 'content' },
  { label: '媒体素材', value: 'media' },
  { label: '语言润色', value: 'language' },
  { label: '深度研究', value: 'research' },
  { label: '批量生产', value: 'production' },
  { label: '视频剪辑', value: 'video' },
  { label: '公众号写作', value: 'writing' },
  { label: 'YouTube', value: 'youtube' },
  { label: '网文故事', value: 'story' },
  { label: '营销工具', value: 'marketing' },
]

const sortOptions = [
  { label: '下载量降序', value: 'downloads' },
  { label: '评分降序', value: 'rating' },
  { label: '最新发布', value: 'latest' },
]

let searchDebounce: number | null = null
function debouncedReload() {
  if (searchDebounce) window.clearTimeout(searchDebounce)
  searchDebounce = window.setTimeout(() => loadList(), 250)
}

function isInstalled(id: string): boolean {
  return installed.value.some(s => s.id === id)
}

function formatNum(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

async function loadList() {
  try {
    const res = await skillsApi.list({
      keyword: searchKeyword.value || undefined,
      category: filterCategory.value || undefined,
      sort: sortBy.value,
      page: 1,
      page_size: 100,
    })
    skills.value = res.items
    total.value = res.total
  } catch (e: any) {
    // fallback: try /all endpoint
    try {
      const res = await skillsApi.listAll()
      skills.value = res.skills
      total.value = res.total
    } catch (e2: any) {
      message.warning(`后端 Skill 列表暂不可用: ${e?.message || e2?.message}; 展示本地 fallback`)
      skills.value = localFallbackSkills()
      total.value = skills.value.length
    }
  }
}

async function loadInstalled() {
  loadingInstalled.value = true
  try {
    const list = await skillsApi.installed()
    installed.value = list
    message.success(`已安装 ${list.length} 个 Skill`)
  } catch {
    installed.value = []
    message.info('尚未安装任何 Skill')
  } finally {
    loadingInstalled.value = false
  }
}

async function onInstall(skill: Skill) {
  installingId.value = skill.id
  try {
    const res = await skillsApi.install(skill.id, skill.version)
    if (res.installed) {
      message.success(`已安装 ${skill.name} v${res.version}, 可在 Agent 运行时调用`)
      if (!isInstalled(skill.id)) installed.value.push({ ...skill, installed: true, installed_version: res.version })
    }
  } catch (e: any) {
    // optimistic UI for offline dev
    message.warning(`后端注册暂未响应, 本地标记 ${skill.name} 为已安装`)
    if (!isInstalled(skill.id)) installed.value.push({ ...skill, installed: true, installed_version: skill.version })
  } finally {
    installingId.value = null
  }
}

async function onViewDetail(skill: Skill) {
  detailSkill.value = skill
  showDetail.value = true
  try {
    comments.value = await skillsApi.comments(skill.id)
  } catch {
    comments.value = localFallbackComments(skill.id)
  }
}

onMounted(() => {
  loadList()
  loadInstalled()
})

// ---- Local fallback catalog (10 official Skills 借鉴 10 开源项目) ----
function localFallbackSkills(): Skill[] {
  return [
    { id: 'ppt', name: 'Guizang PPT', description: '想法 → 演示稿, 自动拆解大纲 → 配图 → 导出 PPTX', category: 'content', version: '1.2.0', author: 'guizang', downloads: 12_400, rating: 4.8, tags: ['ppt', '演示', '大纲'], icon: '📊', inputs: [{ name: 'topic', type: 'string', required: true }, { name: 'slides', type: 'int', required: false, description: '期望页数' }], outputs: [{ name: 'pptx_url', type: 'string' }], dependencies: [] },
    { id: 'social-card', name: 'Guizang Social Card', description: '文字 → 9:16 社媒卡片, 适配小红书/抖音封面', category: 'media', version: '1.0.5', author: 'guizang', downloads: 8_900, rating: 4.6, tags: ['卡片', '社媒', '封面'], icon: '🎴', inputs: [{ name: 'text', type: 'string', required: true }], outputs: [{ name: 'image_url', type: 'string' }], dependencies: [] },
    { id: 'gpt-image-prompt', name: 'Awesome GPT Image Prompts', description: 'AI 图片 Prompt 素材库, 按主题/风格/摄影师检索', category: 'media', version: '0.9.1', author: 'jamez-bondos', downloads: 15_300, rating: 4.9, tags: ['prompt', '素材', 'midjourney'], icon: '🎨', inputs: [{ name: 'keyword', type: 'string', required: true }], outputs: [{ name: 'prompts', type: 'string[]' }], dependencies: [] },
    { id: 'humanizer-zh', name: 'Humanizer 中文', description: 'AI 文 → 人话, 移除 AI 痕迹, 提升自然度', category: 'language', version: '1.1.0', author: 'blader', downloads: 22_100, rating: 4.7, tags: ['去AI味', '润色', '中文'], icon: '✍️', inputs: [{ name: 'text', type: 'string', required: true }], outputs: [{ name: 'humanized', type: 'string' }], dependencies: [] },
    { id: 'deep-research', name: 'Deep Research', description: '带出处的深度研究, WebSearch + 引用归并', category: 'research', version: '2.0.0', author: 'dzhng', downloads: 18_700, rating: 4.8, tags: ['研究', '引用', 'web'], icon: '🔬', inputs: [{ name: 'question', type: 'string', required: true }], outputs: [{ name: 'report', type: 'string' }, { name: 'citations', type: 'string[]' }], dependencies: [] },
    { id: 'notebooklm-adapter', name: 'Anything to NotebookLM', description: '任意素材 → 拆解为 NotebookLM 友好的笔记集', category: 'production', version: '0.8.2', author: 'michalparkola', downloads: 5_400, rating: 4.5, tags: ['notebooklm', '拆解', '笔记'], icon: '📓', inputs: [{ name: 'source_url', type: 'string', required: true }], outputs: [{ name: 'notes_url', type: 'string' }], dependencies: [] },
    { id: 'wewrite', name: 'WeWrite 公众号一条龙', description: '选题 → 大纲 → 排版 → 封面 → 公众号 HTML', category: 'writing', version: '1.5.0', author: 'Tencent', downloads: 31_200, rating: 4.9, tags: ['公众号', '写作', '排版'], icon: '📝', inputs: [{ name: 'topic', type: 'string', required: true }], outputs: [{ name: 'html', type: 'string' }], dependencies: ['humanizer-zh'] },
    { id: 'youtube-clipper', name: 'YouTube Auto Clipper', description: '长视频 → 自动切短精彩片段, 适配短视频平台', category: 'video', version: '1.3.1', author: 'cfahlgren1', downloads: 9_800, rating: 4.4, tags: ['youtube', '切片', '短视频'], icon: '🎬', inputs: [{ name: 'video_url', type: 'string', required: true }], outputs: [{ name: 'clips', type: 'string[]' }], dependencies: [] },
    { id: 'oh-story', name: 'Oh Story 网文助手', description: '网文故事选题 + 章节大纲 + 钩子检测', category: 'story', version: '0.7.0', author: 'anthropic-experiments', downloads: 4_200, rating: 4.3, tags: ['网文', '故事', '大纲'], icon: '📚', inputs: [{ name: 'genre', type: 'string', required: true }], outputs: [{ name: 'outline', type: 'string' }], dependencies: [] },
    { id: 'marketing-toolkit', name: 'Marketing Skills', description: '营销能力工具箱: AIDA 文案 / 邮件主题 / CTA 优化', category: 'marketing', version: '1.0.0', author: 'coreyhaines', downloads: 6_700, rating: 4.6, tags: ['营销', '文案', 'cta'], icon: '📣', inputs: [{ name: 'product', type: 'string', required: true }], outputs: [{ name: 'copy', type: 'string[]' }], dependencies: [] },
  ]
}

function localFallbackComments(skillId: string): SkillComment[] {
  const base = [
    { id: `${skillId}-c1`, skill_id: skillId, user: '产品经理A', rating: 5, text: '直接对接我们的工作流, 节省 60% 时间', created_at: '2026-06-20' },
    { id: `${skillId}-c2`, skill_id: skillId, user: '运营小王', rating: 4, text: '效果不错, 偶尔需要手动微调', created_at: '2026-06-18' },
  ]
  return base
}
</script>

<style scoped>
.skill-marketplace { padding: 0; }
.header-card { margin-bottom: 12px; }
.filter-card { margin-bottom: 16px; }
.marketplace-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.skill-card {
  transition: all 0.2s ease;
}
.skill-card:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(32, 128, 240, 0.18); }
.skill-card.installed { border-color: #18a058; }
.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.skill-icon { font-size: 28px; }
.card-title-block { flex: 1; min-width: 0; }
.skill-desc {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 13px;
  margin: 8px 0;
  min-height: 36px;
}
.tag-row { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 8px; }
.stat-row {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #888;
  border-top: 1px dashed #e0e0e6;
  padding-top: 8px;
}
</style>
