/**
 * R3.5-W2 stub: 解析主题模板 id
 */

import type { ThemeTemplate } from './applyTheme';

const FALLBACK_TEMPLATE: ThemeTemplate = {
  id: 'default',
  name: '默认主题',
  visuals: { style: 'default' },
};

export function resolveThemeTemplate(
  templateId: string,
  customTemplates: Record<string, ThemeTemplate | unknown>
): ThemeTemplate {
  if (templateId === 'default' || !templateId) {
    return FALLBACK_TEMPLATE;
  }
  const custom = customTemplates?.[templateId] as ThemeTemplate | undefined;
  if (custom && typeof custom === 'object') {
    return { ...FALLBACK_TEMPLATE, ...custom };
  }
  return { ...FALLBACK_TEMPLATE, id: templateId };
}
