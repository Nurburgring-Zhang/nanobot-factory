<!--
  SkeletonLoader.vue
  ------------------
  Reusable shimmer placeholder used by Suspense fallbacks while a
  route-level async component is still loading.

  Variants:
    - 'block'   (default) — large hero block + 4 list rows
    - 'list'    — table-like rows only
    - 'card'    — single card-shaped placeholder
    - 'canvas'  — empty canvas + side rail (V5 Infinite Canvas / DAG)

  Behaviour:
    - Pure CSS animation; no JS timer, so unmounts cleanly.
    - Honours `data-theme` via the same `--app-*` tokens App.vue defines.
    - Accessible: role="status" with aria-live="polite" announces the
      loading state to screen readers.

  Usage with vue-router:
    <RouterView v-slot="{ Component }">
      <Suspense>
        <component :is="Component" />
        <template #fallback>
          <SkeletonLoader variant="block" />
        </template>
      </Suspense>
    </RouterView>
-->
<template>
  <div
    class="skeleton-root"
    :class="`skeleton-${variant}`"
    role="status"
    aria-live="polite"
    :aria-label="ariaLabel"
  >
    <div v-if="variant === 'block'" class="block-grid">
      <div class="block-hero shimmer"></div>
      <div class="block-stats">
        <div v-for="i in 4" :key="i" class="block-stat shimmer"></div>
      </div>
      <div class="block-row shimmer" v-for="i in 6" :key="`r-${i}`"></div>
    </div>
    <div v-else-if="variant === 'list'" class="list-grid">
      <div class="list-head shimmer"></div>
      <div class="list-row shimmer" v-for="i in rowCount" :key="`row-${i}`"></div>
    </div>
    <div v-else-if="variant === 'card'" class="card-grid">
      <div class="card-hero shimmer"></div>
      <div class="card-line shimmer"></div>
      <div class="card-line short shimmer"></div>
    </div>
    <div v-else-if="variant === 'canvas'" class="canvas-grid">
      <div class="canvas-side shimmer"></div>
      <div class="canvas-main shimmer">
        <div class="canvas-dot dot-a"></div>
        <div class="canvas-dot dot-b"></div>
        <div class="canvas-dot dot-c"></div>
      </div>
    </div>
    <div v-else class="block-grid">
      <div class="block-hero shimmer"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type SkeletonVariant = 'block' | 'list' | 'card' | 'canvas'

const props = withDefaults(
  defineProps<{
    variant?: SkeletonVariant
    /** Used for the list variant. */
    rowCount?: number
    /** Localised announcement for assistive tech. */
    ariaLabel?: string
  }>(),
  {
    variant: 'block',
    rowCount: 8,
    ariaLabel: 'Loading content…',
  }
)

const _variant = computed<SkeletonVariant>(() => props.variant)
</script>

<style scoped>
.skeleton-root {
  width: 100%;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  color: var(--app-fg, #333);
}

.shimmer {
  position: relative;
  background: var(--app-surface, #fff);
  border: 1px solid var(--app-border, #e0e0e6);
  border-radius: 6px;
  overflow: hidden;
}
.shimmer::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(128, 128, 160, 0.10) 50%,
    transparent 100%
  );
  transform: translateX(-100%);
  animation: shimmer 1.4s ease-in-out infinite;
}

@keyframes shimmer {
  to {
    transform: translateX(100%);
  }
}

/* === block variant: hero + stats + rows === */
.block-grid {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.block-hero {
  height: 140px;
  width: 100%;
}
.block-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.block-stat {
  height: 72px;
}
.block-row {
  height: 48px;
}

/* === list variant: header + rows === */
.list-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.list-head {
  height: 36px;
}
.list-row {
  height: 44px;
}

/* === card variant === */
.card-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
  background: var(--app-surface, #fff);
  border: 1px solid var(--app-border, #e0e0e6);
  border-radius: 8px;
}
.card-hero {
  height: 80px;
}
.card-line {
  height: 14px;
  width: 100%;
}
.card-line.short {
  width: 60%;
}

/* === canvas variant: side rail + main with floating dots === */
.canvas-grid {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 16px;
  min-height: 480px;
}
.canvas-side {
  height: 100%;
  min-height: 480px;
}
.canvas-main {
  position: relative;
  height: 100%;
  min-height: 480px;
}
.canvas-dot {
  position: absolute;
  width: 96px;
  height: 56px;
  background: var(--app-border, #e0e0e6);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}
.canvas-dot.dot-a {
  top: 20%;
  left: 30%;
}
.canvas-dot.dot-b {
  top: 50%;
  left: 55%;
}
.canvas-dot.dot-c {
  top: 70%;
  left: 35%;
}

/* Responsive: stats grid collapses on narrow screens */
@media (max-width: 720px) {
  .block-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .canvas-grid {
    grid-template-columns: 1fr;
  }
  .canvas-side {
    display: none;
  }
}
</style>
