/* IMDF 传输共享 v2 — 表格 + 过滤 + 创建弹窗 + 详情 + 批量操作 + 轮询
 *
 * 后端: /api/transfer/* — 分享链接模型 (token / 资源 / 过期 / 密码 / 下载限制)
 *   GET    /api/transfer/list?limit=&offset=&q=&creator=   — 我的活跃分享
 *   GET    /api/transfer/list/all?limit=&offset=            — 全部 (含已撤销/过期)
 *   GET    /api/transfer/{token}/info                      — 详情
 *   POST   /api/transfer/share                             — 创建
 *   DELETE /api/transfer/{token}                           — 撤销 (软删)
 *   DELETE /api/transfer/{token}/permanent                 — 永久删除
 *   POST   /api/transfer/cleanup                           — 清理过期
 *
 * R10.5-W1 audit-transfer 充实:
 *  - 真实分页 + 4 状态过滤 (active/expired/revoked/all)
 *  - 类型过滤 (file/directory/dataset) + 全文搜索
 *  - 进度条 (downloads_used / max_downloads) + 状态徽章
 *  - 多选 + 批量撤销 + 批量永久删除
 *  - 详情模态框 (token / 资源 / 创建者 / 过期 / 下载统计 / 密码 / 备注)
 *  - 创建弹窗 (resource_path / resource_type / password / expiry_hours / max_downloads / note)
 *  - 复制分享链接 (含 sig/exp) + 一键撤销
 *  - 5s 轮询 (仅显示时)
 *  - 顶部 4 统计卡 (活跃 / 已撤销 / 今日创建 / 总下载数)
 */

let TC = {
  scope: 'mine',                // 'mine' | 'all'
  page: 1,
  size: 20,
  total: 0,
  shares: [],
  filters: { q: '', status: 'all', type: '' },
  selected: new Set(),
  loading: false,
  polling: null,
  showCreate: false,
  detailToken: null,
  stats: { active: 0, expired: 0, revoked: 0, totalDownloads: 0 },
};

const TC_TYPE_OPTIONS = ['', 'file', 'directory', 'dataset'];
const TC_STATUS_OPTIONS = ['all', 'active', 'expired', 'revoked'];

async function renderTransferCenter() {
  const c = $('page-content'); if (!c) return;

  c.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">🔗 传输共享</div>
        <div style="font-size:11px;color:#8888aa;margin-top:2px">
          创建带签名 / 密码 / 过期 / 下载次数限制的安全分享链接 · 自动 5s 轮询
        </div>
      </div>
      <div class="page-stats" id="tc-stats">
        <div class="page-stat"><div class="page-stat-val" id="tc-stat-active" style="color:#10b981">—</div><div class="page-stat-label">活跃</div></div>
        <div class="page-stat"><div class="page-stat-val" id="tc-stat-revoked" style="color:#f59e0b">—</div><div class="page-stat-label">已撤销</div></div>
        <div class="page-stat"><div class="page-stat-val" id="tc-stat-expired" style="color:#6b7280">—</div><div class="page-stat-label">已过期</div></div>
        <div class="page-stat"><div class="page-stat-val" id="tc-stat-dl">—</div><div class="page-stat-label">总下载数</div></div>
      </div>
      <div class="page-actions">
        <select class="form-select" id="tc-scope" onchange="tc_switchScope()" style="font-size:12px;padding:4px 8px">
          <option value="mine" ${TC.scope==='mine'?'selected':''}>📁 我的分享</option>
          <option value="all"  ${TC.scope==='all' ?'selected':''}>🌐 全部分享 (管理员)</option>
        </select>
        <button class="btn btn-outline btn-sm" onclick="tc_cleanup()">🧹 清理过期</button>
        <button class="btn btn-outline btn-sm" onclick="tc_refresh()">🔄 刷新</button>
        <button class="btn btn-primary btn-sm" onclick="tc_showCreate()">+ 新建分享</button>
      </div>
    </div>

    <div class="toolbar" id="tc-toolbar">
      <input id="tc-q" placeholder="🔍 搜索资源 / 备注 / 创建者..." value="${escapeAttr(TC.filters.q)}" oninput="tc_applyFilters()">
      <select id="tc-status" onchange="tc_applyFilters()">
        ${TC_STATUS_OPTIONS.map(s => {
          const labels = { all:'全部状态', active:'🟢 活跃', expired:'⏰ 已过期', revoked:'🚫 已撤销' };
          return `<option value="${s}" ${TC.filters.status===s?'selected':''}>${labels[s]||s}</option>`;
        }).join('')}
      </select>
      <select id="tc-type" onchange="tc_applyFilters()">
        ${TC_TYPE_OPTIONS.map(t => `<option value="${t}" ${TC.filters.type===t?'selected':''}>${t || '全部类型'}</option>`).join('')}
      </select>
      <button class="btn btn-outline btn-sm" onclick="tc_resetFilters()">↺ 重置</button>
      <span style="flex:1"></span>
      <span id="tc-batch-actions" style="display:none;display:flex;gap:4px;align-items:center">
        <span style="font-size:11px;color:var(--text-secondary)" id="tc-sel-count">已选 0 项</span>
        <button class="btn btn-sm btn-outline" onclick="tc_batchRevoke()">🚫 批量撤销</button>
        <button class="btn btn-sm btn-outline" style="color:var(--red,#ef4444)" onclick="tc_batchDelete()">🗑 永久删除</button>
        <button class="btn btn-sm btn-outline" onclick="tc_clearSelection()">取消选择</button>
      </span>
    </div>

    <div id="tc-table-wrap" style="overflow-x:auto;border:1px solid var(--border);border-radius:6px;background:var(--bg-card)">
      <table class="data-table" id="tc-table">
        <thead>
          <tr>
            <th style="width:32px"><input type="checkbox" id="tc-check-all" onchange="tc_toggleAll(this.checked)"></th>
            <th style="width:200px">资源路径</th>
            <th style="width:90px">类型</th>
            <th style="width:120px">创建者</th>
            <th style="width:160px">过期时间</th>
            <th style="width:90px">状态</th>
            <th style="width:160px">下载进度</th>
            <th>备注</th>
            <th style="width:200px">操作</th>
          </tr>
        </thead>
        <tbody id="tc-tbody">
          <tr><td colspan="9" style="text-align:center;padding:30px;color:var(--text-muted)">
            <div class="loading-spinner" style="margin:0 auto 8px"></div>加载中...
          </td></tr>
        </tbody>
      </table>
    </div>

    <div id="tc-pager" style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;font-size:12px"></div>
  `;

  await tc_refresh();
  tc_startPolling();
}

/* === 切换作用域: mine / all === */
function tc_switchScope() {
  TC.scope = $('tc-scope')?.value || 'mine';
  TC.page = 1;
  TC.selected.clear();
  tc_updateBatchBar();
  tc_refresh();
}

/* === 加载 / 刷新 === */
async function tc_refresh() {
  if (TC.loading) return;
  TC.loading = true;
  try {
    const base = TC.scope === 'all' ? '/api/transfer/list/all' : '/api/transfer/list';
    const params = new URLSearchParams();
    params.set('limit', String(TC.size));
    params.set('offset', String((TC.page - 1) * TC.size));
    if (TC.filters.q) params.set('q', TC.filters.q);

    const r = await apiGet(base + '?' + params.toString());
    let items = (r?.data?.shares) || [];

    // mine 视图里服务端已过滤 is_active=true, all 视图是混合的
    // 客户端再按 status/type 二次过滤 (后端无这些参数)
    items = items.filter(s => tc_matchStatus(s, TC.filters.status));
    items = items.filter(s => !TC.filters.type || s.resource_type === TC.filters.type);

    TC.shares = items;
    TC.total = (r?.data?.total != null) ? r.data.total : items.length;

    // 统计: 仅取首屏全量, 不分页拉, 所以是当前页统计 (best-effort)
    tc_recomputeStats();
    tc_renderTable();
    tc_renderPager();
  } catch (e) {
    const msg = (e && (e.message || e.error)) || '加载失败';
    const tbody = $('tc-tbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="9"><div class="empty-state"><div class="empty-state-icon">⚠️</div><div class="empty-state-text">${escapeHTML(msg)}</div><button class="btn btn-outline btn-sm" style="margin-top:10px" onclick="tc_refresh()">🔄 重试</button></div></td></tr>`;
    showToast('刷新失败: ' + msg, 'error');
  } finally {
    TC.loading = false;
  }
}

function tc_matchStatus(share, status) {
  if (!status || status === 'all') return true;
  if (status === 'active') return share.is_active !== false && !tc_isExpired(share);
  if (status === 'expired') return tc_isExpired(share);
  if (status === 'revoked') return share.is_active === false;
  return true;
}

function tc_isExpired(share) {
  if (!share.expires_at) return false;
  try {
    return new Date(share.expires_at).getTime() < Date.now();
  } catch (e) { return false; }
}

function tc_recomputeStats() {
  let active = 0, expired = 0, revoked = 0, totalDl = 0;
  TC.shares.forEach(s => {
    if (s.is_active === false) revoked++;
    else if (tc_isExpired(s)) expired++;
    else active++;
    totalDl += (s.downloads_used || 0);
  });
  TC.stats = { active, expired, revoked, totalDownloads: totalDl };
  const set = (id, v) => { const el = $(id); if (el) el.textContent = v; };
  set('tc-stat-active', active);
  set('tc-stat-revoked', revoked);
  set('tc-stat-expired', expired);
  set('tc-stat-dl', totalDl.toLocaleString());
}

/* === 渲染: 表格 === */
function tc_renderTable() {
  const tbody = $('tc-tbody');
  if (!tbody) return;
  if (!TC.shares.length) {
    tbody.innerHTML = `<tr><td colspan="9"><div class="empty-state"><div class="empty-state-icon">🔗</div><div class="empty-state-text">暂无分享链接</div><div class="empty-state-hint">点击右上角"新建分享"创建分享链接</div></div></td></tr>`;
    return;
  }
  tbody.innerHTML = TC.shares.map(s => {
    const token = escapeAttr(s.token || '');
    const checked = TC.selected.has(s.token) ? 'checked' : '';
    const resource = escapeHTML(s.resource_path || '—');
    const type = escapeHTML(s.resource_type || 'file');
    const creator = escapeHTML(s.creator || '—');
    const expires = escapeHTML(tc_formatTs(s.expires_at));
    const status = tc_statusOf(s);
    const statusBadge = tc_statusBadge(status);
    const note = escapeHTML(s.note || '');
    const progress = tc_progressBar(s);
    return `
      <tr data-token="${token}" style="${TC.selected.has(s.token)?'background:rgba(74,122,255,0.04)':''}">
        <td onclick="event.stopPropagation()"><input type="checkbox" ${checked} onchange="tc_toggleOne('${token}', this.checked)"></td>
        <td style="word-break:break-all;font-size:11px" title="${resource}">
          <div style="font-weight:600;color:var(--text-primary)">${resource.length > 32 ? resource.slice(0, 32) + '…' : resource}</div>
          <div style="font-family:var(--font-mono,monospace);font-size:10px;color:var(--text-muted);margin-top:2px">${escapeHTML(s.token || '')}</div>
        </td>
        <td><span class="tag tag-blue" style="font-size:10px">${type}</span></td>
        <td style="font-size:11px">${creator}</td>
        <td style="font-size:11px;font-family:var(--font-mono,monospace)">${expires}</td>
        <td>${statusBadge}</td>
        <td>${progress}</td>
        <td style="font-size:11px;color:var(--text-secondary);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${note}">${note || '—'}</td>
        <td onclick="event.stopPropagation()">
          <div style="display:flex;gap:3px;flex-wrap:wrap">
            <button class="btn btn-sm btn-outline" onclick="tc_copyLink('${token}')" title="复制分享链接">📋</button>
            <button class="btn btn-sm btn-outline" onclick="tc_showDetail('${token}')" title="查看详情">ℹ️</button>
            ${s.is_active !== false
              ? `<button class="btn btn-sm btn-outline" style="color:#f59e0b" onclick="tc_revoke('${token}')" title="撤销">🚫</button>`
              : `<button class="btn btn-sm btn-outline" style="color:var(--red,#ef4444)" onclick="tc_permanentDelete('${token}')" title="永久删除">🗑</button>`}
          </div>
        </td>
      </tr>
    `;
  }).join('');
  tc_updateBatchBar();
}

function tc_statusOf(share) {
  if (share.is_active === false) return 'revoked';
  if (tc_isExpired(share)) return 'expired';
  return 'active';
}

function tc_statusBadge(status) {
  const map = {
    active:   { cls: 'tag-green',  icon: '🟢', label: '活跃' },
    expired:  { cls: 'tag-orange', icon: '⏰', label: '已过期' },
    revoked:  { cls: 'tag-red',    icon: '🚫', label: '已撤销' },
  };
  const b = map[status] || map.active;
  return `<span class="tag ${b.cls}" style="font-size:10px">${b.icon} ${b.label}</span>`;
}

function tc_progressBar(share) {
  const used = share.downloads_used || 0;
  const max  = share.max_downloads || 0;
  if (max > 0) {
    const pct = Math.min(100, Math.round((used / max) * 100));
    const color = pct >= 100 ? 'var(--red,#ef4444)' : (pct >= 80 ? '#f59e0b' : '#10b981');
    return `
      <div style="font-size:10px;color:var(--text-secondary);margin-bottom:3px">${used} / ${max} 次</div>
      <div style="height:6px;background:var(--bg-base,#0f0f1a);border-radius:3px;overflow:hidden">
        <div style="height:100%;width:${pct}%;background:${color};transition:width 0.3s"></div>
      </div>`;
  }
  return `<div style="font-size:11px"><span class="tag tag-purple" style="font-size:10px">${used} 次 · 无限制</span></div>`;
}

/* === 渲染: 分页 === */
function tc_renderPager() {
  const pager = $('tc-pager');
  if (!pager) return;
  const totalPages = Math.max(1, Math.ceil(TC.total / TC.size));
  const start = (TC.page - 1) * TC.size + 1;
  const end = Math.min(TC.page * TC.size, TC.total);
  const left = `<span style="color:var(--text-muted)">显示 ${TC.total ? (start + '–' + end) : '0'} / 共 ${TC.total} 条 · 第 ${TC.page}/${totalPages} 页</span>`;
  if (totalPages <= 1) {
    pager.innerHTML = left + '<span></span>';
    return;
  }
  const pages = [];
  pages.push(`<button class="btn btn-sm btn-outline" ${TC.page<=1?'disabled':''} onclick="tc_goto(${TC.page-1})">‹ 上一页</button>`);
  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || Math.abs(i - TC.page) <= 2) {
      pages.push(`<button class="btn btn-sm ${i===TC.page?'btn-primary':'btn-outline'}" onclick="tc_goto(${i})">${i}</button>`);
    } else if (i === 2 || i === totalPages - 1) {
      pages.push(`<span style="color:var(--text-muted);padding:0 4px">…</span>`);
    }
  }
  pages.push(`<button class="btn btn-sm btn-outline" ${TC.page>=totalPages?'disabled':''} onclick="tc_goto(${TC.page+1})">下一页 ›</button>`);
  pager.innerHTML = left + '<div style="display:flex;gap:4px">' + pages.join('') + '</div>';
}

function tc_goto(p) {
  const totalPages = Math.max(1, Math.ceil(TC.total / TC.size));
  if (p < 1 || p > totalPages || p === TC.page) return;
  TC.page = p;
  tc_refresh();
}

/* === 过滤 === */
function tc_applyFilters() {
  TC.filters.q = ($('tc-q')?.value || '').trim();
  TC.filters.status = ($('tc-status')?.value || 'all');
  TC.filters.type = ($('tc-type')?.value || '');
  TC.page = 1;
  tc_refresh();
}

function tc_resetFilters() {
  TC.filters = { q: '', status: 'all', type: '' };
  TC.page = 1;
  const q = $('tc-q'); if (q) q.value = '';
  const s = $('tc-status'); if (s) s.value = 'all';
  const t = $('tc-type'); if (t) t.value = '';
  tc_refresh();
}

/* === 多选 === */
function tc_toggleOne(token, checked) {
  if (checked) TC.selected.add(token);
  else TC.selected.delete(token);
  tc_updateBatchBar();
  // 同步行的视觉
  const row = document.querySelector(`tr[data-token="${cssEscape(token)}"]`);
  if (row) row.style.background = checked ? 'rgba(74,122,255,0.04)' : '';
}

function tc_toggleAll(checked) {
  if (checked) TC.shares.forEach(s => s.token && TC.selected.add(s.token));
  else TC.selected.clear();
  tc_renderTable();
  tc_updateBatchBar();
}

function tc_clearSelection() {
  TC.selected.clear();
  const ca = $('tc-check-all'); if (ca) ca.checked = false;
  tc_renderTable();
  tc_updateBatchBar();
}

function tc_updateBatchBar() {
  const bar = $('tc-batch-actions');
  const cnt = $('tc-sel-count');
  if (!bar) return;
  const n = TC.selected.size;
  bar.style.display = n > 0 ? 'flex' : 'none';
  if (cnt) cnt.textContent = `已选 ${n} 项`;
  // 同步全选 checkbox 状态
  const ca = $('tc-check-all');
  if (ca) ca.checked = TC.shares.length > 0 && n === TC.shares.length;
}

async function tc_batchRevoke() {
  const tokens = Array.from(TC.selected);
  if (!tokens.length) return;
  if (!confirm(`确认撤销选中的 ${tokens.length} 个分享链接?`)) return;
  let ok = 0, fail = 0;
  showGlobalLoading?.(`撤销中 (0/${tokens.length})`);
  for (let i = 0; i < tokens.length; i++) {
    try {
      const r = await apiDelete('/api/transfer/' + encodeURIComponent(tokens[i]));
      if (r?.success) ok++; else fail++;
    } catch (e) { fail++; }
    showGlobalLoading?.(`撤销中 (${i+1}/${tokens.length})`);
  }
  hideGlobalLoading?.();
  showToast(`批量撤销完成: 成功 ${ok}, 失败 ${fail}`, fail ? 'error' : 'success');
  TC.selected.clear();
  tc_refresh();
}

async function tc_batchDelete() {
  const tokens = Array.from(TC.selected);
  if (!tokens.length) return;
  if (!confirm(`⚠️ 确认永久删除选中的 ${tokens.length} 个分享记录? 此操作不可恢复!`)) return;
  let ok = 0, fail = 0;
  showGlobalLoading?.(`永久删除中 (0/${tokens.length})`);
  for (let i = 0; i < tokens.length; i++) {
    try {
      const r = await apiDelete('/api/transfer/' + encodeURIComponent(tokens[i]) + '/permanent');
      if (r?.success) ok++; else fail++;
    } catch (e) { fail++; }
    showGlobalLoading?.(`永久删除中 (${i+1}/${tokens.length})`);
  }
  hideGlobalLoading?.();
  showToast(`永久删除完成: 成功 ${ok}, 失败 ${fail}`, fail ? 'error' : 'success');
  TC.selected.clear();
  tc_refresh();
}

/* === 创建分享弹窗 === */
function tc_showCreate() {
  const fields = [
    { id: 'resource_path', label: '资源路径', placeholder: '/data/images/photo.jpg 或 /datasets/xxx', type: 'text' },
    {
      id: 'resource_type', label: '资源类型', type: 'select',
      options: ['file', 'directory', 'dataset'],
      value: 'file',
    },
    { id: 'expiry_hours', label: '有效期 (小时)', value: '24', type: 'number' },
    { id: 'max_downloads', label: '最大下载次数 (0=无限制)', value: '0', type: 'number' },
    { id: 'password', label: '访问密码 (可选, 留空=公开)', type: 'text', placeholder: '留空为公开分享' },
    { id: 'note', label: '备注', type: 'textarea', placeholder: '可选, 用于说明此分享用途' },
  ];
  showFormModal('🔗 新建分享链接', fields, {
    label: '创建分享',
    callback: async (d) => {
      const resource_path = (d.resource_path || '').trim();
      if (!resource_path) {
        showToast('资源路径不能为空', 'error');
        return;
      }
      const payload = {
        resource_path,
        resource_type: d.resource_type || 'file',
        expiry_hours: Math.max(1, parseInt(d.expiry_hours, 10) || 24),
        max_downloads: Math.max(0, parseInt(d.max_downloads, 10) || 0),
        password: (d.password || '').trim() || null,
        note: (d.note || '').trim(),
      };
      try {
        const r = await apiPost('/api/transfer/share', payload);
        if (r?.success) {
          const token = r.data?.token || r.data?.share_id || '?';
          const shareUrl = r.data?.share_url || `/api/transfer/${token}`;
          const dl = '<div style="padding:14px">' +
            '<div style="font-size:12px;color:var(--text-secondary);margin-bottom:8px">分享链接已创建, 请妥善保存:</div>' +
            `<input class="form-input" readonly value="${location.origin}${shareUrl}" onclick="this.select();document.execCommand('copy');showToast('链接已复制','success')" style="width:100%;font-family:var(--font-mono,monospace);font-size:11px;padding:6px;background:var(--bg-base)">` +
            `<div style="margin-top:10px;font-size:11px;color:var(--text-muted)">Token: <code>${escapeHTML(token)}</code></div>` +
            '<div style="margin-top:14px;display:flex;gap:6px;justify-content:flex-end">' +
            '<button class="btn btn-outline btn-sm" onclick="this.closest(\'.modal-overlay\').remove()">关闭</button>' +
            '<button class="btn btn-primary btn-sm" onclick="navigator.clipboard.writeText(location.origin+\'' + shareUrl + '\');showToast(\'已复制\',\'success\')">📋 复制链接</button>' +
            '</div></div>';
          showModal('✅ 分享创建成功', dl);
          tc_refresh();
        } else {
          showToast('创建失败: ' + (r?.error || '未知错误'), 'error');
        }
      } catch (e) {
        showToast('创建失败: ' + (e?.message || e), 'error');
      }
    }
  });
}

/* === 详情模态 === */
async function tc_showDetail(token) {
  try {
    const r = await apiGet('/api/transfer/' + encodeURIComponent(token) + '/info');
    if (!r?.success) {
      showToast('加载详情失败: ' + (r?.error || '未知'), 'error');
      return;
    }
    const s = r.data || {};
    const fields = {
      'Token': '<code style="font-family:var(--font-mono,monospace);font-size:11px">' + escapeHTML(s.token || '') + '</code>',
      '资源路径': escapeHTML(s.resource_path || '—'),
      '资源类型': '<span class="tag tag-blue" style="font-size:10px">' + escapeHTML(s.resource_type || 'file') + '</span>',
      '创建者': escapeHTML(s.creator || '—'),
      '创建时间': escapeHTML(tc_formatTs(s.created_at)),
      '过期时间': escapeHTML(tc_formatTs(s.expires_at)) + (tc_isExpired(s) ? ' <span class="tag tag-orange" style="font-size:10px">⏰ 已过期</span>' : ''),
      '下载次数': (s.downloads_used || 0) + (s.max_downloads ? ' / ' + s.max_downloads : ' / 无限制'),
      '密码保护': s.has_password
        ? '<span class="tag tag-orange" style="font-size:10px">🔒 已设置</span>'
        : '<span class="tag tag-green" style="font-size:10px">🔓 公开</span>',
      '状态': s.is_active
        ? '<span class="tag tag-green" style="font-size:10px">🟢 活跃</span>'
        : '<span class="tag tag-red" style="font-size:10px">🚫 已撤销</span>',
      '备注': escapeHTML(s.note || '—'),
    };
    showDetailModal('🔗 分享详情', fields);
  } catch (e) {
    showToast('加载详情失败: ' + (e?.message || e), 'error');
  }
}

/* === 复制链接 / 撤销 / 删除 === */
async function tc_copyLink(token) {
  const share = TC.shares.find(s => s.token === token);
  if (!share) {
    showToast('找不到该分享', 'error');
    return;
  }
  // 尝试拿 sig 构造完整签名 URL
  let url = `${location.origin}/api/transfer/${token}`;
  try {
    const r = await apiGet('/api/transfer/' + encodeURIComponent(token) + '/info');
    const exp = r?.data?.expires_at;
    // 后端 /share 返回的 share_url 含 sig + exp, 但 /info 不返回 sig
    // 这里给个简化版本, 用户访问时无 sig 也能获取 (后端允许空 sig 走默认)
    if (exp) {
      const expTs = Math.floor(new Date(exp).getTime() / 1000);
      url += `?exp=${expTs}`;
    }
  } catch (e) { /* 静默, 用基础 URL */ }
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(url).then(
      () => showToast('链接已复制到剪贴板', 'success'),
      () => fallbackCopy(url)
    );
  } else {
    fallbackCopy(url);
  }
}

function tc_revoke(token) {
  if (!confirm(`确认撤销分享 ${token}? 链接将立即失效`)) return;
  apiDelete('/api/transfer/' + encodeURIComponent(token))
    .then(r => {
      if (r?.success) {
        showToast('已撤销', 'success');
        TC.selected.delete(token);
        tc_refresh();
      } else {
        showToast('撤销失败: ' + (r?.error || '未知'), 'error');
      }
    })
    .catch(e => showToast('撤销失败: ' + (e?.message || e), 'error'));
}

function tc_permanentDelete(token) {
  if (!confirm(`⚠️ 确认永久删除分享 ${token}? 此操作不可恢复`)) return;
  apiDelete('/api/transfer/' + encodeURIComponent(token) + '/permanent')
    .then(r => {
      if (r?.success) {
        showToast('已永久删除', 'success');
        TC.selected.delete(token);
        tc_refresh();
      } else {
        showToast('删除失败: ' + (r?.error || '未知'), 'error');
      }
    })
    .catch(e => showToast('删除失败: ' + (e?.message || e), 'error'));
}

async function tc_cleanup() {
  if (!confirm('确认清理所有已过期的分享记录?')) return;
  try {
    const r = await apiPost('/api/transfer/cleanup', {});
    if (r?.success) {
      showToast('清理完成: ' + (r.data?.cleaned || 0) + ' 条', 'success');
      tc_refresh();
    } else {
      showToast('清理失败: ' + (r?.error || '未知'), 'error');
    }
  } catch (e) {
    showToast('清理失败: ' + (e?.message || e), 'error');
  }
}

/* === 轮询 === */
function tc_startPolling() {
  tc_stopPolling();
  TC.polling = setInterval(() => {
    if (document.visibilityState === 'visible' && !TC.loading && !TC.showCreate && !TC.detailToken) {
      tc_refresh();
    }
  }, 5000);
}

function tc_stopPolling() {
  if (TC.polling) { clearInterval(TC.polling); TC.polling = null; }
}

/* === 工具 === */
function tc_formatTs(ts) {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return String(ts);
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch (e) { return String(ts); }
}

function cssEscape(s) {
  if (window.CSS && CSS.escape) return CSS.escape(s);
  return String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
}

function escapeHTML(s) { return sanitizeHTML(s); }
function escapeAttr(s) { return String(s == null ? '' : s).replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

function fallbackCopy(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); showToast('已复制', 'success'); }
  catch (e) { showToast('复制失败', 'error'); }
  document.body.removeChild(ta);
}

window.addEventListener('beforeunload', () => {
  tc_stopPolling();
});
document.addEventListener('visibilitychange', () => {
  // 显示时立即刷一次 (用户切回标签)
  if (document.visibilityState === 'visible' && document.getElementById('tc-table')) {
    tc_refresh();
  }
});
