/**
 * R3.5-W2 stub: 应用主题模板到 <html>
 */

export interface ThemeTemplate {
  id?: string;
  name?: string;
  visuals?: {
    style?: string;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export type ThemeMode = 'dark' | 'light';

export function applyThemeTemplate(
  template: ThemeTemplate,
  theme: ThemeMode
): void {
  void template;
  void theme;
  // stub: 真实实现把 CSS 变量注入到 document.documentElement
}
