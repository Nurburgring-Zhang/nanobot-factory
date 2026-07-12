import { onBeforeUnmount, onMounted, type Ref } from 'vue'

/**
 * useKeyboard — global keyboard-shortcut composable (P17-D3)
 *
 * Wires `keydown` listeners on `document` and dispatches to handler
 * callbacks matched by:
 *  - `combo` (e.g. 'ctrl+s', 'ctrl+k', '?', 'escape', 'ctrl+n')
 *  - `keys`  (single key, no modifier)
 *
 * Modifiers supported (case-insensitive):
 *   ctrl / cmd / meta — treated as aliases (Windows ⊕ Mac)
 *   shift            — must match
 *   alt              — must match
 *
 * Behaviour:
 *  - Listeners attached in onMounted, detached in onBeforeUnmount.
 *  - `preventDefault: true` (default) calls `e.preventDefault()` so
 *    browser default shortcuts (Ctrl+S save page) don't fire.
 *  - `stopPropagation: true` (default) keeps the event inside our app.
 *  - `when` is an optional ref<boolean>; when false, the handler is
 *    skipped — useful for not stealing keys while a modal is open.
 *  - Handlers can return `false` to tell the composable NOT to call
 *    preventDefault/stopPropagation for that specific event.
 */

export type Combo =
  | 'ctrl+s'
  | 'ctrl+n'
  | 'ctrl+k'
  | 'escape'
  | '?'
  | 'ctrl+shift+k'
  | 'ctrl+shift+s'
  | string

export interface KeyboardShortcut {
  combo: Combo
  description: string
  /** Optional category for the help dialog grouping. */
  group?: 'global' | 'nav' | 'edit' | 'help'
  handler: (e: KeyboardEvent) => void | boolean | Promise<void>
  /** Disable default browser behaviour for this combo. Default true. */
  preventDefault?: boolean
  /** Stop event propagation. Default true. */
  stopPropagation?: boolean
  /** Optional gate — when the ref is false, the handler is skipped. */
  when?: Ref<boolean> | (() => boolean)
}

function normalizeKey(e: KeyboardEvent): string {
  const parts: string[] = []
  if (e.ctrlKey || e.metaKey) parts.push('ctrl')
  if (e.shiftKey) parts.push('shift')
  if (e.altKey) parts.push('alt')

  // For single-character combos, lowercase. Special keys keep their
  // canonical name (Escape, ?, etc.)
  let key = e.key
  if (key === ' ') key = 'space'
  if (key.length === 1) key = key.toLowerCase()
  parts.push(key)
  return parts.join('+')
}

function matches(combo: string, normalized: string): boolean {
  if (!combo || !normalized) return false
  const want = combo.toLowerCase().split('+').filter(Boolean).sort()
  const got = normalized.split('+').filter(Boolean).sort()
  if (want.length !== got.length) return false
  for (let i = 0; i < want.length; i += 1) {
    if (want[i] !== got[i]) return false
  }
  return true
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (target.isContentEditable) return true
  return false
}

export function useKeyboard(shortcuts: KeyboardShortcut[]) {
  const handler = (e: KeyboardEvent) => {
    // Always allow modifiers to fire even from inputs (e.g. Ctrl+K).
    const hasModifier = e.ctrlKey || e.metaKey || e.altKey
    if (!hasModifier && isEditableTarget(e.target)) {
      return
    }

    const normalized = normalizeKey(e)
    for (const sc of shortcuts) {
      if (!matches(sc.combo, normalized)) continue
      if (sc.when) {
        const gate = typeof sc.when === 'function' ? sc.when() : sc.when.value
        if (!gate) continue
      }
      const preventDefault = sc.preventDefault !== false
      const stopPropagation = sc.stopPropagation !== false

      // The handler may return false to opt out of default prevention.
      let result: unknown
      try {
        result = sc.handler(e)
      } catch (err) {
        // Surface errors via console but never break other shortcuts.
        // eslint-disable-next-line no-console
        console.error('[useKeyboard] handler error for', sc.combo, err)
        return
      }
      if (result === false) return
      if (preventDefault) e.preventDefault()
      if (stopPropagation) e.stopPropagation()
      return
    }
  }

  onMounted(() => {
    if (typeof window === 'undefined') return
    window.addEventListener('keydown', handler, { capture: true })
  })

  onBeforeUnmount(() => {
    if (typeof window === 'undefined') return
    window.removeEventListener('keydown', handler, { capture: true } as EventListenerOptions)
  })

  return {
    /** Programmatic trigger — fire a combo on demand. */
    trigger(combo: Combo) {
      const synthetic = new KeyboardEvent('keydown', {
        key: combo.split('+').pop() ?? '',
        ctrlKey: combo.toLowerCase().includes('ctrl'),
        shiftKey: combo.toLowerCase().includes('shift'),
        altKey: combo.toLowerCase().includes('alt'),
        metaKey: combo.toLowerCase().includes('ctrl'),
        bubbles: true,
      })
      handler(synthetic)
    },
    /** Returns the registered shortcuts (sorted) for help dialogs. */
    list(): KeyboardShortcut[] {
      return [...shortcuts]
    },
  }
}