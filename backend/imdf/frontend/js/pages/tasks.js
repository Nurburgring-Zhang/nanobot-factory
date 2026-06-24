/* IMDF v3 — tasks.js
   P1-C-W2: 5-page API integration. Tasks page uses /api/tasks/* (new endpoints).

   Re-implements the tasks page with the new contract. Loaded AFTER business.js
   in index.html so this version of renderTasks/loadTasks overrides the older
   one inside business.js (which still uses /api/requirements/*).

   Endpoints integrated (≥3):
     - GET  /api/tasks?page=&status=&assignee=     (list)
     - POST /api/tasks                             (create)
     - POST /api/tasks/{id}/assign                 (assign)
     - POST /api/tasks/{id}/submit                 (submit)
     - POST /api/tasks/{id}/review                 (review)
     - POST /api/tasks/{id}/reject                 (reject)
     - GET  /api/tasks/{id}/history                (history)
*/

(function () {
  'use strict';

  const T = {
    page: 1,
    pageSize: 20,
    status: '',
    assignee: '',
    loading: false,
    cache: { items: [], total: 0 },
  };

  const STATUS_LABEL = {
    draft:     '草稿',
    open:      '待领取',
    assigned:  '已分配',
    in_progress:'进行中',
    submitted: '已提交',
    review:    '审核中',
    done:      '已完成',
    rejected:  '已拒绝',
    closed:    '已关闭',
  };
  const PRIORITY_COLOR = {
    P0: 'var(--accent-red)',    P1: 'var(--accent-orange)',
    P2: 'var(--accent-blue)',   P3: 'var(--text-muted)',
  };

  async function renderTasks() {
    const c = document.getElementById('page-content'); if (!c) return;
    c.innerHTML = `
      <div style="margin-bottom:16px">
        <h2 style="font-size:18px;font-weight:600;margin-bottom:4px">📋 任务管理</h2>
        <p style="font-size:12px;color:var(--text-muted)">管理所有数据生产任务，分配人员，追踪进度</p>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
        <button class="tb-pri" data-need="task.create" onclick="TASKS_showCreate()"
                style="background:var(--accent-blue)">➕ 新建任务</button>
        <select data-need="task.read" onchange="TASKS_setStatus(this.value)"
                style="padding:6px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
          <option value="">全部状态</option>
          ${Object.keys(STATUS_LABEL).map(k => `<option value="${k}">${STATUS_LABEL[k]}</option>`).join('')}
        </select>
        <input data-need="task.read" placeholder="按 assignee 过滤 (user_id)"
               onchange="TASKS_setAssignee(this.value)"
               style="padding:6px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)"/>
        <button data-need="task.read" onclick="TASKS_reload()" style="padding:6px 12px;background:var(--bg-card);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);cursor:pointer">🔄 刷新</button>
        <span style="flex:1"></span>
        <span style="font-size:12px;color:var(--text-muted)">📊 共 <strong id="taskTotal">0</strong> 条</span>
      </div>
      <div id="taskTableWrap" style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;overflow:hidden">
        <div id="taskLoading" style="padding:40px;text-align:center;color:var(--text-muted)">⏳ 加载中…</div>
        <table class="data-table" style="display:none">
          <thead><tr>
            <th style="width:90px">ID</th><th>任务名称</th><th style="width:80px">类型</th>
            <th style="width:60px">优先级</th><th style="width:60px">进度</th>
            <th style="width:90px">状态</th><th style="width:90px">负责人</th>
            <th style="width:240px">操作</th>
          </tr></thead>
          <tbody id="taskTableBody"></tbody>
        </table>
      </div>
      <div id="taskPager" style="display:flex;gap:6px;justify-content:center;margin-top:12px"></div>
    `;
    if (window.IMDF_ERROR && window.IMDF_ERROR.applyRbac) {
      window.IMDF_ERROR.applyRbac(c, { '[data-need="task.create"]': 'task.create',
                                      '[data-need="task.read"]':   'task.read' });
    }
    TASKS_reload();
  }

  function TASKS_setStatus(v) { T.status = v; T.page = 1; TASKS_reload(); }
  function TASKS_setAssignee(v) { T.assignee = v; T.page = 1; TASKS_reload(); }
  function TASKS_reload() { loadTasks(T.page); }

  async function loadTasks(page) {
    if (T.loading) return;
    T.loading = true;
    T.page = page || T.page || 1;
    const wrap = document.getElementById('taskTableWrap');
    const loadingEl = document.getElementById('taskLoading');
    const tbl = wrap ? wrap.querySelector('table') : null;
    if (loadingEl) loadingEl.style.display = '';
    if (tbl) tbl.style.display = 'none';

    const path = '/api/tasks' + window.IMDF_ERROR.qs({
      page: T.page, page_size: T.pageSize, status: T.status, assignee: T.assignee,
    });

    const res = await window.httpGet(path, { timeoutMs: 20000 });
    T.loading = false;
    if (res.state !== window.HTTP_STATE.SUCCESS) {
      if (loadingEl) loadingEl.innerHTML = '❌ ' + window.IMDF_ERROR.describe(res.error, '加载失败');
      if (window.IMDF_ERROR.onApiError) window.IMDF_ERROR.onApiError('tasks.list', res.error);
      return;
    }

    const { items, total, pages } = window.IMDF_ERROR.extractList(res.data);
    T.cache.items = items; T.cache.total = total;
    const totalEl = document.getElementById('taskTotal');
    if (totalEl) totalEl.textContent = String(total);
    if (loadingEl) loadingEl.style.display = 'none';
    if (tbl) tbl.style.display = '';

    const tb = document.getElementById('taskTableBody');
    if (!tb) return;
    if (items.length === 0) {
      tb.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:var(--text-muted)">📭 暂无任务</td></tr>';
    } else {
      tb.innerHTML = items.map(r => `
        <tr>
          <td style="color:var(--text-muted);font-size:11px">${escapeHtml((r.id||'').slice(0,12))}</td>
          <td><strong>${escapeHtml(r.title||r.name||'未命名')}</strong></td>
          <td>${escapeHtml(r.type||'annotation')}</td>
          <td style="color:${PRIORITY_COLOR[r.priority]||'var(--text-muted)'}">${escapeHtml(r.priority||'P2')}</td>
          <td>${r.progress||0}%</td>
          <td><span class="task-status ${(r.status||'open').toLowerCase()}">${escapeHtml(STATUS_LABEL[r.status]||r.status||'待领取')}</span></td>
          <td style="color:var(--text-muted)">${escapeHtml(r.assignee||r.assignee_id||'--')}</td>
          <td>
            <button class="tb-btn" onclick="TASKS_showDetail('${escAttr(r.id||'')}')">详情</button>
            <button class="tb-btn" data-need="task.assign" onclick="TASKS_assign('${escAttr(r.id||'')}')">分配</button>
            <button class="tb-btn" data-need="task.submit" onclick="TASKS_submit('${escAttr(r.id||'')}')">提交</button>
            <button class="tb-btn" data-need="task.review" onclick="TASKS_review('${escAttr(r.id||'')}')">通过</button>
            <button class="tb-btn" data-need="task.reject" onclick="TASKS_reject('${escAttr(r.id||'')}')">拒绝</button>
          </td>
        </tr>`).join('');
    }

    renderPager(pages);
    if (window.IMDF_ERROR) window.IMDF_ERROR.applyRbac(document.getElementById('page-content'), {
      '[data-need="task.assign"]': 'task.assign',
      '[data-need="task.submit"]': 'task.submit',
      '[data-need="task.review"]': 'task.review',
      '[data-need="task.reject"]': 'task.reject',
    });
  }

  function renderPager(pages) {
    const el = document.getElementById('taskPager'); if (!el) return;
    const cur = T.page, total = pages || 1;
    let html = `<button onclick="TASKS_reload_page(${cur-1})" ${cur<=1?'disabled':''}>‹</button>`;
    for (let i = 1; i <= total; i++) {
      if (i === 1 || i === total || (i >= cur-2 && i <= cur+2)) {
        html += `<button class="${i===cur?'active':''}" onclick="TASKS_reload_page(${i})">${i}</button>`;
      } else if (i === cur-3 || i === cur+3) {
        html += `<span style="padding:6px 4px">…</span>`;
      }
    }
    html += `<button onclick="TASKS_reload_page(${cur+1})" ${cur>=total?'disabled':''}>›</button>`;
    el.innerHTML = html;
  }
  function TASKS_reload_page(p) { if (p < 1) return; T.page = p; loadTasks(p); }

  /* --------------- Mutations --------------- */
  function TASKS_showCreate() {
    if (typeof showModal === 'function') showModal(`
      <span class="modal-close" onclick="closeModal()">✕</span>
      <h4 style="margin-bottom:16px;color:var(--accent-blue)">📋 新建任务</h4>
      <div style="display:grid;gap:10px">
        <input id="reqTitle" placeholder="任务名称" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)"/>
        <select id="reqType" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
          <option value="annotation">数据标注</option>
          <option value="collection">数据采集</option>
          <option value="cleaning">数据清洗</option>
          <option value="review">质量审核</option>
        </select>
        <select id="reqPriority" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
          <option value="P0">P0 - 紧急</option><option value="P1">P1 - 高</option>
          <option value="P2" selected>P2 - 中</option><option value="P3">P3 - 低</option>
        </select>
        <textarea id="reqDesc" placeholder="任务描述" rows="3" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)"></textarea>
        <button style="padding:10px;background:var(--accent-blue);border:none;border-radius:6px;color:#fff;cursor:pointer" onclick="TASKS_create()">创建</button>
      </div>
    `);
  }

  async function TASKS_create() {
    const body = {
      title:    document.getElementById('reqTitle')?.value || '新任务',
      type:     document.getElementById('reqType')?.value || 'annotation',
      priority: document.getElementById('reqPriority')?.value || 'P2',
      description: document.getElementById('reqDesc')?.value || '',
    };
    const res = await window.httpPost('/api/tasks', body);
    if (res.state !== window.HTTP_STATE.SUCCESS) {
      window.IMDF_ERROR.onApiError('tasks.create', res.error);
      return;
    }
    window.toastOk && window.toastOk('✅ 任务创建成功');
    if (typeof closeModal === 'function') closeModal();
    TASKS_reload();
  }

  async function TASKS_assign(id) {
    const assignee = prompt('分配给 (user_id):', '');
    if (!assignee) return;
    const res = await window.httpPost('/api/tasks/' + encodeURIComponent(id) + '/assign', { assignee: assignee });
    if (res.state !== window.HTTP_STATE.SUCCESS) window.IMDF_ERROR.onApiError('tasks.assign', res.error);
    else { window.toastOk && window.toastOk('✅ 已分配'); TASKS_reload(); }
  }
  async function TASKS_submit(id) {
    if (!confirm('确认提交任务 ' + id + ' ?')) return;
    const res = await window.httpPost('/api/tasks/' + encodeURIComponent(id) + '/submit', { id: id });
    if (res.state !== window.HTTP_STATE.SUCCESS) window.IMDF_ERROR.onApiError('tasks.submit', res.error);
    else { window.toastOk && window.toastOk('✅ 已提交'); TASKS_reload(); }
  }
  async function TASKS_review(id) {
    const note = prompt('审核意见 (可选):', '') || '';
    const res = await window.httpPost('/api/tasks/' + encodeURIComponent(id) + '/review', { id: id, decision: 'approve', note: note });
    if (res.state !== window.HTTP_STATE.SUCCESS) window.IMDF_ERROR.onApiError('tasks.review', res.error);
    else { window.toastOk && window.toastOk('✅ 已通过'); TASKS_reload(); }
  }
  async function TASKS_reject(id) {
    const note = prompt('拒绝原因:', '');
    if (!note) return;
    const res = await window.httpPost('/api/tasks/' + encodeURIComponent(id) + '/reject', { id: id, decision: 'reject', note: note });
    if (res.state !== window.HTTP_STATE.SUCCESS) window.IMDF_ERROR.onApiError('tasks.reject', res.error);
    else { window.toastOk && window.toastOk('✅ 已拒绝'); TASKS_reload(); }
  }

  async function TASKS_showDetail(id) {
    if (!id) return;
    const [detailRes, histRes] = await Promise.all([
      window.httpGet('/api/tasks/' + encodeURIComponent(id), { timeoutMs: 15000 }),
      window.httpGet('/api/tasks/' + encodeURIComponent(id) + '/history', { timeoutMs: 15000 }),
    ]);

    let body;
    if (detailRes.state === window.HTTP_STATE.SUCCESS) {
      const d = detailRes.data && detailRes.data.data ? detailRes.data.data : detailRes.data;
      body = `
        <p><strong>ID:</strong> ${escHtml(d.id||id)}</p>
        <p><strong>名称:</strong> ${escHtml(d.title||d.name||'--')}</p>
        <p><strong>类型:</strong> ${escHtml(d.type||'--')}</p>
        <p><strong>优先级:</strong> ${escHtml(d.priority||'--')}</p>
        <p><strong>状态:</strong> ${escHtml(STATUS_LABEL[d.status]||d.status||'--')}</p>
        <p><strong>负责人:</strong> ${escHtml(d.assignee||d.assignee_id||'--')}</p>
        <p><strong>创建人:</strong> ${escHtml(d.created_by||'--')}</p>
        <p><strong>描述:</strong> ${escHtml(d.description||'暂无')}</p>
      `;
    } else {
      body = `<p style="color:var(--accent-red)">❌ 详情加载失败: ${window.IMDF_ERROR.describe(detailRes.error)}</p>`;
      window.IMDF_ERROR.onApiError('tasks.detail', detailRes.error);
    }

    let histBlock = '';
    if (histRes.state === window.HTTP_STATE.SUCCESS) {
      const ev = window.IMDF_ERROR.extractList(histRes.data).items;
      histBlock = `
        <h5 style="margin:14px 0 8px;color:var(--accent-blue)">📜 历史 (${ev.length})</h5>
        ${ev.length === 0 ? '<p style="color:var(--text-muted);font-size:12px">无</p>' :
          '<div style="max-height:180px;overflow:auto;border:1px solid var(--border);border-radius:4px;padding:8px">' +
          ev.slice(0, 30).map(e => `<div style="font-size:12px;line-height:1.7">
              <span style="color:var(--text-muted)">${escHtml(e.at||e.created_at||'')}</span>
              <strong>${escHtml(e.action||e.event||'')}</strong>
              ${e.user ? '· <span style="color:var(--text-muted)">'+escHtml(e.user)+'</span>' : ''}
              ${e.note ? '<div style="color:var(--text-muted);margin-left:12px">'+escHtml(e.note)+'</div>' : ''}
            </div>`).join('') + '</div>'}
      `;
    } else {
      histBlock = `<p style="color:var(--text-muted);font-size:12px;margin-top:8px">历史不可用: ${window.IMDF_ERROR.describe(histRes.error)}</p>`;
    }

    if (typeof showModal === 'function') showModal(`
      <span class="modal-close" onclick="closeModal()">✕</span>
      <h4 style="margin-bottom:12px;color:var(--accent-blue)">📋 任务详情</h4>
      <div style="color:var(--text-muted);font-size:12px;line-height:1.9">${body}</div>
      ${histBlock}
    `);
  }

  /* ---------------- utils ---------------- */
  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function escAttr(s) { return escapeHtml(s).replace(/`/g, '&#96;'); }

  /* ---------------- Export ---------------- */
  /* Override the legacy global functions from business.js */
  globalThis.renderTasks = renderTasks;
  globalThis.loadTasks   = loadTasks;
  globalThis.TASKS = {
    reload: TASKS_reload, reload_page: TASKS_reload_page,
    setStatus: TASKS_setStatus, setAssignee: TASKS_setAssignee,
    showCreate: TASKS_showCreate, create: TASKS_create,
    assign: TASKS_assign, submit: TASKS_submit,
    review: TASKS_review, reject: TASKS_reject,
    showDetail: TASKS_showDetail,
  };
})();