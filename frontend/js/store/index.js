// store/index.js — Pinia 入口
// 依赖: window.Pinia (由 index.html 通过 CDN <script> 全局加载)
//
// 设计: 与 W2 的 store/auth.js (window.__AUTH__ 模式) 解耦。
//       Pinia auth store 单独维护 token / user / role 状态,
//       持久化到 localStorage 'nanobot.auth'。不与 W2 的 'auth.user' 冲突。
//
// 用法:
//   import { usePinia, useAuthStore } from './store/index.js';
//   const pinia = usePinia(); app.use(pinia);
//   const auth = useAuthStore(); auth.login({...});

import { defineAuthStore } from './auth-pinia.js';

export { defineAuthStore };

/**
 * 返回 Pinia 实例 — 首次调用创建并缓存。
 */
let _pinia = null;
export function usePinia() {
  if (_pinia) return _pinia;
  if (typeof window === 'undefined' || !window.Pinia) {
    throw new Error('[store] window.Pinia not found — 请在 index.html 引入 pinia 的 CDN');
  }
  _pinia = window.Pinia.createPinia();
  return _pinia;
}

/**
 * 返回 Pinia auth store 的 hook 函数 — 给组件内 `useAuthStore()` 调用。
 */
let _useAuth = null;
export function useAuthStore() {
  if (_useAuth) return _useAuth();
  // 确保 Pinia 已初始化
  usePinia();
  const { defineStore } = window.Pinia;
  const { state, getters, actions } = defineAuthStore();
  _useAuth = defineStore('auth', { state, getters, actions });
  return _useAuth();
}

/**
 * 兼容旧 API: authStore() 等价 useAuthStore()。
 */
export function authStore() {
  return useAuthStore;
}