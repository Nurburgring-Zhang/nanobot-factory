<template>
  <NConfigProvider :theme-overrides="themeOverrides" :date-locale="dateEnUS" :locale="enUS">
    <NMessageProvider>
      <NDialogProvider>
        <NLoadingBarProvider>
          <NNotificationProvider>
            <RouterView />
          </NNotificationProvider>
        </NLoadingBarProvider>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<script setup lang="ts">
import { computed, h } from 'vue'
import {
  NConfigProvider,
  NMessageProvider,
  NDialogProvider,
  NLoadingBarProvider,
  NNotificationProvider,
  darkTheme,
  type GlobalThemeOverrides
} from 'naive-ui'
import { enUS, dateEnUS } from 'naive-ui'
import { RouterView } from 'vue-router'

// Naive UI theme overrides — keep minimal in W1
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
}
</style>