/**
 * RBAC 插件 (Role-Based Access Control)
 * ----------------------------------------------------------------
 * 6 角色权限矩阵 + Vue 3 directive (v-permission / v-role) + 路由守卫
 * 设计原则:
 *   - 单一数据源: ROLE_PERMISSIONS[role] = action[] (Set-like)
 *   - 失效安全: 未登录 → 无任何权限 (拒绝优先)
 *   - 指令副作用最小: 仅 remove / display:none, 不动 ARIA 之外属性
 *   - 与 store/auth.js 集成: 通过 window.__AUTH__.currentRole 读取当前角色
 * ----------------------------------------------------------------
 * 6 角色: admin / prod_lead / qc_lead / annotator / reviewer / viewer
 * ----------------------------------------------------------------
 */

// ============================================================
// 权限矩阵 (R6.5-W2 设计, 与产品 PRD §4.2 对齐)
// ============================================================
const ROLE_PERMISSIONS = Object.freeze({
  // 系统管理员: 全部权限
  admin: Object.freeze([
    'view:dashboard', 'view:stats',
    'view:asset', 'create:asset', 'edit:asset', 'delete:asset',
    'view:requirement', 'create:requirement', 'edit:requirement', 'approve:requirement',
    'view:task', 'create:task', 'assign:task', 'submit:task', 'review:task',
    'view:dataset', 'create:dataset', 'export:dataset',
    'view:eval', 'create:eval', 'manage:badcase',
    'view:user', 'manage:user',
    'view:audit', 'view:lineage', 'create:backup',
  ]),

  // 生产负责人: 需求/任务/资产创建 + 审批
  prod_lead: Object.freeze([
    'view:dashboard', 'view:stats',
    'view:asset', 'create:asset', 'edit:asset',
    'view:requirement', 'create:requirement', 'edit:requirement', 'approve:requirement',
    'view:task', 'create:task', 'assign:task',
    'view:dataset', 'create:dataset', 'export:dataset',
    'view:eval', 'create:eval', 'manage:badcase',
    'view:user',
    'view:audit', 'view:lineage',
  ]),

  // 质检负责人: 审核任务 + 评测 + badcase
  qc_lead: Object.freeze([
    'view:dashboard', 'view:stats',
    'view:asset',
    'view:requirement',
    'view:task', 'review:task', 'assign:task',
    'view:dataset',
    'view:eval', 'create:eval', 'manage:badcase',
    'view:user',
    'view:audit',
  ]),

  // 标注员: 接收任务 + 提交 + 创建自有任务
  annotator: Object.freeze([
    'view:dashboard',
    'view:asset',
    'view:requirement',
    'view:task', 'submit:task', 'create:task',
    'view:dataset',
  ]),

  // 复核员: 只读 + 审核
  reviewer: Object.freeze([
    'view:dashboard',
    'view:asset',
    'view:requirement',
    'view:task', 'review:task', 'submit:task',
    'view:dataset',
    'view:eval',
    'view:audit',
  ]),

  // 查看者: 只读 dashboard + 资产 + 统计
  viewer: Object.freeze([
    'view:dashboard', 'view:stats',
    'view:asset',
    'view:requirement',
    'view:task',
    'view:dataset',
    'view:eval',
  ]),
});

// 角色显示名 (用于 UI 与 i18n 键映射)
const ROLE_LABELS = Object.freeze({
  admin:     { zh: '系统管理员', en: 'Admin' },
  prod_lead: { zh: '生产负责人', en: 'Production Lead' },
  qc_lead:   { zh: '质检负责人', en: 'QC Lead' },
  annotator: { zh: '标注员',     en: 'Annotator' },
  reviewer:  { zh: '复核员',     en: 'Reviewer' },
  viewer:    { zh: '查看者',     en: 'Viewer' },
});

const VALID_ROLES = Object.freeze(Object.keys(ROLE_PERMISSIONS));

// ============================================================
// 核心: 权限检查
// ============================================================
function can(role, action) {
  if (!role || !action) return false;
  const perms = ROLE_PERMISSIONS[role];
  if (!perms) return false;
  return perms.includes(action);
}

function canAny(role, actions) {
  if (!Array.isArray(actions) || actions.length === 0) return false;
  return actions.some(a => can(role, a));
}

function canAll(role, actions) {
  if (!Array.isArray(actions) || actions.length === 0) return false;
  return actions.every(a => can(role, a));
}

function getCurrentRole() {
  // 与 store/auth.js 集成: 优先读 reactive store, 其次读 window fallback
  if (window.__AUTH__ && typeof window.__AUTH__.currentRole !== 'undefined') {
    return window.__AUTH__.currentRole;
  }
  // fallback: localStorage (供纯静态 demo 用)
  try { return localStorage.getItem('rbac.role') || null; } catch (e) { return null; }
}

function setCurrentRole(role) {
  if (role && !VALID_ROLES.includes(role)) {
    console.warn('[rbac] invalid role:', role);
    return false;
  }
  if (window.__AUTH__) window.__AUTH__.currentRole = role;
  try { role ? localStorage.setItem('rbac.role', role) : localStorage.removeItem('rbac.role'); } catch (e) {}
  // 触发全局事件, 让 v-permission 指令可以重渲染
  window.dispatchEvent(new CustomEvent('rbac:role-changed', { detail: { role } }));
  return true;
}

// ============================================================
// Vue 3 Plugin
// ============================================================
const RbacPlugin = {
  install(app, options = {}) {
    // globalProperties
    app.config.globalProperties.$rbac = {
      can: can,
      canAny: canAny,
      canAll: canAll,
      getRole: getCurrentRole,
      setRole: setCurrentRole,
      roles: VALID_ROLES,
      labels: ROLE_LABELS,
      permissions: ROLE_PERMISSIONS,
    };
    app.provide('rbac', app.config.globalProperties.$rbac);

    // ---- v-permission: 无权限时移除元素 ----
    app.directive('permission', {
      mounted(el, binding) {
        const action = binding.value;
        if (!action) return;
        const role = getCurrentRole();
        if (!can(role, action)) {
          el.__rbac_hidden__ = true;
          el.style.display = 'none';
          el.setAttribute('aria-hidden', 'true');
        }
      },
      updated(el, binding) {
        const action = binding.value;
        if (!action) return;
        const role = getCurrentRole();
        if (!can(role, action)) {
          if (!el.__rbac_hidden__) {
            el.__rbac_hidden__ = true;
            el.style.display = 'none';
            el.setAttribute('aria-hidden', 'true');
          }
        } else if (el.__rbac_hidden__) {
          el.__rbac_hidden__ = false;
          el.style.display = '';
          el.removeAttribute('aria-hidden');
        }
      },
    });

    // ---- v-role: 仅指定角色可见, 多角色取 OR ----
    app.directive('role', {
      mounted(el, binding) {
        const wanted = binding.value;
        if (!wanted) return;
        const list = Array.isArray(wanted) ? wanted : [wanted];
        const role = getCurrentRole();
        if (!list.includes(role)) {
          el.__rbac_role_hidden__ = true;
          el.style.display = 'none';
          el.setAttribute('aria-hidden', 'true');
        }
      },
      updated(el, binding) {
        const wanted = binding.value;
        if (!wanted) return;
        const list = Array.isArray(wanted) ? wanted : [wanted];
        const role = getCurrentRole();
        if (!list.includes(role)) {
          if (!el.__rbac_role_hidden__) {
            el.__rbac_role_hidden__ = true;
            el.style.display = 'none';
            el.setAttribute('aria-hidden', 'true');
          }
        } else if (el.__rbac_role_hidden__) {
          el.__rbac_role_hidden__ = false;
          el.style.display = '';
          el.removeAttribute('aria-hidden');
        }
      },
    });

    // 监听角色变化, 强制重渲染所有受控元素
    window.addEventListener('rbac:role-changed', () => {
      document.querySelectorAll('[v-permission], [v-role]').forEach(el => {
        // 触发自定义重渲染: 通过下一帧 reflow
        const ev = new Event('rbac:refresh', { bubbles: true });
        el.dispatchEvent(ev);
      });
    });
  },
};

// ============================================================
// 路由守卫 (Vue Router 4 兼容)
// 用法:  router.beforeEach(createRbacGuard({ '/admin': ['admin'], '/audit': ['admin','qc_lead'] }))
// ============================================================
function createRbacGuard(routeMap = {}) {
  return function rbacGuard(to, _from, next) {
    const role = getCurrentRole();
    const required = routeMap[to.path];
    if (!required) return next();
    const list = Array.isArray(required) ? required : [required];
    if (list.includes(role)) return next();
    console.warn(`[rbac] route "${to.path}" denied for role "${role}", required one of:`, list);
    next({ path: '/403', query: { from: to.path, required: list.join(',') } });
  };
}

// ============================================================
// Exports (浏览器全局 + CommonJS 兼容)
// ============================================================
if (typeof window !== 'undefined') {
  window.RbacPlugin = RbacPlugin;
  window.RbacCore = {
    ROLE_PERMISSIONS, ROLE_LABELS, VALID_ROLES,
    can, canAny, canAll,
    getCurrentRole, setCurrentRole,
    createRbacGuard,
  };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { RbacPlugin, ROLE_PERMISSIONS, ROLE_LABELS, VALID_ROLES, can, canAny, canAll, getCurrentRole, setCurrentRole, createRbacGuard };
}
