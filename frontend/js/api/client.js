// api/client.js — fetch wrapper + 错误标准化
// 所有 API 调用统一通过 http() / httpJson() 走
//
// P1-C-W1: BASE_URL 默认改为 /api (对齐 task spec 的 /api/stats/overview 等端点)
// 兼容规则:
//   - path 以 'http' 开头 → 原样使用
//   - path 以 '/api/' 开头 → 原样使用 (绝对路径, 不拼 BASE_URL)
//   - 其他 (/assets, /projects) → BASE_URL + path (向后兼容旧 api/assets.js 等)

import { normalizeError } from '../utils/error.js';

const DEFAULT_TIMEOUT_MS = 10000;
const BASE_URL = (typeof window !== 'undefined' && window.__API_BASE__) || '/api';

/**
 * 内部基础 fetch: 自动注入 timeout, 返回 Response 或 throw NormalizedError。
 */
export async function rawFetch(path, options = {}) {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...rest } = options;
  // P1-C-W1: 支持绝对路径 /api/* (不拼 BASE_URL) + 向后兼容 /assets, /projects (拼 BASE_URL)
  const url = path.startsWith('http')
    ? path
    : (path.startsWith('/api/') ? path : `${BASE_URL}${path}`);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response;
  try {
    response = await fetch(url, {
      ...rest,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(rest.body ? { 'Content-Type': 'application/json' } : {}),
        ...(rest.headers || {}),
      },
    });
  } catch (err) {
    clearTimeout(timer);
    throw normalizeError(err, null);
  }
  clearTimeout(timer);

  if (!response.ok) {
    // 尝试解析后端 error body 增强提示
    let detail = '';
    try {
      const ct = response.headers.get('content-type') || '';
      if (ct.includes('application/json')) {
        const j = await response.json();
        detail = j.detail || j.message || JSON.stringify(j);
      } else {
        detail = await response.text();
      }
    } catch (_) {
      /* ignore */
    }
    const ne = normalizeError(null, response);
    if (detail) ne.message = `${ne.message} — ${detail}`;
    throw ne;
  }

  return response;
}

/**
 * GET 返回 JSON (或空对象)。
 */
export async function httpGet(path, options = {}) {
  const r = await rawFetch(path, { method: 'GET', ...options });
  const ct = r.headers.get('content-type') || '';
  if (ct.includes('application/json')) return r.json();
  return r.text();
}

/**
 * POST/PUT/PATCH/DELETE 返回 JSON (或 null)。
 */
export async function httpSend(method, path, body, options = {}) {
  const init = {
    method,
    body: body !== undefined && body !== null ? JSON.stringify(body) : undefined,
  };
  const r = await rawFetch(path, init);
  // 204 No Content
  if (r.status === 204) return null;
  const ct = r.headers.get('content-type') || '';
  if (ct.includes('application/json')) return r.json();
  return r.text();
}

export const http = {
  get: httpGet,
  post: (path, body, opt) => httpSend('POST', path, body, opt),
  put: (path, body, opt) => httpSend('PUT', path, body, opt),
  patch: (path, body, opt) => httpSend('PATCH', path, body, opt),
  delete: (path, body, opt) => httpSend('DELETE', path, body, opt),
};

export { BASE_URL };