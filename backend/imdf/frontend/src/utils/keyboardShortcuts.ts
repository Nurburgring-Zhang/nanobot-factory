/**
 * R3.5-W2 stub: 键盘快捷键匹配
 */

import type { ShortcutCombo } from '../stores/shortcuts';

export function matchesAnyShortcut(
  combo: ShortcutCombo | ShortcutCombo[] | undefined,
  event: KeyboardEvent | { key: string; ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean; altKey?: boolean }
): boolean {
  if (!combo) return false;
  const list = Array.isArray(combo) ? combo : [combo];
  const key = (event.key ?? '').toLowerCase();
  return list.some((c) => {
    if (!c) return false;
    const ck = (c.key ?? '').toLowerCase();
    if (ck !== key) return false;
    if (c.ctrl && !event.ctrlKey && !event.metaKey) return false;
    if (c.meta && !event.metaKey && !event.ctrlKey) return false;
    if (c.shift && !event.shiftKey) return false;
    if (c.alt && !event.altKey) return false;
    return true;
  });
}
