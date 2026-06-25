// api/users.js — 用户 6 个 API 端点 (P1-C-W1 spec)
import { httpGet, httpSend } from './client.js';

/** GET /api/users?page=&page_size=&role= — 用户列表 (分页 + 角色过滤) */
export function listUsers({ page = 1, pageSize = 20, role = '' } = {}) {
  const qs = new URLSearchParams();
  qs.set('page', String(page));
  qs.set('page_size', String(pageSize));
  if (role) qs.set('role', role);
  return httpGet(`/api/users?${qs.toString()}`);
}

/** POST /api/users — 创建用户 { username, role, email, skills } */
export function createUser(payload) {
  return httpSend('POST', '/api/users', payload);
}

/** PUT /api/users/{id} — 更新用户 (role / status / email) */
export function updateUser(id, payload) {
  return httpSend('PUT', `/api/users/${encodeURIComponent(id)}`, payload);
}

/** DELETE /api/users/{id} — 删除用户 */
export function deleteUser(id) {
  return httpSend('DELETE', `/api/users/${encodeURIComponent(id)}`);
}

/** GET /api/users/{id}/audit?limit= — 用户审计日志 */
export function getUserAudit(id, limit = 20) {
  return httpGet(`/api/users/${encodeURIComponent(id)}/audit?limit=${limit}`);
}
