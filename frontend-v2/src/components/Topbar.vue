<!--
  Topbar.vue
  ----------
  App-bar header rendered at the top of the DefaultLayout. Owns:
    - Page title (h1) bound to the active route meta.
    - Global search trigger (Ctrl/⌘+K shortcut).
    - Locale switcher (9 locales incl. ar-SA with RTL auto-apply).
    - Dark / light / auto theme toggle.
    - Notification bell (WebSocket-driven, P20-O).
    - User avatar dropdown (profile / theme / locale shortcut / logout).

  All state lives in the existing Pinia stores (locale, theme, ui, auth).
  This component is presentational + a thin glue layer.
-->
<template>
  <header class="topbar" role="banner" data-testid="topbar">
    <h1 class="topbar-title">{{ pageTitle }}</h1>

    <div class="topbar-spacer"></div>

    <NSpace align="center" :size="10" class="topbar-actions">
      <!-- P17-D3: Global search palette (Ctrl/⌘+K) -->
      <GlobalSearch />

      <!-- Locale switcher (9 locales, ar-SA auto-apply RTL) -->
      <NPopselect
        v-model:value="localeCurrent"
        :options="localeOptions"
        trigger="click"
        placement="bottom-end"
        scrollable
        @update:value="onLocaleChange"
      >
        <NButton
          class="locale-toggle"
          size="small"
          quaternary
          :title="localeTooltip"
          :aria-label="localeTooltip"
          data-testid="topbar-locale"
        >
          <template #icon>
            <span class="locale-flag" aria-hidden="true">{{ localeFlag }}</span>
          </template>
          <span class="locale-toggle-label">{{ localeShortLabel }}</span>
        </NButton>
      </NPopselect>

      <!-- Theme toggle (light → dark → auto → light) -->
      <NButton
        class="theme-toggle"
        size="small"
        quaternary
        :title="themeTooltip"
        :aria-label="themeTooltip"
        data-testid="topbar-theme"
        @click="onToggleTheme"
      >
        <template #icon>
          <NIcon size="18">
            <component :is="themeIcon" />
          </NIcon>
        </template>
        <span class="theme-toggle-label">{{ themeShortLabel }}</span>
      </NButton>

      <!-- Notification bell (P20-O) -->
      <NotificationBell />

      <!-- User avatar menu -->
      <NDropdown
        trigger="click"
        placement="bottom-end"
        :options="userMenuOptions"
        @select="onUserMenuSelect"
        :show="ui.userMenuOpen"
        @clickoutside="ui.closeUserMenu()"
      >
        <NButton
          circle
          quaternary
          size="small"
          :title="userTooltip"
          :aria-label="userTooltip"
          data-testid="topbar-avatar"
          @click="ui.toggleUserMenu()"
        >
          <span class="avatar-circle" :style="avatarStyle">
            {{ avatarInitials }}
          </span>
        </NButton>
      </NDropdown>
    </NSpace>
  </header>
</template>

<script setup lang="ts">
import { computed, h, markRaw, type Component } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import {
  NButton,
  NDropdown,
  NIcon,
  NPopselect,
  NSpace,
  type DropdownOption,
} from 'naive-ui'
import {
  SunnyOutline,
  MoonOutline,
  DesktopOutline,
  PersonCircleOutline,
  SettingsOutline,
  NotificationsOutline,
  LogOutOutline,
  LanguageOutline,
  HelpCircleOutline,
} from '@vicons/ionicons5'
import GlobalSearch from '@/components/GlobalSearch.vue'
import NotificationBell from '@/components/NotificationBell.vue'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore, type ThemeMode } from '@/stores/theme'
import { useLocaleStore } from '@/stores/locale'
import { useUiStore } from '@/stores/ui'
import { SUPPORTED_LOCALES, LOCALE_META, type LocaleCode } from '@/locales'

defineProps<{
  pageTitle: string
}>()

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const themeStore = useThemeStore()
const localeStore = useLocaleStore()
const ui = useUiStore()

// ============================================================
// Theme (icon + label + tooltip)
// ============================================================
const themeIcon = computed<Component>(() => {
  const map: Record<ThemeMode, Component> = {
    light: markRaw(SunnyOutline),
    dark: markRaw(MoonOutline),
    auto: markRaw(DesktopOutline),
  }
  return map[themeStore.mode] ?? markRaw(SunnyOutline)
})

const themeShortLabel = computed<string>(() => {
  const map: Record<ThemeMode, string> = {
    light: localeStore.current === 'zh-CN' ? '浅色' : 'Light',
    dark: localeStore.current === 'zh-CN' ? '深色' : 'Dark',
    auto: localeStore.current === 'zh-CN' ? '自动' : 'Auto',
  }
  return map[themeStore.mode] ?? (localeStore.current === 'zh-CN' ? '浅色' : 'Light')
})

const themeTooltip = computed<string>(() => {
  const map: Record<ThemeMode, string> = {
    light: localeStore.current === 'zh-CN' ? '当前:浅色 · 点击切换为深色' : 'Light · click for Dark',
    dark: localeStore.current === 'zh-CN' ? '当前:深色 · 点击切换为自动' : 'Dark · click for Auto',
    auto: localeStore.current === 'zh-CN' ? '当前:自动 (跟随系统) · 点击切换为浅色' : 'Auto (system) · click for Light',
  }
  return map[themeStore.mode] ?? (localeStore.current === 'zh-CN' ? '切换主题' : 'Toggle theme')
})

function onToggleTheme(): void {
  themeStore.cycle()
}

// ============================================================
// Locale switcher
// ============================================================
const localeCurrent = computed<LocaleCode>({
  get: () => localeStore.current,
  set: (val: LocaleCode) => {
    void localeStore.changeTo(val)
  },
})

const localeOptions = computed(() =>
  SUPPORTED_LOCALES.map((code) => ({
    label: `${LOCALE_META[code].flag} ${LOCALE_META[code].nativeName}`,
    value: code,
  }))
)

const localeShortLabel = computed<string>(() => localeStore.current.split('-')[0].toUpperCase())

const localeFlag = computed<string>(() => LOCALE_META[localeStore.current].flag)

const localeTooltip = computed<string>(() => {
  const meta = LOCALE_META[localeStore.current]
  return localeStore.current === 'zh-CN'
    ? `语言:${meta.nativeName} (${meta.englishName}) — 点击切换`
    : `Language: ${meta.nativeName} (${meta.englishName}) — click to switch`
})

function onLocaleChange(next: LocaleCode): void {
  void localeStore.changeTo(next)
}

// ============================================================
// User avatar
// ============================================================
const userTooltip = computed<string>(() => {
  if (!auth.user) return localeStore.current === 'zh-CN' ? '账户' : 'Account'
  return `${auth.user.username} (${auth.user.role})`
})

const avatarInitials = computed<string>(() => {
  const u = auth.user?.username ?? '?'
  const trimmed = u.trim()
  if (trimmed.length === 0) return '?'
  // Use up to two characters; for CJK this keeps the first two characters.
  return trimmed.slice(0, 2).toUpperCase()
})

// Stable color derived from the username so the same user always sees
// the same avatar color across sessions.
const avatarStyle = computed<Record<string, string>>(() => {
  const u = auth.user?.username ?? 'guest'
  let hash = 0
  for (let i = 0; i < u.length; i++) {
    hash = (hash * 31 + u.charCodeAt(i)) & 0xffffffff
  }
  const hue = Math.abs(hash) % 360
  return {
    background: `hsl(${hue} 55% 55%)`,
    color: '#fff',
  }
})

const userMenuOptions = computed<DropdownOption[]>(() => {
  const isZh = localeStore.current === 'zh-CN'
  return [
    {
      label: () => h('div', { class: 'user-menu-line' }, [
        h('strong', null, auth.user?.username ?? (isZh ? '游客' : 'Guest')),
        h('span', { class: 'user-menu-sub' }, auth.user?.role ?? (isZh ? '未登录' : 'guest')),
      ]),
      key: 'header',
      type: 'render',
      disabled: true,
    },
    { type: 'divider', key: 'd1' },
    {
      label: () => h('div', { class: 'user-menu-item' }, [
        h(NIcon, null, { default: () => h(PersonCircleOutline) }),
        h('span', null, isZh ? '个人资料' : 'Profile'),
      ]),
      key: 'profile',
    },
    {
      label: () => h('div', { class: 'user-menu-item' }, [
        h(NIcon, null, { default: () => h(NotificationsOutline) }),
        h('span', null, isZh ? `通知 (${ui.unreadCount})` : `Notifications (${ui.unreadCount})`),
      ]),
      key: 'notifications',
    },
    {
      label: () => h('div', { class: 'user-menu-item' }, [
        h(NIcon, null, { default: () => h(LanguageOutline) }),
        h('span', null, isZh ? '语言' : 'Language'),
      ]),
      key: 'language',
      children: SUPPORTED_LOCALES.map<DropdownOption>((code) => ({
        label: `${LOCALE_META[code].flag} ${LOCALE_META[code].nativeName}`,
        key: `lang-${code}`,
      })),
    },
    {
      label: () => h('div', { class: 'user-menu-item' }, [
        h(NIcon, null, { default: () => h(SettingsOutline) }),
        h('span', null, isZh ? '设置' : 'Settings'),
      ]),
      key: 'settings',
    },
    {
      label: () => h('div', { class: 'user-menu-item' }, [
        h(NIcon, null, { default: () => h(HelpCircleOutline) }),
        h('span', null, isZh ? '帮助' : 'Help'),
      ]),
      key: 'help',
    },
    { type: 'divider', key: 'd2' },
    {
      label: () =>
        h(
          RouterLink,
          { to: '/login', class: 'user-menu-item user-menu-logout' },
          () => h('div', { class: 'user-menu-item' }, [
            h(NIcon, null, { default: () => h(LogOutOutline) }),
            h('span', null, isZh ? '退出登录' : 'Sign out'),
          ])
        ),
      key: 'logout',
    },
  ]
})

function onUserMenuSelect(key: string | number): void {
  ui.closeUserMenu()
  if (typeof key !== 'string') return
  if (key === 'logout') {
    auth.logout()
    void router.replace({ name: 'login' })
    return
  }
  if (key === 'profile') {
    void router.push('/user-management')
    return
  }
  if (key === 'notifications') {
    void router.push('/notification-management')
    return
  }
  if (key === 'settings') {
    void router.push('/settings')
    return
  }
  if (key === 'help') {
    void router.push('/shortcut-help').catch(() => {
      // The shortcut help component is global, no route needed.
    })
    return
  }
  if (key.startsWith('lang-')) {
    const code = key.slice('lang-'.length) as LocaleCode
    void localeStore.changeTo(code)
    return
  }
}

// Defensive: re-apply title when route changes
const _title = computed<string>(() => {
  const meta = route.meta?.title
  return typeof meta === 'string' ? meta : (route.name as string) || ''
})
</script>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}
.topbar-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
  color: var(--app-fg, #333);
}
.topbar-spacer {
  flex: 1 1 auto;
}
.topbar-actions {
  flex: 0 0 auto;
}

.locale-toggle,
.theme-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.locale-flag {
  font-size: 16px;
  line-height: 1;
}
.locale-toggle-label,
.theme-toggle-label {
  font-size: 12px;
  margin-left: 2px;
  color: var(--app-muted, #767676);
}
.locale-toggle-label {
  font-weight: 600;
  letter-spacing: 0.5px;
}

.avatar-circle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  background: var(--app-primary, #0a5dc2);
  color: #fff;
  user-select: none;
}

:deep(.user-menu-line) {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 0;
  min-width: 140px;
}
:deep(.user-menu-sub) {
  font-size: 11px;
  color: var(--app-muted, #767676);
}
:deep(.user-menu-item) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--app-fg, #333);
}
:deep(.user-menu-logout) {
  color: var(--app-error, #d03050);
}
:deep(.user-menu-logout .n-icon) {
  color: var(--app-error, #d03050);
}
</style>
