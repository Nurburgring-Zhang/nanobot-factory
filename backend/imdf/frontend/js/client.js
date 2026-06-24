/* IMDF v3 — HTTP client with three-state (loading / success / error)
   + RBAC + i18n error messages.

   Public API:
     window.httpGet(path, opts)       -> Promise<{state, data, error}>
     window.httpSend(method, path, body, opts) -> Promise<{state, data, error}>
     window.HTTP_STATE                 -> enum: 'loading' | 'success' | 'error'
     window.rbac(perm)                 -> boolean (reads window.__RBAC__ / window.currentUser)
     window.t(key, fallback)           -> i18n lookup with fallback

   Three-state contract:
     - {state:'loading'} never returned (callers handle loading UI separately).
     - {state:'success', data} on 2xx.
     - {state:'error', error:{code,message,i18nKey}} on non-2xx or network failure.

   All four business pages (template-market, datasets, eval-review, pipeline) +
   the new tasks.js consume these helpers, replacing inline apiGet/apiPost
   for the new /api/{tasks,templates,datasets,eval,pipeline}/* endpoints.
*/

(function (global) {
  'use strict';

  const STATE = Object.freeze({ LOADING: 'loading', SUCCESS: 'success', ERROR: 'error' });

  /* ---------------- i18n (zh-CN default; en fallback to key) ---------------- */
  const I18N = {
    'error.network':     { zh: '网络异常,请稍后重试', en: 'Network error, please retry' },
    'error.timeout':     { zh: '请求超时,请稍后重试', en: 'Request timed out' },
    'error.unauthorized':{ zh: '请先登录',             en: 'Please sign in first' },
    'error.forbidden':   { zh: '权限不足',             en: 'Permission denied' },
    'error.not_found':   { zh: '资源不存在',           en: 'Resource not found' },
    'error.conflict':    { zh: '资源冲突',             en: 'Resource conflict' },
    'error.server':      { zh: '服务器错误,请稍后重试', en: 'Server error, please retry' },
    'error.validation':  { zh: '请求参数无效',         en: 'Invalid request' },
    'error.unknown':     { zh: '未知错误',             en: 'Unknown error' },
  };

  function detectLang() {
    const lang = (global.localStorage && global.localStorage.getItem('imdf.lang')) || 'zh';
    return lang === 'en' ? 'en' : 'zh';
  }

  function t(key, fallback) {
    const lang = detectLang();
    const entry = I18N[key];
    if (entry) return entry[lang] || entry.zh || fallback || key;
    return fallback || key;
  }

  /* ---------------- RBAC ---------------- */
  function rbac(perm) {
    if (!perm) return true;
    const u = global.currentUser || global.__USER__ || null;
    if (!u) return false;
    const roles = u.roles || (u.role ? [u.role] : []) || [];
    if (roles.includes('admin') || roles.includes('superadmin')) return true;
    const perms = u.permissions || u.perms || [];
    if (perms.includes('*') || perms.includes(perm)) return true;
    return false;
  }

  /* ---------------- Error normalization ---------------- */
  function normalizeError(status, payload, networkErr) {
    if (networkErr) {
      const isTimeout = networkErr.name === 'AbortError';
      return { code: isTimeout ? 'TIMEOUT' : 'NETWORK', status: 0,
               message: networkErr.message || String(networkErr),
               i18nKey: isTimeout ? 'error.timeout' : 'error.network' };
    }
    const map = { 400:'VALIDATION', 401:'UNAUTHORIZED', 403:'FORBIDDEN',
                  404:'NOT_FOUND', 409:'CONFLICT', 422:'VALIDATION',
                  500:'SERVER', 502:'SERVER', 503:'SERVER', 504:'SERVER' };
    const code = map[status] || (status >= 500 ? 'SERVER' : 'UNKNOWN');
    const i18nKey =
      code === 'UNAUTHORIZED' ? 'error.unauthorized' :
      code === 'FORBIDDEN'    ? 'error.forbidden'    :
      code === 'NOT_FOUND'    ? 'error.not_found'    :
      code === 'CONFLICT'     ? 'error.conflict'     :
      code === 'VALIDATION'   ? 'error.validation'   :
      code === 'SERVER'       ? 'error.server'       :
      'error.unknown';
    return {
      code, status,
      message: (payload && (payload.detail || payload.message || payload.error)) || `HTTP ${status}`,
      i18nKey,
    };
  }

  /* ---------------- Core fetch wrapper ---------------- */
  async function httpSend(method, path, body, opts) {
    opts = opts || {};
    const url = path.startsWith('http') ? path : (path.startsWith('/') ? path : '/' + path);
    const init = {
      method: method || 'GET',
      credentials: 'same-origin',
      headers: Object.assign(
        { 'Accept': 'application/json' },
        body ? { 'Content-Type': 'application/json' } : {},
        opts.headers || {}
      ),
    };
    if (body !== undefined && body !== null && method !== 'GET') {
      init.body = typeof body === 'string' ? body : JSON.stringify(body);
    }

    /* CSRF token for state-changing requests (cookie-based) */
    if (method && method !== 'GET' && method !== 'HEAD') {
      const csrf = (global.document && document.cookie || '').match(/(?:^|;\s*)csrf_token=([^;]+)/);
      if (csrf && !init.headers['X-CSRF-Token']) init.headers['X-CSRF-Token'] = decodeURIComponent(csrf[1]);
    }

    /* Auth bearer (if backend stored a token in localStorage under imdf.access) */
    try {
      const tok = global.localStorage && global.localStorage.getItem('imdf.access');
      if (tok && !init.headers['Authorization']) init.headers['Authorization'] = 'Bearer ' + tok;
    } catch (_) { /* localStorage may throw in sandboxed contexts */ }

    /* Timeout */
    const ctl = (typeof AbortController === 'function') ? new AbortController() : null;
    if (ctl) init.signal = ctl.signal;
    const timeoutMs = opts.timeoutMs || 30000;
    let timer = null;
    if (ctl) timer = setTimeout(() => ctl.abort(), timeoutMs);

    let resp;
    try {
      resp = await fetch(url, init);
    } catch (netErr) {
      if (timer) clearTimeout(timer);
      const err = normalizeError(0, null, netErr);
      if (typeof opts.onError === 'function') opts.onError(err);
      return { state: STATE.ERROR, data: null, error: err };
    }
    if (timer) clearTimeout(timer);

    let payload = null;
    const ctype = resp.headers.get('content-type') || '';
    try {
      payload = ctype.includes('application/json') ? await resp.json() : await resp.text();
    } catch (_) { payload = null; }

    if (!resp.ok) {
      const err = normalizeError(resp.status, payload, null);
      if (typeof opts.onError === 'function') opts.onError(err);
      return { state: STATE.ERROR, data: payload, error: err };
    }
    return { state: STATE.SUCCESS, data: payload, error: null };
  }

  function httpGet(path, opts) { return httpSend('GET', path, undefined, opts); }
  function httpPost(path, body, opts) { return httpSend('POST', path, body, opts); }
  function httpPut(path, body, opts)  { return httpSend('PUT',  path, body, opts); }
  function httpDelete(path, opts)    { return httpSend('DELETE', path, undefined, opts); }

  /* ---------------- Export ---------------- */
  global.HTTP_STATE = STATE;
  global.httpSend  = httpSend;
  global.httpGet   = httpGet;
  global.httpPost  = httpPost;
  global.httpPut   = httpPut;
  global.httpDelete= httpDelete;
  global.rbac      = rbac;
  global.t         = t;
  global.IMDF_HTTP = { STATE, httpGet, httpPost, httpPut, httpDelete, httpSend, rbac, t };

  /* showToast bridge — soft-degrade if app.js hasn't loaded yet */
  global.toastError = function (errOrKey, fallback) {
    const key = (errOrKey && errOrKey.i18nKey) || errOrKey;
    const msg = (typeof key === 'string' && I18N[key]) ? t(key) : (fallback || key || t('error.unknown'));
    if (typeof global.showToast === 'function') global.showToast(msg, 'error');
    else if (typeof global.console !== 'undefined') console.error('[toast]', msg);
  };
  global.toastInfo = function (msg) {
    if (typeof global.showToast === 'function') global.showToast(msg, 'info');
  };
  global.toastOk   = function (msg) {
    if (typeof global.showToast === 'function') global.showToast(msg, 'success');
  };
})(typeof window !== 'undefined' ? window : globalThis);