// api/canvas.js — 画布 5 个 API 端点 (P1-C-W1 spec)
import { httpGet, httpSend } from './client.js';

/** GET /api/canvas/{id} — 加载画布 (404 if 不存在) */
export function getCanvas(canvasId) {
  return httpGet(`/api/canvas/${encodeURIComponent(canvasId)}`);
}

/** POST /api/canvas/{id}/save — 保存画布 (nodes + connections) */
export function saveCanvas(canvasId, payload) {
  return httpSend('POST', `/api/canvas/${encodeURIComponent(canvasId)}/save`, payload);
}

/** GET /api/canvas/templates — 画布模板列表 */
export function listCanvasTemplates() {
  return httpGet('/api/canvas/templates');
}

/** POST /api/canvas/{id}/render — 触发渲染 (返回 task_id) */
export function renderCanvas(canvasId, format = 'png') {
  return httpSend('POST', `/api/canvas/${encodeURIComponent(canvasId)}/render`, { format });
}

/** GET /api/canvas/{id}/export?format=json|png|svg|pdf — 导出 (返回 download_url) */
export function exportCanvas(canvasId, format = 'json') {
  return httpGet(`/api/canvas/${encodeURIComponent(canvasId)}/export?format=${encodeURIComponent(format)}`);
}
