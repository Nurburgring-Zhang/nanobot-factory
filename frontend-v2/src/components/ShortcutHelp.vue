<template>
  <NModal
    v-model:show="uiStore.shortcutHelpOpen"
    :mask-closable="true"
    preset="card"
    :title="title"
    :style="{ width: '540px', maxWidth: '92vw' }"
    class="shortcut-help"
  >
    <div class="shortcut-help__body">
      <section
        v-for="group in grouped"
        :key="group.name"
        class="shortcut-help__group"
      >
        <header class="shortcut-help__group-head">
          {{ group.name }}
        </header>
        <ul class="shortcut-help__items">
          <li v-for="sc in group.items" :key="sc.combo" class="shortcut-help__item">
            <span class="shortcut-help__desc">{{ sc.description }}</span>
            <span class="shortcut-help__combo">
              <template v-for="(k, idx) in splitCombo(sc.combo)" :key="`${k}-${idx}`">
                <kbd>{{ k }}</kbd>
                <span v-if="idx < splitCombo(sc.combo).length - 1" class="shortcut-help__plus">+</span>
              </template>
            </span>
          </li>
        </ul>
      </section>
      <div v-if="!grouped.length" class="shortcut-help__empty">
        {{ emptyText }}
      </div>
    </div>
    <template #footer>
      <div class="shortcut-help__foot">
        <NText depth="3" style="font-size: 11px">
          {{ footText }}
        </NText>
        <NButton size="small" @click="uiStore.closeShortcutHelp()">
          {{ closeText }}
        </NButton>
      </div>
    </template>
  </NModal>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NModal, NText } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { useUiStore } from '@/stores/ui'
import type { KeyboardShortcut } from '@/composables/useKeyboard'

/**
 * ShortcutHelp.vue (P17-D3)
 *
 * "?" modal listing every registered shortcut. The shortcuts are
 * passed in as a prop so the host (App.vue / DefaultLayout) keeps the
 * canonical registry — this dialog is purely a renderer.
 */

const props = defineProps<{
  shortcuts: KeyboardShortcut[]
}>()

const uiStore = useUiStore()
const { locale } = useI18n()

const isZh = computed<boolean>(() => (locale.value || '').toLowerCase().startsWith('zh'))
const t = (en: string, zh: string): string => (isZh.value ? zh : en)

const title = computed<string>(() => t('Keyboard shortcuts', '键盘快捷键'))
const emptyText = computed<string>(() => t('No shortcuts registered', '尚未注册快捷键'))
const closeText = computed<string>(() => t('Close', '关闭'))
const footText = computed<string>(() => t('Press ? to toggle this dialog', '按 ? 切换此对话框'))

interface Group {
  name: string
  items: KeyboardShortcut[]
}

const groupOrder: string[] = ['global', 'nav', 'edit', 'help']
const groupNames: Record<string, { en: string; zh: string }> = {
  global: { en: 'Global', zh: '全局' },
  nav: { en: 'Navigation', zh: '导航' },
  edit: { en: 'Editing', zh: '编辑' },
  help: { en: 'Help', zh: '帮助' },
}

const grouped = computed<Group[]>(() => {
  const map = new Map<string, KeyboardShortcut[]>()
  for (const sc of props.shortcuts) {
    const g: string = sc.group ?? 'global'
    if (!map.has(g)) map.set(g, [])
    map.get(g)!.push(sc)
  }
  const out: Group[] = []
  for (const g of groupOrder) {
    const items = map.get(g)
    if (!items || items.length === 0) continue
    const labels = groupNames[g] ?? { en: g, zh: g }
    out.push({
      name: t(labels.en, labels.zh),
      items,
    })
  }
  return out
})

function splitCombo(combo: string): string[] {
  return combo.split('+').filter(Boolean).map((s) => {
    if (s.toLowerCase() === 'ctrl' || s.toLowerCase() === 'cmd' || s.toLowerCase() === 'meta') {
      return 'Ctrl'
    }
    if (s === 'escape') return 'Esc'
    return s.toUpperCase()
  })
}
</script>

<style scoped>
.shortcut-help__group {
  margin-bottom: 14px;
}
.shortcut-help__group-head {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: var(--app-muted, #767676);
  margin-bottom: 6px;
}
.shortcut-help__items {
  list-style: none;
  margin: 0;
  padding: 0;
}
.shortcut-help__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid var(--app-border, rgba(0, 0, 0, 0.06));
}
.shortcut-help__item:last-child {
  border-bottom: 0;
}
.shortcut-help__desc {
  font-size: 13px;
  color: var(--app-fg, #333);
}
.shortcut-help__combo {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.shortcut-help__combo kbd {
  display: inline-block;
  padding: 2px 6px;
  font-size: 11px;
  font-family: monospace;
  background: var(--app-border, rgba(0, 0, 0, 0.06));
  border-radius: 3px;
  color: var(--app-fg, #333);
  min-width: 18px;
  text-align: center;
}
.shortcut-help__plus {
  font-size: 11px;
  color: var(--app-muted, #767676);
}
.shortcut-help__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.shortcut-help__empty {
  font-size: 13px;
  color: var(--app-muted, #767676);
  text-align: center;
  padding: 24px 0;
}
</style>