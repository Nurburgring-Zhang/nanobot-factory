// utils/error.js — 网络/5xx/超时 错误标准化
// 由 api/client.js 调用, 也可被组件直接使用

/**
 * 标准化错误对象, 所有 fetch 失败都转换成这个形状:
 *   { type, message, status, retryable }
 *
 * type 取值:
 *   - 'timeout'    请求超时 (>10s)
 *   - 'network'    网络断开 (fetch reject)
 *   - 'unauthorized' 401 — 跳登录
 *   - 'forbidden'  403
 *   - 'notfound'   404
 *   - 'server'     5xx
 *   - 'client'     4xx 其他
 *   - 'unknown'    兜底
 */
export class NormalizedError extends Error {
  constructor({ type, message, status, retryable, original }) {
    super(message);
    this.name = 'NormalizedError';
    this.type = type;
    this.status = status;
    this.retryable = retryable;
    this.original = original;
  }
}

/**
 * 把任意错误标准化, 第二个参数可选传入 response 对象。
 */
export function normalizeError(err, response) {
  // 已经是标准化过的, 直接返回
  if (err instanceof NormalizedError) return err;

  // 超时 (由 AbortController 触发)
  if (err && err.name === 'AbortError') {
    return new NormalizedError({
      type: 'timeout',
      message: '请求超时,请重试',
      retryable: true,
      original: err,
    });
  }

  // 有 response (HTTP 非 2xx)
  if (response) {
    const status = response.status;
    if (status === 401) {
      return new NormalizedError({
        type: 'unauthorized',
        message: '未登录,跳转登录页',
        status,
        retryable: false,
        original: err,
      });
    }
    if (status === 403) {
      return new NormalizedError({
        type: 'forbidden',
        message: '无权限',
        status,
        retryable: false,
        original: err,
      });
    }
    if (status === 404) {
      return new NormalizedError({
        type: 'notfound',
        message: '资源不存在',
        status,
        retryable: false,
        original: err,
      });
    }
    if (status >= 500 && status < 600) {
      return new NormalizedError({
        type: 'server',
        message: `服务异常 (HTTP ${status})`,
        status,
        retryable: true,
        original: err,
      });
    }
    if (status >= 400 && status < 500) {
      return new NormalizedError({
        type: 'client',
        message: `请求被拒绝 (HTTP ${status})`,
        status,
        retryable: false,
        original: err,
      });
    }
  }

  // 网络断开 (fetch reject) 或其他
  if (err instanceof TypeError) {
    return new NormalizedError({
      type: 'network',
      message: '网络连接失败',
      retryable: true,
      original: err,
    });
  }

  return new NormalizedError({
    type: 'unknown',
    message: (err && err.message) || '未知错误',
    retryable: true,
    original: err,
  });
}

/**
 * 用户友好提示 — 给 UI 直接显示。
 */
export function userMessage(err) {
  if (err instanceof NormalizedError) return err.message;
  if (err && err.message) return err.message;
  return '未知错误';
}