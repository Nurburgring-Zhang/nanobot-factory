<template>
  <div class="wiki-list">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">Wiki (Obsidian-style)</NText>
          <NText depth="3" style="margin-left: 8px">页面按 tag 过滤, Markdown + [[link]] 反向链接</NText>
        </div>
        <NSpace>
          <NInput v-model:value="keyword" placeholder="搜索 Wiki..." size="small" style="width: 240px" @update:value="reload" clearable />
          <NSelect v-model:value="tagFilter" :options="tagOptions" placeholder="按 tag 过滤" size="small" clearable style="width: 180px" @update:value="reload" />
          <NButton type="primary" size="small" @click="gotoNew">+ 新建页面</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <div class="wiki-grid">
      <NCard v-for="p in pages" :key="p.slug" hoverable :bordered="false" class="page-card" @click="gotoEdit(p.slug)">
        <NText strong style="font-size: 15px">{{ p.title }}</NText>
        <NText depth="3" style="font-size: 11px">/{{ p.slug }} · {{ p.author }} · {{ p.word_count }} 字</NText>
        <div class="page-preview">{{ truncate(stripMd(p.content_markdown), 120) }}</div>
        <NSpace>
          <NTag v-for="t in p.tags" :key="t" size="tiny" :bordered="false" type="info">#{{ t }}</NTag>
        </NSpace>
        <div class="page-stats">
          <NText depth="3" style="font-size: 11px">
            ↗ {{ p.outgoing_links.length }} 链出 · ↩ {{ p.backlinks.length }} 反链 · 更新 {{ p.updated_at }}
          </NText>
        </div>
      </NCard>
    </div>
    <NEmpty v-if="!pages.length && !loading" description="无 Wiki 页面" style="margin-top: 32px" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NCard, NSpace, NText, NInput, NSelect, NButton, NTag, NEmpty, useMessage } from 'naive-ui'
import { obsidianApi, type WikiPage, type WikiTag } from '@/api/obsidian'

const router = useRouter()
const message = useMessage()
const pages = ref<WikiPage[]>([])
const tags = ref<WikiTag[]>([])
const keyword = ref('')
const tagFilter = ref<string | null>(null)
const loading = ref(false)

const tagOptions = ref<Array<{ label: string; value: string }>>([])

function truncate(s: string, n: number) { return s.length > n ? s.slice(0, n) + '...' : s }
function stripMd(s: string) { return s.replace(/[#*`>\-\[\]\(\)]/g, '').replace(/\s+/g, ' ').trim() }

async function reload() {
  loading.value = true
  try {
    const res = await obsidianApi.listPages({ tag: tagFilter.value || undefined, keyword: keyword.value || undefined, page: 1, page_size: 50 })
    pages.value = res.pages
  } catch (e: any) {
    pages.value = localFallback()
    message.warning(`后端 Wiki 列表暂不可用, 展示本地示例: ${e?.message || ''}`)
  } finally {
    loading.value = false
  }
}

async function loadTags() {
  try {
    tags.value = await obsidianApi.listTags()
    tagOptions.value = tags.value.map(t => ({ label: `#${t.name} (${t.count})`, value: t.name }))
  } catch {
    tagOptions.value = [
      { label: '#product (5)', value: 'product' },
      { label: '#docs (4)', value: 'docs' },
      { label: '#ops (3)', value: 'ops' },
    ]
  }
}

function gotoNew() { router.push({ name: 'obsidian-wiki-new' }) }
function gotoEdit(slug: string) { router.push({ name: 'obsidian-wiki-edit', params: { slug } }) }

function localFallback(): WikiPage[] {
  const now = '2026-06-24'
  return [
    { id: 'p1', title: '首页', slug: 'index', content_markdown: '# 首页\n欢迎来到 nanobot-factory Wiki, 这里记录所有项目文档。', tags: ['product'], outgoing_links: ['产品手册', 'API 文档'], backlinks: ['产品手册'], created_at: now, updated_at: now, author: 'system', word_count: 32 },
    { id: 'p2', title: '产品手册', slug: 'product-manual', content_markdown: '产品手册详细描述 nanobot-factory 的核心能力: 数据生成、模型训练、Skill 编排。', tags: ['product', 'docs'], outgoing_links: ['API 文档', '部署指南'], backlinks: ['首页', 'API 文档'], created_at: now, updated_at: now, author: 'pm', word_count: 64 },
    { id: 'p3', title: 'API 文档', slug: 'api-docs', content_markdown: 'API 文档列出所有 REST 端点, 包括 /api/v1/skills, /api/v1/multimodal 等。', tags: ['docs'], outgoing_links: ['首页', '产品手册'], backlinks: ['产品手册', '部署指南'], created_at: now, updated_at: now, author: 'dev', word_count: 48 },
    { id: 'p4', title: '部署指南', slug: 'deployment', content_markdown: '部署指南介绍 Docker / K8s / 蓝绿发布等部署方案。', tags: ['ops', 'docs'], outgoing_links: ['故障排查'], backlinks: ['产品手册', '最佳实践'], created_at: now, updated_at: now, author: 'ops', word_count: 80 },
    { id: 'p5', title: '最佳实践', slug: 'best-practices', content_markdown: '最佳实践汇总: 数据生成、模型微调、Skill 调用。', tags: ['ops'], outgoing_links: ['部署指南', '案例研究'], backlinks: ['社区贡献'], created_at: now, updated_at: now, author: 'architect', word_count: 100 },
    { id: 'p6', title: '故障排查', slug: 'troubleshooting', content_markdown: '常见故障排查: 端口冲突、DB 锁、Celery 重启。', tags: ['ops'], outgoing_links: [], backlinks: ['部署指南'], created_at: now, updated_at: now, author: 'ops', word_count: 56 },
    { id: 'p7', title: '案例研究', slug: 'case-studies', content_markdown: '客户案例: 智影 AIGC 数据集生产、电商商品图批量生成。', tags: ['product'], outgoing_links: [], backlinks: ['最佳实践', '社区贡献'], created_at: now, updated_at: now, author: 'marketing', word_count: 72 },
    { id: 'p8', title: '更新日志', slug: 'changelog', content_markdown: '## v0.4.0\n- Skill Marketplace 上线\n- Knowledge Graph 集成', tags: ['product'], outgoing_links: [], backlinks: [], created_at: now, updated_at: now, author: 'release', word_count: 40 },
  ]
}

onMounted(() => {
  loadTags()
  reload()
})
</script>

<style scoped>
.wiki-list { padding: 0; }
.header-card { margin-bottom: 12px; }
.wiki-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.page-card { cursor: pointer; transition: all 0.15s; }
.page-card:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(32, 128, 240, 0.18); }
.page-preview {
  font-size: 12px;
  color: #666;
  margin: 8px 0;
  min-height: 36px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.page-stats { margin-top: 8px; padding-top: 8px; border-top: 1px dashed #e0e0e6; }
</style>
