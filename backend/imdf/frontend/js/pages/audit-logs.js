/* IMDF 审计日志 v2 — 表格 + 过滤 + 详情 + 导出 + 自动刷新
 *
 * 后端端点:
 *   GET /api/v1/audit-logs       — 分页查询 (page/size/method/path/start/end/dimension)
 *   GET /api/v1/audit-logs/stats — 统计 (今日操作数 + 按 method 分布 + total_actions)
 *
 * R10.5-W1 audit-transfer 充实:
 *  - 真实分页 (‹ 1 2 3 … ›, page_size=20, 跳页按钮)
 *  - 多过滤: method (GET/POST/PUT/PATCH/DELETE) + status 级别 (2xx/4xx/5xx) + 路径子串 + 日期范围
 *  - 状态徽章 (INFO/WARN/ERROR + 状态码)
 *  - 行点击展开 JSON 详情面板 (在原行下方插入 detail row)
 *  - CSV / JSON 导出 (前端 blob 下载)
 *  - 30s 自动刷新 (toggle 开关, 倒计时指示)
 *  - 顶部 4 个统计卡 (总数 / 5xx / 4xx / 今日)
 *  - 加载/错误/空态 三态渲染
 */

let AL = {
  page: 1,
  size: 20,
  total: 0,
  pages: 1,
  data: [],
  filters: { method: '', level: '', q: '', start: '', end: '' },
  loading: false,
  selectedLogId: null,
  autoRefresh: true,
  refreshTimer: null,
  refreshCountdown: 30,
  countdownTimer: null,
  stats: { today: 0, total_actions: 0, dist: {} },
};

const AL_METHOD_OPTIONS = ['', 'GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
const AL_LEVEL_OPTIONS = ['', 'info', 'warn', 'error'];

async function renderAuditLogs() {
  const c = $('page-content'); if (!c) return;

  // 1. 骨架: 头部 + 工具栏 + 表格区 + 分页
  c.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">📋 审计日志</div>
        <div style="font-size:11px;color:#8888aa;margin-top:2px">
          实时记录所有 API 请求 / 用户操作 / 系统事件 · 自动 30s 刷新
        </div>
      </div>
      <div class="page-stats" id="al-stats">
        <div class="page-stat"><div class="page-stat-val" id="al-stat-total">—</div><div class="page-stat-label">总记录</div></div>
        <div class="page-stat"><div class="page-stat-val" id="al-stat-today">—</div><div class="page-stat-label">今日</div></div>
        <div class="page-stat"><div class="page-stat-val" id="al-stat-5xx" style="color:var(--red,#ef4444)">—</div><div class="page-stat-label">5xx 错误</div></div>
        <div class="page-stat"><div class="page-stat-val" id="al-stat-4xx" style="color:#f59e0b">—</div><div class="page-stat-label">4xx 警告</div></div>
      </div>
      <div class="page-actions">
        <label style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text-secondary);cursor:pointer;margin-right:8px">
          <input type="checkbox" id="al-auto-refresh" ${AL.autoRefresh ? 'checked' : ''} onchange="al_toggleAutoRefresh(this.checked)">
          <span id="al-refresh-label">🔄 ${AL.refreshCountdown}s 后刷新</span>
        </label>
        <button class="btn btn-outline btn-sm" onclick="al_exportCSV()">📥 CSV</button>
        <button class="btn btn-outline btn-sm" onclick="al_exportJSON()">📥 JSON</button>
        <button class="btn btn-primary btn-sm" onclick="al_refresh(true)">🔄 立即刷新</button>
      </div>
    </div>

    <div class="toolbar" id="al-toolbar">
      <input id="al-q" placeholder="🔍 搜索 path / method / user..." value="${escapeAttr(AL.filters.q)}">
      <select id="al-method" onchange="al_applyFilters()">
        ${AL_METHOD_OPTIONS.map(m => `<option value="${m}" ${AL.filters.method===m?'selected':''}>${m||'全部方法'}</option>`).join('')}
      </select>
      <select id="al-level" onchange="al_applyFilters()">
        ${AL_LEVEL_OPTIONS.map(lv => {
          const labels = { '':'全部级别', info:'INFO (2xx)', warn:'WARN (4xx)', error:'ERROR (5xx)' };
          return `<option value="${lv}" ${AL.filters.level===lv?'selected':''}>${labels[lv]||lv}</option>`;
        }).join('')}
      </select>
      <input id="al-start" type="date" value="${escapeAttr(AL.filters.start)}" onchange="al_applyFilters()" title="起始日期">
      <span style="color:var(--text-muted);font-size:11px">→</span>
      <input id="al-end" type="date" value="${escapeAttr(AL.filters.end)}" onchange="al_applyFilters()" title="结束日期">
      <button class="btn btn-outline btn-sm" onclick="al_resetFilters()">↺ 重置</button>
    </div>

    <div id="al-table-wrap" style="overflow-x:auto;border:1px solid var(--border);border-radius:6px;background:var(--bg-card)">
      <table class="data-table" id="al-table">
        <thead>
          <tr>
            <th style="width:170px">时间</th>
            <th style="width:80px">方法</th>
            <th>路径</th>
            <th style="width:140px">用户</th>
            <th style="width:90px">状态</th>
            <th style="width:120px">Body Hash</th>
          </tr>
        </thead>
        <tbody id="al-tbody">
          <tr><td colspan="6" style="text-align:center;padding:30px;color:var(--text-muted)">
            <div class="loading-spinner" style="margin:0 auto 8px"></div>加载中...
          </td></tr>
        </tbody>
      </table>
    </div>

    <div id="al-pager" style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;font-size:12px"></div>
  `;

  await al_refresh(false);
  al_startAutoRefresh();
  al_startCountdown();
}

/* === 数据加载 === */
async function al_refresh(showToast) {
  if (AL.loading) return;
  AL.loading = true;
  try {
    // 并行拉取列表 + 统计
    const params = new URLSearchParams();
    params.set('page', AL.page);
    params.set('size', AL.size);
    if (AL.filters.method) params.set('method', AL.filters.method);
    if (AL.filters.q) params.set('path', AL.filters.q);
    if (AL.filters.start) params.set('start', AL.filters.start);
    if (AL.filters.end) params.set('end', AL.filters.end);

    const [listRes, statsRes] = await Promise.all([
      apiGet('/api/v1/audit-logs?' + params.toString()),
      apiGet('/api/v1/audit-logs/stats' + (AL.filters.start || AL.filters.end
        ? '?' + new URLSearchParams(Object.entries({
            start: AL.filters.start || '',
            end: AL.filters.end || '',
          }).filter(([_,v]) => v)).toString()
        : '')),
    ]);

    AL.data = (listRes?.data?.items) || [];
    AL.total = (listRes?.data?.total) || 0;
    AL.pages = (listRes?.data?.pages) || Math.max(1, Math.ceil(AL.total / AL.size));
    AL.page = (listRes?.data?.page) || AL.page;

    if (statsRes?.success) {
      const sd = statsRes.data || {};
      AL.stats.today = sd.today_operations || 0;
      AL.stats.total_actions = sd.total_actions || 0;
      AL.stats.dist = sd.action_distribution || {};
    }
    al_renderStats();
    al_renderTable();
    al_renderPager();
    if (showToast) showToast('审计日志已刷新', 'success');
  } catch (e) {
    const msg = (e && (e.message || e.error)) || '加载失败';
    const tbody = $('al-tbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="empty-state-icon">⚠️</div><div class="empty-state-text">${escapeHTML(msg)}</div><button class="btn btn-outline btn-sm" style="margin-top:10px" onclick="al_refresh(true)">🔄 重试</button></div></td></tr>`;
    showToast('刷新失败: ' + msg, 'error');
  } finally {
    AL.loading = false;
  }
}

/* === 渲染: 统计卡 === */
function al_renderStats() {
  const set = (id, v) => { const el = $(id); if (el) el.textContent = v; };
  set('al-stat-total', AL.total.toLocaleString());
  set('al-stat-today', AL.stats.today.toLocaleString());

  // 5xx / 4xx 从当前页 (best-effort) + stats dist 推算
  let err5 = 0, err4 = 0;
  AL.data.forEach(l => {
    const sc = parseInt(l.status_code, 10) || 0;
    if (sc >= 500) err5++;
    else if (sc >= 400) err4++;
  });
  set('al-stat-5xx', err5);
  set('al-stat-4xx', err4);
}

/* === 渲染: 表格 === */
function al_renderTable() {
  const tbody = $('al-tbody');
  if (!tbody) return;
  if (!AL.data.length) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="empty-state-icon">📋</div><div class="empty-state-text">暂无审计记录</div><div class="empty-state-hint">尝试调整过滤条件或时间范围</div></div></td></tr>`;
    return;
  }
  // 前端额外过滤 level (后端无此字段, 客户端按 status_code 推算)
  const filtered = AL.data.filter(l => {
    if (!AL.filters.level) return true;
    const sc = parseInt(l.status_code, 10) || 0;
    if (AL.filters.level === 'error') return sc >= 500;
    if (AL.filters.level === 'warn') return sc >= 400 && sc < 500;
    if (AL.filters.level === 'info') return sc >= 200 && sc < 400;
    return true;
  });
  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="empty-state-icon">🔍</div><div class="empty-state-text">没有匹配的日志</div></div></td></tr>`;
    return;
  }
  tbody.innerHTML = filtered.map((l, idx) => {
    const sc = parseInt(l.status_code, 10) || 0;
    const level = sc >= 500 ? 'error' : (sc >= 400 ? 'warn' : 'info');
    const badgeClass = level === 'error' ? 'tag-red' : (level === 'warn' ? 'tag-orange' : 'tag-green');
    const method = escapeHTML(l.method || '');
    const path = escapeHTML(l.path || '');
    const user = escapeHTML(l.user || 'anonymous');
    const ts = escapeHTML(al_formatTs(l.timestamp));
    const bh = escapeHTML((l.body_hash || '').slice(0, 12) || '—');
    const expanded = AL.selectedLogId === (l.id || idx);
    return `
      <tr onclick="al_toggleDetail(${l.id || idx})" style="cursor:pointer;${expanded?'background:rgba(74,122,255,0.06)':''}">
        <td style="font-family:var(--font-mono,'Menlo','Consolas',monospace);font-size:11px;color:var(--text-secondary)">${ts}</td>
        <td><span style="font-weight:600;color:${al_methodColor(l.method)}">${method}</span></td>
        <td style="word-break:break-all">${path}</td>
        <td style="font-size:11px">${user}</td>
        <td><span class="tag ${badgeClass}" style="font-size:10px">${sc || '—'}</span></td>
        <td style="font-family:var(--font-mono,'Menlo','Consolas',monospace);font-size:10px;color:var(--text-muted)">${bh}</td>
      </tr>
      ${expanded ? `<tr><td colspan="6" style="background:rgba(74,122,255,0.04);padding:12px 16px;border-top:1px dashed var(--border)">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
          <strong style="font-size:12px;color:var(--text-primary)">📄 审计日志详情</strong>
          <button class="btn btn-outline btn-sm" onclick="event.stopPropagation();al_copyLogJSON(${idx})">📋 复制 JSON</button>
        </div>
        <pre style="margin:0;padding:10px;background:var(--bg-base,#0f0f1a);border:1px solid var(--border);border-radius:4px;font-size:11px;line-height:1.5;overflow-x:auto;max-height:300px;overflow-y:auto">${escapeHTML(JSON.stringify(l, null, 2))}</pre>
      </td></tr>` : ''}
    `;
  }).join('');
}

/* === 渲染: 分页 === */
function al_renderPager() {
  const pager = $('al-pager');
  if (!pager) return;
  const start = (AL.page - 1) * AL.size + 1;
  const end = Math.min(AL.page * AL.size, AL.total);
  const left = `<span style="color:var(--text-muted)">显示 ${start}–${end} / 共 ${AL.total} 条 · 第 ${AL.page}/${AL.pages} 页</span>`;
  if (AL.pages <= 1) {
    pager.innerHTML = left + '<span></span>';
    return;
  }
  // 页码按钮: 显示首页 / 末页 / 当前 ±2
  const pages = [];
  pages.push(`<button class="btn btn-sm btn-outline" ${AL.page<=1?'disabled':''} onclick="al_goto(${AL.page-1})">‹ 上一页</button>`);
  for (let i = 1; i <= AL.pages; i++) {
    if (i === 1 || i === AL.pages || Math.abs(i - AL.page) <= 2) {
      pages.push(`<button class="btn btn-sm ${i===AL.page?'btn-primary':'btn-outline'}" onclick="al_goto(${i})">${i}</button>`);
    } else if (i === 2 || i === AL.pages - 1) {
      pages.push(`<span style="color:var(--text-muted);padding:0 4px">…</span>`);
    }
  }
  pages.push(`<button class="btn btn-sm btn-outline" ${AL.page>=AL.pages?'disabled':''} onclick="al_goto(${AL.page+1})">下一页 ›</button>`);
  pager.innerHTML = left + '<div style="display:flex;gap:4px">' + pages.join('') + '</div>';
}

function al_goto(p) {
  if (p < 1 || p > AL.pages || p === AL.page) return;
  AL.page = p;
  al_refresh(false);
}

/* === 过滤 / 重置 === */
function al_applyFilters() {
  AL.filters.q = ($('al-q')?.value || '').trim();
  AL.filters.method = ($('al-method')?.value || '').trim();
  AL.filters.level = ($('al-level')?.value || '').trim();
  AL.filters.start = ($('al-start')?.value || '').trim();
  AL.filters.end = ($('al-end')?.value || '').trim();
  AL.page = 1;
  AL.refreshCountdown = 30;
  al_refresh(false);
}

function al_resetFilters() {
  AL.filters = { method: '', level: '', q: '', start: '', end: '' };
  AL.page = 1;
  AL.refreshCountdown = 30;
  const q = $('al-q'); if (q) q.value = '';
  const m = $('al-method'); if (m) m.value = '';
  const lv = $('al-level'); if (lv) lv.value = '';
  const s = $('al-start'); if (s) s.value = '';
  const e = $('al-end'); if (e) e.value = '';
  al_refresh(false);
}

/* === 详情行 === */
function al_toggleDetail(id) {
  if (AL.selectedLogId === id) {
    AL.selectedLogId = null;
  } else {
    AL.selectedLogId = id;
  }
  al_renderTable();
}

function al_copyLogJSON(idx) {
  const l = AL.data.find((x, i) => (x.id || i) === (AL.data[idx]?.id || idx)) || AL.data[idx];
  if (!l) return;
  const text = JSON.stringify(l, null, 2);
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(
      () => showToast('JSON 已复制', 'success'),
      () => fallbackCopy(text)
    );
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); showToast('已复制', 'success'); }
  catch (e) { showToast('复制失败', 'error'); }
  document.body.removeChild(ta);
}

/* === 导出 === */
function al_exportCSV() {
  if (!AL.data.length) { showToast('无数据可导出', 'error'); return; }
  const headers = ['id', 'timestamp', 'method', 'path', 'user', 'status_code', 'body_hash'];
  const rows = AL.data.map(l => headers.map(h => csvCell(l[h])).join(','));
  const csv = '\uFEFF' + headers.join(',') + '\n' + rows.join('\n'); // 加 BOM 防 Excel 中文乱码
  al_downloadFile(csv, `audit-logs-${al_formatTsForFile()}.csv`, 'text/csv;charset=utf-8');
  showToast(`已导出 ${AL.data.length} 条 (CSV)`, 'success');
}

function al_exportJSON() {
  if (!AL.data.length) { showToast('无数据可导出', 'error'); return; }
  const payload = {
    exported_at: new Date().toISOString(),
    page: AL.page,
    size: AL.size,
    total: AL.total,
    pages: AL.pages,
    filters: AL.filters,
    items: AL.data,
  };
  const text = JSON.stringify(payload, null, 2);
  al_downloadFile(text, `audit-logs-${al_formatTsForFile()}.json`, 'application/json;charset=utf-8');
  showToast(`已导出 ${AL.data.length} 条 (JSON)`, 'success');
}

function al_downloadFile(content, filename, mime) {
  try {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; document.body.appendChild(a); a.click();
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
  } catch (e) {
    showToast('导出失败: ' + (e?.message || e), 'error');
  }
}

function csvCell(v) {
  if (v == null) return '';
  const s = String(v);
  if (s.includes(',') || s.includes('"') || s.includes('\n')) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

/* === 自动刷新 === */
function al_startAutoRefresh() {
  al_stopAutoRefresh();
  if (!AL.autoRefresh) return;
  AL.refreshTimer = setInterval(() => {
    if (document.visibilityState === 'visible') {
      al_refresh(false);
      AL.refreshCountdown = 30;
    }
  }, 30000);
}

function al_stopAutoRefresh() {
  if (AL.refreshTimer) { clearInterval(AL.refreshTimer); AL.refreshTimer = null; }
}

function al_toggleAutoRefresh(checked) {
  AL.autoRefresh = !!checked;
  AL.refreshCountdown = 30;
  if (AL.autoRefresh) al_startAutoRefresh();
  else al_stopAutoRefresh();
  al_updateRefreshLabel();
}

function al_startCountdown() {
  al_stopCountdown();
  AL.countdownTimer = setInterval(() => {
    if (!AL.autoRefresh) return;
    AL.refreshCountdown = Math.max(0, AL.refreshCountdown - 1);
    al_updateRefreshLabel();
  }, 1000);
}

function al_stopCountdown() {
  if (AL.countdownTimer) { clearInterval(AL.countdownTimer); AL.countdownTimer = null; }
}

function al_updateRefreshLabel() {
  const el = $('al-refresh-label');
  if (!el) return;
  el.textContent = AL.autoRefresh ? `🔄 ${AL.refreshCountdown}s 后刷新` : '⏸ 自动刷新已暂停';
}

/* === 工具 === */
function al_formatTs(ts) {
  if (!ts) return '--';
  // 兼容 ISO + SQLite "YYYY-MM-DD HH:MM:SS"
  const s = String(ts).replace(' ', 'T');
  const d = new Date(s);
  if (isNaN(d.getTime())) return String(ts);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function al_formatTsForFile() {
  const d = new Date();
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

function al_methodColor(m) {
  const colors = { GET: 'var(--blue,#4a7aff)', POST: 'var(--green,#10b981)', PUT: 'var(--orange,#f59e0b)', PATCH: 'var(--purple,#8b5cf6)', DELETE: 'var(--red,#ef4444)' };
  return colors[m] || 'var(--text-primary)';
}

function escapeHTML(s) {
  return sanitizeHTML(s);
}

function escapeAttr(s) {
  return String(s == null ? '' : s).replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// 离开页面时清理计时器 (路由切换 / 浏览器关闭)
window.addEventListener('beforeunload', () => {
  al_stopAutoRefresh();
  al_stopCountdown();
});
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && AL.autoRefresh) {
    AL.refreshCountdown = 30;
  }
});
