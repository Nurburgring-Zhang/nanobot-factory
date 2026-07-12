<template>
  <section
    :class="['page-region', regionClass]"
    role="region"
    :aria-labelledby="headingId"
    :aria-describedby="describedById || undefined"
  >
    <h2 :id="headingId" class="sr-only">{{ resolvedLabel }}</h2>
    <slot />
    <p
      v-if="resolvedDescription"
      :id="describedById"
      class="sr-only"
    >
      {{ resolvedDescription }}
    </p>
  </section>
</template>

<script setup lang="ts">
/**
 * PageRegion — semantic landmark wrapper for view roots.
 *
 * P8-1: bulk-fixes the missing `role="region"` + `aria-labelledby` + sr-only
 * heading pattern across the 52 views. Every view should mount its template
 * inside <PageRegion :label="...">...</PageRegion>; the wrapper generates a
 * stable heading id, an optional description slot, and exposes the region to
 * assistive tech.
 *
 * Why a wrapper component (vs raw `<section role="region">`):
 *   - Stable id generation via `useId()`-equivalent (no Naive UI dep)
 *   - Auto-resolves label through i18n (string OR i18n key)
 *   - Single change-point when we later add skip-target / outline tweaks
 *
 * Usage:
 *   <PageRegion label="annotation.pageTitle" description="annotation.pageSubtitle">
 *     ... view body ...
 *   </PageRegion>
 */
import { computed, useId } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(
  defineProps<{
    /** Label or i18n key. Strings with a `.` are looked up in i18n. */
    label: string
    /** Optional secondary description (i18n key or string). */
    description?: string
    regionClass?: string
  }>(),
  { description: '', regionClass: '' }
)

const uid = useId()
const headingId = computed(() => `page-region-heading-${uid}`)
const describedById = computed(() =>
  props.description ? `page-region-desc-${uid}` : ''
)

const { t } = useI18n()
function resolve(input: string): string {
  if (!input) return ''
  // If it looks like an i18n key (has a dot), try to resolve it
  if (input.includes('.')) {
    const resolved = t(input)
    // If t() returns the key itself, no translation exists; fall back to raw string
    if (resolved !== input) return resolved
  }
  return input
}
const resolvedLabel = computed(() => resolve(props.label))
const resolvedDescription = computed(() =>
  props.description ? resolve(props.description) : ''
)
</script>

<style scoped>
.page-region {
  display: contents;
}
</style>
