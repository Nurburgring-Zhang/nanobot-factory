/**
 * Skip-link helper — wire once in the root layout so keyboard users can jump
 * past the navigation chrome. WCAG 2.4.1 Bypass Blocks (Level A).
 *
 * Visual rendering lives in styles/a11y.css; this module only handles the
 * focus-shift behavior because some screen readers ignore programmatic focus()
 * unless the target has a tabindex.
 */
import type { Ref } from 'vue'

export interface SkipLinkOptions {
  /** CSS selector for the main landmark. Default: `#main` */
  targetSelector?: string
}

export function useSkipLink(options: SkipLinkOptions = {}) {
  const targetSelector = options.targetSelector ?? '#main'

  function focusMain(): void {
    if (typeof document === 'undefined') return
    const el = document.querySelector<HTMLElement>(targetSelector)
    if (!el) return
    // Make focusable on demand without permanently breaking tab order.
    if (el.tabIndex < 0) el.tabIndex = -1
    el.focus({ preventScroll: false })
  }

  return { focusMain, targetSelector }
}

export type SkipLinkHandle = ReturnType<typeof useSkipLink>

/**
 * Reactive variant — auto-syncs the skip-link href with the resolved main id
 * when the layout swaps between routes (some SPAs unmount <main> on navigation).
 */
export function bindSkipLinkHref(scope: Ref<string | null | undefined>): void {
  // Intentionally minimal placeholder for future expansion; the current layout
  // keeps <main id="main"> mounted across route changes, so the static href is
  // sufficient. Reserved for multi-layout apps.
  void scope
}