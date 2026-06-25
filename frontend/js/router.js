// router.js — Vue Router 4 配置 (5 个核心页面) — P1-C-W1
// 依赖: window.VueRouter (由 index.html 通过 CDN 全局加载)

import { Dashboard } from './views/Dashboard.js';
import { Projects } from './views/Projects.js';
import { Canvas } from './views/Canvas.js';
import { Assets } from './views/Assets.js';
import { Quality } from './views/Quality.js';
import { Users } from './views/Users.js';
import { Forbidden } from './views/Forbidden.js';

export const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', component: Dashboard, name: 'dashboard', meta: { title: '仪表盘', icon: '📊' } },
  { path: '/projects', component: Projects, name: 'projects', meta: { title: '项目管理', icon: '📁' } },
  { path: '/canvas', component: Canvas, name: 'canvas', meta: { title: '画布', icon: '🎨' } },
  { path: '/assets', component: Assets, name: 'assets', meta: { title: '资产管理', icon: '🖼️' } },
  { path: '/quality', component: Quality, name: 'quality', meta: { title: '质量中心', icon: '🧪' } },
  // P1-C-W1: 新增用户管理路由
  { path: '/users', component: Users, name: 'users', meta: { title: '用户管理', icon: '👤' } },
  { path: '/403', component: Forbidden, name: 'forbidden', meta: { title: '无权限' } },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
];

export function createAppRouter() {
  if (typeof window === 'undefined' || !window.VueRouter) {
    throw new Error('[router] window.VueRouter not found — 请在 index.html 引入 vue-router 的 CDN');
  }
  const { createRouter, createWebHashHistory } = window.VueRouter;
  const router = createRouter({
    history: createWebHashHistory(),
    routes,
  });
  return router;
}

export const navItems = routes
  .filter((r) => r.name)
  .map((r) => ({ name: r.name, path: r.path, title: r.meta && r.meta.title, icon: r.meta && r.meta.icon }));