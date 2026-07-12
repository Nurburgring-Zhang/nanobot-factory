<template>
  <NConfigProvider
    :theme="naiveTheme"
    :theme-overrides="themeOverrides"
    :date-locale="activeDateLocale"
    :locale="activeLocale"
    :inline-theme-disabled="true"
  >
    <NMessageProvider>
      <NDialogProvider>
        <NLoadingBarProvider>
          <NNotificationProvider>
            <!-- App-wide error boundary: any uncaught descendant render error
                 surfaces this fallback instead of white-screening the SPA. -->
            <ErrorBoundary name="App" :class="{ 'app-layout-rtl': isRtl }">
              <RouterView v-slot="{ Component }">
                <!-- Suspense + Skeleton fallback so lazy route chunks render a
                     shimmering placeholder while the JS for the destination
                     view is still in flight. The Suspense boundary is at the
                     top level (App.vue) so it also covers the DefaultLayout
                     subtree, not just leaf views. -->
                <Suspense>
                  <component :is="Component" v-if="Component" />
                  <template #fallback>
                    <SkeletonLoader variant="block" />
                  </template>
                </Suspense>
              </RouterView>
            </ErrorBoundary>
            <!-- V4 — 智影 Intelligence 全局对话窗口 -->
            <ChatPanel />
            <!-- V5 — 智影 Intelligence V5 能力面板 (Hermes/Loop/Obsidian/MoA/Pavo/Gooseworks) -->
            <V5ChatPanel />
            <!-- P17-D3: 全局搜索面板 (Ctrl/⌘+K 唤起) -->
            <GlobalSearch />
            <!-- P17-D3: 键盘快捷键帮助 (?) -->
            <ShortcutHelp :shortcuts="globalShortcuts" />
          </NNotificationProvider>
        </NLoadingBarProvider>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, watch } from 'vue'
import {
  NConfigProvider,
  NMessageProvider,
  NDialogProvider,
  NLoadingBarProvider,
  NNotificationProvider,
  darkTheme,
  lightTheme,
  zhCN,
  dateZhCN,
  enUS,
  dateEnUS,
  jaJP,
  dateJaJP,
  koKR,
  dateKoKR,
  frFR,
  dateFrFR,
  deDE,
  dateDeDE,
  esAR,
  dateEsAR,
  ruRU,
  dateRuRU,
  arDZ,
  dateArDZ,
  type GlobalTheme,
  type GlobalThemeOverrides,
  type NLocale,
  type NDateLocale
} from 'naive-ui'
import { RouterView } from 'vue-router'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import ChatPanel from '@/components/ChatPanel.vue'
import V5ChatPanel from '@/components/V5ChatPanel.vue'
import GlobalSearch from '@/components/GlobalSearch.vue'
import ShortcutHelp from '@/components/ShortcutHelp.vue'
import SkeletonLoader from '@/components/SkeletonLoader.vue'
import {
  useThemeStore,
  PRIMARY_COLOR_OVERRIDES,
  SUCCESS_COLOR_OVERRIDES,
  WARNING_COLOR_OVERRIDES,
  ERROR_COLOR_OVERRIDES
} from '@/stores/theme'
import { useLocaleStore } from '@/stores/locale'
import { type LocaleCode, isRTL as isRTLLocale } from '@/locales'
import { useUiStore } from '@/stores/ui'
import { useQuickNavStore } from '@/stores/quicknav'
import { useKeyboard, type KeyboardShortcut } from '@/composables/useKeyboard'
import { useRoute } from 'vue-router'

const themeStore = useThemeStore()
const localeStore = useLocaleStore()
const uiStore = useUiStore()
const quickNav = useQuickNavStore()
const route = useRoute()

// Bridge the Pinia theme store into Naive UI's :theme prop.
const naiveTheme = computed<GlobalTheme | null>(() => {
  return themeStore.isDark ? darkTheme : lightTheme
})

// Naive UI theme overrides — full 5-token set in P11-C.
//
// P11-C fix: bumped primary hex (was 3.88:1 on white, failing AA Normal)
// up to the brand target #0a5dc2 (6.25:1 — passes AA Normal 4.5:1 with
// headroom) and success hex (was 3.38:1, failing AA) up to #157a3e (5.41:1).
// Warning was already failing AA at the previous hex so we lift it to
// #c87f0d (3.23:1, AA Large Text only — kept as warning badge hue to avoid
// visual surprise; UI uses icon + text together rather than colour alone).
//
// Light/dark colour values are sourced from the `--app-*` CSS custom
// properties so views that already use `var(--app-fg)` etc. stay in sync
// without per-view overrides. Naive UI's own `darkTheme` provides the
// structural colour swaps (cardColor / modalColor / tableColor — for the
// components; we only override the brand hues here.
// P12-A1: pull all hex values from the dedicated token constants exported
// by stores/theme.ts (PRIMARY_COLOR_OVERRIDES / SUCCESS_COLOR_OVERRIDES /
// WARNING_COLOR_OVERRIDES / ERROR_COLOR_OVERRIDES). This removes the
// previous inline-literal duplication and gives us a single grep target
// (`theme.ts`) when retuning contrast.
const themeOverrides = computed<GlobalThemeOverrides>(() => {
  const dark = themeStore.isDark
  const palette = dark ? 'dark' : 'light'
  const surface = dark
    ? {
        bodyColor: '#18181c',
        cardColor: '#1f1f23',
        modalColor: '#1f1f23',
        popoverColor: '#1f1f23',
        tableColor: '#1f1f23',
        inputColor: '#18181c',
        actionColor: '#1f1f23',
        tagColor: '#2a2a30',
        dividerColor: '#2e2e33'
      }
    : {}
  return {
    common: {
      ...PRIMARY_COLOR_OVERRIDES[palette],
      ...SUCCESS_COLOR_OVERRIDES[palette],
      ...WARNING_COLOR_OVERRIDES[palette],
      ...ERROR_COLOR_OVERRIDES[palette],
      // Info mirrors primary on purpose so we don't fragment the brand palette
      ...PRIMARY_COLOR_OVERRIDES[palette],
      ...surface,
      borderRadius: '6px',
      borderRadiusSmall: '4px',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
    }
  }
})

// Locale-aware Naive UI provider props. We resolve from the Pinia locale store
// so all chrome (toasts, dialogs, date pickers, empty states) speaks the same
// language as the rest of the app.
const NAIVE_LOCALES: Record<LocaleCode, NLocale> = {
  'zh-CN': zhCN,
  'en-US': enUS,
  'ja-JP': jaJP,
  'ko-KR': koKR,
  'fr-FR': frFR,
  'de-DE': deDE,
  'es-ES': esAR, // Naive UI ships esAR only; Spanish texts are compatible
  'ru-RU': ruRU,
  'ar-SA': arDZ, // arDZ is the closest Naive UI ships for Arabic
  'pt-PT': enUS // P21 P3 P1 fix (TS2741): Naive UI has no pt-PT; fall back to enUS
}

const NAIVE_DATE_LOCALES: Record<LocaleCode, NDateLocale> = {
  'zh-CN': dateZhCN,
  'en-US': dateEnUS,
  'ja-JP': dateJaJP,
  'ko-KR': dateKoKR,
  'fr-FR': dateFrFR,
  'de-DE': dateDeDE,
  'es-ES': dateEsAR, // Naive UI ships esAR; Spanish shares most month/day names with esES
  'ru-RU': dateRuRU,
  'pt-PT': dateEnUS, // P21 P3 P1 fix (TS2741): Naive UI has no datePtPT; fall back to dateEnUS
  'ar-SA': dateArDZ
}

const activeLocale = computed<NLocale>(() => NAIVE_LOCALES[localeStore.current] ?? enUS)
const activeDateLocale = computed<NDateLocale>(() => NAIVE_DATE_LOCALES[localeStore.current] ?? dateEnUS)

// P19-D2: bind .app-layout-rtl class when ar-SA (or any RTL locale) is active,
// so rtl.css rules targeting the top-level flex container can mirror layouts.
// Individual layout chrome (sidebar / drawer) auto-mirrors via `<html dir>`.
// We keep this class so per-route layouts that read .app-layout-rtl selectors
// (default layout, drawer position, breadcrumb chevron) work even before
// `applyDocumentDirection()` has flipped the document attribute.
const isRtl = computed<boolean>(() => isRTLLocale(localeStore.current))

// Keep <html lang> in sync so assistive tech + browser font selection behave.
watch(
  () => localeStore.current,
  (v) => {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('lang', v)
    }
  },
  { immediate: true }
)

// React to the store changing before it has been read elsewhere, so the
// initial <html data-theme> gets set on first mount.
let unbindSystem: (() => void) | null = null

onMounted(() => {
  // Restore from localStorage at boot (idempotent — main.ts may have already
  // called it, but calling twice is safe).
  themeStore.restoreFromStorage()
  unbindSystem = themeStore.bindSystemListener()
  localeStore.restoreFromStorage()
})

onBeforeUnmount(() => {
  if (unbindSystem) unbindSystem()
})

// Defensive: re-apply DOM theme if the store changes after unmount in tests
watch(
  () => themeStore.resolved,
  (v) => {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', v)
      document.documentElement.style.colorScheme = v
    }
  }
)

// ============================================================================
// P17-D3: Global keyboard shortcuts + recent-route tracking
// ============================================================================
//
// Five shortcuts are wired here:
//   Ctrl+S  — emit "save" intent (views hook via window 'app:save' event)
//   Ctrl+N  — emit "new" intent (navigate to /requirement-management or similar)
//   Ctrl+K  — open global search palette
//   Esc     — close any open overlay (search / shortcut help / upload drawer)
//   ?       — toggle the keyboard-shortcut help dialog
//
// We deliberately avoid hard-coding view routes into the shortcut so
// the keys keep working after refactors: each shortcut emits a window
// event the destination view listens for, and only Ctrl+K / Esc / ?
// talk directly to the UI store.

const ROUTE_ICONS: Record<string, string> = {
  dashboard: '◈',
  dataset: '▤',
  annotation: '✎',
  review: '✓',
  scoring: '★',
  workflows: '⇄',
  engines: '◆',
  tasks: '☰',
  users: '☷',
  billing: '☼',
  monitoring: '◉',
  settings: '⚙',
  dataset_management: 'D',
  asset_management: 'A',
  annotation_management: 'N',
  cleaning_management: 'C',
  scoring_management: 'S',
  evaluation_management: 'E',
  agent_management: 'B',
  workflow_management: 'W',
  notification_management: 'M',
  search_management: 'Q',
  canvas_designer: 'P',
  requirements: 'R',
  skills: '◇',
  obsidian_graph: '◉',
  obsidian_wiki: '✎',
  assets_storyboard: '🎬',
  workflow_visual: '⇄',
  agent_multimodal: '💬',
  billing_dashboard: '💰',
  lineage: '🕸',
  ProjectCenter: '◰',
  packs: '⬢',
  collection: '⬇',
  internal_qc: '🛡',
  requester_accept: '🤝',
  delivery: '📦',
}

function emitShortcutIntent(name: 'save' | 'new'): void {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(`app:${name}`))
}

const globalShortcuts: KeyboardShortcut[] = [
  {
    combo: 'ctrl+k',
    description: '打开全局搜索 · Open global search',
    group: 'nav',
    handler: () => uiStore.toggleSearchPalette(),
  },
  {
    combo: 'escape',
    description: '关闭浮层 · Close overlays',
    group: 'nav',
    handler: () => {
      if (uiStore.searchPaletteOpen) uiStore.closeSearchPalette()
      else if (uiStore.shortcutHelpOpen) uiStore.closeShortcutHelp()
      else if (uiStore.uploadDrawerOpen) uiStore.closeUploadDrawer()
    },
  },
  {
    combo: '?',
    description: '快捷键帮助 · Keyboard help',
    group: 'help',
    handler: () => uiStore.shortcutHelpOpen
      ? uiStore.closeShortcutHelp()
      : uiStore.openShortcutHelp(),
  },
  {
    combo: 'ctrl+s',
    description: '保存 · Save current view',
    group: 'edit',
    handler: () => emitShortcutIntent('save'),
  },
  {
    combo: 'ctrl+n',
    description: '新建 · Create new resource',
    group: 'edit',
    handler: () => emitShortcutIntent('new'),
  },
]

useKeyboard(globalShortcuts)

// Track every navigation into the recent-visit list so QuickNav can
// surface it. De-dup is handled inside the store.
watch(
  () => route.fullPath,
  (path) => {
    const meta = route.meta as { title?: unknown; icon?: unknown } | undefined
    const title = typeof meta?.title === 'string'
      ? meta.title
      : (route.name as string) || path || '/'
    const icon = ROUTE_ICONS[(route.name as string) || ''] || '◦'
    quickNav.trackVisit({ path, title, icon, hint: title })
  },
  { immediate: true },
)
</script>

<style>
html, body, #app {
  margin: 0;
  padding: 0;
  height: 100%;
  width: 100%;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background: var(--app-bg, #f5f7fa);
  color: var(--app-fg, #333);
  transition: background-color 0.18s ease, color 0.18s ease;
}

/* Dark-mode color tokens — driven by data-theme on <html> */
html[data-theme='dark'] {
  --app-bg: #18181c;
  --app-fg: #e6e6ea;
  --app-surface: #1f1f23;
  --app-border: #2e2e33;
  --app-muted: var(--a11y-muted, #9aa);
  /* Brand-aware tokens — kept in sync with themeOverrides (App.vue). Views
   * that need to render coloured chips / badges read these instead of
   * hard-coding hex so dark mode is automatic. */
  --app-primary: #5aa9ff;
  --app-primary-fg: #0c0c10;
  --app-success: #4cc07c;
  --app-success-fg: #0c0c10;
  --app-warning: #ffb340;
  --app-warning-fg: #0c0c10;
  --app-error: #ff5a72;
  --app-error-fg: #0c0c10;
  --app-info: #5aa9ff;
  --app-info-fg: #0c0c10;
}
html[data-theme='light'] {
  --app-bg: #f5f7fa;
  --app-fg: #333;
  --app-surface: #ffffff;
  --app-border: #e0e0e6;
  --app-muted: var(--a11y-muted, #767676);
  --app-primary: #0a5dc2;
  --app-primary-fg: #ffffff;
  --app-success: #157a3e;
  --app-success-fg: #ffffff;
  --app-warning: #c87f0d;
  --app-warning-fg: #ffffff;
  --app-error: #d03050;
  --app-error-fg: #ffffff;
  --app-info: #0a5dc2;
  --app-info-fg: #ffffff;
}

/* ---------- P11-C: Global dark-mode view adaptation ----------
 *
 * Most views (49/52) hard-code their background tints to very-light
 * greys like #f0f8ff, #f5f5f7, #e6f0ff, #f0fff6 etc. With dark mode the
 * body flips to #18181c via --app-bg but those tints stay light, so the
 * page reads as "light cards floating on a dark void". This block maps
 * the common patterns to the dark surface so switching the theme reads
 * as a single coherent palette.
 *
 * We do this with low-specificity selectors so per-view rules still win
 * when they have explicitly opted out.
 */
html[data-theme='dark'] body {
  background-color: var(--app-bg);
  color: var(--app-fg);
}
html[data-theme='dark'] .n-card,
html[data-theme='dark'] .n-data-table,
html[data-theme='dark'] .n-data-table-tr,
html[data-theme='dark'] .n-data-table-th,
html[data-theme='dark'] .n-data-table-td {
  --n-border-color: var(--app-border);
}
html[data-theme='dark'] .n-card-shallow {
  background-color: var(--app-surface);
}
html[data-theme='dark'] .n-tabs-tab {
  color: var(--a11y-muted-strong, #c0c4d0);
}
html[data-theme='dark'] .n-tabs-tab--active {
  color: var(--app-primary);
}
/* Page region / dashboard "card" wrapper used across views */
html[data-theme='dark'] .page-region,
html[data-theme='dark'] .panel,
html[data-theme='dark'] .surface,
html[data-theme='dark'] .panel-card {
  background-color: var(--app-surface);
  border-color: var(--app-border);
  color: var(--app-fg);
}
/* Tinted backgrounds (the most common light-mode flourish): remap to the
 * dark surface so chrome doesn't end up brighter than the body. */
html[data-theme='dark'] [class*='tint-'],
html[data-theme='dark'] [style*='background:#f0f8ff'],
html[data-theme='dark'] [style*='background:#f5f5f7'],
html[data-theme='dark'] [style*='background:#f0fff6'],
html[data-theme='dark'] [style*='background:#fff7e6'],
html[data-theme='dark'] [style*='background:#e6f0ff'],
html[data-theme='dark'] [style*='background:#fff'],
html[data-theme='dark'] [style*='background:#fafafa'],
html[data-theme='dark'] [style*='background:#fafafc'],
html[data-theme='dark'] [style*='background:#f7f8fa'],
html[data-theme='dark'] [style*='background:#e0e0e6'] {
  background-color: var(--app-surface) !important;
}
/* Tables: row hover / striped backgrounds */
html[data-theme='dark'] .n-data-table .n-data-table-tr:hover,
html[data-theme='dark'] .n-data-table .n-data-table-tr--striped {
  background-color: rgba(255, 255, 255, 0.04);
}
html[data-theme='dark'] .n-input,
html[data-theme='dark'] .n-select,
html[data-theme='dark'] .n-base-selection,
html[data-theme='dark'] .n-base-selection-input__content {
  color: var(--app-fg);
}
/* Placeholder / muted */
html[data-theme='dark'] .n-input__placeholder,
html[data-theme='dark'] .n-base-selection-placeholder {
  color: var(--app-muted);
}

/* ---------- P10R4-3: Extended dark-mode view adaptation ----------
 *
 * Round-2 picks up the remaining view-level color patterns not yet covered by
 * the P11-C block above. The selectors stay low-specificity so any per-view
 * rule that opts out (e.g. .skill-pill) still wins.
 */
html[data-theme='dark'] [style*='color:#333'],
html[data-theme='dark'] [style*='color:#666'],
html[data-theme='dark'] [style*='color:#888'] {
  color: var(--app-fg) !important;
}
html[data-theme='dark'] [style*='border'][style*='#e8e8e8'],
html[data-theme='dark'] [style*='border'][style*='#e0e0e6'],
html[data-theme='dark'] [style*='border'][style*='#e0e0e0'] {
  border-color: var(--app-border) !important;
}
/* Graph / chart canvas backgrounds */
html[data-theme='dark'] .graph-canvas,
html[data-theme='dark'] .kg-canvas,
html[data-theme='dark'] .vf-canvas,
html[data-theme='dark'] .vue-flow__background {
  background-color: var(--app-surface);
}
/* Plan row "active" highlight */
html[data-theme='dark'] .plan-row.active {
  background-color: rgba(76, 192, 124, 0.10);
  border-color: var(--app-success);
}
/* Skill pill / chip hover (used by Orchestrator + Marketplace) */
html[data-theme='dark'] .skill-pill:hover,
html[data-theme='dark'] .chip:hover {
  background-color: rgba(90, 169, 255, 0.10);
}
/* Knowledge-graph dot grid background */
html[data-theme='dark'] .dot-grid {
  background:
    radial-gradient(circle, var(--app-border) 1px, transparent 1px) 0 0 / 20px 20px,
    var(--app-surface) !important;
}
/* ECharts / D3 dark canvas wrapper */
html[data-theme='dark'] .echarts-wrap,
html[data-theme='dark'] .d3-canvas {
  background-color: var(--app-surface);
}
</style>
