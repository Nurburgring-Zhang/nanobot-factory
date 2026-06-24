/* IMDF v3 — utils/error.js
   Higher-level error helpers used by business pages.
   Depends on client.js (httpSend / t / toastError).
*/
(function (global) {
  'use strict';

  /** Human-readable message from a three-state result.error or raw error. */
  function describe(errOrResult, fallback) {
    if (!errOrResult) return fallback || '';
    if (errOrResult.i18nKey) return (global.t ? global.t(errOrResult.i18nKey, errOrResult.message) : errOrResult.message);
    if (errOrResult.message) return errOrResult.message;
    if (typeof errOrResult === 'string') return errOrResult;
    return fallback || (global.t ? global.t('error.unknown') : 'Unknown error');
  }

  /** Standard onError handler: show toast + log to console. */
  function onApiError(label, err) {
    const msg = describe(err, label + ' failed');
    if (typeof global.toastError === 'function') global.toastError(err, msg);
    else if (typeof console !== 'undefined') console.error('[' + label + ']', msg, err);
    if (typeof console !== 'undefined' && err && err.code) console.warn('  code=' + err.code + ' status=' + err.status);
  }

  /** Convenience: build query string from object, dropping null/undefined/empty. */
  function qs(params) {
    if (!params) return '';
    const parts = [];
    Object.keys(params).forEach(function (k) {
      const v = params[k];
      if (v === undefined || v === null || v === '') return;
      parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
    });
    return parts.length ? '?' + parts.join('&') : '';
  }

  /** Convenience: extract list + total from common backend envelope shapes. */
  function extractList(payload) {
    if (!payload) return { items: [], total: 0, page: 1, pages: 1 };
    const items =
      payload.items ||
      (payload.data && (payload.data.items || payload.data.list || payload.data)) ||
      payload.list ||
      payload.results ||
      (Array.isArray(payload) ? payload : []);
    const total = payload.total || (payload.data && payload.data.total) || items.length;
    const page  = payload.page  || (payload.data && payload.data.page)  || 1;
    const pages = payload.pages|| (payload.data && payload.data.pages) || Math.max(1, Math.ceil(total / 20));
    return { items: Array.isArray(items) ? items : [], total: Number(total)||0, page: Number(page)||1, pages: Number(pages)||1 };
  }

  /** RBAC-gated UI helper: hides element if user lacks permission. */
  function applyRbac(rootEl, permMap) {
    if (!rootEl || typeof global.rbac !== 'function') return;
    Object.keys(permMap || {}).forEach(function (sel) {
      const need = permMap[sel];
      const el = rootEl.querySelector ? rootEl.querySelector(sel) : null;
      if (el && !global.rbac(need)) {
        el.style.display = 'none';
        el.disabled = true;
      }
    });
  }

  global.IMDF_ERROR = { describe: describe, onApiError: onApiError, qs: qs,
                        extractList: extractList, applyRbac: applyRbac };
})(typeof window !== 'undefined' ? window : globalThis);