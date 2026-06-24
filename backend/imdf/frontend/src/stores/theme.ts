/**
 * R3.5-W2 stub: theme store
 * 用最小可工作实现避免阻塞下游，类型按 imdf-app.tsx 实际使用签名对齐。
 */
import { create } from 'zustand';

export type ThemeMode = 'dark' | 'light';
export type ThemeStyle = 'pixel' | 'default';

export interface ThemeState {
  theme: ThemeMode;
  style: ThemeStyle;
  templateId: string;
  customTemplates: Record<string, unknown>;
  toggleTheme: () => void;
  loadCustomTemplates: () => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
  theme: 'dark',
  style: 'default',
  templateId: 'default',
  customTemplates: {},
  toggleTheme: () => set((s) => ({ theme: s.theme === 'dark' ? 'light' : 'dark' })),
  loadCustomTemplates: () => set({ customTemplates: {} }),
}));
