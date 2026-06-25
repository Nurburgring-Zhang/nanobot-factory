/**
 * i18n 插件 (国际化)
 * ----------------------------------------------------------------
 * 能力:
 *   - Vue plugin $t('key.path') 调用
 *   - localStorage 持久化 ('i18n.lang')
 *   - 切换语言时触发响应式更新 (event 'i18n:lang-changed')
 *   - 支持 zh-CN / en-US 双语, 缺失 key 自动回退到 en-US
 *   - 支持参数插值: $t('greet', { name: 'World' }) → "Hello, World"
 * ----------------------------------------------------------------
 * 用法:
 *   app.use(I18nPlugin, { default: 'zh-CN' });
 *   <h1>{{ $t('nav.dashboard') }}</h1>
 *   this.$t('greet', { name: 'Alice' })
 * ----------------------------------------------------------------
 */

const STORAGE_KEY = 'i18n.lang';
const DEFAULT_LANG = 'zh-CN';
const SUPPORTED = ['zh-CN', 'en-US'];

function loadLocales() {
  // 从 window 加载 (浏览器全局变量模式, 与 locales/*.js 配套)
  const locales = {};
  if (window.I18N_ZH_CN) locales['zh-CN'] = window.I18N_ZH_CN;
  if (window.I18N_EN_US) locales['en-US'] = window.I18N_EN_US;
  return locales;
}

function getStoredLang() {
  try { return localStorage.getItem(STORAGE_KEY); } catch (e) { return null; }
}

function setStoredLang(lang) {
  try { lang ? localStorage.setItem(STORAGE_KEY, lang) : localStorage.removeItem(STORAGE_KEY); } catch (e) {}
}

function detectLang() {
  // 优先级: localStorage > navigator.language > default
  const stored = getStoredLang();
  if (stored && SUPPORTED.includes(stored)) return stored;
  const nav = (navigator.language || navigator.userLanguage || '').toLowerCase();
  if (nav.startsWith('en')) return 'en-US';
  if (nav.startsWith('zh')) return 'zh-CN';
  return DEFAULT_LANG;
}

function resolveKey(locales, lang, key, params) {
  // 链: lang -> fallback (en-US) -> key 字面量
  const primary = locales[lang] || {};
  const fallback = locales['en-US'] || {};
  let template = primary[key];
  if (template == null) template = fallback[key];
  if (template == null) {
    console.warn(`[i18n] missing key: ${key} (lang=${lang})`);
    return key;
  }
  // 参数插值: {name} → params.name
  if (params && typeof template === 'string') {
    return template.replace(/\{(\w+)\}/g, (_, k) => {
      const v = params[k];
      return v == null ? `{${k}}` : String(v);
    });
  }
  return template;
}

// ============================================================
// Vue 3 Plugin
// ============================================================
const I18nPlugin = {
  install(app, options = {}) {
    const locales = options.locales || loadLocales();
    let currentLang = options.default || detectLang();
    if (!SUPPORTED.includes(currentLang)) currentLang = DEFAULT_LANG;
    setStoredLang(currentLang);

    function t(key, params) {
      return resolveKey(locales, currentLang, key, params);
    }

    function setLang(lang) {
      if (!SUPPORTED.includes(lang)) {
        console.warn('[i18n] unsupported lang:', lang);
        return false;
      }
      currentLang = lang;
      setStoredLang(lang);
      // 触发响应式更新: 让 v-text="$t('x')" 重新求值
      window.dispatchEvent(new CustomEvent('i18n:lang-changed', { detail: { lang } }));
      // 同步更新 <html lang="..."> 属性 (对 a11y 友好)
      document.documentElement.setAttribute('lang', lang.split('-')[0]);
      return true;
    }

    function getLang() { return currentLang; }
    function getSupported() { return SUPPORTED.slice(); }

    // globalProperties
    app.config.globalProperties.$t = t;
    app.config.globalProperties.$i18n = {
      t, setLang, getLang, getSupported,
      locales: Object.keys(locales),
    };
    app.provide('i18n', app.config.globalProperties.$i18n);

    // 暴露单例到 window (供 a11y.js v-label i18n 解析使用)
    window.__I18N_INSTANCE__ = { t, setLang, getLang, getSupported };

    // 同步初始 <html lang>
    document.documentElement.setAttribute('lang', currentLang.split('-')[0]);
  },
};

// ============================================================
// Exports
// ============================================================
if (typeof window !== 'undefined') {
  window.I18nPlugin = I18nPlugin;
  window.I18nCore = { t: null, setLang: null, resolveKey, SUPPORTED };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { I18nPlugin, resolveKey, SUPPORTED };
}
