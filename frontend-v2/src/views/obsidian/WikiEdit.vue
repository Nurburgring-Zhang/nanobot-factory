<template>
  <div class="wiki-edit">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NInput v-model:value="title" placeholder="页面标题" size="large" style="width: 400px; font-weight: 600" />
          <NText depth="3" style="margin-left: 12px">/{{ slug }}</NText>
        </div>
        <NSpace>
          <NButton @click="gotoGraph">知识图谱</NButton>
          <NButton @click="gotoList">返回列表</NButton>
          <NButton type="primary" :loading="saving" @click="save">保存</NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <div class="edit-grid">
      <NCard title="Markdown 编辑器" :bordered="false" class="col-editor">
        <NSpace style="margin-bottom: 8px">
          <NButton size="tiny" @click="insertSnippet('# ')">H1</NButton>
          <NButton size="tiny" @click="insertSnippet('## ')">H2</NButton>
          <NButton size="tiny" @click="insertSnippet('**', '**')">Bold</NButton>
          <NButton size="tiny" @click="insertSnippet('*', '*')">Italic</NButton>
          <NButton size="tiny" @click="insertSnippet('[[', ']]')">[[Link]]</NButton>
          <NButton size="tiny" @click="insertSnippet('![alt](', ')')">Image</NButton>
          <NButton size="tiny" @click="insertSnippet('```\n', '\n```')">Code</NButton>
        </NSpace>
        <NInput
          v-model:value="content"
          type="textarea"
          :autosize="{ minRows: 24, maxRows: 32 }"
          placeholder="开始用 Markdown 写作... 输入 [[ 触发 Wiki 链接自动补全"
          @input="onContentInput"
        />
        <div v-if="autocompleteOpen && autocompleteCandidates.length" ref="popupEl" class="autocomplete-popup">
          <div
            v-for="(c, i) in autocompleteCandidates"
            :key="c.slug"
            class="ac-item"
            :class="{ active: i === acIndex }"
            @mousedown.prevent="applyAutocomplete(c)"
          >
            <strong>{{ c.title }}</strong>
            <NText depth="3" style="font-size: 11px; margin-left: 6px">/{{ c.slug }}</NText>
          </div>
        </div>
        <NDivider style="margin: 16px 0" title-placement="left">Tags</NDivider>
        <NSpace>
          <NTag
            v-for="t in tagChips"
            :key="t"
            closable
            type="info"
            :bordered="false"
            @close="removeTag(t)"
          >#{{ t }}</NTag>
          <NInput
            v-model:value="newTag"
            size="tiny"
            placeholder="+ tag"
            style="width: 100px"
            @keyup.enter="addTag"
          />
        </NSpace>
      </NCard>

      <NCard title="实时预览" :bordered="false" class="col-preview">
        <div class="md-preview" v-html="renderedHtml" />
        <NDivider title-placement="left">反向链接</NDivider>
        <NEmpty v-if="!backlinks.length" description="无" size="small" />
        <NList>
          <NListItem v-for="b in backlinks" :key="b" @click="gotoEdit(b)">
            <NText>↩ {{ b }}</NText>
          </NListItem>
        </NList>
      </NCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NCard, NSpace, NText, NInput, NButton, NTag, NDivider, NList, NListItem, NEmpty, useMessage
} from 'naive-ui'
import { obsidianApi, type WikiPage } from '@/api/obsidian'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const title = ref('未命名页面')
const slug = ref('untitled')
const content = ref('# 新页面\n\n开始书写, 使用 [[link]] 关联其他页面。')
const tagChips = ref<string[]>([])
const newTag = ref('')
const saving = ref(false)
const backlinks = ref<string[]>([])

const autocompleteOpen = ref(false)
const autocompleteCandidates = ref<Array<{ slug: string; title: string }>>([])
const acIndex = ref(0)
let acPrefix = ''

function insertSnippet(left: string, right: string = '') {
  content.value = content.value + left + right
}

function onContentInput() {
  // detect [[ autocomplete trigger
  const idx = content.value.lastIndexOf('[[')
  if (idx === -1) {
    autocompleteOpen.value = false
    return
  }
  const tail = content.value.slice(idx + 2)
  if (tail.includes(']') || tail.includes('\n')) {
    autocompleteOpen.value = false
    return
  }
  acPrefix = tail.trim()
  if (!acPrefix) {
    autocompleteOpen.value = false
    return
  }
  obsidianApi.autocomplete(acPrefix).then(c => {
    autocompleteCandidates.value = c
    autocompleteOpen.value = c.length > 0
    acIndex.value = 0
  }).catch(() => {
    // local fallback
    autocompleteCandidates.value = localFallbackPages()
      .filter(p => p.title.toLowerCase().includes(acPrefix.toLowerCase()))
      .slice(0, 6)
    autocompleteOpen.value = autocompleteCandidates.value.length > 0
    acIndex.value = 0
  })
}

function applyAutocomplete(c: { slug: string; title: string }) {
  const idx = content.value.lastIndexOf('[[')
  if (idx === -1) return
  content.value = content.value.slice(0, idx) + `[[${c.title}]]`
  autocompleteOpen.value = false
}

function addTag() {
  const t = newTag.value.trim().replace(/^#/, '')
  if (t && !tagChips.value.includes(t)) tagChips.value.push(t)
  newTag.value = ''
}
function removeTag(t: string) {
  tagChips.value = tagChips.value.filter(x => x !== t)
}

// Very small markdown renderer (handles headings, bold, italic, code, [[link]])
const renderedHtml = computed(() => {
  let html = content.value
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // headings
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>')
  // bold / italic
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  // inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  // wiki links
  const wikiLinkRx = /\[\[([^\]]+)\]\]/g
  const outgoing: string[] = []
  html = html.replace(wikiLinkRx, (_, label) => {
    const slugified = String(label).trim().toLowerCase().replace(/\s+/g, '-')
    outgoing.push(slugified)
    return `<a href="#/obsidian/wiki/${slugified}" class="wiki-link">${label}</a>`
  })
  // paragraphs
  html = html.split(/\n\n+/).map(p => {
    if (p.startsWith('<h') || p.startsWith('<ul') || p.startsWith('<pre')) return p
    return `<p>${p.replace(/\n/g, '<br/>')}</p>`
  }).join('\n')
  // update outgoing links
  backlinks.value = Array.from(new Set(outgoing))
  return html
})

async function loadPage(slugName: string) {
  try {
    const p = await obsidianApi.getPage(slugName)
    title.value = p.title
    slug.value = p.slug
    content.value = p.content_markdown
    tagChips.value = p.tags
    backlinks.value = p.backlinks
  } catch (e: any) {
    message.warning(`后端 Wiki 页面暂不可用, 使用本地占位: ${e?.message || ''}`)
  }
}

async function save() {
  saving.value = true
  try {
    const body: Partial<WikiPage> = {
      title: title.value,
      content_markdown: content.value,
      tags: tagChips.value,
    }
    if (route.name === 'obsidian-wiki-new' || !route.params.slug) {
      const created = await obsidianApi.createPage({ title: title.value, content_markdown: content.value, tags: tagChips.value })
      message.success(`已创建: ${created.slug}`)
      router.replace({ name: 'obsidian-wiki-edit', params: { slug: created.slug } })
    } else {
      const updated = await obsidianApi.updatePage(slug.value, body)
      message.success(`已保存: ${updated.slug}`)
    }
  } catch (e: any) {
    message.warning(`后端保存暂未就绪, 已暂存于本地: ${e?.message || ''}`)
  } finally {
    saving.value = false
  }
}

function gotoList() { router.push({ name: 'obsidian-wiki' }) }
function gotoGraph() { router.push({ name: 'obsidian-graph' }) }
function gotoEdit(s: string) { router.push({ name: 'obsidian-wiki-edit', params: { slug: s } }) }

function localFallbackPages() {
  return [
    { slug: 'index', title: '首页' },
    { slug: 'product-manual', title: '产品手册' },
    { slug: 'api-docs', title: 'API 文档' },
    { slug: 'deployment', title: '部署指南' },
    { slug: 'best-practices', title: '最佳实践' },
    { slug: 'troubleshooting', title: '故障排查' },
    { slug: 'case-studies', title: '案例研究' },
    { slug: 'changelog', title: '更新日志' },
  ]
}

watch(() => route.params.slug, (s) => {
  if (s && typeof s === 'string') loadPage(s)
}, { immediate: true })

onMounted(() => {
  if (route.name === 'obsidian-wiki-new' || !route.params.slug) {
    title.value = '未命名页面'
    slug.value = 'untitled'
  }
})
</script>

<style scoped>
.wiki-edit { padding: 0; }
.header-card { margin-bottom: 12px; }
.edit-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.col-editor, .col-preview { min-height: 600px; }
.md-preview {
  font-size: 14px;
  line-height: 1.7;
  min-height: 400px;
}
.md-preview :deep(h1) { font-size: 22px; margin: 12px 0 8px; }
.md-preview :deep(h2) { font-size: 18px; margin: 10px 0 6px; }
.md-preview :deep(h3) { font-size: 15px; margin: 8px 0 4px; }
.md-preview :deep(p) { margin: 6px 0; }
.md-preview :deep(code) { background: #f0f0f0; padding: 2px 4px; border-radius: 3px; font-size: 12px; }
.md-preview :deep(.wiki-link) { color: #2080f0; text-decoration: none; border-bottom: 1px dashed #2080f0; }
.autocomplete-popup {
  position: absolute;
  margin-top: 4px;
  background: #fff;
  border: 1px solid #e0e0e6;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  z-index: 100;
  max-height: 200px;
  overflow-y: auto;
  width: 320px;
}
.ac-item {
  padding: 6px 10px;
  cursor: pointer;
  font-size: 13px;
}
.ac-item:hover, .ac-item.active { background: #f0f8ff; }
</style>
