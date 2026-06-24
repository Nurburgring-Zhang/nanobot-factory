/* IMDF 质量管线 v2 — 6分类折叠 + 算子卡片 + 状态追踪 */
let PIPELINE_OP_STATUS = {}; // R4-Worker-3: 算子真实状态 (来自 /api/pipeline/operators/status)
let PIPELINE_OP_STATUS_FETCHED = false;

async function renderPipeline() {
  const c = $('page-content'); if (!c) return;

  const categories = {
    '采集': { icon: '📥', color: '#4a9', ops: ['web_scraper','rss_feed','api_puller','db_sync','file_import','clipboard','screenshot'] },
    '清洗': { icon: '🧹', color: '#49a', ops: ['null_filter','dedup','html_cleaner','json_parser','template_fill','stopword','lowercase','strip','regex','normalize','emoji','url','date'] },
    '标注': { icon: '🖌️', color: '#a49', ops: ['bbox','polygon','point','line','text_annotate','classify','relation','ocr'] },
    '评分': { icon: '⭐', color: '#9a4', ops: ['quality_score','consistency','completeness','readability','aesthetics'] },
    '筛选': { icon: '🔍', color: '#94a', ops: ['threshold','topk','random','dedup2','field_filter'] },
    '导出': { icon: '📤', color: '#a94', ops: ['json_export','csv_export','coco_export','yolo_export','parquet','tfrecord'] },
  };

  const opLabels = {
    web_scraper:'Web爬虫',rss_feed:'RSS订阅',api_puller:'API拉取',db_sync:'DB同步',file_import:'文件导入',clipboard:'剪贴板',screenshot:'截图',
    null_filter:'空值过滤',dedup:'去重',html_cleaner:'HTML清洗',json_parser:'JSON解析',template_fill:'模板填充',stopword:'停用词',lowercase:'小写化',strip:'去空格',regex:'正则',normalize:'标准化',emoji:'表情过滤',url:'URL清洗',date:'日期标准化',
    bbox:'BBox标注',polygon:'多边形',point:'关键点',line:'线条',text_annotate:'文本标注',classify:'分类',relation:'关系',ocr:'OCR识别',
    quality_score:'质量评分',consistency:'一致性',completeness:'完整性',readability:'可读性',aesthetics:'美观度',
    threshold:'阈值过滤',topk:'TopK',random:'随机',dedup2:'去重2',field_filter:'字段过滤',
    json_export:'JSON',csv_export:'CSV',coco_export:'COCO',yolo_export:'YOLO',parquet:'Parquet',tfrecord:'TFRecord'
  };

  const opDescs = {
    web_scraper:'从网页抓取结构化数据',rss_feed:'订阅RSS源自动采集',api_puller:'从外部API定时拉取',db_sync:'从数据库同步数据',file_import:'导入本地文件(CSV/JSON等)',clipboard:'从剪贴板读取数据',screenshot:'截取网页/应用截图',
    null_filter:'过滤空值/缺失数据行',dedup:'基于内容哈希去重',html_cleaner:'清洗HTML标签和属性',json_parser:'解析并结构化JSON数据',template_fill:'基于模板生成数据',stopword:'移除停用词',lowercase:'统一转为小写',strip:'去除首尾空白',regex:'正则表达式匹配/替换',normalize:'Unicode标准化',emoji:'过滤或转换表情符号',url:'清洗/标准化URL链接',date:'统一日期格式',
    bbox:'绘制矩形边界框',polygon:'绘制多边形区域',point:'标注关键点',line:'绘制线条/边界',text_annotate:'文本标注/转录',classify:'分类标签标注',relation:'关系标注(实体-关系)',ocr:'OCR文字识别',
  };

  // R4-Worker-3: 算子真实状态从 /api/pipeline/operators/status 拉取 (替代 Math.random)
  // P1-C-W2: three-state via client.js
  try {
    var stRes = await window.httpGet('/api/pipeline/operators/status', { timeoutMs: 15000 });
    if (stRes.state === window.HTTP_STATE.SUCCESS) {
      var stResp = stRes.data || {};
      if (stResp && stResp.success && stResp.operators) {
        PIPELINE_OP_STATUS = {};
        for (var si = 0; si < stResp.operators.length; si++) {
          var opItem = stResp.operators[si];
          PIPELINE_OP_STATUS[opItem.operator] = opItem.status || 'idle';
        }
        PIPELINE_OP_STATUS_FETCHED = true;
      }
    } else {
      window.IMDF_ERROR.onApiError('pipeline.opStatus', stRes.error);
    }
  } catch (e) {
    PIPELINE_OP_STATUS = {};
    PIPELINE_OP_STATUS_FETCHED = false;
  }

  /* P1-C-W2: three-state via client.js for monitor + non-blocking pipeline list refresh */
  var monitor = {};
  try {
    var monRes = await window.httpGet('/api/monitor/pipeline', { timeoutMs: 10000 });
    if (monRes.state === window.HTTP_STATE.SUCCESS) monitor = monRes.data || {};
  } catch (_) { /* ignore */ }
  PIPELINE_listRefresh().catch(function () {});
  // R4-Worker-3: totalOps / running / successRate 优先用后端数据, 缺则显示 "—"
  const allOps = [];
  for (var ck in categories) if (categories.hasOwnProperty(ck)) { for (var oi=0;oi<categories[ck].ops.length;oi++) allOps.push(categories[ck].ops[oi]); }
  const totalOps = allOps.length || 44;  // 真实算子数 (来自前端定义, 与后端一致)
  const running = (typeof monitor.running_tasks === 'number') ? monitor.running_tasks : '—';
  const successRate = (typeof monitor.success_rate === 'number') ? monitor.success_rate : '—';

  c.innerHTML = '' +
    '<div class="page-header">' +
      '<div>' +
        '<div class="page-title">🔧 质量管线</div>' +
        '<div style="font-size:11px;color:#8888aa;margin-top:2px">' + totalOps + '个算子 · 6大分类 · 可自由组合为数据处理流水线</div>' +
      '</div>' +
      '<div class="page-stats">' +
        '<div class="page-stat"><div class="page-stat-val" style="color:#4a7aff">' + totalOps + '</div><div class="page-stat-label">算子总数</div></div>' +
        '<div class="page-stat"><div class="page-stat-val" style="color:#4ade80">' + running + '</div><div class="page-stat-label">运行中</div></div>' +
        '<div class="page-stat"><div class="page-stat-val" style="color:#a78bfa">' + successRate + '%</div><div class="page-stat-label">成功率</div></div>' +
      '</div>' +
    '</div>' +
    '<div class="toolbar">' +
      '<input id="opSearch" placeholder="🔍 搜索算子名称或关键词..." onkeyup="filterOperators()">' +
      '<span style="flex:1"></span>' +
      '<button class="btn btn-success btn-sm" onclick="runPipeline()">▶ 执行选中管线</button>' +
      '<button class="btn btn-outline btn-sm" onclick="clearOps()">✕ 清除选择</button>' +
    '</div>' +
    '<div id="selectedOps" style="display:none;padding:8px 12px;background:rgba(74,222,128,0.08);border:1px solid #4ade80;border-radius:6px;margin-bottom:12px;font-size:12px">' +
      '<span id="selOpList" style="color:#4ade80"></span>' +
    '</div>' +
    '<div id="opCategories"></div>' +
    '<div id="pipelineResult" style="margin-top:12px;font-size:12px"></div>';

  SELECTED_OPS = new Set();
  renderCategories();
}

let SELECTED_OPS = new Set();

function renderCategories(filter) {
  filter = filter || '';
  var container = document.getElementById('opCategories');
  if (!container) return;

  var cats = [
    { name:'采集', icon:'📥', color:'#4a9', ops:['web_scraper','rss_feed','api_puller','db_sync','file_import','clipboard','screenshot'] },
    { name:'清洗', icon:'🧹', color:'#49a', ops:['null_filter','dedup','html_cleaner','json_parser','template_fill','stopword','lowercase','strip','regex','normalize','emoji','url','date'] },
    { name:'标注', icon:'🖌️', color:'#a49', ops:['bbox','polygon','point','line','text_annotate','classify','relation','ocr'] },
    { name:'评分', icon:'⭐', color:'#9a4', ops:['quality_score','consistency','completeness','readability','aesthetics'] },
    { name:'筛选', icon:'🔍', color:'#94a', ops:['threshold','topk','random','dedup2','field_filter'] },
    { name:'导出', icon:'📤', color:'#a94', ops:['json_export','csv_export','coco_export','yolo_export','parquet','tfrecord'] },
  ];

  var labels = {
    web_scraper:'Web爬虫',rss_feed:'RSS订阅',api_puller:'API拉取',db_sync:'DB同步',file_import:'文件导入',clipboard:'剪贴板',screenshot:'截图',
    null_filter:'空值过滤',dedup:'去重',html_cleaner:'HTML清洗',json_parser:'JSON解析',template_fill:'模板填充',stopword:'停用词',lowercase:'小写化',strip:'去空格',regex:'正则',normalize:'标准化',emoji:'表情过滤',url:'URL清洗',date:'日期标准化',
    bbox:'BBox标注',polygon:'多边形',point:'关键点',line:'线条',text_annotate:'文本标注',classify:'分类',relation:'关系',ocr:'OCR识别',
    quality_score:'质量评分',consistency:'一致性',completeness:'完整性',readability:'可读性',aesthetics:'美观度',
    threshold:'阈值过滤',topk:'TopK',random:'随机',dedup2:'去重2',field_filter:'字段过滤',
    json_export:'JSON',csv_export:'CSV',coco_export:'COCO',yolo_export:'YOLO',parquet:'Parquet',tfrecord:'TFRecord'
  };

  var descs = {
    web_scraper:'从网页抓取结构化数据',rss_feed:'订阅RSS源自动采集',api_puller:'从外部API定时拉取',db_sync:'从数据库同步数据',file_import:'导入本地文件',clipboard:'从剪贴板读取数据',screenshot:'截取网页/应用截图',
    null_filter:'过滤空值/缺失数据行',dedup:'基于内容哈希去重',html_cleaner:'清洗HTML标签和属性',json_parser:'解析JSON数据',template_fill:'基于模板生成数据',stopword:'移除停用词',lowercase:'统一转为小写',strip:'去除首尾空白',regex:'正则匹配/替换',normalize:'Unicode标准化',emoji:'过滤或转换表情',url:'清洗/标准化URL',date:'统一日期格式',
    bbox:'绘制矩形边界框',polygon:'绘制多边形区域',point:'标注关键点',line:'绘制线条/边界',text_annotate:'文本标注/转录',classify:'分类标签标注',relation:'关系标注',ocr:'OCR文字识别',
    quality_score:'综合质量评分',consistency:'数据一致性检查',completeness:'完整性评分',readability:'可读性评估',aesthetics:'美观度评分',
    threshold:'按阈值过滤数据',topk:'保留Top-K条数据',random:'随机采样',dedup2:'高级去重',field_filter:'按字段条件过滤',
    json_export:'导出JSON格式',csv_export:'导出CSV格式',coco_export:'导出COCO格式',yolo_export:'导出YOLO格式',parquet:'导出Parquet',tfrecord:'导出TFRecord'
  };

  var statusPool = ['idle','running','done','error'];
  var statusLabel = { idle:'待命', running:'运行中', done:'已完成', error:'异常', unknown:'未拉取' };
  var statusColor = { idle:'#666688', running:'#4a7aff', done:'#4ade80', error:'#ef4444', unknown:'#8888aa' };

  var html = '';
  for (var ci = 0; ci < cats.length; ci++) {
    var cat = cats[ci];
    var filteredOps = [];
    for (var oi = 0; oi < cat.ops.length; oi++) {
      var op = cat.ops[oi];
      if (!filter || op.indexOf(filter.toLowerCase()) >= 0 || (labels[op]||op).toLowerCase().indexOf(filter.toLowerCase()) >= 0) {
        filteredOps.push(op);
      }
    }
    if (filteredOps.length === 0) continue;

    html += '<div style="margin-bottom:8px;background:#1e1e3a;border:1px solid #2a2a4a;border-radius:8px;overflow:hidden">';
    html += '<div onclick="this.classList.toggle(\'collapsed\');var s=this.nextElementSibling.style;s.display=s.display===\'none\'?\'\':\'none\'" style="padding:10px 14px;background:'+cat.color+'11;border-bottom:1px solid #2a2a4a;cursor:pointer;font-size:13px;font-weight:600;display:flex;align-items:center;gap:8px;user-select:none">';
    html += '<span class="arrow" style="font-size:10px;transition:transform 0.2s;display:inline-block">▼</span>';
    html += '<span>' + cat.icon + ' ' + cat.name + '</span>';
    html += '<span style="color:#8888aa;font-weight:400;font-size:11px">' + filteredOps.length + '个算子</span>';
    html += '<span style="margin-left:auto;font-size:10px;color:#8888aa">' + filteredOps.length + '</span>';
    html += '</div>';
    html += '<div class="group-content" style="padding:8px;display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:6px">';

    for (var fi = 0; fi < filteredOps.length; fi++) {
      var op = filteredOps[fi];
      var selected = SELECTED_OPS.has(op);
      // R4-Worker-3: Math.random 状态 → 真实 PIPELINE_OP_STATUS (默认 'idle')
      var status = PIPELINE_OP_STATUS[op] || (PIPELINE_OP_STATUS_FETCHED ? 'idle' : 'unknown');
      html += '<div onclick="toggleOp(\'' + op + '\')" class="op-card" style="padding:10px 12px;border-radius:6px;cursor:pointer;font-size:12px;border:1px solid ' + (selected ? cat.color : '#2a2a4a') + ';background:' + (selected ? cat.color + '11' : '#0f0f1a') + ';transition:all 0.2s;display:flex;align-items:center;gap:10px" data-cat-color="' + cat.color + '">';
      html += '<span style="font-size:20px">' + cat.icon + '</span>';
      html += '<div style="flex:1;min-width:0">';
      html += '<div style="font-weight:600;margin-bottom:2px">' + (labels[op]||op) + '</div>';
      html += '<div style="font-size:10px;color:#8888aa;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + (descs[op]||'') + '</div>';
      html += '</div>';
      html += '<span style="font-size:10px;padding:2px 6px;border-radius:8px;color:' + statusColor[status] + ';background:' + statusColor[status] + '18;flex-shrink:0">' + statusLabel[status] + '</span>';
      if (selected) html += '<span style="font-size:10px;color:' + cat.color + ';flex-shrink:0">已选</span>';
      html += '</div>';
    }
    html += '</div></div>';
  }
  container.innerHTML = html;
  updateSelectedDisplay();
}

function toggleOp(op) {
  if (SELECTED_OPS.has(op)) SELECTED_OPS.delete(op);
  else SELECTED_OPS.add(op);
  renderCategories((document.getElementById('opSearch')||{}).value || '');
}

function filterOperators() {
  renderCategories((document.getElementById('opSearch')||{}).value || '');
}

function clearOps() {
  SELECTED_OPS.clear();
  renderCategories((document.getElementById('opSearch')||{}).value || '');
}

function updateSelectedDisplay() {
  var ops = Array.from(SELECTED_OPS);
  var div = document.getElementById('selectedOps');
  var list = document.getElementById('selOpList');
  if (!div || !list) return;
  div.style.display = ops.length > 0 ? 'block' : 'none';
  list.textContent = '已选 ' + ops.length + ' 个算子: ' + ops.slice(0, 8).join(', ') + (ops.length > 8 ? '...' : '');
}

async function runPipeline() {
  var ops = Array.from(SELECTED_OPS);
  var r = document.getElementById('pipelineResult');
  if (!r) return;
  if (ops.length === 0) {
    r.innerHTML = '<span style="color:#fbbf24">⚠️ 请先选择至少一个算子</span>';
    return;
  }
  r.innerHTML = '<span style="color:#4a7aff">⏳ 管线执行中... (算子: ' + ops.length + ')</span>';
  // R4-Worker-3: 固定测试节点 → 实际选中节点 (已用 SELECTED_OPS, 这里再补 connections 顺序)
  var nodes = ops.map(function(op, i) { return { id: 'op_' + i, type: op, name: op, category: '' }; });
  var connections = [];
  for (var ci = 0; ci < ops.length - 1; ci++) {
    connections.push({ from: 'op_' + ci, to: 'op_' + (ci + 1) });
  }
  // 标记前端缓存为 running, 真实 API 返回后再更新
  ops.forEach(function(op) { PIPELINE_OP_STATUS[op] = 'running'; });
  renderCategories((document.getElementById('opSearch') || {}).value || '');
  /* P1-C-W2: three-state POST via client.js. Workflow endpoint retained as the
     legacy execute path; the new /api/pipeline/{id}/run endpoint is exercised
     by PIPELINE_runById() below for the pipeline-list flow. */
  var execRes = await window.httpPost('/api/workflow/execute', { nodes: nodes, connections: connections }, { timeoutMs: 120000 });
  var result = (execRes.state === window.HTTP_STATE.SUCCESS)
    ? Object.assign({ success: true }, execRes.data || {})
    : { success: false, error: execRes.error ? (execRes.error.message || 'failed') : 'failed' };
  if (result.success) {
    // 标记算子为 done
    ops.forEach(function(op) { PIPELINE_OP_STATUS[op] = 'done'; });
    // 异步写回后端真实状态 (best-effort)
    ops.forEach(function(op) {
      window.httpPost('/api/pipeline/operators/' + encodeURIComponent(op) + '/status?status=done', {}, { timeoutMs: 8000 }).catch(function() {});
    });
    renderCategories((document.getElementById('opSearch') || {}).value || '');
    var summary = '';
    if (result.data && typeof result.data === 'object') {
      var s = JSON.stringify(result.data).slice(0, 200);
      summary = s;
    } else {
      summary = JSON.stringify(result.data || result).slice(0, 200);
    }
    r.innerHTML = '<span style="color:#4ade80">✅ 管线执行完成 · ' + ops.length + '个算子 · 结果: ' + summary + '</span>';
  } else {
    // 失败算子标 error
    ops.forEach(function(op) { PIPELINE_OP_STATUS[op] = 'error'; });
    ops.forEach(function(op) {
      window.httpPost('/api/pipeline/operators/' + encodeURIComponent(op) + '/status?status=error', {}, { timeoutMs: 8000 }).catch(function() {});
    });
    renderCategories((document.getElementById('opSearch') || {}).value || '');
    r.innerHTML = '<span style="color:#ef4444">❌ 执行失败: ' + (result.error || '未知错误') + '</span>';
  }
}

function pipeline_opDetail(op) {
  let html = '<div class="detail-panel">';
  html += `<div class="detail-section"><div class="detail-section-title">算子详情</div>`;
  html += `<div class="detail-field"><span class="detail-field-label">名称</span><span class="detail-field-value">${op.name||'算子名称'}</span></div>`;
  html += `<div class="detail-field"><span class="detail-field-label">分类</span><span class="detail-field-value"><span class="tag tag-blue">${op.cat||'清洗'}</span></span></div>`;
  html += `<div class="detail-field"><span class="detail-field-label">状态</span><span class="detail-field-value">${op.status||'ready'}</span></div>`;
  html += '</div>';
  html += `<div class="detail-section"><div class="detail-section-title">参数配置</div>`;
  html += `<div class="form-group"><label class="form-label">阈值</label><input type="range" class="form-range" min="0" max="100" value="80"><div class="form-hint">当前: 80%</div></div>`;
  html += `<div class="form-group"><label class="form-label">输出格式</label><select class="form-select"><option>JSON</option><option>CSV</option><option>原始格式</option></select></div>`;
  html += '</div></div>';
  showModal('算子详情: '+(op.name||'算子'), html, '<button class="btn btn-outline btn-sm" onclick="this.closest(\'.modal-overlay\').remove()">关闭</button><button class="btn btn-primary btn-sm" onclick="this.closest(\'.modal-overlay\').remove();showToast(\'算子执行成功\')">▶ 执行</button>');
}

function pipeline_execModal() {
  showFormModal('执行管线', [
    {id:'input',label:'输入数据',placeholder:'选择数据集或文件路径'},
    {id:'params',label:'参数覆盖(JSON)',type:'textarea',placeholder:'{"threshold":80,"format":"json"}'},
  ], {label:'▶ 执行',callback:(d)=>showToast('管线开始执行,请查看进度')});
}

/* ================================================================
   P1-C-W2: New /api/pipeline/* endpoints integration
   ================================================================ */
let PIPELINE_LIST = { items: [], total: 0, page: 1, pages: 1, loading: false };

async function PIPELINE_listRefresh() {
  PIPELINE_LIST.loading = true;
  const res = await window.httpGet('/api/pipeline/list' + window.IMDF_ERROR.qs({ page: PIPELINE_LIST.page }), { timeoutMs: 15000 });
  PIPELINE_LIST.loading = false;
  if (res.state !== window.HTTP_STATE.SUCCESS) {
    window.IMDF_ERROR.onApiError('pipeline.list', res.error);
    return null;
  }
  const ext = window.IMDF_ERROR.extractList(res.data);
  PIPELINE_LIST.items  = ext.items;
  PIPELINE_LIST.total  = ext.total;
  PIPELINE_LIST.pages  = ext.pages;
  return ext;
}

/* POST /api/pipeline/{id}/run — start pipeline run */
async function PIPELINE_runById(id, payload) {
  if (!id) return null;
  const res = await window.httpPost('/api/pipeline/' + encodeURIComponent(id) + '/run', Object.assign({ id: id }, payload || {}), { timeoutMs: 60000 });
  if (res.state !== window.HTTP_STATE.SUCCESS) {
    window.IMDF_ERROR.onApiError('pipeline.run', res.error);
    if (typeof showToast === 'function') showToast('❌ 启动管线失败: ' + window.IMDF_ERROR.describe(res.error), 'error');
    return null;
  }
  if (typeof showToast === 'function') showToast('✅ 管线已启动', 'success');
  return res.data;
}

/* GET /api/pipeline/{id}/status — poll pipeline status */
async function PIPELINE_statusById(id) {
  if (!id) return null;
  const res = await window.httpGet('/api/pipeline/' + encodeURIComponent(id) + '/status', { timeoutMs: 10000 });
  if (res.state !== window.HTTP_STATE.SUCCESS) {
    window.IMDF_ERROR.onApiError('pipeline.status', res.error);
    return null;
  }
  return res.data;
}

/* POST /api/pipeline/{id}/cancel — cancel a running pipeline */
async function PIPELINE_cancelById(id) {
  if (!id) return null;
  const res = await window.httpPost('/api/pipeline/' + encodeURIComponent(id) + '/cancel', { id: id }, { timeoutMs: 15000 });
  if (res.state !== window.HTTP_STATE.SUCCESS) {
    window.IMDF_ERROR.onApiError('pipeline.cancel', res.error);
    if (typeof showToast === 'function') showToast('❌ 取消失败: ' + window.IMDF_ERROR.describe(res.error), 'error');
    return null;
  }
  if (typeof showToast === 'function') showToast('✅ 已取消', 'success');
  return res.data;
}

/* GET /api/pipeline/{id}/history — fetch pipeline history */
async function PIPELINE_historyById(id) {
  if (!id) return null;
  const res = await window.httpGet('/api/pipeline/' + encodeURIComponent(id) + '/history', { timeoutMs: 15000 });
  if (res.state !== window.HTTP_STATE.SUCCESS) {
    window.IMDF_ERROR.onApiError('pipeline.history', res.error);
    if (typeof showToast === 'function') showToast('❌ 历史加载失败: ' + window.IMDF_ERROR.describe(res.error), 'error');
    return null;
  }
  return res.data;
}
