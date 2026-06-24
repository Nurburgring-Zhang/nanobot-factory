/* IMDF 交付管理 v2 — 表格 + 筛选 + 详情面板 */
var DELIVERY_FILTER = 'all';
var DELIVERY_DATA = []; // R4-Worker-3: 真实数据缓存 (供详情/审批使用)
var DELIVERY_ERROR = null;

async function renderDelivery() {
  var c = document.getElementById('page-content');
  if (!c) return;

  // R4-Worker-3: 真实 GET /api/delivery/list (无 mock fallback)
  var deliveries = [];
  DELIVERY_ERROR = null;
  try {
    var resp = await apiGet('/api/delivery/list');
    if (resp && resp.success) {
      deliveries = (resp.data && resp.data.deliveries) || resp.deliveries || [];
    } else {
      DELIVERY_ERROR = (resp && (resp.error || resp.message)) || '后端返回非 success';
    }
  } catch (e) {
    DELIVERY_ERROR = e.message || String(e);
  }
  // 兜底: /api/delivery/ (已有端点, 字段不同时降级)
  if (deliveries.length === 0 && !DELIVERY_ERROR) {
    try {
      var resp2 = await apiGet('/api/delivery/');
      if (resp2 && resp2.data && resp2.data.deliveries) {
        deliveries = resp2.data.deliveries;
      }
    } catch (e) {}
  }
  // 不再注入假数据 — 后端无数据即显示空状态
  DELIVERY_DATA = deliveries;

  var pending = 0, approved = 0, rejected = 0;
  for (var i = 0; i < deliveries.length; i++) {
    if (deliveries[i].status === 'pending') pending++;
    else if (deliveries[i].status === 'approved') approved++;
    else rejected++;
  }
  var total = deliveries.length;
  var deliveryRate = total > 0 ? Math.round(approved / total * 100) : 0;

  c.innerHTML = '' +
    '<div class="page-header">' +
      '<div>' +
        '<div class="page-title">📦 交付管理</div>' +
        '<div style="font-size:11px;color:#8888aa;margin-top:2px">数据交付审核 · 格式转换 · 质量追踪 · 交付记录</div>' +
      '</div>' +
      '<div class="page-stats">' +
        '<div class="page-stat"><div class="page-stat-val" style="color:#fbbf24">' + pending + '</div><div class="page-stat-label">待交付</div></div>' +
        '<div class="page-stat"><div class="page-stat-val" style="color:#4ade80">' + approved + '</div><div class="page-stat-label">已交付</div></div>' +
        '<div class="page-stat"><div class="page-stat-val" style="color:#4a7aff">' + deliveryRate + '%</div><div class="page-stat-label">交付率</div></div>' +
      '</div>' +
    '</div>' +
    '<div class="toolbar">' +
      '<button class="btn btn-primary btn-sm" onclick="showCreateDelivery()">➕ 创建交付</button>' +
      '<span style="flex:1"></span>' +
      '<input id="deliverySearch" placeholder="🔍 搜索数据集/目标..." onkeyup="filterDeliveries()" style="max-width:200px">' +
      '<select id="deliveryStatus" onchange="filterDeliveries()" style="min-width:100px">' +
        '<option value="all">全部状态</option>' +
        '<option value="pending">待交付</option>' +
        '<option value="approved">已交付</option>' +
        '<option value="rejected">已退回</option>' +
      '</select>' +
      '<select id="deliveryFormat" onchange="filterDeliveries()" style="min-width:100px">' +
        '<option value="all">全部格式</option>' +
        '<option value="COCO">COCO</option><option value="YOLO">YOLO</option><option value="JSON">JSON</option><option value="CSV">CSV</option><option value="Parquet">Parquet</option><option value="DICOM">DICOM</option>' +
      '</select>' +
    '</div>' +
    '<div style="display:grid;grid-template-columns:1fr 320px;gap:12px">' +
      '<div style="background:#1e1e3a;border:1px solid #2a2a4a;border-radius:8px;overflow:hidden">' +
        '<table class="data-table">' +
          '<thead><tr>' +
            '<th>交付单号</th><th>数据集</th><th>目标</th><th>格式</th><th style="width:70px">状态</th><th style="width:70px">数据量</th><th style="width:70px">质量</th><th style="width:100px">截止日期</th><th style="width:80px">操作</th>' +
          '</tr></thead>' +
          '<tbody id="deliveryTableBody"></tbody>' +
        '</table>' +
      '</div>' +
      '<div id="deliveryDetailPanel" class="side-panel" style="background:#1e1e3a;border:1px solid #2a2a4a;border-radius:8px;padding:14px">' +
        '<div class="section-title">📋 详情</div>' +
        '<div style="color:#8888aa;font-size:12px;text-align:center;padding:40px 0">点击左侧交付单查看详情</div>' +
      '</div>' +
    '</div>';

  renderDeliveryTable(deliveries);
}

function renderDeliveryTable(deliveries) {
  var tbody = document.getElementById('deliveryTableBody');
  if (!tbody) return;

  var statusLabel = { pending:'待交付', approved:'已交付', rejected:'已退回', draft:'草稿' };
  var statusColor = { pending:'#fbbf24', approved:'#4ade80', rejected:'#ef4444', draft:'#8888aa' };
  var statusBg = { pending:'rgba(251,191,36,0.15)', approved:'rgba(74,222,128,0.15)', rejected:'rgba(239,68,68,0.15)', draft:'rgba(136,136,170,0.15)' };

  var search = ((document.getElementById('deliverySearch') || {}).value || '').toLowerCase();
  var statusFilter = (document.getElementById('deliveryStatus') || {}).value || 'all';
  var formatFilter = (document.getElementById('deliveryFormat') || {}).value || 'all';

  var html = '';
  for (var i = 0; i < deliveries.length; i++) {
    var d = deliveries[i];
    // Apply filters
    if (statusFilter !== 'all' && d.status !== statusFilter) continue;
    if (formatFilter !== 'all' && d.format !== formatFilter) continue;
    if (search && (d.dataset + d.target + d.id).toLowerCase().indexOf(search) < 0) continue;

    var deadlineDate = new Date(d.deadline || '');
    var today = new Date();
    var daysLeft = Math.ceil((deadlineDate - today) / 86400000);
    var deadlineColor = daysLeft < 0 ? '#ef4444' : daysLeft <= 3 ? '#fbbf24' : '#8888aa';
    var deadlineText = daysLeft < 0 ? '已逾期' + Math.abs(daysLeft) + '天' : '剩' + daysLeft + '天';

    html += '<tr onclick="showDeliveryDetail(\'' + (d.id || '') + '\')" style="cursor:pointer">' +
      '<td style="font-size:11px;font-family:monospace;color:#4a7aff">' + (d.id || 'DLV-' + (i + 1)) + '</td>' +
      '<td style="font-weight:600">' + (d.dataset || '--') + '</td>' +
      '<td style="font-size:11px;color:#8888aa">' + (d.target || '--') + '</td>' +
      '<td><span class="tag tag-blue">' + (d.format || '--') + '</span></td>' +
      '<td><span style="font-size:10px;padding:2px 8px;border-radius:10px;color:' + (statusColor[d.status] || '#8888aa') + ';background:' + (statusBg[d.status] || '#1e1e3a') + '">' + (statusLabel[d.status] || d.status || '--') + '</span></td>' +
      '<td>' + ((d.items || 0).toLocaleString()) + '</td>' +
      '<td style="font-weight:600;color:' + (d.quality >= 90 ? '#4ade80' : d.quality >= 80 ? '#fbbf24' : '#ef4444') + '">' + (typeof d.quality === 'number' ? d.quality.toFixed(1) : d.quality) + '</td>' +
      '<td style="font-size:11px;color:' + deadlineColor + '">' + (d.deadline ? deadlineText : '--') + '</td>' +
      '<td>' +
        (d.status === 'pending' ? '<button class="btn btn-success btn-sm" onclick="event.stopPropagation();approveDelivery(\'' + (d.id || '') + '\')" style="margin-right:4px">✅</button>' : '') +
        '<button class="btn btn-outline btn-sm" onclick="event.stopPropagation();showDeliveryDetail(\'' + (d.id || '') + '\')">📋</button>' +
      '</td>' +
      '</tr>';
  }

  if (html === '') {
    var emptyHtml;
    if (DELIVERY_ERROR) {
      emptyHtml = '⚠️ 后端加载失败: ' + DELIVERY_ERROR + '<br/><span style="color:#666;font-size:11px">检查 /api/delivery/list 是否可用</span>';
    } else {
      emptyHtml = '📭 暂无匹配的交付记录<br/><span style="color:#666;font-size:11px">点击上方"创建交付"或调整筛选条件</span>';
    }
    html = '<tr><td colspan="9" style="text-align:center;padding:40px;color:#8888aa">' + emptyHtml + '</td></tr>';
  }

  tbody.innerHTML = html;
}

function filterDeliveries() {
  // Re-render is handled by re-fetching real backend data
  renderDelivery();
}

function showDeliveryDetail(id) {
  var panel = document.getElementById('deliveryDetailPanel');
  if (!panel) return;

  // R4-Worker-3: 详情接 API GET /api/delivery/{id}
  var statusLabel = { pending:'待交付', approved:'已交付', rejected:'已退回' };
  var statusColor = { pending:'#fbbf24', approved:'#4ade80', rejected:'#ef4444' };

  function renderDetail(d) {
    if (!d) {
      panel.innerHTML = '' +
        '<div class="section-title">📋 详情</div>' +
        '<div style="color:#8888aa;font-size:12px;text-align:center;padding:40px 0">⚠️ 加载详情失败或后端无数据<br/><span style="color:#666;font-size:11px">' + (DELIVERY_ERROR || '请检查后端 /api/delivery/' + id) + '</span></div>';
      return;
    }
    panel.innerHTML = '' +
      '<div class="section-title">📋 交付详情</div>' +
      '<div style="font-size:12px;line-height:2.2">' +
        '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #2a2a4a"><span style="color:#8888aa">单号</span><span style="font-family:monospace;color:#4a7aff">' + (d.id || '--') + '</span></div>' +
        '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #2a2a4a"><span style="color:#8888aa">数据集</span><span>' + (d.dataset || d.name || '--') + '</span></div>' +
        '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #2a2a4a"><span style="color:#8888aa">目标</span><span>' + (d.target || '--') + '</span></div>' +
        '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #2a2a4a"><span style="color:#8888aa">格式</span><span class="tag tag-blue">' + (d.format || '--') + '</span></div>' +
        '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #2a2a4a"><span style="color:#8888aa">状态</span><span style="color:' + (statusColor[d.status] || '#8888aa') + '">' + (statusLabel[d.status] || d.status) + '</span></div>' +
        '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #2a2a4a"><span style="color:#8888aa">数据量</span><span>' + ((d.items || 0).toLocaleString()) + ' 条</span></div>' +
        '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #2a2a4a"><span style="color:#8888aa">质量评分</span><span style="color:' + ((d.quality || 0) >= 90 ? '#4ade80' : '#fbbf24') + '">' + (typeof d.quality === 'number' ? d.quality.toFixed(1) : (d.quality || '--')) + '</span></div>' +
        '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #2a2a4a"><span style="color:#8888aa">创建日期</span><span>' + (d.created || '--') + '</span></div>' +
        '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #2a2a4a"><span style="color:#8888aa">截止日期</span><span>' + (d.deadline || '--') + '</span></div>' +
        (d.reviewer ? '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #2a2a4a"><span style="color:#8888aa">审核人</span><span>' + d.reviewer + '</span></div>' : '') +
      '</div>' +
      '<div style="margin-top:12px;display:flex;gap:6px;flex-wrap:wrap">' +
        (d.status === 'pending' ? '<button class="btn btn-success btn-sm" onclick="approveDelivery(\'' + (d.id || '') + '\')">✅ 确认交付</button>' : '') +
        (d.status === 'pending' ? '<button class="btn btn-danger btn-sm" onclick="rejectDelivery(\'' + (d.id || '') + '\')">❌ 退回</button>' : '') +
        '<button class="btn btn-outline btn-sm" onclick="downloadDelivery(\'' + (d.id || '') + '\')">📥 下载</button>' +
      '</div>';
  }

  // 先从缓存取, 缓存里没有再调 API
  var cached = null;
  for (var i = 0; i < DELIVERY_DATA.length; i++) {
    if (DELIVERY_DATA[i].id === id) { cached = DELIVERY_DATA[i]; break; }
  }
  if (cached) {
    renderDetail(cached);
    return;
  }

  // 显示加载态
  panel.innerHTML = '<div class="section-title">📋 详情</div><div style="color:#8888aa;font-size:12px;text-align:center;padding:40px 0">加载中...</div>';

  apiGet('/api/delivery/' + encodeURIComponent(id)).then(function(resp) {
    if (resp && resp.success && resp.data) {
      renderDetail(resp.data);
    } else {
      renderDetail(null);
    }
  }).catch(function() {
    renderDetail(null);
  });
}

/* ===== 创建交付 ===== */
function showCreateDelivery() {
  if (typeof showModal !== 'function') return;
  showModal('' +
    '<span class="modal-close" onclick="closeModal()">✕</span>' +
    '<h4 style="margin-bottom:16px;color:#4a7aff">📦 创建交付</h4>' +
    '<div style="display:grid;gap:10px">' +
      '<input id="delDs" placeholder="数据集名称" style="padding:8px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0">' +
      '<input id="delTarget" placeholder="交付目标" style="padding:8px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0">' +
      '<select id="delFormat" style="padding:8px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0">' +
        '<option value="JSON">JSON</option><option value="COCO">COCO</option><option value="YOLO">YOLO</option><option value="CSV">CSV</option><option value="Parquet">Parquet</option>' +
      '</select>' +
      '<input id="delDeadline" type="date" style="padding:8px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0">' +
      '<button onclick="createDelivery()" class="btn btn-primary" style="width:100%;padding:10px">📦 创建交付</button>' +
    '</div>');
}

async function createDelivery() {
  var dataset = (document.getElementById('delDs') || {}).value || '新数据集';
  var target = (document.getElementById('delTarget') || {}).value || '客户';
  var format = (document.getElementById('delFormat') || {}).value || 'JSON';
  var ok = false;
  try {
    var r = await apiPost('/api/delivery/create', { name: dataset, format: format.toLowerCase(), items: [] });
    ok = !!(r && r.success);
  } catch (e) { ok = false; }
  if (typeof closeModal === 'function') closeModal();
  if (typeof showToast === 'function') showToast(ok ? ('交付已创建: ' + dataset) : '创建失败, 请重试', ok ? 'success' : 'error');
  renderDelivery();
}

/* ===== 审批操作 ===== */
// R4-Worker-3: 接真实 API
async function approveDelivery(id) {
  var reviewer = (typeof getCurrentUser === 'function' && getCurrentUser() && getCurrentUser().username) || 'system';
  try {
    var r = await apiPost('/api/delivery/' + encodeURIComponent(id) + '/approve', { reviewer: reviewer, comments: '确认交付' });
    if (r && r.success) {
      if (typeof showToast === 'function') showToast('交付单 ' + id + ' 已确认交付', 'success');
    } else {
      if (typeof showToast === 'function') showToast('操作失败: ' + (r?.error || '未知'), 'error');
    }
  } catch (e) {
    if (typeof showToast === 'function') showToast('网络错误: ' + e.message, 'error');
  }
  renderDelivery();
}

async function rejectDelivery(id) {
  var reviewer = (typeof getCurrentUser === 'function' && getCurrentUser() && getCurrentUser().username) || 'system';
  try {
    var r = await apiPost('/api/delivery/' + encodeURIComponent(id) + '/reject', { reviewer: reviewer, comments: '审核不通过, 已退回' });
    if (r && r.success) {
      if (typeof showToast === 'function') showToast('交付单 ' + id + ' 已退回', 'warning');
    } else {
      if (typeof showToast === 'function') showToast('操作失败: ' + (r?.error || '未知'), 'error');
    }
  } catch (e) {
    if (typeof showToast === 'function') showToast('网络错误: ' + e.message, 'error');
  }
  renderDelivery();
}

async function downloadDelivery(id) {
  try {
    var r = await apiGet('/api/delivery/' + encodeURIComponent(id) + '/download');
    if (r && r.success && r.data && r.data.download_url) {
      if (typeof showToast === 'function') showToast('下载链接已生成: ' + r.data.download_url, 'info');
      // 真实场景: 触发浏览器下载
      try { window.open(r.data.download_url, '_blank'); } catch (e) {}
    } else {
      if (typeof showToast === 'function') showToast('下载准备失败: ' + (r?.error || '未知'), 'error');
    }
  } catch (e) {
    if (typeof showToast === 'function') showToast('网络错误: ' + e.message, 'error');
  }
}
