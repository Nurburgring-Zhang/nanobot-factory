// app.js — Vue 应用入口
// 依赖: window.Vue / window.VueRouter / window.Pinia / window.ElementPlus (由 index.html 加载)
// 模块依赖: ./router.js, ./store/, ./components/, ./views/

import { createAppRouter, navItems } from './router.js';
import { usePinia, authStore } from './store/index.js';
import { LoadingSpinner } from './components/LoadingSpinner.js';
import { EmptyState } from './components/EmptyState.js';
import { ErrorBanner } from './components/ErrorBanner.js';
import { AsyncBoundary } from './components/AsyncBoundary.js';

// 全局 Vue 来自 CDN
const { createApp, ref, computed } = Vue;

function bootstrap() {
  if (typeof window === 'undefined') return;
  if (!window.Vue) {
    console.error('[app] window.Vue missing');
    return;
  }
  if (!window.ElementPlus) {
    console.error('[app] window.ElementPlus missing');
    return;
  }

  const app = createApp({
    name: 'NanobotApp',
    setup() {
      const useAuth = authStore();
      const auth = useAuth();

      // 顶栏 nav 用 navItems (来自 router.js)
      const navs = ref(navItems);

      const userLabel = computed(() => auth.displayName);
      const roleLabel = computed(() => auth.role || 'guest');

      function onLogout() {
        auth.logout();
      }

      return { navs, userLabel, roleLabel, onLogout, auth };
    },
    template: `
      <div class="ls-shell">
        <aside class="ls-sidebar">
          <div class="ls-logo">
            <span class="ls-logo-emoji">🎬</span>
            <span class="ls-logo-text">智影数据工场</span>
          </div>

          <!-- Element Plus el-menu: 与 Vue Router 集成, :default-active 由 $route.path 驱动 -->
          <div class="ls-menu-host">
            <el-menu
              :default-active="$route.path"
              :router="true"
              background-color="transparent"
              text-color="#aaa"
              active-text-color="#409eff">
              <el-menu-item
                v-for="n in navs"
                :key="n.name"
                :index="n.path">
                <span class="ls-mi-icon">{{ n.icon }}</span>
                <span>{{ n.title }}</span>
              </el-menu-item>
            </el-menu>
          </div>

          <div class="ls-sidebar-foot">
            <span class="muted">v1.0.0 | API v2</span>
          </div>
        </aside>

        <div class="ls-main">
          <header class="ls-header">
            <div class="ls-header-title">{{ $route.meta && $route.meta.title || '智影数据工场' }}</div>
            <div class="ls-header-right">
              <el-tag size="small" type="success">服务在线</el-tag>
              <span class="ls-user">
                <span class="ls-user-name">{{ userLabel }}</span>
                <el-tag size="small" :type="auth.isAdmin ? 'danger' : 'info'">{{ roleLabel }}</el-tag>
              </span>
              <el-button size="small" plain @click="onLogout">退出</el-button>
            </div>
          </header>

          <main class="ls-content">
            <router-view v-slot="{ Component }">
              <transition name="fade" mode="out-in">
                <component :is="Component" />
              </transition>
            </router-view>
          </main>
        </div>
      </div>
    `,
  });

  // Element Plus
  app.use(window.ElementPlus, { locale: window.ElementPlusLocaleZhCn });

  // 三态全局组件
  app.component('LoadingSpinner', LoadingSpinner);
  app.component('EmptyState', EmptyState);
  app.component('ErrorBanner', ErrorBanner);
  app.component('AsyncBoundary', AsyncBoundary);

  // Pinia
  try {
    const pinia = usePinia();
    app.use(pinia);
  } catch (e) {
    console.warn('[app] pinia not registered:', e.message);
  }

  // Router
  try {
    const router = createAppRouter();
    app.use(router);
  } catch (e) {
    console.warn('[app] router not registered:', e.message);
  }

  // 全局错误 — 401 跳登录 (后续 worker 完善)
  app.config.errorHandler = (err, _vm, info) => {
    console.error('[app:error]', info, err);
  };

  // 暴露到 window.app 便于其他 worker (如 Forbidden.js) 拿到 router
  window.app = app;

  app.mount('#app');

  // 全局 toast 事件 (供子组件 emit)
  window.addEventListener('toast', (e) => {
    const d = (e && e.detail) || {};
    if (window.ElementPlus && window.ElementPlus.ElMessage) {
      const fn = window.ElementPlus.ElMessage[d.type || 'info'];
      if (typeof fn === 'function') fn(d.message || '');
    }
  });

  // 全局导航事件
  window.addEventListener('navigate', (e) => {
    const to = e && e.detail && e.detail.to;
    if (to && app.config.globalProperties.$router) {
      app.config.globalProperties.$router.push(to);
    }
  });

  console.info('[app] Nanobot SPA mounted');
}

// DOMContentLoaded 后启动
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrap);
} else {
  bootstrap();
}