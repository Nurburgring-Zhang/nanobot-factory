<!--
  LocaleToggle.vue — Floating language switcher button.

  Renders a small globe icon button that, when clicked, opens a dropdown
  listing all 9 supported locales with their native names and flags.

  Usage:
    <LocaleToggle />     (anywhere in the layout, e.g. DefaultLayout header)

  Why a floating toggle + dropdown (rather than a select):
    - Discoverable from any page without scrolling to Settings
    - Mirrors the pattern of a "language" floating action button common in
      i18n-aware apps (Notion, Linear, etc.)
    - Dropdown allows one-click switching without page reload
-->
<template>
  <NPopselect
    v-model:value="currentLocale"
    :options="localeOptions"
    trigger="click"
    placement="bottom-end"
    scrollable
    @update:value="onLocaleChange"
  >
    <NButton circle quaternary :title="t('common.language')">
      <template #icon>
        <NIcon><LanguageOutline /></NIcon>
      </template>
    </NButton>
  </NPopselect>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NPopselect, NButton, NIcon } from 'naive-ui'
import { LanguageOutline } from '@vicons/ionicons5'
import { useLocaleStore } from '@/stores/locale'
import { SUPPORTED_LOCALES, LOCALE_META, type LocaleCode } from '@/locales'

const { t } = useI18n()
const localeStore = useLocaleStore()

const currentLocale = computed<LocaleCode>({
  get: () => localeStore.current,
  set: (val: LocaleCode) => {
    void localeStore.changeTo(val)
  }
})

const localeOptions = computed(() =>
  SUPPORTED_LOCALES.map((code) => ({
    label: `${LOCALE_META[code].flag} ${LOCALE_META[code].nativeName}`,
    value: code,
    key: code
  }))
)

async function onLocaleChange(next: LocaleCode): Promise<void> {
  await localeStore.changeTo(next)
}
</script>

<style scoped>
/* No custom styles — Naive UI handles layout. The button auto-mirrors
   via the RTL rules in styles/rtl.css when dir="rtl". */
</style>