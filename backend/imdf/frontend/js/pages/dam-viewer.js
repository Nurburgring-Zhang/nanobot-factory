/* IMDF v4 资产管理 DAM — 统一页面规范 */
/* 头部: 标题+统计 | 工具栏: 搜索+筛选+排序 | 卡片+表格双模式 | 空状态 | 分页 */

let DAM = { page:1, total:0, pages:1, view:'card', data:[], search:'', category:'', sort:'date' };

async function renderDAMViewer() {
  const c = $('page-content'); if (!c) return;
  c.innerHTML = `
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <div class="page-title">资产管理</div>
        <div class="page-stats" style="margin-top:4px">
          <div class="page-stat"><div class="page-stat-val" id="damFileCount">0</div><div class="page-stat-label">总文件</div></div>
          <div class="page-stat"><div class="page-stat-val" id="damFormatCount">0</div><div class="page-stat-label">格式数</div></div>
          <div class="page-stat"><div class="page-stat-val" id="damTotalSize">0</div><div class="page-stat-label">总大小</div></div>
        </div>
      </div>
      <div class="page-actions">
        <div class="view-toggle" id="damViewToggle">
          <button class="active" onclick="switchDAMView('card')">卡片</button>
          <button onclick="switchDAMView('table')">表格</button>
        </div>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <input id="damSearch" placeholder="搜索文件名/标签..." onkeydown="if(event.key==='Enter')loadDAM(1)">
        <select id="damCategory" onchange="DAM.category=this.value;loadDAM(1)">
          <option value="">全部类型</option>
          <option value="image">图片</option><option value="video">视频</option>
          <option value="audio">音频</option><option value="3d">3D模型</option>
          <option value="document">文档</option><option value="dataset">数据集</option><option value="archive">压缩包</option>
        </select>
        <select id="damSort" onchange="DAM.sort=this.value;loadDAM(1)">
          <option value="-date">最新</option>
          <option value="date">最旧</option>
          <option value="name">名称A-Z</option>
          <option value="-size">大小递减</option>
        </select>
      </div>
      <div class="toolbar-right">
        <span style="font-size:11px;color:var(--text-muted)">共 <strong id="damTotal">0</strong> 个文件</span>
      </div>
    </div>

    <!-- 卡片视图 -->
    <div id="damCardView">
      <div class="view-container-grid" id="damCardGrid">
        <div class="empty-state" style="grid-column:1/-1"><span>加载中...</span></div>
      </div>
    </div>

    <!-- 表格视图 -->
    <div id="damTableView" style="display:none" class="view-container">
      <div class="view-container-table">
        <table class="data-table">
          <thead><tr>
            <th>名称</th><th style="width:80px">类型</th><th style="width:80px">大小</th>
            <th style="width:60px">格式</th><th style="width:120px">标签</th><th style="width:120px">操作</th>
          </tr></thead>
          <tbody id="damTableBody"><tr><td colspan="6"><div class="empty-state"><span>暂无文件</span></div></td></tr></tbody>
        </table>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pagination" id="damPager"></div>
  `;
  await loadDAM(1);
}

async function loadDAM(page) {
  DAM.page = page;
  DAM.search = $('damSearch')?.value?.trim() || '';
  DAM.category = $('damCategory')?.value || '';
  DAM.sort = $('damSort')?.value || '-date';

  try {
    const params = new URLSearchParams({page, size:24, sort:DAM.sort});
    if (DAM.search) params.set('search', DAM.search);
    if (DAM.category) params.set('category', DAM.category);
    const r = await apiGet(`/api/dam/files?${params.toString()}`);
    if (r.success) { DAM.data = r.items || []; DAM.total = r.total || DAM.data.length; }
    else { DAM.data = []; DAM.total = 0; }
  } catch {
    // 模拟数据
    DAM.data = Array.from({length:24}, (_,i) => ({
      id:`file_${i+1}`, name:`资产文件_${i+1}.${['jpg','mp4','wav','obj','pdf','json','zip'][i%7]}`,
      category:['image','video','audio','3d','document','dataset','archive'][i%7],
      ext:['jpg','mp4','wav','obj','pdf','json','zip'][i%7],
      size_bytes:Math.floor(Math.random()*50000000)+100000,
      tags:[['高清','室外'],['4K','场景'],['立体声'],['高模'],['报告'],['训练集'],['备份']][i%7],
      created_at:`2026-0${(i%6)+1}-${String((i%28)+1).padStart(2,'0')}`
    }));
    DAM.total = DAM.data.length;
  }

  DAM.pages = Math.max(1, Math.ceil(DAM.total / 24));

  // 统计
  const fc = $('damFileCount'); if (fc) fc.textContent = DAM.total;
  const cats = new Set(DAM.data.map(d=>d.category||d.ext));
  const fmtEl = $('damFormatCount'); if (fmtEl) fmtEl.textContent = cats.size;
  const totalSize = DAM.data.reduce((s,d)=>s+(d.size_bytes||0),0);
  const tsEl = $('damTotalSize'); if (tsEl) tsEl.textContent = formatSize(totalSize);
  const totEl = $('damTotal'); if (totEl) totEl.textContent = DAM.total;

  renderCards();
  renderTable();
  renderPager();
}

function renderCards() {
  const grid = $('damCardGrid'); if (!grid) return;
  if (!DAM.data.length) {
    grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1"><div class="empty-state-icon">🗄️</div><div class="empty-state-text">暂无文件</div><div class="empty-state-hint">调整筛选条件或上传新文件</div></div>`;
    return;
  }
  const icons = {image:'🖼️',video:'🎬',audio:'🎵','3d':'🎯',document:'📄',dataset:'📊',archive:'📦'};
  grid.innerHTML = DAM.data.map(f => `
    <div class="card" style="padding:0;overflow:hidden;cursor:pointer" onclick="damPreview('${f.id}')"
      onmouseover="this.style.borderColor='var(--blue)'" onmouseout="this.style.borderColor='var(--border)'">
      <div class="card-grid-thumb">${icons[f.category]||'📎'}</div>
      <div class="card-grid-info">
        <div class="card-grid-name" title="${f.name}">${f.name}</div>
        <div class="card-grid-meta">
          <span>${formatSize(f.size_bytes||0)}</span>
          <span class="tag tag-purple">${f.ext}</span>
        </div>
        ${f.tags&&f.tags.length ? `<div style="margin-top:4px;display:flex;gap:2px;flex-wrap:wrap">${f.tags.slice(0,3).map(t=>`<span class="tag tag-blue">${t}</span>`).join('')}</div>` : ''}
      </div>
    </div>`).join('');
}

function renderTable() {
  const tbody = $('damTableBody'); if (!tbody) return;
  if (!DAM.data.length) {
    tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="empty-state-icon">🗄️</div><div class="empty-state-text">暂无文件</div></div></td></tr>`;
    return;
  }
  const icons = {image:'🖼️',video:'🎬',audio:'🎵','3d':'🎯',document:'📄',dataset:'📊',archive:'📦'};
  tbody.innerHTML = DAM.data.map(f => `
    <tr style="cursor:pointer" onclick="damPreview('${f.id}')">
      <td><span style="font-size:16px;margin-right:6px">${icons[f.category]||'📎'}</span><strong>${f.name}</strong></td>
      <td><span class="tag tag-blue">${f.category}</span></td>
      <td>${formatSize(f.size_bytes||0)}</td>
      <td style="color:#a78bfa">${f.ext}</td>
      <td>${(f.tags||[]).slice(0,3).map(t=>`<span class="tag tag-purple">${t}</span>`).join(' ')||'—'}</td>
      <td>
        <button class="btn btn-sm btn-outline" onclick="event.stopPropagation();damPreview('${f.id}')" style="padding:2px 6px">预览</button>
        <button class="btn btn-sm btn-outline" onclick="event.stopPropagation();damTag('${f.id}')" style="padding:2px 6px">AI打标</button>
      </td>
    </tr>`).join('');
}

function renderPager() {
  const pager = $('damPager'); if (!pager) return;
  if (DAM.pages <= 1) { pager.innerHTML = ''; return; }
  let html = `<button onclick="loadDAM(${DAM.page-1})" ${DAM.page<=1?'disabled':''}>‹</button>`;
  for (let i=1;i<=DAM.pages;i++) {
    if (i===1||i===DAM.pages||Math.abs(i-DAM.page)<=2)
      html += `<button class="${i===DAM.page?'active':''}" onclick="loadDAM(${i})">${i}</button>`;
    else if (i===2||i===DAM.pages-1) html += '<span style="color:var(--text-muted)">...</span>';
  }
  html += `<button onclick="loadDAM(${DAM.page+1})" ${DAM.page>=DAM.pages?'disabled':''}>›</button>`;
  pager.innerHTML = html;
}

function switchDAMView(mode) {
  DAM.view = mode;
  const toggle = $('damViewToggle');
  if (toggle) toggle.querySelectorAll('button').forEach((b,i) => b.classList.toggle('active', (i===0&&mode==='card')||(i===1&&mode==='table')));
  const cv = $('damCardView'); const tv = $('damTableView');
  if (cv) cv.style.display = mode === 'card' ? '' : 'none';
  if (tv) tv.style.display = mode === 'table' ? '' : 'none';
}

function damPreview(fileId) {
  showModal(`<span class="modal-close" onclick="closeModal()">✕</span><h4 style="margin-bottom:8px">🔍 文件预览</h4><div id="damPreviewContent" style="color:var(--text-muted);font-size:12px">加载中...</div>`);
  apiGet(`/api/dam/files/${fileId}/preview`).then(r => {
    const el = $('damPreviewContent'); if (!el) return;
    if (r.success && r.data) {
      const d = r.data;
      el.innerHTML = `<div style="text-align:center;font-size:48px;margin-bottom:12px">${catIcon(d.category)}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:11px;color:var(--text-secondary)">
          <div><strong>文件名:</strong> ${d.name}</div><div><strong>类型:</strong> ${d.category} (${d.ext})</div>
          <div><strong>大小:</strong> ${formatSize(d.size_bytes||0)}</div><div><strong>MIME:</strong> ${d.mime||'—'}</div>
        </div>
        <div class="mt-12">
          <button class="btn btn-sm btn-primary" onclick="closeModal();damTag('${fileId}')">AI打标</button>
        </div>`;
    } else {
      el.innerHTML = '<div style="color:var(--red)">预览失败</div>';
    }
  }).catch(ex => {
    const el = $('damPreviewContent');
    if (el) el.innerHTML = `<div style="color:var(--red)">预览失败: ${ex.message}</div>`;
  });
}

function damTag(fileId) {
  showModal(`<span class="modal-close" onclick="closeModal()">✕</span><h4 style="margin-bottom:8px">🤖 AI自动打标</h4><div id="damTagResult" style="color:var(--text-muted);font-size:12px">正在分析...</div>`);
  apiPost(`/api/dam/files/${fileId}/tag`).then(r => {
    const el = $('damTagResult'); if (!el) return;
    if (r.success) {
      const d = r.data;
      el.innerHTML = `<div style="color:var(--green);margin-bottom:8px">✅ 打标完成</div>
        <div><strong>标签:</strong> ${(d.tags||[]).map(t=>`<span class="tag tag-purple">${t}</span>`).join(' ')||'无'}</div>
        ${d.description?`<div style="margin-top:4px;color:var(--text-muted);font-size:11px"><strong>描述:</strong> ${d.description}</div>`:''}`;
      setTimeout(()=>{closeModal();loadDAM(DAM.page);},2000);
    } else {
      el.innerHTML = `<div style="color:var(--red)">❌ 打标失败: ${r.error||'未知错误'}</div>`;
    }
  }).catch(ex => {
    const el = $('damTagResult');
    if (el) el.innerHTML = `<div style="color:var(--red)">❌ 错误: ${ex.message}</div>`;
  });
}

function catIcon(cat) {
  return {image:'🖼️',video:'🎬',audio:'🎵','3d':'🎯',document:'📄',dataset:'📊',archive:'📦'}[cat]||'📎';
}

function formatSize(bytes) {
  if (!bytes||bytes===0) return '0 B';
  const u=['B','KB','MB','GB','TB']; const i=Math.floor(Math.log(bytes)/Math.log(1024));
  return (bytes/Math.pow(1024,i)).toFixed(i>0?1:0)+' '+u[i];
}
