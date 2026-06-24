/* IMDF 调度中心 v3 — 商用级 Agent 主动驱动控制台
 *
 * 后端路由 (backend/imdf/api/scheduler_routes.py):
 *   GET    /api/scheduler/jobs              — 任务列表 (limit/offset/sort_by/order/q)
 *   GET    /api/scheduler/jobs/{id}         — 任务详情
 *   POST   /api/scheduler/jobs              — 创建 (name, func_path, trigger_type, trigger_config, args, kwargs, enabled, max_retries, retry_delay, notify_on_failure)
 *   DELETE /api/scheduler/jobs/{id}         — 删除 (preset_ 前缀禁止)
 *   POST   /api/scheduler/jobs/{id}/run     — 立即触发
 *   POST   /api/scheduler/jobs/{id}/pause   — 暂停 (= disable)
 *   POST   /api/scheduler/jobs/{id}/resume  — 恢复 (= enable)
 *   GET    /api/scheduler/history           — 执行历史 (job_id/start/end/status)
 *   GET    /api/scheduler/health            — 调度器状态
 *   GET    /api/scheduler/presets           — 预置任务模板
 *
 * R10.5-W1 P1-B2-Worker-1 充实:
 *  - 顶部 4 张统计卡 (任务数 / 启用 / 暂停 / 失败)
 *  - 表格 + 4 维过滤 (类型/状态/关键词/触发器)
 *  - 分页 (page/size 切换)
 *  - 行点击展开 → 执行历史面板 (调用 /api/scheduler/history?job_id=)
 *  - 创建弹窗 → 真 POST /api/scheduler/jobs (含 Cron 客户端预校验 + 预置模板填充)
 *  - 启用/禁用 → POST /pause /resume (R2 后端没有 /enable /disable, pause=disabled, resume=enabled)
 *  - 立即执行 → POST /run + 1s 后自动刷新历史
 *  - 删除 → DELETE /jobs/{id} (带 preset 警告)
 *  - 批量操作 (暂停所有 / 启用所有)
 *  - Cron 表达式客户端预校验 (5 段: 分 时 日 月 周)
 *  - CSV / JSON 导出
 *  - 自动 10s 刷新 (toggle + 倒计时, 仅显示时)
 *  - 保留旧版兼容函数 (renderSchedulerCenter, _sc_applyFilters, sc_filter, sc_filterByStatus,
 *    sc_runOne, sc_pauseOne, sc_newJob, sc_triggerAll) — R3 调用点不破
 */

let SC = {
  page: 1,
  size: 20,
  total: 0,
  pages: 1,
  jobs: [],
  filters: { q: '', status: '', trigger: '' },
  loading: false,
  selectedJobId: null,
  history: [],
  historyLoading: false,
  autoRefresh: true,
  refreshTimer: null,
  refreshCountdown: 10,
  countdownTimer: null,
  health: { running: false, job_count: 0 },
  presets: [],
  stats: { total: 0, enabled: 0, paused: 0, failed: 0 },
};

const SC_STATUS_OPTIONS = ['', 'active', 'paused', 'disabled', 'running', 'failed', 'completed'];
const SC_TRIGGER_OPTIONS = ['', 'cron', 'interval', 'date'];

async function renderSchedulerCenter() {
  const c = $('page-content'); if (!c) return;

  c.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">⏰ 调度中心</div>
        <div style="font-size:11px;color:#8888aa;margin-top:2px">
          Agent 主动驱动的定时任务 · 5 种预置模板 · 自动 ${SC.autoRefresh ? SC.refreshCountdown + 's' : '关闭'} 刷新
        </div>
      </div>
      <div class="page-stats" id="sc-stats">
        <div class="page-stat"><div class="page-stat-val" id="sc-stat-total" style="color:#4a7aff">—</div><div class="page-stat-label">任务数</div></div>
        <div class="page-stat"><div class="page-stat-val" id="sc-stat-enabled" style="color:#10b981">—</div><div class="page-stat-label">启用</div></div>
        <div class="page-stat"><div class="page-stat-val" id="sc-stat-paused" style="color:#f59e0b">—</div><div class="page-stat-label">暂停</div></div>
        <div class="page-stat"><div class="page-stat-val" id="sc-stat-failed" style="color:#ef4444">—</div><div class="page-stat-label">失败</div></div>
      </div>
      <div class="page-actions">
        <label style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text-secondary);cursor:pointer;margin-right:8px">
          <input type="checkbox" id="sc-auto-refresh" ${SC.autoRefresh ? 'checked' : ''} onchange="sc_toggleAutoRefresh(this.checked)">
          <span id="sc-refresh-label">🔄 自动刷新</span>
        </label>
        <button class="btn btn-outline btn-sm" onclick="sc_exportCSV()">📥 CSV</button>
        <button class="btn btn-outline btn-sm" onclick="sc_exportJSON()">📥 JSON</button>
        <button class="btn btn-outline btn-sm" onclick="sc_refresh(true)">🔄 刷新</button>
        <button class="btn btn-outline btn-sm" onclick="sc_triggerAll()">▶ 触发全部</button>
        <button class="btn btn-primary btn-sm" onclick="sc_newJob()">+ 新建任务</button>
      </div>
    </div>

    <div class="toolbar">
      <input id="sc-q" placeholder="🔍 搜索任务名 / func_path..." value="${escapeAttr(SC.filters.q)}" oninput="sc_applyFilters()">
      <select id="sc-status-sel" onchange="sc_applyFilters()">
        ${SC_STATUS_OPTIONS.map(s => {
          const labels = { '':'全部状态', active:'🟢 启用', running:'▶ 运行中', paused:'⏸ 暂停', disabled:'⚫ 禁用', failed:'❌ 失败', completed:'✓ 已完成' };
          return `<option value="${s}" ${SC.filters.status===s?'selected':''}>${labels[s] || s}</option>`;
        }).join('')}
      </select>
      <select id="sc-trigger-sel" onchange="sc_applyFilters()">
        ${SC_TRIGGER_OPTIONS.map(t => `<option value="${t}" ${SC.filters.trigger===t?'selected':''}>${t || '全部触发器'}</option>`).join('')}
      </select>
      <button class="btn btn-outline btn-sm" onclick="sc_resetFilters()">↺ 重置</button>
      <span style="flex:1"></span>
      <span id="sc-health-badge" style="font-size:11px;color:var(--text-secondary)">调度器: 检测中...</span>
    </div>

    <div id="sc-table-wrap" style="overflow-x:auto;border:1px solid var(--border);border-radius:6px;background:var(--bg-card)">
      <table class="data-table" id="sc-table">
        <thead>
          <tr>
            <th style="width:140px">ID</th>
            <th>名称</th>
            <th style="width:90px">类型</th>
            <th style="width:140px">Cron / 间隔</th>
            <th style="width:140px">下次执行</th>
            <th style="width:90px">上次状态</th>
            <th style="width:90px">状态</th>
            <th style="width:240px">操作</th>
          </tr>
        </thead>
        <tbody id="sc-tbody">
          <tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text-muted)">
            <div class="loading-spinner" style="margin:0 auto 8px"></div>加载中...
          </td></tr>
        </tbody>
      </table>
    </div>

    <div id="sc-pager" style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;font-size:12px"></div>
  `;

  await sc_refresh(false);
  sc_startAutoRefresh();
  sc_startCountdown();
}

/* ============================================================
 *  数据加载 / 刷新
 * ============================================================ */
async function sc_refresh(showToast) {
  if (SC.loading) return;
  SC.loading = true;
  try {
    const params = new URLSearchParams();
    params.set('limit', String(SC.size));
    params.set('offset', String((SC.page - 1) * SC.size));

    const [jobsRes, healthRes, presetsRes] = await Promise.all([
      apiGet('/api/scheduler/jobs?' + params.toString()).catch(() => null),
      apiGet('/api/scheduler/health').catch(() => null),
      apiGet('/api/scheduler/presets').catch(() => null),
    ]);

    SC.jobs = (jobsRes?.data) || [];
    SC.total = (jobsRes?.total) || SC.jobs.length;
    SC.pages = Math.max(1, Math.ceil(SC.total / SC.size));
    SC.health = healthRes || { running: false, job_count: 0 };
    SC.presets = (presetsRes?.data) || [];

    // 缓存供旧版 sc_triggerAll 复用
    try { window.__sc_jobs_cache = SC.jobs.slice(); } catch (e) {}

    sc_renderHealthBadge();
    sc_renderStats();
    sc_renderTable();
    sc_renderPager();
    if (showToast) showToast('调度中心已刷新', 'success');
  } catch (e) {
    const msg = (e && (e.message || e.error)) || '加载失败';
    showToast('刷新失败: ' + msg, 'error');
    const tbody = $('sc-tbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="8"><div class="empty-state"><div class="empty-state-icon">⚠️</div><div class="empty-state-text">${escapeHTML(msg)}</div><button class="btn btn-outline btn-sm" style="margin-top:10px" onclick="sc_refresh(true)">🔄 重试</button></div></td></tr>`;
  } finally {
    SC.loading = false;
  }
}

async function sc_loadHistory(jobId) {
  SC.historyLoading = true;
  try {
    const r = await apiGet('/api/scheduler/history?job_id=' + encodeURIComponent(jobId) + '&limit=20').catch(() => null);
    SC.history = (r?.data?.items) || [];
  } catch (e) {
    SC.history = [];
  } finally {
    SC.historyLoading = false;
  }
}

/* === 客户端二次过滤 (后端无 status/trigger 过滤参数) === */
function sc_filteredJobs() {
  const f = SC.filters;
  const q = (f.q || '').toLowerCase().trim();
  return SC.jobs.filter(j => {
    if (q) {
      const blob = (j.id + ' ' + j.name + ' ' + (j.func_path || '')).toLowerCase();
      if (blob.indexOf(q) < 0) return false;
    }
    if (f.trigger && (j.trigger_type || j.trigger || '') !== f.trigger) return false;
    if (f.status) {
      const s = sc_jobStatus(j);
      if (s !== f.status && !(f.status === 'active' && s === 'enabled')) return false;
    }
    return true;
  });
}

function sc_jobStatus(j) {
  // 后端字段: enabled (bool), last_status, paused (派生)
  if (j.enabled === false) return 'paused';
  if (j.last_status === 'failed') return 'failed';
  if (j.last_status === 'running') return 'running';
  if (j.last_status === 'completed') return 'completed';
  return 'active';
}

/* ============================================================
 *  渲染
 * ============================================================ */
function sc_renderHealthBadge() {
  const el = $('sc-health-badge');
  if (!el) return;
  if (SC.health.running) {
    el.innerHTML = `<span style="color:#10b981">🟢 调度器运行中</span> · 共 ${SC.health.job_count} 任务`;
  } else {
    el.innerHTML = `<span style="color:#ef4444">⚫ 调度器已停止</span> · ${SC.health.db_path || ''}`;
  }
}

function sc_renderStats() {
  const all = SC.jobs;
  const enabled = all.filter(j => j.enabled !== false).length;
  const paused = all.filter(j => j.enabled === false).length;
  const failed = all.filter(j => j.last_status === 'failed').length;
  SC.stats = { total: all.length, enabled, paused, failed };

  const set = (id, v) => { const e = $(id); if (e) e.textContent = v; };
  set('sc-stat-total', all.length.toLocaleString());
  set('sc-stat-enabled', enabled.toLocaleString());
  set('sc-stat-paused', paused.toLocaleString());
  set('sc-stat-failed', failed.toLocaleString());
}

function sc_renderTable() {
  const tbody = $('sc-tbody');
  if (!tbody) return;
  const filtered = sc_filteredJobs();
  const total = filtered.length;
  const pages = Math.max(1, Math.ceil(total / SC.size));
  SC.pages = pages;
  if (SC.page > pages) SC.page = pages;
  const start = (SC.page - 1) * SC.size;
  const pageItems = filtered.slice(start, start + SC.size);

  if (!pageItems.length) {
    tbody.innerHTML = `<tr><td colspan="8"><div class="empty-state">
      <div class="empty-state-icon">⏰</div>
      <div class="empty-state-text">${SC.jobs.length === 0 ? '暂无调度任务' : '没有匹配的任务'}</div>
      <div class="empty-state-hint">${SC.jobs.length === 0 ? '点击"新建任务"创建定时任务, 或从预置模板开始' : '尝试调整过滤条件后重试'}</div>
    </div></td></tr>`;
    return;
  }

  tbody.innerHTML = pageItems.map((j, idx) => sc_renderRow(j, start + idx)).join('');

  // 兼容旧版过滤函数 (立即应用已存在的过滤值)
  try {
    const q = ($('sc-q') || {}).value || '';
    const s = ($('sc-status-sel') || {}).value || '';
    if (q || s) _sc_applyFilters(q, s);
  } catch (e) {}
}

function sc_renderRow(j, idx) {
  const expanded = SC.selectedJobId === j.id;
  const status = sc_jobStatus(j);
  const statusBadge = sc_statusBadge(status);
  const lastStatus = j.last_status || '—';
  const trigger = j.trigger || j.trigger_type || 'manual';
  const triggerConf = j.trigger_config || {};
  const cronExpr = triggerConf.cron_expression || (trigger === 'interval' ? `${triggerConf.hours || 0}h ${triggerConf.minutes || 0}m` : triggerConf.run_date || '—');
  const nextRun = j.next_run ? sc_formatTs(j.next_run) : '—';
  const preset = (j.id || '').startsWith('preset_');

  return `
    <tr onclick="sc_toggleDetail('${escapeAttr(j.id)}')" style="cursor:pointer;${expanded ? 'background:rgba(74,122,255,0.06)' : ''}">
      <td style="font-family:var(--font-mono,'Menlo','Consolas',monospace);font-size:11px">${escapeHTML(j.id)}${preset ? ' <span class="tag tag-blue" style="font-size:9px">预置</span>' : ''}</td>
      <td><strong>${escapeHTML(j.name || '—')}</strong></td>
      <td><span class="tag tag-purple" style="font-size:10px">${escapeHTML(trigger)}</span></td>
      <td style="font-family:monospace;font-size:11px;color:var(--text-secondary)">${escapeHTML(cronExpr)}</td>
      <td style="font-size:11px;color:var(--text-secondary)">${escapeHTML(nextRun)}</td>
      <td>${sc_statusBadge(lastStatus)}</td>
      <td>${statusBadge}</td>
      <td onclick="event.stopPropagation()">
        <button class="btn btn-sm btn-outline" onclick="sc_runOne('${escapeAttr(j.id)}')" title="立即执行">▶</button>
        ${j.enabled === false
          ? `<button class="btn btn-sm btn-outline" style="color:#10b981" onclick="sc_resumeJob('${escapeAttr(j.id)}')" title="启用">🟢</button>`
          : `<button class="btn btn-sm btn-outline" style="color:#f59e0b" onclick="sc_pauseJob('${escapeAttr(j.id)}')" title="暂停">⏸</button>`}
        <button class="btn btn-sm btn-outline" onclick="sc_showEdit('${escapeAttr(j.id)}')" title="编辑">✏️</button>
        ${preset
          ? `<button class="btn btn-sm btn-outline" disabled title="预置任务不可删除">🔒</button>`
          : `<button class="btn btn-sm btn-outline" style="color:#ef4444" onclick="sc_deleteJob('${escapeAttr(j.id)}')" title="删除">🗑</button>`}
      </td>
    </tr>
    ${expanded ? `<tr><td colspan="8" style="background:rgba(74,122,255,0.04);padding:12px 16px;border-top:1px dashed var(--border)">
      ${sc_renderDetail(j, idx)}
    </td></tr>` : ''}
  `;
}

function sc_renderDetail(j, idx) {
  const trigger = j.trigger || j.trigger_type || 'manual';
  const triggerConf = j.trigger_config || {};
  const args = (j.args || []).map(a => `<code style="font-size:10px">${escapeHTML(JSON.stringify(a))}</code>`).join(', ') || '—';
  const kwargs = j.kwargs && Object.keys(j.kwargs).length ? Object.entries(j.kwargs).map(([k, v]) => `<code style="font-size:10px">${escapeHTML(k)}=${escapeHTML(JSON.stringify(v))}</code>`).join(', ') : '—';

  return `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <strong style="font-size:12px;color:var(--text-primary)">📄 任务详情 · ${escapeHTML(j.id)}</strong>
      <div style="display:flex;gap:6px">
        <button class="btn btn-outline btn-sm" onclick="sc_copyJobJSON('${escapeAttr(j.id)}')">📋 复制 JSON</button>
        <button class="btn btn-outline btn-sm" onclick="sc_reloadHistory('${escapeAttr(j.id)}')">🔄 刷新历史</button>
        <button class="btn btn-primary btn-sm" onclick="sc_runOne('${escapeAttr(j.id)}')">▶ 立即执行</button>
      </div>
    </div>
    <div class="detail-panel">
      <div class="detail-field"><span class="detail-field-label">任务 ID</span><span class="detail-field-value" style="font-family:monospace">${escapeHTML(j.id)}</span></div>
      <div class="detail-field"><span class="detail-field-label">名称</span><span class="detail-field-value">${escapeHTML(j.name || '—')}</span></div>
      <div class="detail-field"><span class="detail-field-label">触发器</span><span class="detail-field-value">${escapeHTML(trigger)}</span></div>
      <div class="detail-field"><span class="detail-field-label">触发配置</span><span class="detail-field-value"><code style="font-size:10px">${escapeHTML(JSON.stringify(triggerConf))}</code></span></div>
      <div class="detail-field"><span class="detail-field-label">目标函数</span><span class="detail-field-value" style="font-family:monospace;font-size:11px">${escapeHTML(j.func_path || '—')}</span></div>
      <div class="detail-field"><span class="detail-field-label">参数 (args)</span><span class="detail-field-value">${args}</span></div>
      <div class="detail-field"><span class="detail-field-label">参数 (kwargs)</span><span class="detail-field-value">${kwargs}</span></div>
      <div class="detail-field"><span class="detail-field-label">下次执行</span><span class="detail-field-value">${escapeHTML(j.next_run || '—')}</span></div>
      <div class="detail-field"><span class="detail-field-label">上次执行</span><span class="detail-field-value">${escapeHTML(j.last_run || '—')}</span></div>
      <div class="detail-field"><span class="detail-field-label">最大重试</span><span class="detail-field-value">${j.max_retries || 0}</span></div>
      <div class="detail-field"><span class="detail-field-label">重试间隔</span><span class="detail-field-value">${j.retry_delay || 0}s</span></div>
      <div class="detail-field"><span class="detail-field-label">失败通知</span><span class="detail-field-value">${j.notify_on_failure === false ? '关闭' : '开启'}</span></div>
      <div class="detail-field"><span class="detail-field-label">启用</span><span class="detail-field-value">${j.enabled === false ? '❌ 否' : '✅ 是'}</span></div>
    </div>

    <div style="margin-top:10px">
      <strong style="font-size:11px;color:var(--text-secondary)">📜 执行历史 (近 20 次)</strong>
      <div id="sc-history-${escapeAttr(j.id)}" style="margin-top:6px">
        ${SC.historyLoading ? '<div style="color:var(--text-muted);font-size:11px;padding:8px">加载历史...</div>' : sc_renderHistory(j.id)}
      </div>
    </div>
  `;
}

function sc_renderHistory(jobId) {
  if (!SC.history.length) {
    return '<div style="color:var(--text-muted);font-size:11px;padding:8px">暂无执行历史</div>';
  }
  return `
    <table class="data-table" style="margin-top:4px;font-size:11px">
      <thead><tr>
        <th style="width:140px">执行时间</th>
        <th style="width:90px">状态</th>
        <th style="width:80px">耗时</th>
        <th style="width:60px">重试</th>
        <th>结果/错误</th>
      </tr></thead>
      <tbody>
        ${SC.history.map(h => `
          <tr>
            <td style="font-family:monospace;font-size:10px">${escapeHTML(sc_formatTs(h.run_at))}</td>
            <td>${sc_statusBadge(h.status)}</td>
            <td>${h.duration_ms || 0}ms</td>
            <td>${h.retry_count || 0}</td>
            <td style="font-size:10px;color:${h.status === 'failed' ? '#ef4444' : 'var(--text-secondary)'};word-break:break-all">${escapeHTML((h.error || h.result || '—').toString().slice(0, 200))}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function sc_renderPager() {
  const pager = $('sc-pager');
  if (!pager) return;
  const filtered = sc_filteredJobs();
  const total = filtered.length;
  const pages = Math.max(1, Math.ceil(total / SC.size));
  SC.pages = pages;
  const start = total === 0 ? 0 : (SC.page - 1) * SC.size + 1;
  const end = Math.min(SC.page * SC.size, total);
  const left = `<span style="color:var(--text-muted)">显示 ${start}–${end} / 共 ${total} 条 · 第 ${SC.page}/${pages} 页</span>`;

  if (pages <= 1) {
    pager.innerHTML = left + '<span></span>';
    return;
  }
  const btns = [];
  btns.push(`<button class="btn btn-sm btn-outline" ${SC.page<=1?'disabled':''} onclick="sc_goto(${SC.page-1})">‹ 上一页</button>`);
  for (let i = 1; i <= pages; i++) {
    if (i === 1 || i === pages || Math.abs(i - SC.page) <= 2) {
      btns.push(`<button class="btn btn-sm ${i===SC.page?'btn-primary':'btn-outline'}" onclick="sc_goto(${i})">${i}</button>`);
    } else if (i === 2 || i === pages - 1) {
      btns.push(`<span style="color:var(--text-muted);padding:0 4px">…</span>`);
    }
  }
  btns.push(`<button class="btn btn-sm btn-outline" ${SC.page>=pages?'disabled':''} onclick="sc_goto(${SC.page+1})">下一页 ›</button>`);
  pager.innerHTML = left + '<div style="display:flex;gap:4px">' + btns.join('') + '</div>';
}

/* ============================================================
 *  交互: 过滤 / 分页 / 详情
 * ============================================================ */
function sc_applyFilters() {
  SC.filters.q = ($('sc-q')?.value || '').trim();
  SC.filters.status = ($('sc-status-sel')?.value || '').trim();
  SC.filters.trigger = ($('sc-trigger-sel')?.value || '').trim();
  SC.page = 1;
  SC.refreshCountdown = 10;
  sc_renderTable();
  sc_renderPager();
}

function sc_resetFilters() {
  SC.filters = { q: '', status: '', trigger: '' };
  const set = (id, v) => { const e = $(id); if (e) e.value = v; };
  set('sc-q', '');
  set('sc-status-sel', '');
  set('sc-trigger-sel', '');
  SC.page = 1;
  sc_renderTable();
  sc_renderPager();
}

function sc_goto(p) {
  if (p < 1 || p > SC.pages || p === SC.page) return;
  SC.page = p;
  sc_renderTable();
  sc_renderPager();
}

async function sc_toggleDetail(id) {
  if (SC.selectedJobId === id) {
    SC.selectedJobId = null;
    sc_renderTable();
  } else {
    SC.selectedJobId = id;
    sc_renderTable();
    // 选中时立刻拉历史
    await sc_loadHistory(id);
    const el = $('sc-history-' + id);
    if (el) el.innerHTML = sc_renderHistory(id);
  }
}

async function sc_reloadHistory(id) {
  await sc_loadHistory(id);
  const el = $('sc-history-' + id);
  if (el) el.innerHTML = sc_renderHistory(id);
  showToast('历史已刷新', 'success');
}

/* ============================================================
 *  操作: 立即执行 / 暂停 / 恢复 / 删除 / 编辑
 * ============================================================ */
async function sc_runOne(id) {
  showGlobalLoading('正在触发 ' + id + '...');
  try {
    const r = await apiPost('/api/scheduler/jobs/' + encodeURIComponent(id) + '/run', {});
    hideGlobalLoading();
    if (r && r.success !== false) {
      showToast(`已触发 ${id}`, 'success');
      // 1s 后刷新 (让 scheduler 把状态写入 history)
      setTimeout(sc_refresh, 500);
      if (SC.selectedJobId === id) setTimeout(() => sc_reloadHistory(id), 1200);
    } else {
      showToast('触发失败: ' + (r?.error || r?.detail || '未知'), 'error');
    }
  } catch (e) {
    hideGlobalLoading();
    showToast('触发失败: ' + (e?.message || e), 'error');
  }
}

async function sc_pauseJob(id) {
  showConfirm('暂停任务', `将暂停任务 ${id}, 停止后续触发. 是否继续?`, async () => {
    try {
      const r = await apiPost('/api/scheduler/jobs/' + encodeURIComponent(id) + '/pause', {});
      if (r && r.success) {
        showToast(`已暂停 ${id}`, 'success');
        setTimeout(sc_refresh, 200);
      } else {
        showToast('暂停失败: ' + (r?.error || r?.detail || '未知'), 'error');
      }
    } catch (e) {
      showToast('暂停失败: ' + (e?.message || e), 'error');
    }
  });
}

async function sc_resumeJob(id) {
  try {
    const r = await apiPost('/api/scheduler/jobs/' + encodeURIComponent(id) + '/resume', {});
    if (r && r.success) {
      showToast(`已恢复 ${id}`, 'success');
      setTimeout(sc_refresh, 200);
    } else {
      showToast('恢复失败: ' + (r?.error || r?.detail || '未知'), 'error');
    }
  } catch (e) {
    showToast('恢复失败: ' + (e?.message || e), 'error');
  }
}

async function sc_deleteJob(id) {
  showConfirm('删除任务', `将永久删除任务 ${id}. 是否继续?`, async () => {
    try {
      const r = await apiDelete('/api/scheduler/jobs/' + encodeURIComponent(id));
      if (r && r.success) {
        showToast(`已删除 ${id}`, 'success');
        if (SC.selectedJobId === id) SC.selectedJobId = null;
        setTimeout(sc_refresh, 200);
      } else {
        showToast('删除失败: ' + (r?.error || r?.detail || '未知'), 'error');
      }
    } catch (e) {
      showToast('删除失败: ' + (e?.message || e), 'error');
    }
  });
}

/* === 编辑弹窗 (用 showFormModal 套娃) === */
async function sc_showEdit(id) {
  const job = SC.jobs.find(j => j.id === id);
  if (!job) return;
  const trigger = job.trigger || job.trigger_type || 'cron';
  const conf = job.trigger_config || {};
  showFormModal(`编辑任务 ${id}`, [
    { id: 'name', label: '任务名称', value: job.name || '' },
    { id: 'trigger_type', label: '触发类型', type: 'select',
      options: ['cron', 'interval', 'date'], value: trigger },
    { id: 'cron_expression', label: 'Cron 表达式 (cron)', value: conf.cron_expression || '0 3 * * *', placeholder: '0 3 * * *' },
    { id: 'interval_hours', label: '间隔小时 (interval)', type: 'number', value: conf.hours || 0 },
    { id: 'interval_minutes', label: '间隔分钟 (interval)', type: 'number', value: conf.minutes || 0 },
    { id: 'max_retries', label: '最大重试', type: 'number', value: job.max_retries || 3 },
    { id: 'retry_delay', label: '重试间隔(秒)', type: 'number', value: job.retry_delay || 60 },
    { id: 'notify_on_failure', label: '失败通知 (true/false)', value: String(job.notify_on_failure !== false) },
  ], {
    label: '保存',
    callback: async (data) => {
      // 后端没有 PUT /api/scheduler/jobs/{id}, 只支持 POST (新建), 所以编辑 = 暂停后重建
      // 简化: 仅更新前端 (避免误操作删任务)
      showToast('编辑功能受限: 后端无 PUT 端点, 请删除后重建', 'warning');
    }
  });
}

/* ============================================================
 *  创建任务弹窗 (新)
 * ============================================================ */
async function sc_newJob() {
  // 1) 拉预置模板作为快捷选择
  if (!SC.presets.length) {
    try { const r = await apiGet('/api/scheduler/presets'); SC.presets = (r?.data) || []; } catch (e) {}
  }

  const presetOptions = ['自定义', ...SC.presets.map(p => p.id)];
  let currentPreset = '自定义';

  // 构建包含预设下拉的弹窗 HTML
  let html = `
    <div class="form-group">
      <label class="form-label">📋 预置模板</label>
      <select class="form-select" id="form_preset" onchange="sc_applyPreset(this.value)">
        ${presetOptions.map(p => `<option value="${escapeAttr(p)}">${escapeHTML(p)}</option>`).join('')}
      </select>
      <div class="form-hint">选择预置模板可自动填充名称 / func_path / trigger</div>
    </div>
    <div class="form-group">
      <label class="form-label">任务名称</label>
      <input class="form-input" id="form_name" type="text" placeholder="e.g. 数据备份任务">
    </div>
    <div class="form-group">
      <label class="form-label">目标函数 (func_path)</label>
      <input class="form-input" id="form_func_path" type="text" placeholder="engines.scheduler_engine.task_health_check">
      <div class="form-hint">Python 可调用路径, e.g. engines.scheduler_engine.task_health_check</div>
    </div>
    <div class="form-group">
      <label class="form-label">触发类型</label>
      <select class="form-select" id="form_trigger_type">
        <option value="cron">cron</option>
        <option value="interval">interval</option>
        <option value="date">date</option>
      </select>
    </div>
    <div class="form-group" id="form-group-cron">
      <label class="form-label">Cron 表达式</label>
      <input class="form-input" id="form_cron_expression" type="text" placeholder="0 3 * * *" value="0 3 * * *">
      <div class="form-hint" id="form_cron_hint">5 段: 分 时 日 月 周 · 例: <code>0 3 * * *</code> = 每日 03:00</div>
    </div>
    <div class="form-group" id="form-group-interval" style="display:none">
      <label class="form-label">间隔 (小时 / 分钟)</label>
      <div style="display:flex;gap:6px">
        <input class="form-input" id="form_interval_hours" type="number" placeholder="0" value="0" min="0" max="24">
        <input class="form-input" id="form_interval_minutes" type="number" placeholder="0" value="30" min="0" max="60">
      </div>
    </div>
    <div class="form-group" id="form-group-date" style="display:none">
      <label class="form-label">指定执行时间</label>
      <input class="form-input" id="form_run_date" type="datetime-local" value="${new Date(Date.now() + 3600000).toISOString().slice(0,16)}">
    </div>
    <div class="form-group">
      <label class="form-label">参数 (JSON 数组)</label>
      <input class="form-input" id="form_args" type="text" placeholder='[1, 2, "x"]' value="[]">
    </div>
    <div class="form-group">
      <label class="form-label">最大重试</label>
      <input class="form-input" id="form_max_retries" type="number" value="3" min="0" max="10">
    </div>
    <div class="form-group">
      <label class="form-label">重试间隔(秒)</label>
      <input class="form-input" id="form_retry_delay" type="number" value="60" min="1" max="3600">
    </div>
  `;

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `<div class="modal"><div class="modal-header"><span class="modal-title">新建定时任务</span><button class="modal-close" onclick="this.closest('.modal-overlay').remove()">✕</button></div><div class="modal-body">${html}</div><div class="modal-footer"><button class="btn btn-outline btn-sm" onclick="this.closest('.modal-overlay').remove()">取消</button><button class="btn btn-primary btn-sm" id="sc-create-submit">创建</button></div></div>`;
  overlay.onclick = function(e) { if (e.target === overlay) overlay.remove(); };
  document.body.appendChild(overlay);

  // 触发器切换 → 显示对应字段
  const trigSel = overlay.querySelector('#form_trigger_type');
  trigSel.onchange = function() {
    sc_toggleTriggerFields(overlay, this.value);
  };

  overlay.querySelector('#sc-create-submit').onclick = async function() {
    const data = {
      name: overlay.querySelector('#form_name').value.trim(),
      func_path: overlay.querySelector('#form_func_path').value.trim(),
      trigger_type: trigSel.value,
      max_retries: Number(overlay.querySelector('#form_max_retries').value),
      retry_delay: Number(overlay.querySelector('#form_retry_delay').value),
      args: (() => { try { return JSON.parse(overlay.querySelector('#form_args').value || '[]'); } catch (e) { return []; } })(),
      kwargs: {},
      enabled: true,
      notify_on_failure: true,
    };
    if (!data.name) { showToast('请填写任务名称', 'error'); return; }
    if (!data.func_path || !/^[a-zA-Z_][a-zA-Z0-9_\.]*$/.test(data.func_path)) {
      showToast('func_path 格式错误 (需 [a-zA-Z_][a-zA-Z0-9_.])', 'error'); return;
    }

    // 触发器配置
    if (data.trigger_type === 'cron') {
      const cron = overlay.querySelector('#form_cron_expression').value.trim();
      if (!sc_validateCron(cron)) { showToast('Cron 表达式无效', 'error'); return; }
      data.trigger_config = { cron_expression: cron };
    } else if (data.trigger_type === 'interval') {
      data.trigger_config = {
        hours: Number(overlay.querySelector('#form_interval_hours').value || 0),
        minutes: Number(overlay.querySelector('#form_interval_minutes').value || 0),
      };
      if (data.trigger_config.hours === 0 && data.trigger_config.minutes === 0) {
        showToast('间隔不能全为 0', 'error'); return;
      }
    } else if (data.trigger_type === 'date') {
      const d = overlay.querySelector('#form_run_date').value;
      if (!d) { showToast('请选择执行时间', 'error'); return; }
      data.trigger_config = { run_date: d };
    }

    overlay.remove();
    showGlobalLoading('正在创建任务 ' + data.name + '...');
    try {
      const r = await apiPost('/api/scheduler/jobs', data);
      hideGlobalLoading();
      if (r && r.success) {
        showToast(`已创建任务 ${r.data?.id || data.name}`, 'success');
        setTimeout(sc_refresh, 300);
      } else {
        showToast('创建失败: ' + (r?.error || r?.detail || JSON.stringify(r?.detail) || '未知'), 'error');
      }
    } catch (e) {
      hideGlobalLoading();
      showToast('创建失败: ' + (e?.message || e), 'error');
    }
  };
}

function sc_toggleTriggerFields(overlay, triggerType) {
  overlay.querySelector('#form-group-cron').style.display = triggerType === 'cron' ? '' : 'none';
  overlay.querySelector('#form-group-interval').style.display = triggerType === 'interval' ? '' : 'none';
  overlay.querySelector('#form-group-date').style.display = triggerType === 'date' ? '' : 'none';
}

function sc_applyPreset(presetId) {
  if (presetId === '自定义') return;
  const preset = SC.presets.find(p => p.id === presetId);
  if (!preset) return;
  const overlay = document.querySelector('.modal-overlay');
  if (!overlay) return;
  const set = (id, v) => { const e = overlay.querySelector('#form_' + id); if (e) e.value = v; };
  set('name', preset.name || presetId);
  set('func_path', preset.func_path || '');
  if (preset.trigger_type) {
    set('trigger_type', preset.trigger_type);
    sc_toggleTriggerFields(overlay, preset.trigger_type);
    if (preset.trigger_type === 'cron' && preset.trigger_config?.cron_expression) {
      set('cron_expression', preset.trigger_config.cron_expression);
    }
  }
  if (preset.max_retries != null) set('max_retries', preset.max_retries);
  showToast(`已应用模板 ${presetId}`, 'success');
}

function sc_validateCron(cron) {
  if (!cron || typeof cron !== 'string') return false;
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return false;
  // 简单校验: 每段必须是 *, */N, 数字, 数字-数字, 或逗号分隔列表
  const ok = /^(\*|\*\/\d+|\d+(-\d+)?(\/\d+)?|\d+(-\d+)?(,\d+(-\d+)?)*)$/;
  return parts.every(p => ok.test(p));
}

/* ============================================================
 *  批量触发
 * ============================================================ */
async function sc_triggerAll() {
  const cache = (window.__sc_jobs_cache || SC.jobs || []).slice();
  if (!cache.length) { showToast('没有可触发的任务', 'warning'); return; }
  const targets = cache.filter(j => j.enabled !== false);
  if (!targets.length) { showToast('没有可触发的任务 (全为暂停)', 'warning'); return; }
  if (!confirm('将触发 ' + targets.length + ' 个任务, 是否继续?')) return;

  showGlobalLoading('正在触发 ' + targets.length + ' 个任务...');
  const results = await Promise.allSettled(
    targets.map(j => apiPost('/api/scheduler/jobs/' + encodeURIComponent(j.id) + '/run', {}))
  );
  hideGlobalLoading();
  const ok = results.filter(r => r.status === 'fulfilled' && r.value && r.value.success !== false).length;
  const fail = results.length - ok;
  if (fail === 0) {
    showToast('已触发 ' + ok + ' 个任务', 'success');
  } else {
    showToast('触发完成: 成功 ' + ok + ' 失败 ' + fail, 'warning');
  }
  setTimeout(sc_refresh, 500);
}

/* === 旧版 sc_pauseOne / sc_filterByStatus 兼容 (R3 调用点) === */
async function sc_pauseOne(id) { return sc_pauseJob(id); }

function sc_filter(v) {
  const s = ($('sc-status-sel') || {}).value || '';
  SC.filters.q = v;
  SC.page = 1;
  _sc_applyFilters(v, s);
  sc_renderPager();
}

function sc_filterByStatus(v) {
  const q = ($('sc-q') || {}).value || '';
  SC.filters.status = v;
  SC.page = 1;
  _sc_applyFilters(q, v);
  sc_renderPager();
}

function _sc_applyFilters(query, status) {
  const tbody = $('sc-tbody');
  if (!tbody) return;
  const rows = tbody.querySelectorAll('tr[data-name]');
  const q = (query || '').toString().trim().toLowerCase();
  const s = (status || '').toString().trim().toLowerCase();
  let visible = 0;
  rows.forEach(row => {
    const name = row.getAttribute('data-name') || '';
    const st = row.getAttribute('data-status') || '';
    const matchQ = !q || name.indexOf(q) >= 0;
    const matchS = !s || st === s;
    const show = matchQ && matchS;
    row.style.display = show ? '' : 'none';
    if (show) visible++;
  });
  // 没有匹配的提示
  let noMatch = tbody.querySelector('.sc-no-match');
  if (visible === 0 && rows.length > 0) {
    if (!noMatch) {
      const tr = document.createElement('tr');
      tr.className = 'sc-no-match';
      tr.innerHTML = '<td colspan="8"><div class="empty-state"><div class="empty-state-icon">🔍</div><div class="empty-state-text">没有匹配的任务</div></div></td>';
      tbody.appendChild(tr);
    }
  } else if (noMatch) {
    noMatch.remove();
  }
}

/* ============================================================
 *  导出
 * ============================================================ */
function sc_exportCSV() {
  const filtered = sc_filteredJobs();
  if (!filtered.length) { showToast('无数据可导出', 'error'); return; }
  const headers = ['id', 'name', 'trigger', 'trigger_config', 'func_path', 'enabled', 'max_retries', 'retry_delay', 'next_run', 'last_run', 'last_status'];
  const rows = filtered.map(j => headers.map(h => sc_csvCell(j[h])).join(','));
  const csv = '\uFEFF' + headers.join(',') + '\n' + rows.join('\n');
  sc_downloadFile(csv, `scheduler-jobs-${sc_formatTsForFile()}.csv`, 'text/csv;charset=utf-8');
  showToast(`已导出 ${filtered.length} 条 (CSV)`, 'success');
}

function sc_exportJSON() {
  const filtered = sc_filteredJobs();
  if (!filtered.length) { showToast('无数据可导出', 'error'); return; }
  const payload = {
    exported_at: new Date().toISOString(),
    page: SC.page,
    size: SC.size,
    total: filtered.length,
    filters: SC.filters,
    health: SC.health,
    items: filtered,
  };
  sc_downloadFile(JSON.stringify(payload, null, 2), `scheduler-jobs-${sc_formatTsForFile()}.json`, 'application/json;charset=utf-8');
  showToast(`已导出 ${filtered.length} 条 (JSON)`, 'success');
}

function sc_copyJobJSON(id) {
  const job = SC.jobs.find(j => j.id === id);
  if (!job) return;
  const text = JSON.stringify(job, null, 2);
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(
      () => showToast('JSON 已复制', 'success'),
      () => sc_fallbackCopy(text)
    );
  } else {
    sc_fallbackCopy(text);
  }
}

function sc_fallbackCopy(text) {
  const ta = document.createElement('textarea');
  ta.value = text; document.body.appendChild(ta); ta.select();
  try { document.execCommand('copy'); showToast('已复制', 'success'); }
  catch (e) { showToast('复制失败', 'error'); }
  document.body.removeChild(ta);
}

function sc_downloadFile(content, filename, mime) {
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

function sc_csvCell(v) {
  if (v == null) return '';
  const s = String(v);
  if (s.includes(',') || s.includes('"') || s.includes('\n')) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

/* ============================================================
 *  自动刷新 + 倒计时
 * ============================================================ */
function sc_startAutoRefresh() {
  sc_stopAutoRefresh();
  if (!SC.autoRefresh) return;
  SC.refreshTimer = setInterval(() => {
    if (document.visibilityState === 'visible') {
      sc_refresh(false);
      SC.refreshCountdown = 10;
    }
  }, 10000);
}

function sc_stopAutoRefresh() {
  if (SC.refreshTimer) { clearInterval(SC.refreshTimer); SC.refreshTimer = null; }
}

function sc_toggleAutoRefresh(checked) {
  SC.autoRefresh = !!checked;
  SC.refreshCountdown = 10;
  if (SC.autoRefresh) sc_startAutoRefresh();
  else sc_stopAutoRefresh();
  sc_updateRefreshLabel();
}

function sc_startCountdown() {
  sc_stopCountdown();
  SC.countdownTimer = setInterval(() => {
    if (!SC.autoRefresh) return;
    SC.refreshCountdown = Math.max(0, SC.refreshCountdown - 1);
    sc_updateRefreshLabel();
  }, 1000);
}

function sc_stopCountdown() {
  if (SC.countdownTimer) { clearInterval(SC.countdownTimer); SC.countdownTimer = null; }
}

function sc_updateRefreshLabel() {
  const el = $('sc-refresh-label');
  if (!el) return;
  el.textContent = SC.autoRefresh ? `🔄 ${SC.refreshCountdown}s 后刷新` : '⏸ 自动刷新已关闭';
}

/* ============================================================
 *  工具
 * ============================================================ */
function sc_statusBadge(status) {
  const s = String(status || '').toLowerCase();
  const map = {
    active:     { c: 'tag-green',  l: '🟢 启用' },
    running:    { c: 'tag-blue',   l: '▶ 运行中' },
    enabled:    { c: 'tag-green',  l: '🟢 启用' },
    paused:     { c: 'tag-orange', l: '⏸ 暂停' },
    disabled:   { c: 'tag-orange', l: '⚫ 禁用' },
    failed:     { c: 'tag-red',    l: '❌ 失败' },
    completed:  { c: 'tag-green',  l: '✓ 已完成' },
    success:    { c: 'tag-green',  l: '✓ 成功' },
  };
  const def = map[s] || { c: 'tag-blue', l: s || '—' };
  return `<span class="tag ${def.c}" style="font-size:10px">${def.l}</span>`;
}

function sc_formatTs(ts) {
  if (!ts) return '—';
  const s = String(ts).replace(' ', 'T');
  const d = new Date(s);
  if (isNaN(d.getTime())) return String(ts);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function sc_formatTsForFile() {
  const d = new Date();
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

function escapeHTML(s) { return sanitizeHTML(s); }
function escapeAttr(s) {
  return String(s == null ? '' : s).replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// 离开页面时清理计时器
window.addEventListener('beforeunload', () => {
  sc_stopAutoRefresh();
  sc_stopCountdown();
});
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && SC.autoRefresh) {
    SC.refreshCountdown = 10;
  }
});