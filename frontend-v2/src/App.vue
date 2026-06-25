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
            <ErrorBoundary name="App">
              <RouterView v-slot="{ Component }">
                <!-- Keep <RouterView> stable across re-renders so the layout
                     doesn't unmount on every navigation. -->
                <component :is="Component" v-if="Component" />
              </RouterView>
            </ErrorBoundary>
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
  type GlobalTheme,
  type GlobalThemeOverrides,
  type NLocale,
  type NDateLocale
} from 'naive-ui'
import { RouterView } from 'vue-router'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import { useThemeStore } from '@/stores/theme'
import { useLocaleStore } from '@/stores/locale'

const themeStore = useThemeStore()
const localeStore = useLocaleStore()

// Bridge the Pinia theme store into Naive UI's :theme prop.
const naiveTheme = computed<GlobalTheme | null>(() => {
  return themeStore.isDark ? darkTheme : lightTheme
})

// Naive UI theme overrides — keep minimal in W1.
// Using CSS custom properties driven by data-theme for body / layout chrome
// so the design system can be re-skinned without touching component code.
const themeOverrides = computed<GlobalThemeOverrides>(() => ({
  common: {
    primaryColor: '#2080f0',
    primaryColorHover: '#4098fc',
    primaryColorPressed: '#1060c9',
    primaryColorSuppl: '#4098fc',
    borderRadius: '6px',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
  }
}))

// Locale-aware Naive UI provider props. We resolve from the Pinia locale store
// so all chrome (toasts, dialogs, date pickers, empty states) speaks the same
// language as the rest of the app.
const activeLocale = computed<NLocale>(() => (localeStore.current === 'zh-CN' ? zhCN : enUS))
const activeDateLocale = computed<NDateLocale>(() =>
  localeStore.current === 'zh-CN' ? dateZhCN : dateEnUS
)

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
}
html[data-theme='light'] {
  --app-bg: #f5f7fa;
  --app-fg: #333;
  --app-surface: #ffffff;
  --app-border: #e0e0e6;
  --app-muted: var(--a11y-muted, #767676);
}
</style>