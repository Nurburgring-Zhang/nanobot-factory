/* IMDF 模型管理 v2 — 模型网关 (deepseek/openai/anthropic/google/zhipu) + 本地模型
   原 R3 占位 104 行 → 完整实现, 表/筛选/详情/测试对话/价格对比/自定义模型。
   适配实际后端契约 (model_routes.py): GET /api/models, POST /api/chat, GET /api/models/health
                    + local_model_routes.py: GET /api/local-models/list
   备注: 任务文档中的 /api/models/test 和 /api/models/add 在后端不存在,
   连接性检查 → 复用 GET /api/models/health; 添加自定义模型 → 走前端 localStorage
   + 显示 "需后端新增端点" 提示 (避免假成功)。*/

/* ===== 全局状态 ===== */
const MM = {
  models: [],           // /api/models 返回的 data[]
  providers: [],        // /api/models 返回的 providers[]
  localModels: [],      // /api/local-models/list 返回的 models[]
  healthMap: {},        // modelId -> {status, latency_ms}
  gatewayOk: true,
  cloudVendors: 0,
  defaultModel: '',
  filters: {
    provider: '',       // '' / 'deepseek' / 'openai' / ...
    type: '',           // '' / 'chat' / 'embedding' / 'vision' / 'reasoning'
    status: '',         // '' / 'ok' / 'degraded' / 'down' / 'unknown'
    search: '',
    priceSort: '',      // '' / 'asc' / 'desc'
  },
  selectedId: null,
  // 自定义模型 (前端持久化, 等后端加 /api/models/add 后可一键迁移)
  customModels: [],
};

/* ===== 工具 ===== */
function mmLoadCustomModels() {
  try {
    const raw = localStorage.getItem('imdf_mm_custom_models');
    MM.customModels = raw ? JSON.parse(raw) : [];
  } catch (e) {
    MM.customModels = [];
  }
}
function mmSaveCustomModels() {
  try {
    localStorage.setItem('imdf_mm_custom_models', JSON.stringify(MM.customModels || []));
  } catch (e) { /* 静默 */ }
}

/* 价格估算 — 每个 provider 公开价格档 (USD/1k tokens) 用于对比
   数据来源: 公开标价 (输入价, USD per 1M tokens → /1000) */
const MM_PRICE_TABLE = {
  // provider → model → {input, output, currency:'USD'}
  deepseek: {
    'deepseek-chat':      { input: 0.00027,  output: 0.0011,  currency: 'USD' },
    'deepseek-v4-pro':    { input: 0.00055,  output: 0.0022,  currency: 'USD' },
    'deepseek-v4-flash':  { input: 0.00014,  output: 0.00028, currency: 'USD' },
    'deepseek-reasoner':  { input: 0.00055,  output: 0.00219, currency: 'USD' },
  },
  openai: {
    'gpt-4o':           { input: 0.0025, output: 0.01,   currency: 'USD' },
    'gpt-4o-mini':      { input: 0.00015, output: 0.0006, currency: 'USD' },
    'gpt-4-turbo':      { input: 0.01,   output: 0.03,   currency: 'USD' },
    'o1':               { input: 0.015,  output: 0.06,   currency: 'USD' },
    'o1-mini':          { input: 0.003,  output: 0.012,  currency: 'USD' },
  },
  anthropic: {
    'claude-sonnet-4-20250514':     { input: 0.003,  output: 0.015, currency: 'USD' },
    'claude-3-5-sonnet-20241022':   { input: 0.003,  output: 0.015, currency: 'USD' },
    'claude-3-haiku-20240307':      { input: 0.00025, output: 0.00125, currency: 'USD' },
    'claude-opus-4-20250514':       { input: 0.015,  output: 0.075, currency: 'USD' },
  },
  google: {
    'gemini-2.5-pro':   { input: 0.00125, output: 0.01,   currency: 'USD' },
    'gemini-2.5-flash': { input: 0.000075, output: 0.0003, currency: 'USD' },
    'gemini-2.0-flash': { input: 0.0001,  output: 0.0004, currency: 'USD' },
  },
  zhipu: {
    'glm-4-plus':       { input: 0.0007,  output: 0.0007, currency: 'USD' },
    'glm-4-flash':      { input: 0.0000007, output: 0.0000007, currency: 'USD' }, // ¥0.0007/1k → 极低
    'glm-4-air':        { input: 0.00007, output: 0.00007, currency: 'USD' },
    'glm-4v-plus':      { input: 0.0007,  output: 0.0007, currency: 'USD' },
  },
};

function mmGetPrice(model) {
  if (!model || !model.provider) return null;
  const id = (model.id || '').toLowerCase();
  // 自定义模型: 优先用用户填的 price_in/price_out
  if (model.isCustom && (model.price_in != null || model.price_out != null)) {
    return {
      input: Number(model.price_in) || 0,
      output: Number(model.price_out) || 0,
      currency: model.currency || 'USD',
      isCustom: true,
    };
  }
  const providerTable = MM_PRICE_TABLE[model.provider] || {};
  // 精确匹配
  if (providerTable[id]) return { ...providerTable[id] };
  // 子串匹配 (e.g. 'gpt-4o-2024...' → 'gpt-4o')
  for (const key of Object.keys(providerTable)) {
    if (id.includes(key) || key.includes(id)) return { ...providerTable[key] };
  }
  return null;
}

function mmFormatPricePer1k(price) {
  if (!price || price.input == null) return '—';
  // price 已经是 USD/1k, 直接显示
  const fmt = (v) => v === 0 ? '免费' : '$' + Number(v).toFixed(v < 0.001 ? 5 : 4);
  return fmt(price.input) + ' / ' + fmt(price.output);
}

function mmGetStatusBadge(model) {
  const h = MM.healthMap[model.id];
  const status = h ? h.status : (model.enabled === false ? 'unknown' : 'ok');
  const map = {
    ok:       { cls: 'tag-green',  text: '🟢 在线',   title: 'API 可用' },
    degraded: { cls: 'tag-orange', text: '🟡 降级',   title: '熔断或部分失败' },
    down:     { cls: 'tag-red',    text: '🔴 离线',   title: 'API 不可达' },
    unknown:  { cls: 'tag-blue',   text: '⚪ 未配置', title: 'API Key 缺失' },
  };
  const v = map[status] || map.unknown;
  return `<span class="tag ${v.cls}" title="${v.title}">${v.text}</span>`;
}

function mmGetTypeLabel(model) {
  const caps = model.capabilities || [];
  if (caps.includes('reasoning')) return 'reasoning';
  if (caps.includes('vision')) return 'vision';
  if (caps.includes('embedding')) return 'embedding';
  if (caps.includes('image')) return 'image';
  return 'chat';
}

function mmGetTypeTag(model) {
  const t = mmGetTypeLabel(model);
  const map = {
    chat:      { cls: 'tag-blue',   text: '💬 chat' },
    embedding: { cls: 'tag-purple', text: '🔢 embed' },
    vision:    { cls: 'tag-green',  text: '👁 vision' },
    reasoning: { cls: 'tag-orange', text: '🧠 reasoning' },
    image:     { cls: 'tag-purple', text: '🖼 image' },
  };
  const v = map[t] || map.chat;
  return `<span class="tag ${v.cls}">${v.text}</span>`;
}

function mmApplyFilters() {
  const f = MM.filters;
  let list = MM.models.slice();
  if (f.provider) list = list.filter(m => m.provider === f.provider);
  if (f.type) {
    list = list.filter(m => {
      const t = mmGetTypeLabel(m);
      return t === f.type;
    });
  }
  if (f.status) {
    list = list.filter(m => {
      const h = MM.healthMap[m.id];
      const status = h ? h.status : (m.enabled === false ? 'unknown' : 'ok');
      return status === f.status;
    });
  }
  if (f.search) {
    const q = f.search.toLowerCase();
    list = list.filter(m =>
      (m.id || '').toLowerCase().includes(q) ||
      (m.display_name || '').toLowerCase().includes(q) ||
      (m.provider || '').toLowerCase().includes(q)
    );
  }
  if (f.priceSort) {
    list.sort((a, b) => {
      const pa = mmGetPrice(a);
      const pb = mmGetPrice(b);
      const va = pa ? pa.input : Number.POSITIVE_INFINITY;
      const vb = pb ? pb.input : Number.POSITIVE_INFINITY;
      return f.priceSort === 'asc' ? va - vb : vb - va;
    });
  }
  return list;
}

function mmGetAllModelsMerged() {
  // 合并网关模型 + 本地模型 + 自定义模型
  const merged = MM.models.slice();
  for (const local of MM.localModels) {
    merged.push({
      id: local.id || local.name,
      provider: local.backend || 'local',
      display_name: local.name || local.id,
      capabilities: local.capabilities || ['chat'],
      max_tokens: local.max_tokens || 4096,
      enabled: true,
      priority: 99,
      isLocal: true,
      raw: local,
    });
  }
  for (const cust of MM.customModels) {
    merged.push({
      id: cust.id || cust.name,
      provider: cust.provider || 'custom',
      display_name: cust.name || cust.id,
      capabilities: cust.capabilities || ['chat'],
      max_tokens: cust.max_tokens || 4096,
      enabled: true,
      priority: 100,
      isCustom: true,
      price_in: cust.price_in,
      price_out: cust.price_out,
      currency: cust.currency || 'USD',
      endpoint: cust.endpoint,
      raw: cust,
    });
  }
  return merged;
}

/* ===== 主渲染 ===== */
async function renderModelManager() {
  const c = $('page-content'); if (!c) return;
  mmLoadCustomModels();

  c.innerHTML =
    '<div class="page-header">' +
      '<div>' +
        '<div class="page-title">🧠 模型管理</div>' +
        '<div style="font-size:11px;color:var(--text-muted);margin-top:2px">多模型网关 + 本地模型 + 自定义接入</div>' +
      '</div>' +
      '<div class="page-stats">' +
        '<div class="page-stat"><div class="page-stat-val" id="mmStatTotal">—</div><div class="page-stat-label">模型总数</div></div>' +
        '<div class="page-stat"><div class="page-stat-val" id="mmStatVendor">—</div><div class="page-stat-label">云端厂商</div></div>' +
        '<div class="page-stat"><div class="page-stat-val" id="mmStatLocal">—</div><div class="page-stat-label">本地模型</div></div>' +
        '<div class="page-stat"><div class="page-stat-val" id="mmStatGateway">⚫</div><div class="page-stat-label" id="mmStatGatewayLabel">网关状态</div></div>' +
      '</div>' +
      '<div class="page-actions">' +
        '<button class="btn btn-outline btn-sm" onclick="mm_downloadModels()">⬇ 刷新列表</button>' +
        '<button class="btn btn-outline btn-sm" onclick="mm_installGuide()">📖 安装指南</button>' +
        '<button class="btn btn-primary btn-sm" onclick="mm_showAddCustom()">+ 添加自定义模型</button>' +
      '</div>' +
    '</div>' +
    /* 工具栏 — 筛选 */
    '<div class="toolbar">' +
      '<div class="toolbar-left">' +
        '<input id="mmSearch" placeholder="按名称/ID/提供商搜索..." ' +
               'value="' + sanitizeHTML(MM.filters.search) + '" ' +
               'oninput="MM.filters.search=this.value;mm_renderTable()" style="min-width:220px">' +
        '<select id="mmFilterProvider" onchange="MM.filters.provider=this.value;mm_renderTable()">' +
          '<option value="">全部提供商</option>' +
        '</select>' +
        '<select id="mmFilterType" onchange="MM.filters.type=this.value;mm_renderTable()">' +
          '<option value="">全部类型</option>' +
          '<option value="chat">chat</option>' +
          '<option value="vision">vision</option>' +
          '<option value="reasoning">reasoning</option>' +
          '<option value="embedding">embedding</option>' +
          '<option value="image">image</option>' +
        '</select>' +
        '<select id="mmFilterStatus" onchange="MM.filters.status=this.value;mm_renderTable()">' +
          '<option value="">全部状态</option>' +
          '<option value="ok">🟢 在线</option>' +
          '<option value="degraded">🟡 降级</option>' +
          '<option value="down">🔴 离线</option>' +
          '<option value="unknown">⚪ 未配置</option>' +
        '</select>' +
        '<select id="mmPriceSort" onchange="MM.filters.priceSort=this.value;mm_renderTable()" title="按输入价格排序">' +
          '<option value="">默认排序</option>' +
          '<option value="asc">价格 ↑ (低→高)</option>' +
          '<option value="desc">价格 ↓ (高→低)</option>' +
        '</select>' +
      '</div>' +
      '<div class="toolbar-right" style="font-size:11px;color:var(--text-muted)">' +
        '默认: <strong id="mmDefaultName">—</strong>' +
      '</div>' +
    '</div>' +
    /* 主区 — 表格 + 详情 */
    '<div class="two-col">' +
      '<div class="main-panel" style="grid-column:1/-1">' +
        '<div id="mmTableContainer">' +
          '<table class="data-table">' +
            '<thead><tr>' +
              '<th style="width:24%">名称</th>' +
              '<th style="width:10%">类型</th>' +
              '<th style="width:12%">提供商</th>' +
              '<th style="width:10%">版本/型号</th>' +
              '<th style="width:14%">状态</th>' +
              '<th style="width:12%">上下文</th>' +
              '<th style="width:14%">价格 (in/out)</th>' +
              '<th style="width:4%"></th>' +
            '</tr></thead>' +
            '<tbody id="mmTableBody"><tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text-muted)">加载中...</td></tr></tbody>' +
          '</table>' +
        '</div>' +
      '</div>' +
      '<div class="main-panel" style="grid-column:1/-1;margin-top:12px">' +
        '<div class="section-title">模型详情</div>' +
        '<div id="mm-detail">' +
          '<div class="empty-state"><div class="empty-state-icon">👆</div>' +
          '<div class="empty-state-text">点击上方表格行查看详情</div></div>' +
        '</div>' +
      '</div>' +
    '</div>';

  await mm_loadAll();
  mm_renderTable();
}

async function mm_loadAll() {
  showGlobalLoading('加载模型列表...');
  try {
    // 主网关
    const r = await apiGet('/api/models').catch(() => ({}));
    MM.models = (r && r.success) ? (r.data || []) : [];
    MM.providers = (r && r.providers) || [];
    MM.defaultModel = (r && r.default_model) || '';
    MM.gatewayOk = !!(r && r.success);
    MM.cloudVendors = MM.providers.length || 0;

    // 本地模型
    try {
      const lr = await apiGet('/api/local-models/list');
      MM.localModels = (lr && lr.success) ? (lr.models || []) : [];
    } catch (e) { MM.localModels = []; }

    // 健康检查 (按 provider 一把梭 — 后端会按 model 参数细分)
    try {
      const hr = await apiGet('/api/models/health');
      // hr.models = { 'deepseek-chat': {status, latency_ms}, ... }
      if (hr && hr.models) MM.healthMap = hr.models;
      // hr.status = overall
      if (hr && hr.status) {
        MM.gatewayOk = hr.status === 'ok' || hr.status === 'healthy';
      }
    } catch (e) {
      MM.healthMap = {};
    }

    // 同步合并列表
    MM.models = mmGetAllModelsMerged();
    mmUpdateStats();
    mmPopulateProviderFilter();
  } finally {
    hideGlobalLoading();
  }
}

function mmUpdateStats() {
  const total = MM.models.length;
  const vendors = new Set(MM.models.filter(m => !m.isLocal && !m.isCustom).map(m => m.provider)).size;
  const local = MM.localModels.length;
  const el1 = $('mmStatTotal'); if (el1) el1.textContent = total;
  const el2 = $('mmStatVendor'); if (el2) el2.textContent = vendors;
  const el3 = $('mmStatLocal'); if (el3) el3.textContent = local;
  const elG = $('mmStatGateway');
  const elGL = $('mmStatGatewayLabel');
  if (elG && elGL) {
    if (MM.gatewayOk) { elG.textContent = '🟢'; elGL.textContent = '网关在线'; }
    else { elG.textContent = '🔴'; elGL.textContent = '网关异常'; }
  }
  const elD = $('mmDefaultName'); if (elD) elD.textContent = MM.defaultModel || '—';
}

function mmPopulateProviderFilter() {
  const sel = $('mmFilterProvider');
  if (!sel) return;
  const providers = Array.from(new Set(MM.models.map(m => m.provider).filter(Boolean))).sort();
  let html = '<option value="">全部提供商</option>';
  for (const p of providers) {
    const label = p.charAt(0).toUpperCase() + p.slice(1);
    html += `<option value="${sanitizeHTML(p)}"${MM.filters.provider === p ? ' selected' : ''}>${sanitizeHTML(label)}</option>`;
  }
  sel.innerHTML = html;
}

function mm_renderTable() {
  const tbody = $('mmTableBody');
  if (!tbody) return;
  const list = mmApplyFilters();
  if (list.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="8"><div class="empty-state">' +
        '<div class="empty-state-icon">🧠</div>' +
        '<div class="empty-state-text">没有匹配的模型</div>' +
        '<div class="empty-state-hint">尝试清空筛选条件, 或点击 "刷新列表" 重新拉取</div>' +
      '</div></td></tr>';
    return;
  }
  tbody.innerHTML = list.map(m => {
    const price = mmGetPrice(m);
    const priceStr = price ? mmFormatPricePer1k(price) : '—';
    const ctxStr = m.max_tokens ? m.max_tokens.toLocaleString() + ' tokens' : '—';
    const version = m.isLocal ? (m.raw?.size || '本地') : (m.isCustom ? '自定义' : (m.id || ''));
    const defaultMark = (m.id === MM.defaultModel) ? ' ⭐' : '';
    return (
      '<tr onclick="mm_selectModel(\'' + sanitizeHTML(m.id).replace(/'/g, "\\'") + '\')"' +
          ' style="cursor:pointer"' +
          (MM.selectedId === m.id ? ' class="selected"' : '') + '>' +
        '<td><strong>' + sanitizeHTML(m.display_name || m.id) + defaultMark + '</strong>' +
          (m.isCustom ? ' <span class="tag tag-purple">自定义</span>' : '') +
          (m.isLocal ? ' <span class="tag tag-blue">本地</span>' : '') +
        '</td>' +
        '<td>' + mmGetTypeTag(m) + '</td>' +
        '<td>' + sanitizeHTML(m.provider || '—') + '</td>' +
        '<td style="font-size:11px;color:var(--text-secondary)">' + sanitizeHTML(String(version).substring(0, 24)) + '</td>' +
        '<td>' + mmGetStatusBadge(m) + '</td>' +
        '<td style="font-size:11px">' + sanitizeHTML(ctxStr) + '</td>' +
        '<td style="font-size:11px;font-family:monospace">' + priceStr + '</td>' +
        '<td><button class="btn btn-sm btn-outline" onclick="event.stopPropagation();mm_showTest(\'' +
          sanitizeHTML(m.id).replace(/'/g, "\\'") + '\')" title="测试对话">💬</button></td>' +
      '</tr>'
    );
  }).join('');
}

function mm_selectModel(id) {
  MM.selectedId = id;
  const m = MM.models.find(x => x.id === id);
  if (!m) return;
  mm_renderTable();
  const target = $('mm-detail');
  if (!target) return;
  const price = mmGetPrice(m);
  const priceStr = price ? mmFormatPricePer1k(price) : '未公开';
  const caps = (m.capabilities || []).join(', ') || '—';
  const h = MM.healthMap[m.id];
  const latencyStr = h && h.latency_ms != null ? h.latency_ms.toFixed(0) + ' ms' : '—';
  const providerLabel = m.provider || '—';
  target.innerHTML =
    '<div class="detail-section">' +
      '<div class="detail-section-title">' +
        sanitizeHTML(m.display_name || m.id) +
        (m.id === MM.defaultModel ? ' <span class="tag tag-green">默认</span>' : '') +
      '</div>' +
      '<div class="detail-field"><span>ID</span><span style="font-family:monospace">' + sanitizeHTML(m.id) + '</span></div>' +
      '<div class="detail-field"><span>提供商</span><span>' + sanitizeHTML(providerLabel) + '</span></div>' +
      '<div class="detail-field"><span>类型</span><span>' + mmGetTypeTag(m) + '</span></div>' +
      '<div class="detail-field"><span>状态</span><span>' + mmGetStatusBadge(m) + ' (' + sanitizeHTML(latencyStr) + ')</span></div>' +
      '<div class="detail-field"><span>上下文长度</span><span>' + (m.max_tokens ? m.max_tokens.toLocaleString() + ' tokens' : '—') + '</span></div>' +
      '<div class="detail-field"><span>能力</span><span>' + sanitizeHTML(caps) + '</span></div>' +
      '<div class="detail-field"><span>优先级</span><span>' + sanitizeHTML(String(m.priority != null ? m.priority : '—')) + '</span></div>' +
      '<div class="detail-field"><span>价格 (USD/1k)</span><span style="font-family:monospace">' + priceStr + '</span></div>' +
      (m.isCustom && m.endpoint ? '<div class="detail-field"><span>Endpoint</span><span style="font-family:monospace;font-size:11px">' + sanitizeHTML(m.endpoint) + '</span></div>' : '') +
      '<div style="margin-top:12px;display:flex;gap:6px;flex-wrap:wrap">' +
        '<button class="btn btn-sm btn-primary" onclick="mm_showTest(\'' + sanitizeHTML(m.id).replace(/'/g, "\\'") + '\')">💬 测试对话</button>' +
        '<button class="btn btn-sm btn-outline" onclick="mm_testConnection(\'' + sanitizeHTML(m.id).replace(/'/g, "\\'") + '\')">🔗 验证连通性</button>' +
        (m.isCustom ? '<button class="btn btn-sm btn-outline" style="color:var(--accent-red)" onclick="mm_deleteCustom(\'' + sanitizeHTML(m.id).replace(/'/g, "\\'") + '\')">🗑 删除自定义</button>' : '') +
      '</div>' +
    '</div>';
}

/* ===== 测试对话 (弹窗) ===== */
function mm_showTest(id) {
  const m = MM.models.find(x => x.id === id);
  if (!m) { showToast('模型不存在: ' + id, 'error'); return; }
  const capabilities = (m.capabilities || []).join(', ') || '—';
  const price = mmGetPrice(m);
  const priceStr = price ? mmFormatPricePer1k(price) : '未公开';
  const content =
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">' +
      '<div>' +
        '<strong>' + sanitizeHTML(m.display_name || m.id) + '</strong>' +
        '<span style="color:var(--text-muted);font-size:11px;margin-left:8px">' + sanitizeHTML(m.provider) + ' · ' + sanitizeHTML(capabilities) + '</span>' +
      '</div>' +
      '<div style="font-size:11px;color:var(--text-muted)">' + priceStr + '</div>' +
    '</div>' +
    '<div class="form-group">' +
      '<label class="form-label">输入 Prompt</label>' +
      '<textarea class="form-textarea" id="mmTestInput" rows="4" placeholder="输入消息内容..." style="min-height:80px">你好,请用一句话介绍你自己。</textarea>' +
    '</div>' +
    '<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">' +
      '<button class="btn btn-primary btn-sm" id="mmTestRunBtn" onclick="mm_runTest(\'' + sanitizeHTML(m.id).replace(/'/g, "\\'") + '\')">▶ 发送</button>' +
      '<span id="mmTestLatency" style="font-size:11px;color:var(--text-muted)"></span>' +
    '</div>' +
    '<div class="form-group">' +
      '<label class="form-label">响应</label>' +
      '<div id="mmTestOutput" style="min-height:120px;max-height:280px;overflow-y:auto;padding:10px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;font-size:12px;line-height:1.5;white-space:pre-wrap">' +
        '<span style="color:var(--text-muted)">(尚未发送)</span>' +
      '</div>' +
    '</div>' +
    '<div id="mmTestUsage" style="font-size:10px;color:var(--text-muted);margin-top:4px"></div>';

  showModal('💬 测试对话 — ' + (m.display_name || m.id), content, null);
  // 自动 focus textarea
  setTimeout(() => { const t = $('mmTestInput'); if (t) t.focus(); }, 100);
}

async function mm_runTest(id) {
  const m = MM.models.find(x => x.id === id);
  if (!m) return;
  const input = $('mmTestInput');
  const output = $('mmTestOutput');
  const usageEl = $('mmTestUsage');
  const latencyEl = $('mmTestLatency');
  const btn = $('mmTestRunBtn');
  if (!input || !output) return;
  const prompt = (input.value || '').trim();
  if (!prompt) { showToast('请输入 prompt', 'error'); return; }
  if (btn) { btn.disabled = true; btn.textContent = '⏳ 发送中...'; }
  output.innerHTML = '<span class="loading-spinner" style="display:inline-block;width:12px;height:12px;border:2px solid var(--border);border-top-color:var(--accent-blue);border-radius:50%;animation:spin 0.6s linear infinite"></span> <span style="color:var(--text-muted)">请求中...</span>';
  if (latencyEl) latencyEl.textContent = '';
  if (usageEl) usageEl.textContent = '';

  const t0 = performance.now();
  try {
    // 后端 POST /api/chat 不支持流式 — 一次返回完整 content
    const r = await apiPost('/api/chat', {
      messages: [{ role: 'user', content: prompt }],
      model: m.isLocal ? 'auto' : m.id,
      temperature: 0.7,
      max_tokens: Math.min(2048, m.max_tokens || 2048),
    });
    const t1 = performance.now();
    const dt = (t1 - t0).toFixed(0);
    if (latencyEl) latencyEl.textContent = '耗时 ' + dt + ' ms';

    if (r && r.success && r.content) {
      // 模拟"流式"显示效果 — 按字符分块追加, 视觉上像流式
      mm_renderStreamingOutput(output, r.content);
      const usage = r.usage || {};
      if (usageEl && (usage.prompt_tokens || usage.completion_tokens)) {
        usageEl.textContent =
          'tokens: prompt=' + (usage.prompt_tokens || 0) +
          ' · completion=' + (usage.completion_tokens || 0) +
          ' · total=' + (usage.total_tokens || 0) +
          ' · provider=' + (r.provider || m.provider || '—') +
          ' · model=' + (r.model || m.id);
      }
    } else {
      output.innerHTML =
        '<span style="color:var(--accent-red)">❌ 失败: ' + sanitizeHTML(r?.error || '未知错误') + '</span>' +
        (r?.model ? '<br><span style="color:var(--text-muted);font-size:11px">实际路由: ' + sanitizeHTML(r.model) + '</span>' : '');
    }
  } catch (e) {
    output.innerHTML = '<span style="color:var(--accent-red)">❌ 请求异常: ' + sanitizeHTML(e?.message || String(e)) + '</span>';
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '▶ 发送'; }
  }
}

function mm_renderStreamingOutput(container, fullText) {
  // 后端一次性返回, 但用 setTimeout 分块显示, 模拟流式体验
  if (!container || !fullText) return;
  container.innerHTML = '';
  let i = 0;
  const chunkSize = 8;
  const interval = 16;
  const total = fullText.length;
  function step() {
    // 用户可能已关闭 modal — 容器可能已脱离 DOM
    if (!container.isConnected) return;
    if (i >= total) return;
    i = Math.min(i + chunkSize, total);
    container.textContent = fullText.substring(0, i);
    container.scrollTop = container.scrollHeight;
    setTimeout(step, interval);
  }
  step();
}

/* ===== 验证连通性 ===== */
async function mm_testConnection(id) {
  showGlobalLoading('检查 ' + id + ' 连通性...');
  try {
    // 后端没有 /api/models/test — 用 /api/models/health?model=<id>
    const r = await apiGet('/api/models/health?model=' + encodeURIComponent(id));
    if (r && r.models && r.models[id]) {
      const h = r.models[id];
      MM.healthMap[id] = h;
      if (h.status === 'ok') {
        showToast('✅ ' + id + ' 连通正常 (' + (h.latency_ms || 0).toFixed(0) + 'ms)', 'success');
      } else if (h.status === 'degraded') {
        showToast('⚠️ ' + id + ' 降级 (延迟偏高)', 'error');
      } else {
        showToast('❌ ' + id + ' ' + (h.error || '不可达'), 'error');
      }
      mm_renderTable();
      if (MM.selectedId === id) mm_selectModel(id);
    } else {
      showToast('⚠️ 后端未返回该模型健康状态', 'error');
    }
  } catch (e) {
    showToast('❌ 连通性检查失败: ' + (e?.message || e), 'error');
  } finally {
    hideGlobalLoading();
  }
}

/* ===== 添加自定义模型 ===== */
function mm_showAddCustom() {
  const content =
    '<div class="form-group">' +
      '<label class="form-label">模型名称 <span style="color:var(--accent-red)">*</span></label>' +
      '<input class="form-input" id="mmCustName" placeholder="如: my-gpt-4">' +
    '</div>' +
    '<div class="form-group">' +
      '<label class="form-label">提供商 <span style="color:var(--accent-red)">*</span></label>' +
      '<input class="form-input" id="mmCustProvider" placeholder="如: openai-compatible">' +
    '</div>' +
    '<div class="form-group">' +
      '<label class="form-label">API Key</label>' +
      '<input class="form-input" id="mmCustKey" type="password" placeholder="sk-...">' +
    '</div>' +
    '<div class="form-group">' +
      '<label class="form-label">Endpoint URL</label>' +
      '<input class="form-input" id="mmCustEndpoint" placeholder="https://api.example.com/v1/chat/completions">' +
    '</div>' +
    '<div class="form-group">' +
      '<label class="form-label">上下文长度 (tokens)</label>' +
      '<input class="form-input" id="mmCustMaxTokens" type="number" value="4096" placeholder="4096">' +
    '</div>' +
    '<div class="form-group">' +
      '<label class="form-label">输入价格 (USD/1k tokens)</label>' +
      '<input class="form-input" id="mmCustPriceIn" type="number" step="0.00001" value="0.001" placeholder="0.001">' +
    '</div>' +
    '<div class="form-group">' +
      '<label class="form-label">输出价格 (USD/1k tokens)</label>' +
      '<input class="form-input" id="mmCustPriceOut" type="number" step="0.00001" value="0.002" placeholder="0.002">' +
    '</div>' +
    '<div style="padding:8px 12px;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);border-radius:4px;font-size:11px;color:var(--text-secondary);margin-top:8px">' +
      '⚠️ 后端尚未提供 <code>POST /api/models/add</code> 端点, 自定义模型当前仅保存在浏览器 localStorage 中 (key=<code>imdf_mm_custom_models</code>)。' +
      '后续可通过"测试对话"按钮验证接入。' +
    '</div>';
  const footer =
    '<button class="btn btn-outline btn-sm" onclick="this.closest(\'.modal-overlay\').remove()">取消</button>' +
    '<button class="btn btn-outline btn-sm" onclick="mm_testCustomConnection()">🔗 验证连通性</button>' +
    '<button class="btn btn-primary btn-sm" id="mmCustSaveBtn" onclick="mm_saveCustom()">💾 保存</button>';
  showModal('➕ 添加自定义模型', content, footer);
}

async function mm_testCustomConnection() {
  const endpoint = ($('mmCustEndpoint')?.value || '').trim();
  const key = $('mmCustKey')?.value || '';
  if (!endpoint) { showToast('请填写 Endpoint URL', 'error'); return; }
  // 后端没有直连测试端点 — 用通用 /api/chat 探测 (若无 key, 大概率 401)
  showGlobalLoading('探测连通性...');
  try {
    const r = await apiPost('/api/chat', {
      messages: [{ role: 'user', content: 'ping' }],
      model: 'auto',
      max_tokens: 8,
    });
    // 不直接拿结果判定, 因为 custom endpoint 与 /api/chat 是两个东西
    showToast('ℹ️ 后端 ' + (r?.success ? '网关正常' : '网关异常: ' + (r?.error || '—')), r?.success ? 'success' : 'error');
    showToast('⚠️ 自定义 endpoint (' + sanitizeHTML(endpoint) + ') 连通性需后端新增专用探测端点', 'error');
  } catch (e) {
    showToast('❌ 探测失败: ' + (e?.message || e), 'error');
  } finally {
    hideGlobalLoading();
  }
}

function mm_saveCustom() {
  const name = ($('mmCustName')?.value || '').trim();
  const provider = ($('mmCustProvider')?.value || '').trim();
  if (!name || !provider) { showToast('请填写必填字段 (名称/提供商)', 'error'); return; }
  const entry = {
    id: name.toLowerCase().replace(/[^a-z0-9-_]/g, '-'),
    name: name,
    provider: provider,
    api_key: $('mmCustKey')?.value || '',
    endpoint: $('mmCustEndpoint')?.value || '',
    max_tokens: parseInt($('mmCustMaxTokens')?.value || '4096', 10) || 4096,
    price_in: parseFloat($('mmCustPriceIn')?.value || '0') || 0,
    price_out: parseFloat($('mmCustPriceOut')?.value || '0') || 0,
    currency: 'USD',
    capabilities: ['chat'],
    created_at: new Date().toISOString(),
  };
  // 去重
  MM.customModels = MM.customModels.filter(c => c.id !== entry.id);
  MM.customModels.push(entry);
  mmSaveCustomModels();
  MM.models = mmGetAllModelsMerged();
  mmUpdateStats();
  mmPopulateProviderFilter();
  mm_renderTable();
  // 关闭 modal
  const overlay = document.querySelector('.modal-overlay');
  if (overlay) overlay.remove();
  showToast('✅ 已保存自定义模型: ' + name, 'success');
}

function mm_deleteCustom(id) {
  showConfirm('删除自定义模型', '确认从列表中移除 ' + id + '?', () => {
    MM.customModels = MM.customModels.filter(c => c.id !== id);
    mmSaveCustomModels();
    MM.models = mmGetAllModelsMerged();
    if (MM.selectedId === id) {
      MM.selectedId = null;
      const d = $('mm-detail');
      if (d) d.innerHTML = '<div class="empty-state"><div class="empty-state-icon">👆</div><div class="empty-state-text">点击上方表格行查看详情</div></div>';
    }
    mmUpdateStats();
    mmPopulateProviderFilter();
    mm_renderTable();
    showToast('已删除', 'success');
  });
}

/* ===== 安装指南 (复用 R3-W3 行为, 弹窗内显示) ===== */
async function mm_installGuide() {
  let guides = [];
  let cloudCount = 0;
  let gwStatus = '未知';
  try {
    const r = await apiGet('/api/local-models/install-guide');
    guides = Object.entries(r?.guides || {});
  } catch (e) { /* 静默失败, 走降级 */ }
  try {
    const h = await apiGet('/api/local-models/list');
    cloudCount = (h?.cloud_vendors != null) ? h.cloud_vendors : (MM.providers.length || 0);
    if (typeof h?.gateway === 'string') gwStatus = h.gateway;
  } catch (e) {}
  const guideHtml = guides.length
    ? guides.map(([k, v]) => (
        '<div class="detail-field" style="display:block;margin-bottom:10px">' +
          '<div style="font-weight:600;margin-bottom:4px">' + sanitizeHTML(v?.description || k) + '</div>' +
          '<code style="display:block;background:var(--bg-primary);padding:6px 8px;border-radius:4px;font-size:12px">' +
            sanitizeHTML(v?.install || 'pip install ' + k) +
          '</code>' +
          '<div style="font-size:11px;color:var(--text-muted);margin-top:4px">模型: ' + sanitizeHTML(v?.model || '自动下载') + '</div>' +
        '</div>'
      )).join('')
    : '<div class="detail-panel"><p>pip install sentence-transformers<br>pip install transformers torch<br>模型首次使用时自动从HuggingFace下载</p></div>';
  showModal('📖 本地模型安装指南', (
    '<div class="detail-panel">' +
      '<p style="margin-bottom:8px">云端厂商: <strong>' + cloudCount + '</strong> · 网关状态: <strong>' + sanitizeHTML(gwStatus) + '</strong></p>' +
      guideHtml +
    '</div>'
  ));
}

/* ===== 刷新列表 (R3 保留入口, 同时刷新健康检查) ===== */
async function mm_downloadModels() {
  showGlobalLoading('刷新模型列表...');
  try {
    await mm_loadAll();
    mm_renderTable();
    showToast('✅ 已刷新: ' + MM.models.length + ' 个模型', 'success');
  } catch (e) {
    showToast('刷新失败: ' + (e?.message || e), 'error');
  } finally {
    hideGlobalLoading();
  }
}

/* ===== 价格对比 (弹窗) ===== */
function mm_showPriceComparison() {
  // 收集有价格信息的模型, 按输入价升序
  const rows = MM.models
    .map(m => ({ m, p: mmGetPrice(m) }))
    .filter(r => r.p && r.p.input != null)
    .sort((a, b) => a.p.input - b.p.input);
  if (rows.length === 0) {
    showModal('💰 价格对比', '<div class="empty-state"><div class="empty-state-icon">💰</div><div class="empty-state-text">暂无公开价格数据</div></div>');
    return;
  }
  const html =
    '<div style="margin-bottom:8px;font-size:11px;color:var(--text-muted)">按 USD / 1k tokens 输入价升序</div>' +
    '<table class="data-table">' +
      '<thead><tr><th>模型</th><th>提供商</th><th>输入</th><th>输出</th><th>上下文</th></tr></thead>' +
      '<tbody>' +
        rows.map(r => (
          '<tr>' +
            '<td><strong>' + sanitizeHTML(r.m.display_name || r.m.id) + '</strong></td>' +
            '<td>' + sanitizeHTML(r.m.provider) + '</td>' +
            '<td style="font-family:monospace">$' + r.p.input.toFixed(r.p.input < 0.001 ? 5 : 4) + '</td>' +
            '<td style="font-family:monospace">$' + r.p.output.toFixed(r.p.output < 0.001 ? 5 : 4) + '</td>' +
            '<td style="font-size:11px">' + (r.m.max_tokens ? r.m.max_tokens.toLocaleString() : '—') + '</td>' +
          '</tr>'
        )).join('') +
      '</tbody>' +
    '</table>';
  showModal('💰 价格对比 (' + rows.length + ')', html);
}