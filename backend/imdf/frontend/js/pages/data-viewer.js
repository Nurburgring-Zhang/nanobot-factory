/* IMDF v4 多视图查阅器 — 统一页面规范 */
/* 头部: 标题+4视图切换 | 工具栏: 搜索+排序 | 网格/卡片/列表/时间线 */

let DV = { view:'grid', sortField:null, sortDir:-1, data:[], allData:[] };

async function renderDataViewer() {
  const c = $('page-content'); if (!c) return;
  c.innerHTML = `
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="page-title">多视图查阅</div>
      <div class="page-actions">
        <div class="view-toggle" id="dvViewToggle">
          <button class="active" onclick="switchDVView('grid')">网格</button>
          <button onclick="switchDVView('card')">卡片</button>
          <button onclick="switchDVView('list')">列表</button>
          <button onclick="switchDVView('timeline')">时间线</button>
        </div>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <input id="dvSearch" placeholder="搜索文件/标签/内容..." onkeydown="if(event.key==='Enter')dvSearch()">
      </div>
      <div class="toolbar-right" id="dvSortBar"></div>
    </div>

    <!-- 视图内容 -->
    <div id="dvContent" style="overflow-y:auto;max-height:calc(100vh - 300px)"></div>

    <!-- 状态栏 -->
    <div style="margin-top:8px;font-size:11px;color:var(--text-muted);display:flex;justify-content:space-between" id="dvStatus">
      <span id="dvCount">共 0 项</span>
    </div>
  `;

  // 排序栏
  const sortFields = [
    {id:null,label:'默认'},{id:'aesthetic_score',label:'审美分'},
    {id:'name',label:'名称'},{id:'created_at',label:'日期'},
    {id:'quality_score',label:'质量分'},
  ];
  const sortBar = $('dvSortBar');
  sortBar.innerHTML = sortFields.map(sf => 
    `<button class="btn btn-sm ${DV.sortField===sf.id?'btn-primary':'btn-outline'}" 
      onclick="setSortField('${sf.id||''}',this)">${sf.label}${DV.sortField===sf.id?(DV.sortDir===1?' ↑':' ↓'):''}</button>`
  ).join('');

  document.getElementById('dvSearch').onkeyup = function(e) {
    const q = e.target.value.trim().toLowerCase();
    if (!q) { DV.data = [...DV.allData]; applySort(); renderView(); return; }
    DV.data = DV.allData.filter(i => JSON.stringify(i).toLowerCase().includes(q));
    applySort(); renderView();
  };

  await loadData();
}

async function loadData() {
  // R4-W4-others: 移除所有 Math.random() 兜底, 无数据时显示空态而非造数据
  try {
    const r = await apiGet('/api/datasets?page=1&size=100');
    DV.allData = (r.items || []).map(item => {
      // 真实字段, 缺则标 null (渲染时显示 '—')
      if (item.aesthetic_score == null && item.quality_score != null) {
        // 仅在 API 真实返回 quality_score 时用其作为审美分 (无则 null, 不假造)
        item.aesthetic_score = item.quality_score;
      }
      if (item.aesthetic_score != null) {
        const s = item.aesthetic_score;
        item.aesthetic_grade = s>=90?'S':s>=80?'A':s>=65?'B':s>=50?'C':'D';
      }
      return item;
    });
  } catch (e) {
    // API 失败时显示空态, 不再用 24 条 Math.random() 假数据
    console.warn('loadData failed:', e);
    DV.allData = [];
  }
  DV.data = [...DV.allData];
  applySort();
  renderView();
}

function setSortField(field, btn) {
  if (DV.sortField === field) DV.sortDir *= -1;
  else { DV.sortField = field || null; DV.sortDir = -1; }
  // Rebuild sort buttons
  const sortBar = $('dvSortBar');
  const sortFields = [
    {id:null,label:'默认'},{id:'aesthetic_score',label:'审美分'},
    {id:'name',label:'名称'},{id:'created_at',label:'日期'},
    {id:'quality_score',label:'质量分'},
  ];
  sortBar.innerHTML = sortFields.map(sf => 
    `<button class="btn btn-sm ${DV.sortField===sf.id?'btn-primary':'btn-outline'}" 
      onclick="setSortField('${sf.id||''}',this)">${sf.label}${DV.sortField===sf.id?(DV.sortDir===1?' ↑':' ↓'):''}</button>`
  ).join('');
  applySort();
  renderView();
}

function applySort() {
  if (!DV.sortField) return;
  DV.data.sort((a,b) => {
    const va = a[DV.sortField] !== undefined ? a[DV.sortField] : '';
    const vb = b[DV.sortField] !== undefined ? b[DV.sortField] : '';
    if (typeof va==='number' && typeof vb==='number') return (va-vb)*DV.sortDir;
    return String(va).localeCompare(String(vb))*DV.sortDir;
  });
}

function switchDVView(view) {
  DV.view = view;
  const toggle = $('dvViewToggle');
  if (toggle) {
    const views = ['grid','card','list','timeline'];
    toggle.querySelectorAll('button').forEach((b,i) => b.classList.toggle('active', views[i]===view));
  }
  renderView();
}
window.switchDVView = switchDVView;
window.setSortField = setSortField;

function aestheticBadge(score, grade) {
  const colors = {S:'#FFD700',A:'#4CAF50',B:'#2196F3',C:'#FF9800',D:'#f44336'};
  const bgColors = {S:'#3d3520',A:'#1e3a1e',B:'#1e2a3a',C:'#3a2e1e',D:'#3a1e1e'};
  // R4-W4-others: 无 score 时显示 '—' 而非 grade 兜底
  if (score == null) return `<span style="background:#1e1e3a;color:#666;padding:1px 6px;border-radius:3px;font-size:10px">— —</span>`;
  return `<span style="background:${bgColors[grade]||'#1e1e3a'};color:${colors[grade]||'#888'};padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600">${grade||'?'} ${score}</span>`;
}

function renderView() {
  const el = $('dvContent'); if (!el) return;
  const countEl = $('dvCount'); if (countEl) countEl.textContent = `共 ${DV.data.length} 项 | ${DV.view}视图`;

  switch(DV.view) {
    case 'grid': el.innerHTML = `<div class="view-container-grid">${DV.data.map(i=>gridItem(i)).join('')||'<div class="empty-state" style="grid-column:1/-1"><div class="empty-state-icon">📊</div><div class="empty-state-text">暂无数据</div></div>'}</div>`; break;
    case 'card': el.innerHTML = `<div style="display:flex;flex-wrap:wrap;gap:10px">${DV.data.map(i=>cardItem(i)).join('')||'<div class="empty-state"><div class="empty-state-icon">📊</div><div class="empty-state-text">暂无数据</div></div>'}</div>`; break;
    case 'list': el.innerHTML = `<div class="view-container"><div class="view-container-table"><table class="data-table">
      <thead><tr><th>名称</th><th>类型</th><th>大小</th><th>标签</th><th>审美分</th><th>等级</th><th>质量</th><th>日期</th></tr></thead>
      <tbody>${DV.data.map(i=>listRow(i)).join('')||'<tr><td colspan="8"><div class="empty-state">暂无数据</div></td></tr>'}</tbody>
    </table></div></div>`; break;
    case 'timeline': el.innerHTML = timelineView(DV.data); break;
  }
}

function gridItem(i) {
  const score = i.aesthetic_score;
  const grade = i.aesthetic_grade;
  const icon = {image:'🖼️',video:'🎬',text:'📝',audio:'🎵','3d':'🎯'}[i.type]||'📄';
  // R4-W4-others: 真实缩略图, 若 API 返回 preview_url/thumbnail_url 则用, 否则用 emoji (非 picsum)
  const thumb = i.preview_url || i.thumbnail_url
    ? `<img src="${sanitizeHTML(i.preview_url || i.thumbnail_url)}" style="width:100%;height:100%;object-fit:cover" onerror="this.outerHTML='<div style=\\'width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:32px\\'>${icon}</div>'">`
    : `<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:32px">${icon}</div>`;
  return `<div class="card" style="padding:0;overflow:hidden;cursor:pointer">
    <div class="card-grid-thumb" style="height:120px;overflow:hidden">${thumb}</div>
    <div class="card-grid-info">
      <div class="card-grid-name">${(i.name||'未命名').substring(0,24)}</div>
      <div class="card-grid-meta"><span>${i.size != null ? i.size + 'MB' : '—'}</span>${aestheticBadge(score,grade)}</div>
    </div></div>`;
}

function cardItem(i) {
  const tags = (i.tags||[]).slice(0,3).map(t=>`<span class="tag tag-purple">${sanitizeHTML(t)}</span>`).join(' ');
  const score = i.aesthetic_score;
  const grade = i.aesthetic_grade;
  return `<div class="card" style="width:280px">
    <div style="font-size:14px;font-weight:600;margin-bottom:4px">${sanitizeHTML((i.name||'未命名').substring(0,30))}</div>
    <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px">${sanitizeHTML(i.description||i.summary||'无描述')}</div>
    <div style="margin-bottom:4px">${tags}</div>
    <div style="display:flex;justify-content:space-between;align-items:center;font-size:10px;color:var(--text-muted)">
      <span>${(i.created_at||'').slice(0,10) || '—'}</span><span>${aestheticBadge(score,grade)}</span>
    </div></div>`;
}

function listRow(i) {
  const tags = (i.tags||[]).slice(0,2).map(t => sanitizeHTML(t)).join(', ');
  const score = i.aesthetic_score;
  const grade = i.aesthetic_grade;
  return `<tr>
    <td>${sanitizeHTML((i.name||'未命名').substring(0,40))}</td>
    <td><span class="tag tag-blue">${sanitizeHTML(i.type||i.format||'—')}</span></td>
    <td>${i.size != null ? i.size + 'MB' : '—'}</td>
    <td style="color:#a78bfa;font-size:11px">${tags||'—'}</td>
    <td style="font-weight:600">${score != null ? score : '—'}</td>
    <td>${aestheticBadge(score,grade)}</td>
    <td>${i.quality_score != null ? i.quality_score : '—'}</td>
    <td style="font-size:10px;color:var(--text-muted)">${(i.created_at||'').slice(0,10) || '—'}</td>
  </tr>`;
}

function timelineView(items) {
  const sorted = [...items].sort((a,b)=>(b.created_at||'').localeCompare(a.created_at||''));
  const groups = {};
  sorted.forEach(i => {
    const d = (i.created_at||'').substring(0,10)||'未知';
    groups[d] = groups[d] || [];
    groups[d].push(i);
  });
  if (!Object.keys(groups).length) return '<div class="empty-state"><div class="empty-state-icon">📅</div><div class="empty-state-text">暂无数据</div></div>';
  return Object.entries(groups).map(([d,grp]) => `
    <div class="mb-16">
      <div style="font-size:14px;font-weight:600;margin-bottom:8px;padding:4px 0;border-bottom:1px solid var(--border)">📅 ${sanitizeHTML(d)} (${grp.length}项)</div>
      <div class="view-container-grid" style="grid-template-columns:repeat(auto-fill,minmax(120px,1fr))">
        ${grp.map(i => {
          const score = i.aesthetic_score;
          const grade = i.aesthetic_grade;
          const icon = {image:'🖼️',video:'🎬',text:'📝',audio:'🎵','3d':'🎯'}[i.type]||'📄';
          return `<div class="card" style="text-align:center;padding:10px"><div style="font-size:24px">${icon}</div><div style="font-size:10px;margin:4px 0">${sanitizeHTML((i.name||'').substring(0,10))}</div>${aestheticBadge(score,grade)}</div>`;
        }).join('')}
      </div>
    </div>`).join('');
}
