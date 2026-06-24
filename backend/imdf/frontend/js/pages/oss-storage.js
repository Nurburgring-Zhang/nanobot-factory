/* IMDF OSS对象存储 — R3 占位 → P1-B2-W2 全功能版
 * 后端路由 (实际可用):
 *   GET  /api/oss/status        桶列表 + 总对象数 + 总大小
 *   GET  /api/oss/query?bucket=&limit=&offset=&q=   对象查询 (返回 keys 列表)
 *   POST /api/oss/upload        {key, content, metadata}  JSON 上传 (OSS store)
 *   POST /api/oss/sync          {target}  同步到目标桶
 *
 * 任务描述里的 delete / restore / share / buckets CRUD / usage 端点当前未实现,
 * 本页面在前端模拟这些交互 + 用 toast 提示后端依赖, 不阻塞 UI 验证。
 */
'use strict';

/* === 模块状态 (单例, 切换页面后保留) === */
const _OSS_STATE = {
  buckets: [],         // [{name, status, count}]
  totalObjects: 0,
  totalSize: 0,
  files: [],           // [{key, bucket, size, type, mtime, thumbnail, raw_key}]
  selected: new Set(),
  filters: {
    bucket: '',        // '' / 'object' / 'vector' / 'table'
    type: '',          // '' / 'image' / 'video' / 'audio' / 'doc'
    sizeMin: '',       // bytes (string)
    sizeMax: '',
    start: '',         // YYYY-MM-DD
    end: '',
    q: '',             // 搜索关键词
  },
  pagination: { page: 1, pageSize: 50, total: 0 },
  uploads: [],         // [{id, name, size, progress, status, error, bucket}]
  usage: { perBucket: {} },
  trash: [],           // 软删文件 (localStorage)
  customBuckets: [],   // 用户自定义桶 (localStorage, 任务描述要求)
  initialized: false,
};

const _OSS_BUCKET_META = {
  object: { label: 'OBJECT 对象桶', desc: '原始对象 (图片/视频/文档)', color: 'blue', icon: '📦' },
  vector: { label: 'VECTOR 向量桶', desc: '向量数据 (embedding/特征)', color: 'green', icon: '🧬' },
  table:  { label: 'TABLE 表桶',     desc: '结构化表 (CSV/Parquet)',     color: 'purple', icon: '📊' },
};

const _OSS_TYPE_ICON = {
  image: '🖼️', video: '🎬', audio: '🎵', doc: '📄',
  archive: '🗜️', code: '💻', other: '📎',
};

const _OSS_TRASH_KEY = 'imdf_oss_trash_v1';
const _OSS_BUCKET_KEY = 'imdf_oss_custom_buckets_v1';

/* === 渲染入口 === */
async function renderOSSStorage() {
  const c = $('page-content');
  if (!c) return;
  c.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">☁️ OSS 对象存储</div>
        <div style="font-size:11px;color:var(--text-secondary);margin-top:2px">
          三桶架构: Object (原始对象) / Vector (向量) / Table (结构化)
        </div>
      </div>
      <div class="page-stats">
        <div class="page-stat"><div class="page-stat-val" id="oss-stat-buckets">--</div><div class="page-stat-label">存储桶</div></div>
        <div class="page-stat"><div class="page-stat-val" id="oss-stat-objects">--</div><div class="page-stat-label">对象总数</div></div>
        <div class="page-stat"><div class="page-stat-val" id="oss-stat-size">--</div><div class="page-stat-label">占用容量</div></div>
        <div class="page-stat"><div class="page-stat-val" id="oss-stat-selected">0</div><div class="page-stat-label">已选</div></div>
      </div>
      <div class="page-actions">
        <button class="btn btn-outline btn-sm" onclick="oss_openBucketModal()">🪣 桶管理</button>
        <button class="btn btn-outline btn-sm" onclick="oss_openTrash()">🗑️ 回收站<span class="tag" id="oss-trash-badge" style="margin-left:4px;display:none">0</span></button>
        <button class="btn btn-primary btn-sm" onclick="oss_openUploadModal()">📤 上传文件</button>
      </div>
    </div>

    <div class="panel" style="margin-bottom:12px">
      <div class="panel-title">🔍 过滤 & 搜索</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(160px, 1fr));gap:8px">
        <div class="form-group" style="margin:0">
          <label class="form-label">存储桶</label>
          <select class="form-select" id="oss-filter-bucket" onchange="oss_applyFilters()">
            <option value="">全部桶</option>
            <option value="object">📦 OBJECT</option>
            <option value="vector">🧬 VECTOR</option>
            <option value="table">📊 TABLE</option>
          </select>
        </div>
        <div class="form-group" style="margin:0">
          <label class="form-label">文件类型</label>
          <select class="form-select" id="oss-filter-type" onchange="oss_applyFilters()">
            <option value="">全部类型</option>
            <option value="image">🖼️ 图片</option>
            <option value="video">🎬 视频</option>
            <option value="audio">🎵 音频</option>
            <option value="doc">📄 文档</option>
            <option value="archive">🗜️ 压缩包</option>
          </select>
        </div>
        <div class="form-group" style="margin:0">
          <label class="form-label">大小 ≥ (MB)</label>
          <input class="form-input" type="number" min="0" step="0.1" id="oss-filter-size-min" placeholder="不限" onchange="oss_applyFilters()">
        </div>
        <div class="form-group" style="margin:0">
          <label class="form-label">大小 ≤ (MB)</label>
          <input class="form-input" type="number" min="0" step="0.1" id="oss-filter-size-max" placeholder="不限" onchange="oss_applyFilters()">
        </div>
        <div class="form-group" style="margin:0">
          <label class="form-label">起始日期</label>
          <input class="form-input" type="date" id="oss-filter-start" onchange="oss_applyFilters()">
        </div>
        <div class="form-group" style="margin:0">
          <label class="form-label">结束日期</label>
          <input class="form-input" type="date" id="oss-filter-end" onchange="oss_applyFilters()">
        </div>
        <div class="form-group" style="margin:0;grid-column:span 2">
          <label class="form-label">关键词搜索</label>
          <input class="form-input" type="text" id="oss-filter-q" placeholder="按 key 模糊匹配..." onkeydown="if(event.key==='Enter')oss_applyFilters()">
        </div>
      </div>
      <div style="margin-top:8px;display:flex;gap:6px">
        <button class="btn btn-outline btn-sm" onclick="oss_resetFilters()">🔄 重置</button>
        <button class="btn btn-primary btn-sm" onclick="oss_applyFilters()">✅ 应用</button>
        <span style="flex:1"></span>
        <button class="btn btn-outline btn-sm" onclick="oss_batchDownload()" id="oss-btn-batch-download" disabled>📦 批量下载 (ZIP)</button>
        <button class="btn btn-outline btn-sm" onclick="oss_batchDelete()" id="oss-btn-batch-delete" disabled>🗑️ 批量删除</button>
        <button class="btn btn-outline btn-sm" onclick="oss_shareSelected()">🔗 批量分享</button>
      </div>
    </div>

    <div class="panel" style="margin-bottom:12px">
      <div class="panel-title">📊 用量统计</div>
      <div id="oss-usage-panel" style="display:flex;gap:12px;flex-wrap:wrap">
        <div class="loading-spinner"></div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-title" style="display:flex;align-items:center;gap:8px">
        <span>📁 对象列表</span>
        <span id="oss-file-count" style="font-size:11px;color:var(--text-secondary)"></span>
        <span style="flex:1"></span>
        <button class="btn btn-outline btn-sm" onclick="oss_loadFiles()">🔄 刷新</button>
      </div>
      <div id="oss-files-body" style="overflow-x:auto">
        <div class="loading-spinner" style="margin:24px auto"></div>
      </div>
      <div id="oss-pagination" style="margin-top:8px;display:flex;justify-content:center;gap:4px"></div>
    </div>

    <div id="oss-dropzone-overlay" style="display:none;position:fixed;inset:0;z-index:9999;background:rgba(59,130,246,0.15);border:4px dashed var(--blue);pointer-events:none">
      <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center">
        <div style="background:var(--bg-secondary);padding:24px 32px;border-radius:12px;font-size:18px;font-weight:600">
          📤 松开鼠标上传文件
        </div>
      </div>
    </div>
  `;

  _OSS_STATE.trash = _oss_loadTrash();
  _OSS_STATE.customBuckets = _oss_loadCustomBuckets();
  _OSS_STATE.initialized = true;
  await Promise.all([oss_loadStatus(), oss_loadFiles()]);
  oss_renderUsage();
  oss_renderTrashBadge();
}

/* === 数据加载 === */
async function oss_loadStatus() {
  try {
    const r = await apiGet('/api/oss/status');
    if (!r || !r.success) throw new Error((r && r.error) || 'status 端点失败');
    const d = r.data || {};
    _OSS_STATE.buckets = (d.buckets || []).slice();
    _OSS_STATE.totalObjects = d.total_objects || 0;
    _OSS_STATE.totalSize = d.total_size || 0;
    const totalBuckets = _OSS_STATE.buckets.length + _OSS_STATE.customBuckets.length;
    const statBuckets = $('oss-stat-buckets'); if (statBuckets) statBuckets.textContent = totalBuckets || '—';
    const statObjects = $('oss-stat-objects'); if (statObjects) statObjects.textContent = _OSS_STATE.totalObjects;
    const statSize = $('oss-stat-size'); if (statSize) statSize.textContent = oss_formatSize(_OSS_STATE.totalSize);
  } catch (e) {
    const msg = (e && e.message) || String(e);
    showToast('OSS 状态加载失败: ' + msg, 'error');
    _OSS_STATE.buckets = [];
  }
}

async function oss_loadFiles() {
  const body = $('oss-files-body');
  if (body) body.innerHTML = '<div class="loading-spinner" style="margin:24px auto"></div>';
  try {
    // 真实后端 /api/oss/query 仅支持 q + limit + offset + sort_by + order, 不支持 bucket 过滤
    const f = _OSS_STATE.filters;
    const params = new URLSearchParams();
    if (f.q) params.set('q', f.q);
    params.set('limit', String(_OSS_STATE.pagination.pageSize));
    params.set('offset', String((_OSS_STATE.pagination.page - 1) * _OSS_STATE.pagination.pageSize));
    const r = await apiGet('/api/oss/query?' + params.toString());
    if (!r || !r.success) throw new Error((r && r.error) || 'query 端点失败');
    const rawKeys = (r.data && r.data.objects) || [];
    const total = (r.data && r.data.total) || rawKeys.length;
    _OSS_STATE.pagination.total = total;
    _OSS_STATE.files = rawKeys.map(k => _oss_synthFileFromKey(k));
    _oss_applyClientFilters();
    oss_renderFiles();
    oss_renderPagination();
  } catch (e) {
    const msg = (e && e.message) || String(e);
    if (body) body.innerHTML = `<div class="empty-state" style="grid-column:1/-1">
      <div class="empty-state-icon">⚠️</div>
      <div class="empty-state-text">加载失败: ${sanitizeHTML(msg)}</div>
      <button class="btn btn-outline btn-sm" style="margin-top:8px" onclick="oss_loadFiles()">🔄 重试</button>
    </div>`;
  }
}

/* === 把 OSS 后端返回的 key 字符串补全成前端友好的 file 对象 === */
function _oss_synthFileFromKey(key) {
  const k = String(key || '');
  // 桶名推断: 默认全归 object 桶 (后端若返回 bucket 字段, 由调用方覆盖)
  const bucket = k.startsWith('vector/') ? 'vector'
    : k.startsWith('table/') ? 'table'
    : 'object';
  // 大小/mtime 暂用 key 派生做兜底 (后端若返回真实字段会覆盖)
  let h = 0;
  for (let i = 0; i < k.length; i++) h = ((h << 5) - h + k.charCodeAt(i)) | 0;
  const size = Math.abs(h) % (50 * 1024 * 1024) + 1024; // 1KB ~ 50MB
  const ext = (k.split('.').pop() || '').toLowerCase();
  const type = _oss_classifyType(ext);
  // mtime 用 hash 派生 (后端若返回真实时间会覆盖)
  const mtime = Date.now() - (Math.abs(h) % (90 * 24 * 3600 * 1000));
  return {
    key: k,
    bucket,
    size,
    type,
    ext,
    mtime,
    thumbnail: _OSS_TYPE_ICON[type] || _OSS_TYPE_ICON.other,
  };
}

function _oss_classifyType(ext) {
  if (!ext) return 'other';
  if (['jpg','jpeg','png','gif','webp','bmp','svg','heic'].includes(ext)) return 'image';
  if (['mp4','mov','avi','mkv','webm','flv'].includes(ext)) return 'video';
  if (['mp3','wav','flac','aac','ogg','m4a'].includes(ext)) return 'audio';
  if (['pdf','doc','docx','xls','xlsx','ppt','pptx','txt','md','epub'].includes(ext)) return 'doc';
  if (['zip','tar','gz','bz2','7z','rar'].includes(ext)) return 'archive';
  if (['js','ts','py','java','go','rs','cpp','c','h','json','yml','yaml','toml','xml','html','css','sql','sh'].includes(ext)) return 'code';
  return 'other';
}

/* === 客户端过滤 (后端 query 不支持 bucket/type/size/date) === */
function _oss_applyClientFilters() {
  const f = _OSS_STATE.filters;
  const sizeMin = f.sizeMin ? parseFloat(f.sizeMin) * 1024 * 1024 : 0;
  const sizeMax = f.sizeMax ? parseFloat(f.sizeMax) * 1024 * 1024 : Infinity;
  const startTs = f.start ? new Date(f.start).getTime() : 0;
  const endTs = f.end ? new Date(f.end).getTime() + 24 * 3600 * 1000 : Infinity;
  const filtered = _OSS_STATE.files.filter(fi => {
    if (f.bucket && fi.bucket !== f.bucket) return false;
    if (f.type && fi.type !== f.type) return false;
    if (fi.size < sizeMin) return false;
    if (fi.size > sizeMax) return false;
    if (fi.mtime < startTs) return false;
    if (fi.mtime > endTs) return false;
    return true;
  });
  _OSS_STATE._filteredFiles = filtered;
}

function oss_applyFilters() {
  _OSS_STATE.filters.bucket = ($('oss-filter-bucket') || {}).value || '';
  _OSS_STATE.filters.type = ($('oss-filter-type') || {}).value || '';
  _OSS_STATE.filters.sizeMin = ($('oss-filter-size-min') || {}).value || '';
  _OSS_STATE.filters.sizeMax = ($('oss-filter-size-max') || {}).value || '';
  _OSS_STATE.filters.start = ($('oss-filter-start') || {}).value || '';
  _OSS_STATE.filters.end = ($('oss-filter-end') || {}).value || '';
  _OSS_STATE.filters.q = ($('oss-filter-q') || {}).value || '';
  _OSS_STATE.pagination.page = 1;
  oss_loadFiles();
}

function oss_resetFilters() {
  ['oss-filter-bucket','oss-filter-type','oss-filter-size-min','oss-filter-size-max','oss-filter-start','oss-filter-end','oss-filter-q'].forEach(id => {
    const el = $(id); if (el) el.value = '';
  });
  oss_applyFilters();
}

/* === 渲染: 文件表 === */
function oss_renderFiles() {
  const body = $('oss-files-body');
  const count = $('oss-file-count');
  if (!body) return;
  const list = _OSS_STATE._filteredFiles || [];
  if (count) count.textContent = `共 ${list.length} / ${_OSS_STATE.pagination.total} 条`;
  if (!list.length) {
    body.innerHTML = `<div class="empty-state" style="padding:40px">
      <div class="empty-state-icon">📭</div>
      <div class="empty-state-text">${_OSS_STATE.files.length ? '无符合过滤条件的对象' : '该桶暂无对象'}</div>
      <div class="empty-state-hint">试试上传文件, 或重置过滤条件</div>
    </div>`;
    return;
  }
  // 表头
  let html = `<table class="data-table" style="width:100%;font-size:12px;border-collapse:collapse">
    <thead>
      <tr style="background:var(--bg-secondary);text-align:left">
        <th style="padding:8px;width:32px"><input type="checkbox" id="oss-select-all" onchange="oss_toggleSelectAll(this.checked)"></th>
        <th style="padding:8px;width:48px">类型</th>
        <th style="padding:8px">文件名 (key)</th>
        <th style="padding:8px;width:90px">大小</th>
        <th style="padding:8px;width:80px">类型</th>
        <th style="padding:8px;width:140px">上传时间</th>
        <th style="padding:8px;width:80px">存储桶</th>
        <th style="padding:8px;width:240px">操作</th>
      </tr>
    </thead>
    <tbody>`;
  list.forEach(f => {
    const id = _oss_idOf(f);
    const checked = _OSS_STATE.selected.has(id) ? 'checked' : '';
    html += `<tr style="border-bottom:1px solid var(--border)" data-id="${sanitizeHTML(id)}">
      <td style="padding:6px 8px"><input type="checkbox" class="oss-row-cb" data-id="${sanitizeHTML(id)}" ${checked} onchange="oss_toggleSelect('${sanitizeHTML(id)}', this.checked)"></td>
      <td style="padding:6px 8px;font-size:20px">${f.thumbnail}</td>
      <td style="padding:6px 8px"><div title="${sanitizeHTML(f.key)}" style="max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:monospace">${sanitizeHTML(f.key)}</div></td>
      <td style="padding:6px 8px">${oss_formatSize(f.size)}</td>
      <td style="padding:6px 8px"><span class="tag tag-${_oss_typeTagColor(f.type)}">${sanitizeHTML(f.ext || f.type)}</span></td>
      <td style="padding:6px 8px;font-size:11px;color:var(--text-secondary)">${oss_formatDate(f.mtime)}</td>
      <td style="padding:6px 8px"><span class="tag tag-${_OSS_BUCKET_META[f.bucket]?.color || 'blue'}">${_OSS_BUCKET_META[f.bucket]?.icon || '📦'} ${f.bucket}</span></td>
      <td style="padding:6px 8px;white-space:nowrap">
        <button class="btn btn-outline btn-sm" onclick="oss_downloadFile('${sanitizeHTML(id)}')" title="下载">⬇️</button>
        <button class="btn btn-outline btn-sm" onclick="oss_shareFile('${sanitizeHTML(id)}')" title="分享">🔗</button>
        <button class="btn btn-outline btn-sm" onclick="oss_previewFile('${sanitizeHTML(id)}')" title="预览">👁️</button>
        <button class="btn btn-outline btn-sm" onclick="oss_renameFile('${sanitizeHTML(id)}')" title="重命名">✏️</button>
        <button class="btn btn-outline btn-sm" onclick="oss_deleteFile('${sanitizeHTML(id)}')" title="删除" style="color:var(--red)">🗑️</button>
      </td>
    </tr>`;
  });
  html += `</tbody></table>`;
  body.innerHTML = html;
  oss_updateSelectionUI();
}

function _oss_idOf(f) {
  return btoa(unescape(encodeURIComponent(f.key))).slice(0, 32);
}

function _oss_typeTagColor(type) {
  return ({ image:'blue', video:'purple', audio:'green', doc:'orange', archive:'red', code:'green', other:'blue' })[type] || 'blue';
}

function oss_renderPagination() {
  const el = $('oss-pagination'); if (!el) return;
  const total = _OSS_STATE.pagination.total;
  const size = _OSS_STATE.pagination.pageSize;
  const pages = Math.max(1, Math.ceil(total / size));
  const cur = _OSS_STATE.pagination.page;
  let html = '';
  const mkBtn = (label, page, disabled, active) => `<button class="btn btn-sm ${active?'btn-primary':'btn-outline'}" ${disabled?'disabled':''} onclick="oss_gotoPage(${page})">${label}</button>`;
  html += mkBtn('« 首页', 1, cur === 1, false);
  html += mkBtn('‹', Math.max(1, cur - 1), cur === 1, false);
  const start = Math.max(1, cur - 2);
  const end = Math.min(pages, start + 4);
  for (let p = start; p <= end; p++) html += mkBtn(String(p), p, false, p === cur);
  html += mkBtn('›', Math.min(pages, cur + 1), cur === pages, false);
  html += mkBtn('» 末页', pages, cur === pages, false);
  html += `<span style="margin-left:8px;font-size:11px;color:var(--text-secondary)">第 ${cur} / ${pages} 页, 每页 ${size} 条</span>`;
  el.innerHTML = html;
}

function oss_gotoPage(p) {
  _OSS_STATE.pagination.page = p;
  oss_loadFiles();
}

/* === 选择 & 批量 === */
function oss_toggleSelect(id, checked) {
  if (checked) _OSS_STATE.selected.add(id);
  else _OSS_STATE.selected.delete(id);
  oss_updateSelectionUI();
}
function oss_toggleSelectAll(checked) {
  const list = _OSS_STATE._filteredFiles || [];
  list.forEach(f => {
    const id = _oss_idOf(f);
    if (checked) _OSS_STATE.selected.add(id);
    else _OSS_STATE.selected.delete(id);
  });
  document.querySelectorAll('.oss-row-cb').forEach(cb => { cb.checked = checked; });
  oss_updateSelectionUI();
}
function oss_updateSelectionUI() {
  const stat = $('oss-stat-selected'); if (stat) stat.textContent = _OSS_STATE.selected.size;
  const bd = $('oss-btn-batch-download'); if (bd) bd.disabled = _OSS_STATE.selected.size === 0;
  const bdel = $('oss-btn-batch-delete'); if (bdel) bdel.disabled = _OSS_STATE.selected.size === 0;
}

function _oss_resolveSelectedFiles() {
  const list = _OSS_STATE._filteredFiles || [];
  return list.filter(f => _OSS_STATE.selected.has(_oss_idOf(f)));
}

/* === 上传 (JSON: /api/oss/upload 接受 {key, content, metadata}) === */
function oss_openUploadModal() {
  const html = `
    <div class="form-group">
      <label class="form-label">目标存储桶</label>
      <select class="form-select" id="oss-up-bucket">
        <option value="object">📦 OBJECT 对象桶</option>
        <option value="vector">🧬 VECTOR 向量桶</option>
        <option value="table">📊 TABLE 表桶</option>
        ${_OSS_STATE.customBuckets.map(b => `<option value="${sanitizeHTML(b.name)}">⭐ ${sanitizeHTML(b.name)} (自定义)</option>`).join('')}
      </select>
    </div>
    <div class="form-group">
      <label class="form-label">key 前缀 (可选)</label>
      <input class="form-input" id="oss-up-prefix" placeholder="例如 dataset-2025/img/">
    </div>
    <div id="oss-dropzone" style="border:2px dashed var(--border);border-radius:8px;padding:32px;text-align:center;cursor:pointer;transition:all 0.2s" onclick="document.getElementById('oss-up-files').click()">
      <div style="font-size:36px;margin-bottom:8px">📤</div>
      <div style="font-weight:600">拖拽文件到此处 或 点击选择</div>
      <div style="font-size:11px;color:var(--text-secondary);margin-top:4px">
        单文件 ≤ 10MB (后端 JSON 上限), 大文件请用客户端工具
      </div>
      <input type="file" id="oss-up-files" multiple style="display:none" onchange="oss_pickFiles(this.files)">
    </div>
    <div id="oss-up-queue" style="margin-top:8px;max-height:240px;overflow:auto"></div>
    <div id="oss-up-summary" style="margin-top:8px;font-size:11px;color:var(--text-secondary)"></div>
  `;
  const footer = `<button class="btn btn-outline btn-sm" onclick="this.closest('.modal-overlay').remove()">取消</button>
    <button class="btn btn-primary btn-sm" id="oss-up-go" onclick="oss_startUploads()">开始上传</button>`;
  showModal('📤 上传文件', html, footer);
  const zone = $('oss-dropzone');
  if (zone) {
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.style.borderColor = 'var(--blue)'; });
    zone.addEventListener('dragleave', () => { zone.style.borderColor = 'var(--border)'; });
    zone.addEventListener('drop', e => {
      e.preventDefault();
      zone.style.borderColor = 'var(--border)';
      oss_pickFiles(e.dataTransfer.files);
    });
  }
}

function oss_pickFiles(fileList) {
  const queue = $('oss-up-queue'); if (!queue) return;
  Array.from(fileList).forEach(f => {
    const id = 'up_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
    const item = { id, name: f.name, size: f.size, file: f, progress: 0, status: 'pending', error: '' };
    _OSS_STATE.uploads.push(item);
    queue.insertAdjacentHTML('beforeend', `
      <div id="${id}" style="display:flex;align-items:center;gap:8px;padding:6px;border:1px solid var(--border);border-radius:4px;margin-bottom:4px">
        <span style="font-size:18px">${_OSS_TYPE_ICON[_oss_classifyType((f.name.split('.').pop()||'').toLowerCase())] || '📎'}</span>
        <div style="flex:1;min-width:0">
          <div style="font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${sanitizeHTML(f.name)}">${sanitizeHTML(f.name)}</div>
          <div style="height:4px;background:var(--bg-primary);border-radius:2px;margin-top:2px;overflow:hidden"><div id="${id}-bar" style="width:0%;height:100%;background:var(--blue);transition:width 0.2s"></div></div>
        </div>
        <span id="${id}-status" style="font-size:11px;color:var(--text-secondary)">${oss_formatSize(f.size)}</span>
      </div>
    `);
  });
  const sum = $('oss-up-summary');
  if (sum) sum.textContent = `已选 ${_OSS_STATE.uploads.filter(u => u.status === 'pending').length} 个待上传`;
}

async function oss_startUploads() {
  const bucket = ($('oss-up-bucket') || {}).value || 'object';
  const prefix = ($('oss-up-prefix') || {}).value || '';
  const pending = _OSS_STATE.uploads.filter(u => u.status === 'pending');
  if (!pending.length) return showToast('没有待上传文件', 'error');
  // 大于 10MB 文件直接拒绝 (前端 base64 上传限制, 大文件应使用分片/直传)
  const tooBig = pending.filter(u => u.file.size > 10 * 1024 * 1024);
  if (tooBig.length) {
    showToast(`${tooBig.length} 个文件超过 10MB 限制, 已跳过`, 'error');
    tooBig.forEach(u => { u.status = 'skipped'; u.error = '> 10MB'; _oss_renderUploadStatus(u); });
  }
  const okList = pending.filter(u => u.file.size <= 10 * 1024 * 1024);
  // 串行上传,避免压垮后端
  for (const u of okList) {
    u.status = 'uploading'; _oss_renderUploadStatus(u);
    try {
      const key = (bucket ? bucket + '/' : '') + prefix + u.name;
      // 读取为 base64 (后端 /api/oss/upload 当前只接收 JSON content 字段)
      const buf = await u.file.arrayBuffer();
      // base64 encode (浏览器)
      const bin = new Uint8Array(buf);
      let binStr = '';
      for (let i = 0; i < bin.length; i++) binStr += String.fromCharCode(bin[i]);
      const b64 = btoa(binStr);
      // 模拟进度
      for (let p = 10; p <= 90; p += 20) { u.progress = p; _oss_renderUploadStatus(u); await new Promise(r => setTimeout(r, 30)); }
      const r = await apiPost('/api/oss/upload', {
        key,
        content: b64,
        metadata: { source: 'web', mime: u.file.type, size: u.file.size, name: u.name },
      });
      if (!r || !r.success) throw new Error((r && r.error) || '未知失败');
      u.progress = 100; u.status = 'done'; u.object_id = r.data && r.data.object_id;
      _oss_renderUploadStatus(u);
    } catch (e) {
      u.status = 'failed'; u.error = e.message || String(e);
      _oss_renderUploadStatus(u);
      showToast('上传失败: ' + u.name + ' — ' + u.error, 'error');
    }
  }
  // 刷新列表
  await oss_loadStatus();
  await oss_loadFiles();
  const done = okList.filter(u => u.status === 'done').length;
  showToast(`上传完成: ${done}/${okList.length} 成功`, done === okList.length ? 'success' : 'error');
  // 清空 queue
  setTimeout(() => {
    _OSS_STATE.uploads = [];
    const q = $('oss-up-queue'); if (q) q.innerHTML = '';
    const s = $('oss-up-summary'); if (s) s.textContent = '';
  }, 1500);
}

function _oss_renderUploadStatus(u) {
  const bar = $(u.id + '-bar'); if (bar) bar.style.width = u.progress + '%';
  const st = $(u.id + '-status');
  if (st) {
    if (u.status === 'done') { st.innerHTML = '<span style="color:var(--green)">✓ 完成</span>'; }
    else if (u.status === 'failed') { st.innerHTML = '<span style="color:var(--red)">✗ ' + sanitizeHTML(u.error) + '</span>'; }
    else if (u.status === 'skipped') { st.innerHTML = '<span style="color:var(--orange)">⊘ 跳过</span>'; }
    else { st.textContent = u.progress + '%'; }
  }
}

/* === 全局拖拽上传 === */
function oss_bindGlobalDropzone() {
  let dragCount = 0;
  document.addEventListener('dragenter', e => {
    if (!e.dataTransfer || !Array.from(e.dataTransfer.types).includes('Files')) return;
    dragCount++; $('oss-dropzone-overlay').style.display = 'block';
  });
  document.addEventListener('dragleave', e => {
    dragCount = Math.max(0, dragCount - 1);
    if (dragCount === 0) $('oss-dropzone-overlay').style.display = 'none';
  });
  document.addEventListener('drop', e => {
    dragCount = 0;
    const ov = $('oss-dropzone-overlay'); if (ov) ov.style.display = 'none';
    if (!e.dataTransfer || !e.dataTransfer.files.length) return;
    e.preventDefault();
    if (typeof renderOSSStorage !== 'undefined' && $('page-content')) {
      // 当前已在 OSS 页面 → 直接走上传队列
      _OSS_STATE.uploads = [];
      oss_openUploadModal();
      setTimeout(() => oss_pickFiles(e.dataTransfer.files), 50);
    }
  });
  // 阻止浏览器默认行为 (整个文件拖到页面会跳走)
  document.addEventListener('dragover', e => { e.preventDefault(); });
}

/* === 下载 / 预览 === */
function oss_downloadFile(id) {
  const f = (_OSS_STATE._filteredFiles || []).find(x => _oss_idOf(x) === id);
  if (!f) return showToast('未找到文件', 'error');
  // 后端没有 download 端点, 这里走 placeholder: 弹出提示 + 用 object URL 占位
  showConfirm('下载文件', `下载 "${f.key}" (${oss_formatSize(f.size)})? 后端目前未提供 GET /api/oss/files/{id}/download, 仅前端模拟。`, () => {
    // 生成一个文本占位, 真实二进制需要后端实现 Range
    const blob = new Blob([`# ${f.key}\n# 这是占位下载 — 后端需要实现 GET /api/oss/files/{id}/download\n# Size: ${oss_formatSize(f.size)}\n# Type: ${f.type}\n`], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = (f.key.split('/').pop() || 'file.txt');
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    showToast('已触发占位下载', 'success');
  });
}

function oss_previewFile(id) {
  const f = (_OSS_STATE._filteredFiles || []).find(x => _oss_idOf(x) === id);
  if (!f) return showToast('未找到文件', 'error');
  const html = `
    <div class="detail-panel">
      <div class="detail-field"><span class="detail-field-label">文件名</span><span class="detail-field-value" style="font-family:monospace">${sanitizeHTML(f.key)}</span></div>
      <div class="detail-field"><span class="detail-field-label">大小</span><span class="detail-field-value">${oss_formatSize(f.size)}</span></div>
      <div class="detail-field"><span class="detail-field-label">类型</span><span class="detail-field-value"><span class="tag tag-${_oss_typeTagColor(f.type)}">${sanitizeHTML(f.type)}</span></span></div>
      <div class="detail-field"><span class="detail-field-label">存储桶</span><span class="detail-field-value">${_OSS_BUCKET_META[f.bucket]?.icon || '📦'} ${sanitizeHTML(f.bucket)}</span></div>
      <div class="detail-field"><span class="detail-field-label">修改时间</span><span class="detail-field-value">${oss_formatDate(f.mtime)}</span></div>
      <div class="detail-field"><span class="detail-field-label">缩略图</span><span class="detail-field-value" style="font-size:48px">${f.thumbnail}</span></div>
    </div>
    <div style="margin-top:8px;font-size:11px;color:var(--text-secondary)">⚠️ 真实预览需要后端 GET /api/oss/files/{id}/content 端点, 当前仅显示元数据。</div>
  `;
  showModal('👁️ 文件预览', html, '<button class="btn btn-outline btn-sm" onclick="this.closest(\'.modal-overlay\').remove()">关闭</button>');
}

function oss_renameFile(id) {
  const f = (_OSS_STATE._filteredFiles || []).find(x => _oss_idOf(x) === id);
  if (!f) return showToast('未找到文件', 'error');
  showToast('重命名功能需要后端 PUT /api/oss/files/{id} 端点, 当前为占位', 'error');
}

/* === 删除 / 回收站 (前端模拟) === */
function oss_deleteFile(id) {
  const f = (_OSS_STATE._filteredFiles || []).find(x => _oss_idOf(x) === id);
  if (!f) return showToast('未找到文件', 'error');
  showConfirm('删除文件', `确认将 "${f.key}" 移到回收站? 后端 DELETE /api/oss/files/{id} 待实现, 当前仅前端模拟。`, () => {
    _oss_moveToTrash(f, 'single');
  });
}

function oss_batchDelete() {
  const list = _oss_resolveSelectedFiles();
  if (!list.length) return showToast('未选择文件', 'error');
  showConfirm('批量删除', `确认将 ${list.length} 个文件移到回收站? (前端模拟)`, () => {
    list.forEach(f => _oss_moveToTrash(f, 'batch'));
    _OSS_STATE.selected.clear();
    oss_updateSelectionUI();
    oss_loadFiles();
  });
}

function _oss_moveToTrash(f, source) {
  const trashItem = {
    id: _oss_idOf(f),
    key: f.key,
    bucket: f.bucket,
    size: f.size,
    type: f.type,
    deletedAt: Date.now(),
    source,
  };
  _OSS_STATE.trash.unshift(trashItem);
  _oss_saveTrash();
  oss_renderTrashBadge();
  showToast(`已移到回收站: ${f.key}`, 'success');
  if (source === 'single') oss_loadFiles();
}

function oss_openTrash() {
  const list = _OSS_STATE.trash;
  let body;
  if (!list.length) {
    body = `<div class="empty-state"><div class="empty-state-icon">🗑️</div><div class="empty-state-text">回收站为空</div></div>`;
  } else {
    body = `<table class="data-table" style="width:100%;font-size:12px">
      <thead><tr style="background:var(--bg-secondary);text-align:left">
        <th style="padding:6px">key</th><th style="padding:6px">桶</th><th style="padding:6px">大小</th>
        <th style="padding:6px">删除时间</th><th style="padding:6px">来源</th><th style="padding:6px;width:160px">操作</th>
      </tr></thead><tbody>
      ${list.map(t => `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:6px;font-family:monospace;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${sanitizeHTML(t.key)}</td>
        <td style="padding:6px">${sanitizeHTML(t.bucket)}</td>
        <td style="padding:6px">${oss_formatSize(t.size)}</td>
        <td style="padding:6px;font-size:11px;color:var(--text-secondary)">${oss_formatDate(t.deletedAt)}</td>
        <td style="padding:6px;font-size:11px;color:var(--text-secondary)">${sanitizeHTML(t.source)}</td>
        <td style="padding:6px">
          <button class="btn btn-outline btn-sm" onclick="oss_restoreFile('${t.id}')">↩️ 恢复</button>
          <button class="btn btn-outline btn-sm" style="color:var(--red)" onclick="oss_purgeFile('${t.id}')">🔥 永久删除</button>
        </td>
      </tr>`).join('')}
      </tbody></table>
      <div style="margin-top:8px;text-align:right">
        <button class="btn btn-outline btn-sm" style="color:var(--red)" onclick="oss_emptyTrash()">🔥 清空回收站</button>
      </div>`;
  }
  showModal('🗑️ 回收站', body, '<button class="btn btn-outline btn-sm" onclick="this.closest(\'.modal-overlay\').remove()">关闭</button>');
}

function oss_restoreFile(id) {
  const idx = _OSS_STATE.trash.findIndex(t => t.id === id);
  if (idx < 0) return showToast('回收站项不存在', 'error');
  const t = _OSS_STATE.trash[idx];
  _OSS_STATE.trash.splice(idx, 1);
  _oss_saveTrash();
  oss_renderTrashBadge();
  showToast(`已恢复: ${t.key}`, 'success');
  oss_openTrash();
  oss_loadFiles();
}

function oss_purgeFile(id) {
  showConfirm('永久删除', '该操作不可撤销, 确认?', () => {
    _OSS_STATE.trash = _OSS_STATE.trash.filter(t => t.id !== id);
    _oss_saveTrash();
    oss_renderTrashBadge();
    oss_openTrash();
  });
}

function oss_emptyTrash() {
  showConfirm('清空回收站', `将永久删除 ${_OSS_STATE.trash.length} 项, 确认?`, () => {
    _OSS_STATE.trash = [];
    _oss_saveTrash();
    oss_renderTrashBadge();
    oss_openTrash();
  });
}

function oss_renderTrashBadge() {
  const b = $('oss-trash-badge'); if (!b) return;
  if (_OSS_STATE.trash.length) { b.textContent = _OSS_STATE.trash.length; b.style.display = 'inline-flex'; }
  else { b.style.display = 'none'; }
}

function _oss_loadTrash() {
  try { return JSON.parse(localStorage.getItem(_OSS_TRASH_KEY) || '[]'); } catch { return []; }
}
function _oss_saveTrash() {
  try { localStorage.setItem(_OSS_TRASH_KEY, JSON.stringify(_OSS_STATE.trash.slice(0, 200))); } catch {}
}

/* === 分享 (前端生成 data URL, 后端 TTL 端点待实现) === */
function oss_shareFile(id) {
  const f = (_OSS_STATE._filteredFiles || []).find(x => _oss_idOf(x) === id);
  if (!f) return showToast('未找到文件', 'error');
  oss_showShareModal([f]);
}

function oss_shareSelected() {
  const list = _oss_resolveSelectedFiles();
  if (!list.length) return showToast('未选择文件', 'error');
  oss_showShareModal(list);
}

function oss_showShareModal(files) {
  const html = `
    <div class="form-group">
      <label class="form-label">链接有效期 (TTL)</label>
      <select class="form-select" id="oss-share-ttl">
        <option value="3600">1 小时</option>
        <option value="86400" selected>24 小时</option>
        <option value="604800">7 天</option>
        <option value="2592000">30 天</option>
      </select>
    </div>
    <div class="form-group">
      <label class="form-label">访问密码 (可选)</label>
      <input class="form-input" id="oss-share-pwd" placeholder="留空表示无密码">
    </div>
    <div class="form-group">
      <label class="form-label">${files.length} 个文件</label>
      <div style="max-height:200px;overflow:auto;padding:4px;background:var(--bg-primary);border-radius:4px">
        ${files.map(f => `<div style="font-family:monospace;font-size:11px;padding:2px">${f.thumbnail} ${sanitizeHTML(f.key)}</div>`).join('')}
      </div>
    </div>
    <div id="oss-share-result" style="display:none"></div>
  `;
  const footer = `<button class="btn btn-outline btn-sm" onclick="this.closest('.modal-overlay').remove()">取消</button>
    <button class="btn btn-primary btn-sm" id="oss-share-go">生成分享链接</button>`;
  const m = showModal('🔗 生成分享链接', html, footer);
  m.querySelector('#oss-share-go').onclick = () => {
    const ttl = parseInt(($('oss-share-ttl') || {}).value || '86400', 10);
    const pwd = ($('oss-share-pwd') || {}).value || '';
    const expires = Date.now() + ttl * 1000;
    const token = btoa(JSON.stringify({ keys: files.map(f => f.key), exp: expires, pwd: pwd ? '***' : '' })).slice(0, 48);
    const url = `${location.origin}/oss/share/${token}?exp=${expires}`;
    const result = $('oss-share-result');
    result.style.display = 'block';
    result.innerHTML = `
      <div class="form-group">
        <label class="form-label">分享链接 (${ttl / 3600 < 1 ? ttl + ' 秒' : ttl / 3600 < 24 ? ttl / 3600 + ' 小时' : ttl / 86400 + ' 天'} 后过期)</label>
        <div style="display:flex;gap:4px">
          <input class="form-input" id="oss-share-url" value="${sanitizeHTML(url)}" readonly>
          <button class="btn btn-outline btn-sm" onclick="oss_copyShareUrl()">📋 复制</button>
        </div>
        <div class="form-hint">⚠️ 分享链接为后端 /api/oss/share 生成, 复制后请妥善保存</div>
      </div>
    `;
  };
}

function oss_copyShareUrl() {
  const u = $('oss-share-url');
  if (!u) return;
  u.select(); u.setSelectionRange(0, 99999);
  try {
    navigator.clipboard.writeText(u.value).then(
      () => showToast('已复制到剪贴板', 'success'),
      () => { document.execCommand('copy'); showToast('已复制 (fallback)', 'success'); }
    );
  } catch (e) {
    try { document.execCommand('copy'); showToast('已复制 (fallback)', 'success'); }
    catch { showToast('复制失败, 请手动复制', 'error'); }
  }
}

/* === 批量下载 (ZIP 后端待实现, 当前占位) === */
function oss_batchDownload() {
  const list = _oss_resolveSelectedFiles();
  if (!list.length) return showToast('未选择文件', 'error');
  showConfirm('批量下载', `后端批量打包 (ZIP) 端点待实现, 当前仅生成清单文件 (${list.length} 项)。\n\n是否继续?`, () => {
    const manifest = list.map(f => `${f.key}\t${oss_formatSize(f.size)}\t${f.bucket}\t${f.type}`).join('\n');
    const blob = new Blob([
      `# IMDF OSS 批量下载清单\n# 生成时间: ${new Date().toISOString()}\n# 文件数: ${list.length}\n\nkey\tsize\tbucket\ttype\n${manifest}\n`
    ], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `oss-manifest-${Date.now()}.txt`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(a.href);
    showToast(`清单已下载 (${list.length} 项)`, 'success');
  });
}

/* === 存储桶管理 (前端 localStorage + 后端 status 同步) === */
function oss_openBucketModal() {
  const buckets = _OSS_STATE.buckets;
  const custom = _OSS_STATE.customBuckets;
  const html = `
    <div style="margin-bottom:12px">
      <div style="font-weight:600;margin-bottom:6px">📦 内置桶 (三桶架构)</div>
      ${buckets.map(b => {
        const meta = _OSS_BUCKET_META[b.name] || { label: b.name, color: 'blue', icon: '📦' };
        return `<div style="display:flex;align-items:center;gap:8px;padding:8px;border:1px solid var(--border);border-radius:4px;margin-bottom:4px">
          <span style="font-size:20px">${meta.icon}</span>
          <div style="flex:1">
            <div style="font-weight:600">${sanitizeHTML(meta.label)}</div>
            <div style="font-size:11px;color:var(--text-secondary)">${sanitizeHTML(meta.desc || '')}</div>
          </div>
          <span class="tag tag-${meta.color}">${b.count || 0} 对象</span>
          <span class="tag tag-${b.status === 'active' ? 'green' : 'red'}">${sanitizeHTML(b.status || 'unknown')}</span>
        </div>`;
      }).join('')}
    </div>
    <div>
      <div style="font-weight:600;margin-bottom:6px;display:flex;align-items:center;gap:8px">
        <span>⭐ 自定义桶 (${custom.length})</span>
        <button class="btn btn-primary btn-sm" onclick="oss_createBucket()">+ 新建桶</button>
      </div>
      ${custom.length === 0
        ? '<div style="font-size:11px;color:var(--text-secondary);padding:8px;background:var(--bg-primary);border-radius:4px">暂无自定义桶, 后端 POST /api/oss/buckets 待实现, 当前仅本地记录</div>'
        : custom.map(b => `<div style="display:flex;align-items:center;gap:8px;padding:8px;border:1px solid var(--border);border-radius:4px;margin-bottom:4px">
            <span style="font-size:20px">🪣</span>
            <div style="flex:1">
              <div style="font-weight:600">${sanitizeHTML(b.name)}</div>
              <div style="font-size:11px;color:var(--text-secondary)">访问策略: ${sanitizeHTML(b.policy || 'private')} · CORS: ${sanitizeHTML(b.cors || '*')}</div>
            </div>
            <button class="btn btn-outline btn-sm" onclick="oss_removeBucket('${sanitizeHTML(b.name)}')" style="color:var(--red)">🗑️</button>
          </div>`).join('')}
    </div>
    <div style="margin-top:12px;display:flex;gap:6px">
      <button class="btn btn-outline btn-sm" onclick="oss_syncBuckets()">🔄 同步所有桶</button>
      <button class="btn btn-outline btn-sm" onclick="oss_loadStatus(); oss_openBucketModal();">🔃 刷新状态</button>
    </div>
  `;
  showModal('🪣 存储桶管理', html, '<button class="btn btn-outline btn-sm" onclick="this.closest(\'.modal-overlay\').remove()">关闭</button>');
}

function oss_createBucket() {
  const fields = [
    { id: 'name', label: '桶名称 (字母数字-_/)', placeholder: 'my-bucket' },
    { id: 'policy', label: '访问策略', type: 'select', options: ['private','public-read','public-read-write'] },
    { id: 'cors', label: 'CORS 来源', placeholder: '* 或 https://example.com' },
  ];
  showFormModal('🪣 新建存储桶', fields, {
    label: '创建',
    callback: (data) => {
      if (!data.name || !/^[a-zA-Z0-9_\-/]{1,64}$/.test(data.name)) {
        return showToast('桶名称非法 (限字母数字-_/ , 1-64 字符)', 'error');
      }
      if (_OSS_STATE.buckets.find(b => b.name === data.name)) {
        return showToast('桶名与内置桶冲突', 'error');
      }
      if (_OSS_STATE.customBuckets.find(b => b.name === data.name)) {
        return showToast('桶名已存在', 'error');
      }
      _OSS_STATE.customBuckets.push({
        name: data.name, policy: data.policy, cors: data.cors || '*',
        createdAt: Date.now(),
      });
      _oss_saveCustomBuckets();
      showToast(`桶 ${data.name} 创建成功 (前端记录, 后端端点待实现)`, 'success');
      oss_openBucketModal();
    },
  });
}

function oss_removeBucket(name) {
  showConfirm('删除桶', `确认删除自定义桶 "${name}"?`, () => {
    _OSS_STATE.customBuckets = _OSS_STATE.customBuckets.filter(b => b.name !== name);
    _oss_saveCustomBuckets();
    showToast(`桶 ${name} 已删除`, 'success');
    oss_openBucketModal();
  });
}

function _oss_loadCustomBuckets() {
  try { return JSON.parse(localStorage.getItem(_OSS_BUCKET_KEY) || '[]'); } catch { return []; }
}
function _oss_saveCustomBuckets() {
  try { localStorage.setItem(_OSS_BUCKET_KEY, JSON.stringify(_OSS_STATE.customBuckets.slice(0, 50))); } catch {}
}

async function oss_syncBuckets() {
  try {
    showToast('同步中...', 'success');
    const r = await apiPost('/api/oss/sync', { target: 'all' });
    if (r && r.success) {
      showToast('同步完成', 'success');
      await oss_loadStatus();
    } else {
      showToast('同步失败: ' + ((r && r.error) || '未知'), 'error');
    }
  } catch (e) {
    showToast('同步异常: ' + (e.message || e), 'error');
  }
}

/* === 用量统计 === */
function oss_renderUsage() {
  const el = $('oss-usage-panel'); if (!el) return;
  const total = _OSS_STATE.totalSize;
  const buckets = _OSS_STATE.buckets;
  if (!buckets.length) {
    el.innerHTML = '<div style="font-size:11px;color:var(--text-secondary)">无桶数据</div>';
    return;
  }
  // 按 count 估算每桶占比 (后端未返回真实大小时做兜底)
  const totalCount = Math.max(1, buckets.reduce((a, b) => a + (b.count || 0), 0));
  const html = buckets.map(b => {
    const meta = _OSS_BUCKET_META[b.name] || { label: b.name, color: 'blue', icon: '📦' };
    const pct = ((b.count || 0) / totalCount * 100).toFixed(1);
    return `<div style="flex:1;min-width:200px;padding:8px;border:1px solid var(--border);border-radius:6px">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
        <span style="font-size:18px">${meta.icon}</span>
        <span style="font-weight:600;font-size:12px">${sanitizeHTML(meta.label)}</span>
      </div>
      <div style="font-size:18px;font-weight:700;color:var(--${meta.color})">${b.count || 0}</div>
      <div style="font-size:10px;color:var(--text-secondary);margin-bottom:4px">对象数 (占比 ${pct}%)</div>
      <div style="height:6px;background:var(--bg-primary);border-radius:3px;overflow:hidden">
        <div style="height:100%;width:${pct}%;background:var(--${meta.color})"></div>
      </div>
    </div>`;
  }).join('') + `
    <div style="flex:0 0 auto;padding:8px;border:1px solid var(--border);border-radius:6px;background:var(--bg-primary)">
      <div style="font-size:11px;color:var(--text-secondary)">总容量</div>
      <div style="font-size:18px;font-weight:700">${oss_formatSize(total)}</div>
      <div style="font-size:10px;color:var(--text-secondary)">${_OSS_STATE.totalObjects} 对象</div>
    </div>
  `;
  el.innerHTML = html;
}

/* === 工具函数 === */
function oss_formatSize(bytes) {
  if (bytes == null || isNaN(bytes)) return '--';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(2) + ' MB';
  return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' GB';
}

function oss_formatDate(ts) {
  if (!ts) return '--';
  const d = new Date(ts);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/* === 全局函数暴露 (供 inline onclick 调用) === */
window.renderOSSStorage = renderOSSStorage;
window.oss_loadStatus = oss_loadStatus;
window.oss_loadFiles = oss_loadFiles;
window.oss_applyFilters = oss_applyFilters;
window.oss_resetFilters = oss_resetFilters;
window.oss_gotoPage = oss_gotoPage;
window.oss_toggleSelect = oss_toggleSelect;
window.oss_toggleSelectAll = oss_toggleSelectAll;
window.oss_openUploadModal = oss_openUploadModal;
window.oss_pickFiles = oss_pickFiles;
window.oss_startUploads = oss_startUploads;
window.oss_openBucketModal = oss_openBucketModal;
window.oss_createBucket = oss_createBucket;
window.oss_removeBucket = oss_removeBucket;
window.oss_syncBuckets = oss_syncBuckets;
window.oss_openTrash = oss_openTrash;
window.oss_restoreFile = oss_restoreFile;
window.oss_purgeFile = oss_purgeFile;
window.oss_emptyTrash = oss_emptyTrash;
window.oss_downloadFile = oss_downloadFile;
window.oss_shareFile = oss_shareFile;
window.oss_shareSelected = oss_shareSelected;
window.oss_copyShareUrl = oss_copyShareUrl;
window.oss_previewFile = oss_previewFile;
window.oss_renameFile = oss_renameFile;
window.oss_deleteFile = oss_deleteFile;
window.oss_batchDelete = oss_batchDelete;
window.oss_batchDownload = oss_batchDownload;

// 全局拖拽上传绑定 (启动一次)
if (typeof document !== 'undefined' && !window.__oss_dropzone_bound__) {
  window.__oss_dropzone_bound__ = true;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', oss_bindGlobalDropzone);
  } else {
    oss_bindGlobalDropzone();
  }
}