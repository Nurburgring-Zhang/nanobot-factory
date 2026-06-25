/**
 * Dashboard Demo (独立 Vue 3 应用)
 * ----------------------------------------------------------------
 * 演示 3 个 plugin 同时工作:
 *   - RBAC: v-permission / v-role 指令
 *   - a11y:  v-label 指令 + skip-link + focus-visible
 *   - i18n:  $t('key.path') 模板调用 + 顶栏下拉切换
 * ----------------------------------------------------------------
 * 页面特性:
 *   - 顶栏: 品牌 + 角色选择 + 语言切换 + 当前用户
 *   - 主区: 6 个统计卡片 + 6 个 demo 按钮 (v-permission 过滤)
 * ----------------------------------------------------------------
 */
(function () {
  if (!window.Vue) { console.error('[dashboard-demo] Vue 3 not loaded'); return; }
  if (!window.RbacPlugin) { console.error('[dashboard-demo] RbacPlugin not loaded'); return; }
  if (!window.I18nPlugin) { console.error('[dashboard-demo] I18nPlugin not loaded'); return; }
  if (!window.A11yPlugin) { console.error('[dashboard-demo] A11yPlugin not loaded'); return; }

  const { createApp, ref, reactive, computed, onMounted } = Vue;
  const auth = window.__AUTH__ || {};

  const app = createApp({
    setup() {
      // === 状态 ===
      const stats = reactive({
        totalUsers: 6, totalAssets: 1248, totalDatasets: 12,
        totalTasks: 87, completedTasks: 64, storageGb: 156,
        approvalRate: 73,
      });

      const roles = window.RbacCore.VALID_ROLES;
      const languages = window.I18nCore.SUPPORTED;

      // 响应式: 当前语言 (i18n plugin 切换后会更新)
      const currentLang = ref((localStorage.getItem('i18n.lang') || 'zh-CN').split('-')[0]);

      // 响应式: 当前角色, 配合 v-permission 重新求值
      const currentRole = ref(auth.currentRole || 'admin');

      // 触发 v-permission 重渲染的 tick
      const roleTick = ref(0);

      // 演示按钮 (每个有 1 个 action + 1 个 i18n key)
      const demoActions = [
        { i18nKey: 'btn.create_user',     action: 'create:user' },
        { i18nKey: 'btn.create_asset',    action: 'create:asset' },
        { i18nKey: 'btn.create_eval',     action: 'create:eval' },
        { i18nKey: 'btn.review',          action: 'review:task' },
        { i18nKey: 'btn.backup',          action: 'create:backup' },
        { i18nKey: 'btn.decompose',       action: 'edit:requirement' },
      ];

      // 权限矩阵展示数据 (action × roles)
      const rbacCore = window.RbacCore;
      const matrixActions = [
        'create:user', 'create:asset', 'create:requirement', 'approve:requirement',
        'create:task', 'assign:task', 'submit:task', 'review:task',
        'create:dataset', 'export:dataset',
        'create:eval', 'manage:badcase',
        'view:user', 'view:audit', 'create:backup', 'view:stats',
      ];
      const matrixRows = matrixActions.map(action => ({
        action,
        flags: roles.reduce((acc, r) => {
          acc[r] = rbacCore.can(r, action);
          return acc;
        }, {}),
      }));

      // 暴露 $rbac 工具给 template
      const rbac = {
        can: rbacCore.can,
        canAny: rbacCore.canAny,
        canAll: rbacCore.canAll,
      };

      function onRoleChange(role) {
        if (auth.login) auth.login(role);
        if (window.RbacCore.setCurrentRole) window.RbacCore.setCurrentRole(role);
        currentRole.value = role;
        roleTick.value++; // 触发 v-permission 重渲染
      }

      function onLangChange(lang) {
        const inst = app.config.globalProperties.$i18n;
        if (inst && inst.setLang) inst.setLang(lang);
        currentLang.value = lang.split('-')[0];
      }

      onMounted(() => {
        // 启动时同步
        if (auth.currentRole && window.RbacCore.setCurrentRole) {
          window.RbacCore.setCurrentRole(auth.currentRole);
        }
        // 监听 rbac 变化, 触发 v-permission 重渲染
        window.addEventListener('rbac:role-changed', (e) => {
          if (e.detail && e.detail.role) currentRole.value = e.detail.role;
          roleTick.value++;
        });
        // 监听 i18n 变化
        window.addEventListener('i18n:lang-changed', (e) => {
          if (e.detail && e.detail.lang) currentLang.value = e.detail.lang.split('-')[0];
        });
      });

      return {
        stats, roles, languages,
        currentRole, currentLang, roleTick,
        demoActions,
        matrixRows,
        rbac,
        onRoleChange, onLangChange,
        auth,
      };
    },
  });

  // === 安装 3 个 plugin ===
  app.use(window.RbacPlugin);
  app.use(window.A11yPlugin, { autoLogTabOrder: true });
  app.use(window.I18nPlugin, { default: 'zh-CN' });

  // === 挂载 ===
  const target = document.getElementById('dashboard-demo-app');
  if (target) {
    app.mount('#dashboard-demo-app');
    console.log('[dashboard-demo] mounted, RBAC + a11y + i18n active');
  } else {
    console.warn('[dashboard-demo] #dashboard-demo-app not found in DOM');
  }
})();
