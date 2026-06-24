/* IMDF v4 数据采集 — 统一页面规范 */
/* 头部: 标题+统计 | 三Tab: 爬虫配置|RSS订阅|API拉取 | 表单+列表 */

let DC = { activeTab:'crawler', crawlerJobs:[], rssFeeds:[], apiConfigs:[], history:[] };

// R4-W4-others: 启动时拉真实历史记录, 供 refreshDCStats 兜底链使用
async function dc_loadHistory() {
  try { const r = await apiGet('/api/v1/ingest/history?limit=200').catch(()=>({})); DC.history = r.history || r.data || []; }
  catch { DC.history = []; }
}

function renderDataCollection() {
  const c = $('page-content'); if (!c) return;
  c.innerHTML = `
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <div class="page-title">数据采集</div>
        <div class="page-stats" style="margin-top:4px">
          <div class="page-stat"><div class="page-stat-val" id="dcSourceCount">0</div><div class="page-stat-label">采集源数</div></div>
          <div class="page-stat"><div class="page-stat-val" id="dcTodayCount">0</div><div class="page-stat-label">今日采集量</div></div>
        </div>
      </div>
      <div class="page-actions">
        <button class="btn btn-primary btn-sm" onclick="refreshDCStats()">刷新</button>
      </div>
    </div>

    <!-- Tab切换 -->
    <div class="subtab-bar" id="dcTabs">
      <button class="subtab-btn active" onclick="switchDCTab('crawler')">爬虫配置</button>
      <button class="subtab-btn" onclick="switchDCTab('rss')">RSS订阅</button>
      <button class="subtab-btn" onclick="switchDCTab('api')">API拉取</button>
    </div>

    <!-- Tab内容 -->
    <div id="dcTabContent"></div>
  `;
  switchDCTab('crawler');
  dc_loadHistory().then(refreshDCStats);
  refreshDCStats();
}

function switchDCTab(tab) {
  DC.activeTab = tab;
  const tabs = document.querySelectorAll('#dcTabs .subtab-btn');
  tabs.forEach((b,i) => b.classList.toggle('active', ['crawler','rss','api'][i]===tab));
  const content = $('dcTabContent'); if (!content) return;
  switch(tab) {
    case 'crawler': renderCrawlerTab(content); break;
    case 'rss': renderRSSTab(content); break;
    case 'api': renderAPITab(content); break;
  }
}

async function refreshDCStats() {
  // R4-W4-others: 兜底链 — API.source_count → 真实列表计数 → '—' (无 Math.random)
  try {
    const r = await apiGet('/api/v1/ingest/stats').catch(() => ({}));
    const s = r.stats || r.data || {};
    const sc = $('dcSourceCount');
    if (sc) {
      if (typeof s.source_count === 'number' && s.source_count > 0) {
        sc.textContent = s.source_count;
      } else {
        // 后端暂无 source_count, 用本地真实列表计数 (rss + api + 1 个 crawler)
        const real = DC.rssFeeds.length + DC.apiConfigs.length + (DC.crawlerJobs.length > 0 ? 1 : 0);
        sc.textContent = real > 0 ? real : '—';
      }
    }
    const tc = $('dcTodayCount');
    if (tc) {
      if (typeof s.today_count === 'number' && s.today_count > 0) {
        tc.textContent = s.today_count;
      } else {
        // 真实历史记录求和 (DC.history 来自 /api/v1/ingest/history)
        const real = (DC.history || []).reduce((a, h) => a + (h.count || 0), 0);
        tc.textContent = real > 0 ? real : '—';
      }
    }
  } catch {
    const sc = $('dcSourceCount'); if (sc) sc.textContent = '—';
    const tc = $('dcTodayCount'); if (tc) tc.textContent = '—';
  }
}
window.switchDCTab = switchDCTab;

/* ===== 爬虫配置 Tab ===== */
function renderCrawlerTab(container) {
  container.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <!-- 表单 -->
      <div class="content-panel">
        <div class="section-title">新建爬虫任务</div>
        <form id="crawlerForm" onsubmit="submitCrawler(event)" style="display:grid;gap:10px">
          <div class="form-field"><label class="form-label">任务名称</label><input id="cjName" class="form-input" placeholder="例如：新闻采集-科技类" required></div>
          <div class="form-field"><label class="form-label">目标URL</label><input id="cjUrl" class="form-input" placeholder="https://example.com/articles" required></div>
          <div class="form-row">
            <div class="form-field"><label class="form-label">内容选择器</label><input id="cjSelector" class="form-input" placeholder="article .content"></div>
            <div class="form-field"><label class="form-label">标题选择器</label><input id="cjTitleSelector" class="form-input" placeholder="h2.title"></div>
          </div>
          <div class="form-row">
            <div class="form-field"><label class="form-label">最大页数</label><input id="cjMaxPages" class="form-input" type="number" value="10" min="1"></div>
            <div class="form-field"><label class="form-label">请求间隔(秒)</label><input id="cjDelay" class="form-input" type="number" value="2" min="0.5" step="0.5"></div>
          </div>
          <div class="form-field"><label class="form-label">输出格式</label><select id="cjFormat" class="form-select"><option value="json">JSON</option><option value="jsonl">JSONL</option><option value="csv">CSV</option></select></div>
          <div class="form-actions">
            <button type="submit" class="btn btn-primary">启动采集</button>
            <button type="button" class="btn btn-outline" onclick="document.getElementById('crawlerForm').reset()">重置</button>
          </div>
        </form>
        <div id="cjResult" class="result-msg" style="display:none"></div>
      </div>

      <!-- 任务列表 -->
      <div class="content-panel">
        <div class="section-title">爬虫任务列表</div>
        <div id="crawlerJobList">
          <div class="empty-state"><div class="empty-state-icon">🕷️</div><div class="empty-state-text">暂无爬虫任务</div><div class="empty-state-hint">在左侧表单创建新任务</div></div>
        </div>
      </div>
    </div>
  `;
  loadCrawlerJobs();
}

async function submitCrawler(e) {
  e.preventDefault();
  const job = {
    name: $('cjName')?.value?.trim(),
    url: $('cjUrl')?.value?.trim(),
    selectors: { content: $('cjSelector')?.value?.trim(), title: $('cjTitleSelector')?.value?.trim() },
    max_pages: parseInt($('cjMaxPages')?.value||'10'),
    delay: parseFloat($('cjDelay')?.value||'2'),
    output_format: $('cjFormat')?.value,
  };
  if (!job.name || !job.url) return;
  const res = $('cjResult'); res.style.display='block'; res.className='result-msg info'; res.textContent='提交中...';
  try {
    const resp = await apiPost('/api/v1/ingest/crawler', job);
    res.className = `result-msg ${resp.success?'success':'error'}`;
    res.textContent = resp.success ? '任务已创建' : '失败: '+(resp.error||'未知错误');
    if (resp.success) { document.getElementById('crawlerForm').reset(); loadCrawlerJobs(); }
  } catch(err) { res.className='result-msg error'; res.textContent='网络错误: '+err.message; }
}

async function loadCrawlerJobs() {
  try { const r = await apiGet('/api/v1/ingest/crawler/jobs').catch(()=>({})); DC.crawlerJobs = r.jobs||r.data||[]; }
  catch { DC.crawlerJobs = []; }
  const list = $('crawlerJobList');
  if (!list) return;
  if (!DC.crawlerJobs.length) {
    list.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🕷️</div><div class="empty-state-text">暂无爬虫任务</div></div>';
    return;
  }
  list.innerHTML = DC.crawlerJobs.map(j => `
    <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border)">
      <div style="flex:1;min-width:0">
        <div style="font-weight:600;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${j.name||'未命名'}</div>
        <div style="color:var(--text-muted);font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${j.url||''}</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;font-size:11px">
        <span class="tag ${j.status==='running'?'tag-blue':j.status==='done'?'tag-green':'tag-orange'}">${j.status||'pending'}</span>
        <span style="color:var(--text-muted)">${j.count||0}条</span>
      </div>
    </div>`).join('');
}

/* ===== RSS订阅 Tab ===== */
function renderRSSTab(container) {
  container.innerHTML = `
    <div class="toolbar mb-12">
      <div class="toolbar-left">
        <input id="rssUrl" placeholder="RSS源URL..." style="flex:1">
        <input id="rssName" placeholder="源名称" style="width:150px">
      </div>
      <div class="toolbar-right">
        <button class="btn btn-primary btn-sm" onclick="addRSS()">添加</button>
        <button class="btn btn-outline btn-sm" onclick="refreshAllRSS()">刷新全部</button>
      </div>
    </div>
    <div class="content-panel" id="rssFeedList">
      <div class="empty-state"><div class="empty-state-icon">📡</div><div class="empty-state-text">暂无RSS源</div><div class="empty-state-hint">添加RSS源URL开始订阅</div></div>
    </div>
  `;
  loadRSSFeeds();
}

async function loadRSSFeeds() {
  try { const r = await apiGet('/api/v1/ingest/rss').catch(()=>({})); DC.rssFeeds = r.feeds||r.data||[]; }
  catch { DC.rssFeeds = []; }
  const list = $('rssFeedList'); if (!list) return;
  if (!DC.rssFeeds.length) {
    list.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📡</div><div class="empty-state-text">暂无RSS源</div><div class="empty-state-hint">添加RSS源URL开始订阅</div></div>';
    return;
  }
  list.innerHTML = `
    <table class="data-table">
      <thead><tr><th>名称</th><th>URL</th><th style="width:70px">状态</th><th style="width:60px">条数</th><th style="width:100px">操作</th></tr></thead>
      <tbody>${DC.rssFeeds.map((f,i) => `
        <tr>
          <td><strong>${f.name||'未命名'}</strong></td>
          <td style="color:var(--text-muted);font-size:11px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${f.url||''}</td>
          <td><span class="tag ${f.status==='active'?'tag-green':'tag-orange'}">${f.status||'active'}</span></td>
          <td>${f.item_count||0}</td>
          <td>
            <button class="btn btn-sm btn-outline" onclick="refreshRSS(${i})" title="刷新" style="padding:2px 6px">🔄</button>
            <button class="btn btn-sm btn-outline" onclick="deleteRSS(${i})" title="删除" style="padding:2px 6px;color:var(--red)">🗑</button>
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

async function addRSS() {
  const url = $('rssUrl')?.value?.trim(); const name = $('rssName')?.value?.trim();
  if (!url) return;
  try { await apiPost('/api/v1/ingest/rss',{url,name}); $('rssUrl').value='';$('rssName').value=''; loadRSSFeeds(); refreshDCStats(); }
  catch(err) { (window.toastError || ((m) => alert(m)))('添加失败: '+err.message); }
}
async function refreshRSS(i) { try{await apiPost(`/api/v1/ingest/rss/${DC.rssFeeds[i]?.id||i}/refresh`)}catch{} loadRSSFeeds(); }
async function refreshAllRSS() { try{await apiPost('/api/v1/ingest/rss/refresh-all')}catch{} loadRSSFeeds(); }
async function deleteRSS(i) {
  const f = DC.rssFeeds[i]; if(!f||!confirm(`删除RSS源 "${f.name||f.url}"?`))return;
  try{await api('DELETE',`/api/v1/ingest/rss/${f.id||i}`)}catch{} loadRSSFeeds(); refreshDCStats();
}

/* ===== API拉取 Tab ===== */
function renderAPITab(container) {
  container.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div class="content-panel">
        <div class="section-title">API拉取配置</div>
        <form id="apiPullForm" onsubmit="submitAPIConfig(event)" style="display:grid;gap:10px">
          <div class="form-field"><label class="form-label">配置名称</label><input id="apiName" class="form-input" placeholder="例如：GitHub API" required></div>
          <div class="form-field"><label class="form-label">API端点URL</label><input id="apiEndpoint" class="form-input" placeholder="https://api.example.com/v1/data" required></div>
          <div class="form-row">
            <div class="form-field"><label class="form-label">请求方法</label><select id="apiMethod" class="form-select"><option value="GET">GET</option><option value="POST">POST</option></select></div>
            <div class="form-field"><label class="form-label">分页模式</label><select id="apiPagination" class="form-select"><option value="offset">Offset/Limit</option><option value="page">Page</option><option value="none">无分页</option></select></div>
          </div>
          <div class="form-row">
            <div class="form-field"><label class="form-label">每页数量</label><input id="apiPageSize" class="form-input" type="number" value="100"></div>
            <div class="form-field"><label class="form-label">最大页数</label><input id="apiMaxPages" class="form-input" type="number" value="50"></div>
          </div>
          <div class="form-field"><label class="form-label">Headers (JSON)</label><textarea id="apiHeaders" class="form-textarea" rows="2" placeholder='{"Authorization":"Bearer xxx"}'></textarea></div>
          <div class="form-actions">
            <button type="submit" class="btn btn-primary">保存配置</button>
            <button type="button" class="btn btn-outline" onclick="document.getElementById('apiPullForm').reset()">重置</button>
          </div>
        </form>
        <div id="apiResult" class="result-msg" style="display:none"></div>
      </div>

      <div class="content-panel">
        <div class="section-title">API配置列表</div>
        <div id="apiConfigList">
          <div class="empty-state"><div class="empty-state-icon">🔌</div><div class="empty-state-text">暂无API配置</div><div class="empty-state-hint">在左侧表单创建API拉取配置</div></div>
        </div>
      </div>
    </div>
  `;
  loadAPIConfigs();
}

async function submitAPIConfig(e) {
  e.preventDefault();
  let headers={};
  const raw = $('apiHeaders')?.value?.trim();
  if (raw) { try{headers=JSON.parse(raw)}catch{(window.toastError || ((m) => alert(m)))('Headers格式错误');return;} }
  const cfg = {
    name:$('apiName')?.value?.trim(), endpoint:$('apiEndpoint')?.value?.trim(),
    method:$('apiMethod')?.value, pagination:$('apiPagination')?.value,
    page_size:parseInt($('apiPageSize')?.value||'100'), max_pages:parseInt($('apiMaxPages')?.value||'50'), headers
  };
  if(!cfg.name||!cfg.endpoint)return;
  const res=$('apiResult');res.style.display='block';res.className='result-msg info';res.textContent='保存中...';
  try{
    const resp=await apiPost('/api/v1/ingest/api-config',cfg);
    res.className=`result-msg ${resp.success?'success':'error'}`;
    res.textContent=resp.success?'配置已保存':'失败: '+(resp.error||'未知错误');
    if(resp.success){document.getElementById('apiPullForm').reset();loadAPIConfigs();refreshDCStats();}
  }catch(err){res.className='result-msg error';res.textContent='网络错误: '+err.message;}
}

async function loadAPIConfigs() {
  try{const r=await apiGet('/api/v1/ingest/api-configs').catch(()=>({}));DC.apiConfigs=r.configs||r.data||[];}
  catch{DC.apiConfigs=[];}
  const list=$('apiConfigList');if(!list)return;
  if(!DC.apiConfigs.length){list.innerHTML='<div class="empty-state"><div class="empty-state-icon">🔌</div><div class="empty-state-text">暂无API配置</div></div>';return;}
  list.innerHTML=DC.apiConfigs.map(c=>`
    <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border)">
      <div style="flex:1;min-width:0">
        <div style="font-weight:600;font-size:12px">${c.name||'未命名'}</div>
        <div style="color:var(--text-muted);font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${c.endpoint||''}</div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;font-size:11px">
        <span class="tag tag-purple">${c.method||'GET'}</span>
        <button class="btn btn-sm btn-outline" onclick="deleteAPIConfig('${c.id||c.name}')" style="color:var(--red);padding:2px 6px">🗑</button>
      </div>
    </div>`).join('');
}

async function deleteAPIConfig(id) {
  if(!confirm('删除此API配置?'))return;
  try{await api('DELETE',`/api/v1/ingest/api-config/${id}`)}catch{}
  loadAPIConfigs();refreshDCStats();
}
