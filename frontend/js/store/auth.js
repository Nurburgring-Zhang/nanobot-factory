/**
 * 认证 Store (mock, 供前端 demo 用)
 * ----------------------------------------------------------------
 * 提供:
 *   - currentUser: { id, username, role, email }
 *   - currentRole: string (rbac 读取这个)
 *   - login / logout / switchRole (角色热切换)
 *   - 持久化到 localStorage ('auth.user')
 * ----------------------------------------------------------------
 * 与 rbac 集成: rbac.getCurrentRole() 优先读 window.__AUTH__.currentRole
 * ----------------------------------------------------------------
 */
(function () {
  const STORAGE_KEY = 'auth.user';

  const DEFAULT_USERS = {
    admin:     { id: 'u-001', username: 'admin',     role: 'admin',     email: 'admin@hermes.local' },
    prod_lead: { id: 'u-002', username: 'prod_lead', role: 'prod_lead', email: 'prod@hermes.local' },
    qc_lead:   { id: 'u-003', username: 'qc_lead',   role: 'qc_lead',   email: 'qc@hermes.local' },
    annotator: { id: 'u-004', username: 'annotator', role: 'annotator', email: 'anno@hermes.local' },
    reviewer:  { id: 'u-005', username: 'reviewer',  role: 'reviewer',  email: 'rev@hermes.local' },
    viewer:    { id: 'u-006', username: 'viewer',    role: 'viewer',    email: 'view@hermes.local' },
  };

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) return JSON.parse(raw);
    } catch (e) {}
    return { ...DEFAULT_USERS.admin };
  }

  function save(user) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(user)); } catch (e) {}
  }

  // 暴露到 window.__AUTH__, 给 rbac.js 读取
  const authStore = {
    currentUser: load(),
    get currentRole() { return this.currentUser && this.currentUser.role; },
    set currentRole(role) {
      // 通过用户名映射找用户; 若无则用 admin 默认
      const user = Object.values(DEFAULT_USERS).find(u => u.role === role) || DEFAULT_USERS.admin;
      this.currentUser = { ...user };
      save(this.currentUser);
    },
    login(roleOrUsername) {
      // 接受 role 或 username
      let user = DEFAULT_USERS[roleOrUsername];
      if (!user) {
        user = Object.values(DEFAULT_USERS).find(u => u.role === roleOrUsername);
      }
      if (!user) { console.warn('[auth] unknown role/user:', roleOrUsername); return false; }
      this.currentUser = { ...user };
      save(this.currentUser);
      window.dispatchEvent(new CustomEvent('auth:login', { detail: { user: this.currentUser } }));
      return true;
    },
    logout() {
      this.currentUser = null;
      try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
      window.dispatchEvent(new CustomEvent('auth:logout'));
    },
    availableUsers: Object.values(DEFAULT_USERS).map(u => ({ ...u })),
  };

  window.__AUTH__ = authStore;
  window.AuthStore = authStore;
})();
