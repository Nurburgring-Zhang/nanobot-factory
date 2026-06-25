// api/dashboard.js — 仪表盘 5 个 API 端点 (P1-C-W1 spec)
import { httpGet, httpSend } from './client.js';

/** GET /api/stats/overview?period=today|week|month — 仪表盘聚合数据 */
export function getStatsOverview(period = 'today') {
  return httpGet(`/api/stats/overview?period=${encodeURIComponent(period)}`);
}

/** GET /api/tasks/recent?limit=&status= — 最近任务 */
export function getRecentTasks(limit = 10, status = '') {
  const qs = new URLSearchParams();
  qs.set('limit', String(limit));
  if (status) qs.set('status', status);
  return httpGet(`/api/tasks/recent?${qs.toString()}`);
}

/** GET /api/notifications?limit=&unread_only= — 通知列表 */
export function getNotifications(limit = 20, unreadOnly = false) {
  const qs = new URLSearchParams();
  qs.set('limit', String(limit));
  if (unreadOnly) qs.set('unread_only', 'true');
  return httpGet(`/api/notifications?${qs.toString()}`);
}

/** POST /api/notifications/{id}/read — 标记已读 */
export function markNotificationRead(id) {
  return httpSend('POST', `/api/notifications/${encodeURIComponent(id)}/read`);
}

/** GET /api/audit/stats?period=today|week|month — 操作审计统计 */
export function getAuditStats(period = 'today') {
  return httpGet(`/api/audit/stats?period=${encodeURIComponent(period)}`);
}

/** GET /api/users/me — 当前用户 (需鉴权, 401 if 未登录) */
export function getMe() {
  return httpGet('/api/users/me');
}
