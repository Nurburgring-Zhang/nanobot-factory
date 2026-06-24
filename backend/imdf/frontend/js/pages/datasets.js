/* IMDF v4 数据集管理 — 统一页面规范 */
/* 头部: 标题+统计+按钮 | 工具栏: 搜索+筛选+排序 | 表格/网格双视图 | 空状态 | 分页 */

let DS = { page:1, total:0, pages:1, sort:'created_at', order:'desc', search:'', type:'', view:'table', data:[], selected:new Set() };

async function renderDatasets() {
  const c = $('page-content'); if (!c) return;
  c.innerHTML = `
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <div class="page-title">数据集管理</div>
        <div class="page-stats" style="margin-top:4px">
          <div class="page-stat"><div class="page-stat-val" id="dsTotal">0</div><div class="page-stat-label">总数</div></div>
          <div class="page-stat"><div class="page-stat-val" id="dsTodayNew">0</div><div class="page-stat-label">今日新增</div></div>
          <div class="page-stat"><div class="page-stat-val" id="dsTotalSize">0</div><div class="page-stat-label">总大小</div></div>
        </div>
      </div>
      <div class="page-actions">
        <button class="btn btn-outline btn-sm" onclick="showImportModal()">导入</button>
        <button class="btn btn-primary" onclick="showCreateDataset()">+ 新建数据集</button>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <input id="dsSearch" placeholder="搜索数据集名称..." onkeydown="if(event.key==='Enter')loadDatasets(1)">
        <select id="dsTypeFilter" onchange="DS.type=this.value;loadDatasets(1)">
          <option value="">全部类型</option>
          <option value="image">图片</option><option value="video">视频</option>
          <option value="text">文本</option><option value="audio">音频</option>
          <option value="3d">3D</option>
        </select>
        <select id="dsSort" onchange="const v=this.value;DS.sort=v.replace('-','');DS.order=v.startsWith('-')?'desc':'asc';loadDatasets(1)">
          <option value="-created_at">最新优先</option>
          <option value="created_at">最早优先</option>
          <option value="name">名称A-Z</option>
          <option value="-name">名称Z-A</option>
          <option value="-size">大小递减</option>
        </select>
      </div>
      <div class="toolbar-right">
        <div class="view-toggle" id="dsViewToggle">
          <button class="active" onclick="switchDsView('table')">表格</button>
          <button onclick="switchDsView('grid')">网格</button>
        </div>
        <button class="btn btn-outline btn-sm" onclick="showImportModal()">导入</button>
      </div>
    </div>

    <!-- 表格视图 -->
    <div id="dsTableView" class="view-container">
      <div class="view-container-table">
        <table class="data-table">
          <thead><tr>
            <th style="width:30px"><input type="checkbox" id="selectAll" onchange="toggleSelectAll()"></th>
            <th class="sortable" onclick="sortDS('name')">名称</th>
            <th class="sortable" onclick="sortDS('type')" style="width:70px">类型</th>
            <th class="sortable" onclick="sortDS('size')" style="width:80px">大小</th>
            <th class="sortable" onclick="sortDS('status')" style="width:70px">状态</th>
            <th class="sortable" onclick="sortDS('created_at')" style="width:100px">创建时间</th>
            <th style="width:100px">操作</th>
          </tr></thead>
          <tbody id="dsTableBody"><tr><td colspan="7"><div class="empty-state"><span>加载中...</span></div></td></tr></tbody>
        </table>
      </div>
    </div>

    <!-- 网格视图 -->
    <div id="dsGridView" class="view-container" style="display:none">
      <div class="view-container-grid" id="dsGridContainer">
        <div class="empty-state" style="grid-column:1/-1"><span>加载中...</span></div>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pagination" id="dsPager"></div>
  `;
  await loadDatasets(1);
}

async function loadDatasets(page) {
  DS.page = page;
  DS.search = $('dsSearch')?.value?.trim() || '';
  DS.type = $('dsTypeFilter')?.value || '';
  const sortParam = DS.order === 'desc' ? '-' + DS.sort : DS.sort;
  let url = `/api/datasets?page=${page}&size=20&search=${encodeURIComponent(DS.search)}&sort=${sortParam}`;
  if (DS.type) url += `&type=${encodeURIComponent(DS.type)}`;

  /* P1-C-W2: three-state GET /api/datasets via client.js */
  const res = await window.httpGet(url, { timeoutMs: 20000 });
  if (res.state !== window.HTTP_STATE.SUCCESS) {
    window.IMDF_ERROR.onApiError('datasets.list', res.error);
    if (typeof showToast === 'function') showToast('❌ 加载失败: ' + window.IMDF_ERROR.describe(res.error), 'error');
    DS.data = []; DS.total = 0; DS.pages = 1;
    renderTable(); renderGrid(); renderPager();
    return;
  }
  const result = res.data || {};
  const items = result.items || [];
  DS.total = result.total || items.length;
  DS.pages = result.pages || Math.max(1, Math.ceil(DS.total / 20));
  // R4-Worker-3: 移除 Math.random() fallback — 保留后端 size, 缺则显示 "—"
  DS.data = items.map(item => {
    if (!item.tags) item.tags = [];
    // 不再注入随机 size; item.size 缺省保持 undefined → 表格列显示 "—"
    return item;
  });

  // 更新统计
  const tEl = $('dsTotal'); if (tEl) tEl.textContent = DS.total;
  // R4-Worker-3: 移除 Math.random()*12 → 后端缺今日新增时显示 "—"
  const nEl = $('dsTodayNew');
  if (nEl) nEl.textContent = (typeof result.today_new === 'number') ? result.today_new : '—';
  const totalSize = DS.data.reduce((s, d) => s + (d.size || 0), 0);
  const sEl = $('dsTotalSize');
  if (sEl) sEl.textContent = totalSize > 0 ? formatSize(totalSize) : '—';

  renderTable();
  renderGrid();
  renderPager();
}

function renderTable() {
  const tbody = $('dsTableBody'); if (!tbody) return;
  if (DS.data.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state"><div class="empty-state-icon">📁</div><div class="empty-state-text">暂无数据集</div><div class="empty-state-hint">点击\"新建数据集\"或\"导入\"来添加数据</div></div></td></tr>`;
    return;
  }
  tbody.innerHTML = DS.data.map(item => {
    const id = item.id || item.name || '';
    const checked = DS.selected.has(id) ? 'checked' : '';
    const statusMap = { active:'tag-green', pending:'tag-orange', done:'tag-green', completed:'tag-green', error:'tag-red' };
    const statusCls = statusMap[item.status] || 'tag-blue';
    const statusLabel = item.status || 'active';
    // R4-Worker-3: 无 size 时显示 "—" (保留 fallback 但不再注入随机数)
    const sizeStr = (typeof item.size === 'number' && item.size > 0) ? formatSize(item.size) : '—';
    return `<tr>
      <td><input type="checkbox" ${checked} onchange="toggleSelect('${id}')"></td>
      <td><strong>${sanitizeHTML(item.name || id)}</strong></td>
      <td><span class="tag tag-blue">${item.type || 'image'}</span></td>
      <td>${sizeStr}</td>
      <td><span class="tag ${statusCls}">${statusLabel}</span></td>
      <td style="color:var(--text-muted);font-size:11px">${item.created_at ? item.created_at.slice(0,10) : '--'}</td>
      <td>
        <button class="btn btn-sm btn-outline" onclick="previewDataset('${id}')" title="预览" style="padding:2px 6px">👁</button>
        <button class="btn btn-sm btn-outline" onclick="exportDataset('${id}')" title="导出" style="padding:2px 6px">📤</button>
        <button class="btn btn-sm btn-outline" onclick="deleteDataset('${id}')" title="删除" style="padding:2px 6px;color:var(--red)">🗑</button>
      </td>
    </tr>`;
  }).join('');
}

function renderGrid() {
  const container = $('dsGridContainer'); if (!container) return;
  if (DS.data.length === 0) {
    container.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><div class="empty-state-icon">📁</div><div class="empty-state-text">暂无数据集</div><div class="empty-state-hint">点击\"新建数据集\"或\"导入\"来添加数据</div></div>`;
    return;
  }
  const icons = { image:'🖼️', video:'🎬', audio:'🎵', text:'📝', '3d':'🧊' };
  const colors = { image:'#1a2a4a', video:'#1a1a3a', audio:'#2a1a3a', text:'#1a2a2a', '3d':'#2a2a1a' };
  container.innerHTML = DS.data.map(item => {
    const id = item.id || item.name || '';
    const checked = DS.selected.has(id) ? 'selected' : '';
    const icon = icons[item.type] || '📄';
    const bg = colors[item.type] || colors.image;
    return `<div class="card" style="padding:0;overflow:hidden;cursor:pointer;${checked?'border-color:var(--blue);box-shadow:0 0 0 1px rgba(74,122,255,0.3)':''}" onclick="toggleSelect('${id}');renderGrid();renderTable()">
      <div class="card-grid-thumb" style="background:${bg}">${icon}</div>
      <div class="card-grid-info">
        <div class="card-grid-name">${sanitizeHTML(item.name || id)}</div>
        <div class="card-grid-meta">
          <span class="tag tag-blue">${item.type || 'image'}</span>
          <span>${(typeof item.size === 'number' && item.size > 0) ? formatSize(item.size) : '—'}</span>
        </div>
        <div style="margin-top:4px;font-size:10px;color:var(--text-muted)">
          <span class="tag tag-green">${item.status || 'active'}</span>
          ${item.created_at ? ' · '+item.created_at.slice(0,10) : ''}
        </div>
      </div>
    </div>`;
  }).join('');
}

function renderPager() {
  const pager = $('dsPager'); if (!pager) return;
  if (DS.pages <= 1) { pager.innerHTML = ''; return; }
  let html = `<button onclick="loadDatasets(${DS.page-1})" ${DS.page<=1?'disabled':''}>‹</button>`;
  for (let i=1;i<=DS.pages;i++) {
    if (i===1||i===DS.pages||Math.abs(i-DS.page)<=2)
      html += `<button class="${i===DS.page?'active':''}" onclick="loadDatasets(${i})">${i}</button>`;
    else if (i===2||i===DS.pages-1) html += '<span style="color:var(--text-muted)">...</span>';
  }
  html += `<button onclick="loadDatasets(${DS.page+1})" ${DS.page>=DS.pages?'disabled':''}>›</button>`;
  pager.innerHTML = html;
}

function switchDsView(mode) {
  DS.view = mode;
  const toggle = $('dsViewToggle');
  if (toggle) toggle.querySelectorAll('button').forEach((b,i) => b.classList.toggle('active', (i===0&&mode==='table')||(i===1&&mode==='grid')));
  const tv = $('dsTableView'); const gv = $('dsGridView');
  if (tv) tv.style.display = mode === 'table' ? '' : 'none';
  if (gv) gv.style.display = mode === 'grid' ? '' : 'none';
  if (mode === 'grid') renderGrid();
}

function sortDS(col) {
  if (DS.sort===col) DS.order = DS.order==='desc'?'asc':'desc';
  else { DS.sort=col; DS.order='desc'; }
  loadDatasets(1);
}

function toggleSelect(id) {
  if (DS.selected.has(id)) DS.selected.delete(id); else DS.selected.add(id);
  renderTable();
}
function toggleSelectAll() { const c=$('selectAll')?.checked; if(c) DS.data.forEach(d=>DS.selected.add(d.id||d.name)); else DS.selected.clear(); renderTable(); }

function previewDataset(id) {
  /* P1-C-W2: GET /api/datasets/{id}/preview via client.js */
  window.httpGet('/api/datasets/' + encodeURIComponent(id) + '/preview', { timeoutMs: 15000 }).then(res => {
    if (res.state !== window.HTTP_STATE.SUCCESS) {
      window.IMDF_ERROR.onApiError('datasets.preview', res.error);
      if (typeof showToast === 'function') showToast('❌ 预览失败: ' + window.IMDF_ERROR.describe(res.error), 'error');
      return;
    }
    const data = res.data || {};
    const items = (data.items||[]).slice(0,10);
    const html = items.map((it,i) => `<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:12px"><span style="color:var(--text-muted)">#${i+1}</span> ${it.name||it.id||'样本'}</div>`).join('');
    showModal(`<span class="modal-close" onclick="closeModal()">✕</span><h4 style="margin-bottom:12px">📁 ${sanitizeHTML(id)} — 预览</h4>${items.length?html:'<p style="color:var(--text-muted)">暂无数据</p>'}<p style="margin-top:8px;font-size:11px;color:var(--text-muted)">共 ${items.length} 条</p>`);
  });
}

function exportDataset(id) {
  showModal(`<span class="modal-close" onclick="closeModal()">✕</span><h4 style="margin-bottom:16px">📤 导出: ${sanitizeHTML(id)}</h4>
    <div style="display:grid;gap:8px">
      <button class="btn btn-outline" onclick="doExport('${id}','json')">JSON 格式</button>
      <button class="btn btn-outline" onclick="doExport('${id}','csv')">CSV 格式</button>
      <button class="btn btn-outline" onclick="doExport('${id}','coco')">COCO 格式</button>
    </div>`);
}
/* P1-C-W2: POST /api/datasets/{id}/export per task spec (was /api/v1/export). */
function doExport(id,fmt) {
  window.httpPost('/api/datasets/' + encodeURIComponent(id) + '/export', { format: fmt, dataset_id: id }, { timeoutMs: 60000 }).then(res => {
    if (typeof closeModal === 'function') closeModal();
    if (res.state !== window.HTTP_STATE.SUCCESS) {
      window.IMDF_ERROR.onApiError('datasets.export', res.error);
      showModal(`<span class="modal-close" onclick="closeModal()">✕</span><h4 style="color:var(--accent-red)">❌ 导出失败: ${window.IMDF_ERROR.describe(res.error)}</h4>`);
      return;
    }
    const d = res.data || {};
    showModal(`<span class="modal-close" onclick="closeModal()">✕</span><h4 style="color:var(--accent-green)">✅ ${d.success ? '导出成功' : '导出请求已提交'}</h4>
      ${d.url ? '<p style="font-size:12px;color:var(--text-muted);margin-top:6px">下载链接: <a href="'+d.url+'" target="_blank" style="color:var(--accent-blue)">'+d.url+'</a></p>' : ''}
      ${d.task_id ? '<p style="font-size:12px;color:var(--text-muted);margin-top:6px">任务 ID: '+d.task_id+'</p>' : ''}`);
  });
}

/* P1-C-W2: DELETE /api/datasets/{id} per task spec (was POST /api/v1/batch/delete). */
function deleteDataset(id) {
  if(!confirm(`确认删除数据集 ${id}？`)) return;
  window.httpDelete('/api/datasets/' + encodeURIComponent(id), { timeoutMs: 15000 }).then(res => {
    if (res.state !== window.HTTP_STATE.SUCCESS) {
      window.IMDF_ERROR.onApiError('datasets.delete', res.error);
      if (typeof showToast === 'function') showToast('❌ 删除失败: ' + window.IMDF_ERROR.describe(res.error), 'error');
      return;
    }
    if (typeof showToast === 'function') showToast('✅ 已删除: ' + id, 'success');
    loadDatasets(DS.page);
  });
}

function showImportModal() {
  showModal(`<span class="modal-close" onclick="closeModal()">✕</span><h4 style="margin-bottom:16px">📥 导入数据</h4>
    <div class="form-field"><label class="form-label">导入格式</label><select id="importFormat" class="form-select"><option value="csv">CSV</option><option value="json">JSON</option><option value="excel">Excel</option></select></div>
    <div class="form-field"><label class="form-label">文件路径</label><input id="importPath" class="form-input" placeholder="/path/to/file.csv"></div>
    <div class="form-actions"><button class="btn btn-primary" onclick="doImport()">导入</button></div>`);
}
function doImport() {
  // R4-Worker-3: 导入模态 callback 接真实 API (POST /api/datasets/import)
  const path=$('importPath')?.value, fmt=$('importFormat')?.value||'csv';
  if(!path){ if (typeof showToast==='function') showToast('请输入文件路径', 'warning'); return; }
  // 目标数据集名沿用 path 的 basename (去掉后缀)
  const name = path.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '') || 'imported';
  /* P1-C-W2: three-state POST /api/datasets/import via client.js */
  window.httpPost('/api/datasets/import', { name, format: fmt, source: path, options: 'append' }, { timeoutMs: 60000 }).then(res => {
    if (typeof closeModal === 'function') closeModal();
    if (res.state !== window.HTTP_STATE.SUCCESS) {
      window.IMDF_ERROR.onApiError('datasets.import', res.error);
      if (typeof showToast==='function') showToast('❌ 导入失败: '+window.IMDF_ERROR.describe(res.error), 'error');
      return;
    }
    const d = res.data || {};
    if(d && d.success){
      loadDatasets(1);
      if (typeof showToast==='function') showToast('✅ 导入任务已提交', 'success');
    } else {
      if (typeof showToast==='function') showToast('导入失败: '+(d.error||'未知错误'), 'error');
    }
  });
}

function showCreateDataset() {
  // R4-Worker-3: 死按钮接真实 POST — 由 submitCreateDataset 处理提交
  showModal(`<span class="modal-close" onclick="closeModal()">✕</span><h4 style="margin-bottom:16px">➕ 新建数据集</h4>
    <div class="form-field"><label class="form-label">数据集名称</label><input id="newDsName" class="form-input" placeholder="输入名称"></div>
    <div class="form-field"><label class="form-label">类型</label><select id="newDsType" class="form-select"><option value="image">图片</option><option value="video">视频</option><option value="text">文本</option><option value="audio">音频</option><option value="3d">3D</option></select></div>
    <div class="form-field"><label class="form-label">描述(可选)</label><textarea id="newDsDesc" class="form-input" placeholder="用途与说明"></textarea></div>
    <div class="form-field"><label class="form-label">标签(逗号分隔)</label><input id="newDsTags" class="form-input" placeholder="训练集,COCO"></div>
    <div class="form-actions"><button class="btn btn-primary" id="newDsSubmitBtn" onclick="submitCreateDataset()">创建</button></div>`);
}

// R4-Worker-3: 新建数据集 — 调用 POST /api/datasets
async function submitCreateDataset() {
  const name = $('newDsName')?.value?.trim();
  if (!name) { if (typeof showToast === 'function') showToast('请输入数据集名称', 'warning'); return; }
  const type = $('newDsType')?.value || 'image';
  const desc = $('newDsDesc')?.value?.trim() || '';
  const tagsRaw = $('newDsTags')?.value?.trim() || '';
  const tags = tagsRaw ? tagsRaw.split(',').map(s => s.trim()).filter(Boolean) : [];
  const btn = $('newDsSubmitBtn');
  if (btn) { btn.disabled = true; btn.textContent = '创建中...'; }
  try {
    /* P1-C-W2: three-state POST /api/datasets via client.js */
    const res = await window.httpPost('/api/datasets', { name, type, desc, tags }, { timeoutMs: 20000 });
    if (res.state !== window.HTTP_STATE.SUCCESS) {
      window.IMDF_ERROR.onApiError('datasets.create', res.error);
      if (typeof showToast === 'function') showToast('❌ 创建失败: ' + window.IMDF_ERROR.describe(res.error), 'error');
      return;
    }
    const r = res.data || {};
    if (r && r.success) {
      if (typeof showToast === 'function') showToast(`数据集 ${name} 创建成功`, 'success');
      if (typeof closeModal === 'function') closeModal();
      loadDatasets(1);
    } else {
      const msg = r.error || r.message || '创建失败';
      if (typeof showToast === 'function') showToast(msg, 'error');
    }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '创建'; }
  }
}

function formatSize(bytes) {
  if (!bytes||bytes===0) return '0 B';
  const u=['B','KB','MB','GB','TB']; const i=Math.floor(Math.log(bytes)/Math.log(1024));
  return (bytes/Math.pow(1024,i)).toFixed(i>0?1:0)+' '+u[i];
}

/* === 三级模态 === */
// R4-Worker-3: 三级模态 callback 接真实 API
function datasets_newModal() {
  showFormModal('新建数据集', [
    {id:'name',label:'数据集名称',placeholder:'输入数据集名称'},
    {id:'type',label:'类型',type:'select',options:['图像','视频','文本','音频','多模态']},
    {id:'desc',label:'描述',type:'textarea',placeholder:'数据集用途与说明'},
    {id:'tags',label:'标签',placeholder:'逗号分隔,如: 训练集,分类,COCO'},
  ], {
    label:'创建',
    callback: async (d) => {
      // 映射显示值 → 实际 type 字段
      const typeMap = { '图像':'image', '视频':'video', '文本':'text', '音频':'audio', '多模态':'image' };
      const tags = (d.tags || '').split(',').map(s => s.trim()).filter(Boolean);
      /* P1-C-W2: three-state POST /api/datasets via client.js */
      const res = await window.httpPost('/api/datasets', {
        name: d.name,
        type: typeMap[d.type] || 'image',
        desc: d.desc || '',
        tags: tags,
      }, { timeoutMs: 20000 });
      if (res.state !== window.HTTP_STATE.SUCCESS) {
        window.IMDF_ERROR.onApiError('datasets.create', res.error);
        if (typeof showToast === 'function') showToast('❌ 创建失败: ' + window.IMDF_ERROR.describe(res.error), 'error');
        return;
      }
      const r = res.data || {};
      if (r && r.success) {
        if (typeof showToast === 'function') showToast(`数据集 "${d.name}" 创建成功`, 'success');
        setTimeout(() => loadDatasets(1), 500);
      } else {
        if (typeof showToast === 'function') showToast('创建失败: '+(r?.error||'未知错误'), 'error');
      }
    }
  });
}

function datasets_importModal() {
  showFormModal('导入数据', [
    {id:'format',label:'格式',type:'select',options:['CSV','JSON','COCO','YOLO','Pascal VOC','自动检测']},
    {id:'source',label:'文件路径',placeholder:'/data/uploads/xxx.zip'},
    {id:'dataset',label:'目标数据集',placeholder:'选择或输入数据集名称'},
    {id:'options',label:'导入选项',type:'select',options:['追加','覆盖','新建数据集']},
  ], {
    label:'开始导入',
    callback: async (d) => {
      const fmtMap = { 'CSV':'csv', 'JSON':'json', 'COCO':'coco', 'YOLO':'yolo', 'Pascal VOC':'voc', '自动检测':'json' };
      const optMap = { '追加':'append', '覆盖':'overwrite', '新建数据集':'new' };
      /* P1-C-W2: three-state POST /api/datasets/import via client.js */
      const res = await window.httpPost('/api/datasets/import', {
        name: d.dataset || 'imported',
        format: fmtMap[d.format] || 'csv',
        source: d.source || '',
        options: optMap[d.options] || 'append',
      }, { timeoutMs: 60000 });
      if (res.state !== window.HTTP_STATE.SUCCESS) {
        window.IMDF_ERROR.onApiError('datasets.import', res.error);
        if (typeof showToast === 'function') showToast('❌ 导入失败: ' + window.IMDF_ERROR.describe(res.error), 'error');
        return;
      }
      const r = res.data || {};
      if (r && r.success) {
        if (typeof showToast === 'function') showToast(`开始导入 ${d.format} → ${d.dataset}`, 'success');
        setTimeout(() => loadDatasets(1), 500);
      } else {
        if (typeof showToast === 'function') showToast('导入失败: '+(r?.error||'未知错误'), 'error');
      }
    }
  });
}

function datasets_detailModal(item) {
  showDetailModal('数据集详情', {
    '名称':item.name,'类型':item.type,'大小':item.size,
    '文件数':item.file_count||'--','状态':item.status||'active',
    '创建时间':item.created||'--','描述':item.desc||'--'
  });
}
