// api/projects.js — /api/projects 调用 (P1-C-W1 spec)
import { httpGet, httpSend } from './client.js';

/**
 * P1-C-W1: 项目 API 全部走完整路径 /api/projects/* (task spec 强制)
 * 列表 / 详情 / 创建 / 更新 / 删除 / 成员
 */

/** GET /api/projects?page=&page_size=&status= — 项目列表 */
export function listProjects(params = {}) {
  const { page = 1, pageSize = 20, status = '' } = params;
  const qs = new URLSearchParams();
  qs.set('page', String(page));
  qs.set('page_size', String(pageSize));
  if (status) qs.set('status', status);
  return httpGet(`/api/projects?${qs.toString()}`);
}

/** GET /api/projects/{id} — 详情 (兼容) */
export function getProject(id) {
  return httpGet(`/api/projects/${encodeURIComponent(id)}`);
}

/** POST /api/projects — 创建项目 { name, description, status, owner, members } */
export function createProject(payload) {
  return httpSend('POST', '/api/projects', payload);
}

/** PUT /api/projects/{id} — 更新项目 */
export function updateProject(id, payload) {
  return httpSend('PUT', `/api/projects/${encodeURIComponent(id)}`, payload);
}

/** DELETE /api/projects/{id} — 删除项目 */
export function deleteProject(id) {
  return httpSend('DELETE', `/api/projects/${encodeURIComponent(id)}`);
}

/** GET /api/projects/{id}/members — 项目成员 */
export function getProjectMembers(id) {
  return httpGet(`/api/projects/${encodeURIComponent(id)}/members`);
}
