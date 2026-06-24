/**
 * R3.5-W2 stub: 快捷键 store
 */
import { create } from 'zustand';

export interface ShortcutCombo {
  key: string;
  meta?: boolean;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
}

interface ShortcutState {
  shortcuts: Record<string, ShortcutCombo | ShortcutCombo[]>;
}

export const useShortcutStore = create<ShortcutState>(() => ({
  shortcuts: {
    'global.resource-library': { key: 'r', ctrl: true },
  },
}));
