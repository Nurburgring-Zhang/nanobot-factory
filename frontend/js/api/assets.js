// api/assets.js — /api/assets 调用 (P1-C-W1 spec)
import { httpGet, httpSend, BASE_URL } from './client.js';

/**
 * P1-C-W1: 资产 API 全部走完整路径 /api/assets/* (task spec 强制)
 * 列表 / 详情 / 创建 / 更新 / 删除 / 上传 / 下载 / 标签
 */

function buildQuery(params) {
  const qs = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
  });
  const tail = qs.toString() ? `?${qs}` : '';
  return tail;
}

/** GET /api/assets?page=&page_size=&type=&q= — 列表 (分页 + 类型 + 搜索) */
export function listAssets(params = {}) {
  const { page = 1, pageSize = 20, type = '', q = '' } = params;
  const qs = new URLSearchParams();
  qs.set('page', String(page));
  qs.set('page_size', String(pageSize));
  if (type) qs.set('type', type);
  if (q) qs.set('q', q);
  return httpGet(`/api/assets?${qs.toString()}`);
}

/** GET /api/assets/{id} — 详情 (如果后端支持) */
export function getAsset(id) {
  return httpGet(`/api/assets/${encodeURIComponent(id)}`);
}

/** POST /api/assets — 创建资产 (JSON 方式, 小数据) */
export function createAsset(payload) {
  return httpSend('POST', '/api/assets', payload);
}

/** PUT /api/assets/{id} — 更新资产 */
export function updateAsset(id, payload) {
  return httpSend('PUT', `/api/assets/${encodeURIComponent(id)}`, payload);
}

/** DELETE /api/assets/{id} — 删除资产 */
export function deleteAsset(id) {
  return httpSend('DELETE', `/api/assets/${encodeURIComponent(id)}`);
}

/**
 * POST /api/assets/upload — multipart 上传
 * 用法: uploadAsset(file, { type: 'image', tags: 'demo,test' })
 * 返回 Promise<{success, data: {id, name, size, ...}}>
 */
export async function uploadAsset(file, { type = 'image', tags = '' } = {}) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('type', type);
  if (tags) fd.append('tags', tags);
  const token = (typeof localStorage !== 'undefined' && localStorage.getItem('imdf_token')) || '';
  const res = await fetch('/api/assets/upload', {
    method: 'POST',
    headers: token ? { 'Authorization': 'Bearer ' + token } : {},
    body: fd,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error('Upload failed: HTTP ' + res.status + ' ' + text.substring(0, 200));
  }
  return res.json();
}

/** GET /api/assets/{id}/download — 下载资产 (浏览器原生跳转, 不用 fetch) */
export function buildDownloadUrl(id) {
  return `/api/assets/${encodeURIComponent(id)}/download`;
}

/** POST /api/assets/{id}/tag — 打标签 { tags: [...] } */
export function tagAsset(id, tags) {
  return httpSend('POST', `/api/assets/${encodeURIComponent(id)}/tag`, { tags });
}
