/* IMDF v4 数据浏览器 — 统一页面规范 */
/* 头部: 标题+统计+视图切换 | 工具栏: 搜索+筛选 | 网格/表格双视图 | 空状态 | 分页 */

let DBG = { page:1, total:0, pages:1, view:'grid', data:[], search:'', dataset:'', type:'', sort:'-created_at' };

async function renderDataBrowserGrid() {
  const c = $('page-content'); if (!c) return;
  c.innerHTML = `
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <div class="page-title">数据浏览器</div>
        <div class="page-stats" style="margin-top:4px">
          <div class="page-stat"><div class="page-stat-val" id="dbgItemCount">0</div><div class="page-stat-label">项目数</div></div>
          <div class="page-stat"><div class="page-stat-val" id="dbgFormatCount">0</div><div class="page-stat-label">格式数</div></div>
        </div>
      </div>
      <div class="page-actions">
        <div class="view-toggle" id="dbgViewToggle">
          <button class="active" onclick="switchDBGView('grid')">网格</button>
          <button onclick="switchDBGView('table')">表格</button>
        </div>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <input id="dbgSearch" placeholder="搜索数据内容..." onkeydown="if(event.key==='Enter')loadDBG(1)">
        <select id="dbgDataset" onchange="DBG.dataset=this.value;loadDBG(1)">
          <option value="">全部数据集</option>
        </select>
        <select id="dbgType" onchange="DBG.type=this.value;loadDBG(1)">
          <option value="">全部格式</option>
          <option value="image">图片</option><option value="video">视频</option>
          <option value="text">文本</option><option value="audio">音频</option>
          <option value="3d">3D</option>
        </select>
        <select id="dbgSort" onchange="DBG.sort=this.value;loadDBG(1)">
          <option value="-created_at">最新</option>
          <option value="created_at">最旧</option>
          <option value="name">名称A-Z</option>
          <option value="-name">名称Z-A</option>
        </select>
      </div>
      <div class="toolbar-right">
        <span style="font-size:11px;color:var(--text-muted)">共 <strong id="dbgTotal">0</strong> 条</span>
      </div>
    </div>

    <!-- 网格视图 -->
    <div id="dbgGridView" class="view-container">
      <div class="view-container-grid" id="dbgGridWrap">
        <div class="empty-state" style="grid-column:1/-1"><span>加载中...</span></div>
      </div>
    </div>

    <!-- 表格视图 -->
    <div id="dbgTableView" class="view-container" style="display:none">
      <div class="view-container-table">
        <table class="data-table">
          <thead><tr>
            <th>名称</th><th style="width:80px">类型</th><th style="width:80px">大小</th>
            <th style="width:100px">创建时间</th><th style="width:60px">操作</th>
          </tr></thead>
          <tbody id="dbgTableBody"><tr><td colspan="5"><div class="empty-state"><span>暂无数据</span></div></td></tr></tbody>
        </table>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pagination" id="dbgPager"></div>
  `;

  // 加载数据集下拉
  apiGet('/api/datasets').then(d => {
    const sel = $('dbgDataset');
    const items = d.items || d.data?.items || [];
    if (sel && items.length) items.forEach(item => {
      const o = document.createElement('option');
      o.value = item.id || item.name || '';
      o.textContent = item.name || item.id || '';
      sel.appendChild(o);
    });
  });

  await loadDBG(1);
}

async function loadDBG(page) {
  DBG.page = page;
  DBG.search = $('dbgSearch')?.value?.trim() || '';
  DBG.dataset = $('dbgDataset')?.value || '';
  DBG.type = $('dbgType')?.value || '';
  DBG.sort = $('dbgSort')?.value || '-created_at';

  let url = `/api/datasets?page=${page}&size=24&search=${encodeURIComponent(DBG.search)}&sort=${DBG.sort}`;
  if (DBG.dataset) url += `&dataset_id=${encodeURIComponent(DBG.dataset)}`;
  if (DBG.type) url += `&type=${encodeURIComponent(DBG.type)}`;

  const result = await apiGet(url).catch(() => ({}));
  const items = result.items || result.data?.items || [];
  DBG.total = result.total || items.length;
  DBG.pages = result.pages || Math.max(1, Math.ceil(DBG.total / 24));
  DBG.data = items;

  // 统计
  const tEl = $('dbgTotal'); if (tEl) tEl.textContent = DBG.total;
  const iEl = $('dbgItemCount'); if (iEl) iEl.textContent = DBG.total;
  const types = new Set(items.map(i => i.type || 'image'));
  const fEl = $('dbgFormatCount'); if (fEl) fEl.textContent = types.size;

  renderGrid();
  renderTable();
  renderPager();
}

function renderGrid() {
  const wrap = $('dbgGridWrap'); if (!wrap) return;
  if (DBG.data.length === 0) {
    wrap.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><div class="empty-state-icon">🔍</div><div class="empty-state-text">暂无数据</div><div class="empty-state-hint">尝试调整筛选条件</div></div>`;
    return;
  }
  const icons = { image:'🖼️', video:'🎬', text:'📄', audio:'🎵', '3d':'🧊' };
  wrap.innerHTML = DBG.data.map((item, i) => {
    const id = item.id || item.name || `item_${i}`;
    const type = item.type || 'image';
    const icon = icons[type] || '📁';
    const thumb = item.thumbnail_url || item.preview_url || '';
    return `<div class="card" style="padding:0;overflow:hidden;cursor:pointer" onclick="previewDBG('${id}')"
      onmouseover="this.style.borderColor='var(--blue)'" onmouseout="this.style.borderColor='var(--border)'">
      <div class="card-grid-thumb">
        ${thumb ? `<img src="${thumb}" style="width:100%;height:100%;object-fit:cover" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">` : ''}
        <span style="${thumb?'display:none':''}">${icon}</span>
      </div>
      <div class="card-grid-info">
        <div class="card-grid-name">${item.name || id}</div>
        <div class="card-grid-meta">
          <span class="tag tag-blue">${type}</span>
          <span>${item.size ? formatSize(item.size) : '--'}</span>
        </div>
      </div>
    </div>`;
  }).join('');
}

function renderTable() {
  const tbody = $('dbgTableBody'); if (!tbody) return;
  if (DBG.data.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5"><div class="empty-state"><div class="empty-state-icon">🔍</div><div class="empty-state-text">暂无数据</div></div></td></tr>`;
    return;
  }
  tbody.innerHTML = DBG.data.map((item, i) => {
    const id = item.id || item.name || `item_${i}`;
    return `<tr style="cursor:pointer" onclick="previewDBG('${id}')">
      <td><strong>${item.name || id}</strong></td>
      <td><span class="tag tag-blue">${item.type || 'image'}</span></td>
      <td>${item.size ? formatSize(item.size) : '--'}</td>
      <td style="color:var(--text-muted);font-size:11px">${item.created_at ? item.created_at.slice(0,10) : '--'}</td>
      <td><button class="btn btn-sm btn-outline" onclick="event.stopPropagation();previewDBG('${id}')">👁</button></td>
    </tr>`;
  }).join('');
}

function renderPager() {
  const pager = $('dbgPager'); if (!pager) return;
  if (DBG.pages <= 1) { pager.innerHTML = ''; return; }
  let html = `<button onclick="loadDBG(${DBG.page-1})" ${DBG.page<=1?'disabled':''}>‹</button>`;
  for (let i=1;i<=DBG.pages;i++) {
    if (i===1||i===DBG.pages||Math.abs(i-DBG.page)<=2)
      html += `<button class="${i===DBG.page?'active':''}" onclick="loadDBG(${i})">${i}</button>`;
    else if (i===2||i===DBG.pages-1) html += '<span style="color:var(--text-muted)">...</span>';
  }
  html += `<button onclick="loadDBG(${DBG.page+1})" ${DBG.page>=DBG.pages?'disabled':''}>›</button>`;
  pager.innerHTML = html;
}

function switchDBGView(mode) {
  DBG.view = mode;
  const toggle = $('dbgViewToggle');
  if (toggle) toggle.querySelectorAll('button').forEach((b,i) => b.classList.toggle('active', (i===0&&mode==='grid')||(i===1&&mode==='table')));
  const gv = $('dbgGridView'); const tv = $('dbgTableView');
  if (gv) gv.style.display = mode === 'grid' ? '' : 'none';
  if (tv) tv.style.display = mode === 'table' ? '' : 'none';
}

function previewDBG(id) {
  apiGet(`/api/datasets/${encodeURIComponent(id)}/preview`).then(data => {
    const items = (data.items || data.data?.items || []).slice(0, 10);
    const html = items.map((it,i) => `<div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:12px;display:flex;gap:8px;align-items:center">
      <span style="color:var(--text-muted);min-width:24px">#${i+1}</span>
      ${it.thumbnail_url?`<img src="${it.thumbnail_url}" style="width:48px;height:48px;border-radius:4px;object-fit:cover">`:''}
      <span style="flex:1">${it.name||it.id||'样本'}</span>
      <span style="color:var(--text-muted)">${it.type||'image'}</span>
    </div>`).join('');
    showModal(`<span class="modal-close" onclick="closeModal()">✕</span><h4 style="margin-bottom:12px">🔍 ${id} — 预览</h4>${items.length?html:'<p style="color:var(--text-muted);padding:20px 0">暂无数据</p>'}<p style="margin-top:8px;font-size:11px;color:var(--text-muted)">共 ${items.length} 条 · 仅显示前10条</p>`);
  });
}

function formatSize(bytes) {
  if (!bytes||bytes===0) return '0 B';
  const u=['B','KB','MB','GB','TB']; const i=Math.floor(Math.log(bytes)/Math.log(1024));
  return (bytes/Math.pow(1024,i)).toFixed(i>0?1:0)+' '+u[i];
}
