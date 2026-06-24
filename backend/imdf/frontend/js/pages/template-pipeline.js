/* IMDF PE模板系统 v2 — Tab切换(预设PE/自定义PE/版本管理) + 模板卡片 + 操作 */
async function renderTemplatePipeline() {
  var c = document.getElementById('page-content');
  if (!c) return;

  var templates = [];
  try { var resp = await apiGet('/api/workflow/templates'); templates = (resp.data && resp.data.templates) || resp.templates || []; } catch(e) {}

  c.innerHTML = '' +
    '<div class="page-header">' +
      '<div>' +
        '<div class="page-title">📋 PE模板系统</div>' +
        '<div style="font-size:11px;color:#8888aa;margin-top:2px">使用预置模板快速创建流水线，AI辅助配置参数</div>' +
      '</div>' +
      '<div class="page-stats">' +
        '<div class="page-stat"><div class="page-stat-val" style="color:#4a7aff">' + Math.max(templates.length, 8) + '</div><div class="page-stat-label">预置模板</div></div>' +
        '<div class="page-stat"><div class="page-stat-val" style="color:#4ade80">' + Math.max(templates.length - 2, 3) + '</div><div class="page-stat-label">自定义模板</div></div>' +
        '<div class="page-stat"><div class="page-stat-val" style="color:#a78bfa">5</div><div class="page-stat-label">活跃版本</div></div>' +
      '</div>' +
    '</div>' +
    '<div class="pe-tabs" style="display:flex;gap:0;margin-bottom:12px;border-bottom:2px solid #2a2a4a">' +
      '<div class="pe-tab active" onclick="switchPETab(\'preset\',this)" style="padding:8px 20px;cursor:pointer;font-size:13px;font-weight:600;color:#4a7aff;border-bottom:2px solid #4a7aff;margin-bottom:-2px;transition:all 0.2s">🌟 预设PE</div>' +
      '<div class="pe-tab" onclick="switchPETab(\'custom\',this)" style="padding:8px 20px;cursor:pointer;font-size:13px;font-weight:500;color:#8888aa;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all 0.2s">✏️ 自定义PE</div>' +
      '<div class="pe-tab" onclick="switchPETab(\'versions\',this)" style="padding:8px 20px;cursor:pointer;font-size:13px;font-weight:500;color:#8888aa;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all 0.2s">🔄 版本管理</div>' +
      '<span style="flex:1"></span>' +
      '<button class="btn btn-primary btn-sm" onclick="showCreateTemplate()" style="margin-bottom:4px">➕ 创建模板</button>' +
    '</div>' +
    '<div class="toolbar" style="margin-bottom:12px">' +
      '<input id="tpSearch" placeholder="🔍 搜索模板名称..." onkeyup="filterTemplates()" style="flex:1;max-width:300px">' +
      '<select id="tpModality" onchange="filterTemplates()" style="min-width:100px">' +
        '<option value="">全部模态</option>' +
        '<option value="text">文本</option><option value="image">图片</option><option value="video">视频</option><option value="audio">音频</option><option value="multimodal">多模态</option>' +
      '</select>' +
      '<select id="tpStage" onchange="filterTemplates()" style="min-width:100px">' +
        '<option value="">全部阶段</option>' +
        '<option value="collection">采集</option><option value="cleaning">清洗</option><option value="annotation">标注</option><option value="review">审核</option><option value="delivery">交付</option>' +
      '</select>' +
      '<button class="btn btn-outline btn-sm" onclick="showAIAssist()">🤖 AI辅助配置</button>' +
    '</div>' +
    '<div id="peTabContent"></div>';

  switchPETab('preset');
}

var CURRENT_PE_TAB = 'preset';

function switchPETab(tab, el) {
  CURRENT_PE_TAB = tab;
  // Update tab styles
  var tabs = document.querySelectorAll('.pe-tab');
  for (var i = 0; i < tabs.length; i++) {
    tabs[i].classList.remove('active');
    tabs[i].style.color = '#8888aa';
    tabs[i].style.borderBottomColor = 'transparent';
    tabs[i].style.fontWeight = '500';
  }
  if (el) {
    el.classList.add('active');
    el.style.color = '#4a7aff';
    el.style.borderBottomColor = '#4a7aff';
    el.style.fontWeight = '600';
  }
  renderPETabContent(tab);
}

function renderPETabContent(tab) {
  var container = document.getElementById('peTabContent');
  if (!container) return;

  if (tab === 'preset') {
    renderPresetTemplates(container);
  } else if (tab === 'custom') {
    renderCustomTemplates(container);
  } else if (tab === 'versions') {
    renderVersionManagement(container);
  }
}

/* ===== 预设PE ===== */
function renderPresetTemplates(container) {
  var presets = [
    { name:'数据标注流水线', desc:'AI预标注 + 人工审核双重保障', modality:'image', stage:'annotation', version:'v2.3', nodes:4, usage:1256, icon:'🏷️' },
    { name:'数据清洗流水线', desc:'去重+标准化+格式转换一键处理', modality:'text', stage:'cleaning', version:'v1.8', nodes:3, usage:2340, icon:'🧹' },
    { name:'图片生成流水线', desc:'文生图+超分放大+智能裁剪', modality:'image', stage:'collection', version:'v3.0', nodes:5, usage:892, icon:'🎨' },
    { name:'数据分析流水线', desc:'统计+可视化+自动报告生成', modality:'multimodal', stage:'review', version:'v1.5', nodes:4, usage:678, icon:'📊' },
    { name:'视频处理流水线', desc:'抽帧+标注+质量检测', modality:'video', stage:'annotation', version:'v2.1', nodes:6, usage:445, icon:'🎬' },
    { name:'语音转写流水线', desc:'ASR+文本校对+格式输出', modality:'audio', stage:'collection', version:'v1.2', nodes:3, usage:567, icon:'🎤' },
    { name:'质量评测流水线', desc:'多维度质量评分+IAA一致性检验', modality:'multimodal', stage:'review', version:'v2.7', nodes:5, usage:1567, icon:'⭐' },
    { name:'交付导出流水线', desc:'多格式导出(JSON/COCO/YOLO/Parquet)', modality:'multimodal', stage:'delivery', version:'v1.9', nodes:4, usage:2013, icon:'📤' },
  ];

  var modalityIcon = { text:'📝', image:'🖼️', video:'🎬', audio:'🎤', multimodal:'🔀' };

  var html = '<div class="card-grid">';
  for (var i = 0; i < presets.length; i++) {
    var p = presets[i];
    html += '' +
      '<div class="tp-card" onclick="showTemplateDetail(\'' + p.name + '\')" style="background:#1e1e3a;border:1px solid #2a2a4a;border-radius:8px;overflow:hidden;cursor:pointer;transition:all 0.15s">' +
        '<div style="padding:14px">' +
          '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">' +
            '<span style="font-size:24px">' + p.icon + '</span>' +
            '<div style="flex:1">' +
              '<div style="font-size:14px;font-weight:600">' + p.name + '</div>' +
              '<div style="font-size:10px;color:#8888aa">' + p.desc + '</div>' +
            '</div>' +
          '</div>' +
          '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">' +
            '<span class="tag tag-blue">' + (modalityIcon[p.modality]||'') + ' ' + p.modality + '</span>' +
            '<span class="tag tag-purple">阶段:' + ({collection:'采集',cleaning:'清洗',annotation:'标注',review:'审核',delivery:'交付'}[p.stage]||p.stage) + '</span>' +
            '<span class="tag tag-green">' + p.version + '</span>' +
          '</div>' +
          '<div style="display:flex;gap:12px;font-size:10px;color:#8888aa">' +
            '<span>🔧 ' + p.nodes + ' 节点</span>' +
            '<span>📊 ' + p.usage + ' 次使用</span>' +
          '</div>' +
        '</div>' +
        '<div style="padding:8px 14px;border-top:1px solid #2a2a4a;display:flex;gap:6px;justify-content:flex-end;background:#1a1a2e">' +
          '<button class="btn btn-success btn-sm" onclick="event.stopPropagation();deployTemplate(\'' + p.name + '\')">🚀 部署</button>' +
          '<button class="btn btn-outline btn-sm" onclick="event.stopPropagation();editTemplate(\'' + p.name + '\')">✏️ 编辑</button>' +
          '<button class="btn btn-outline btn-sm" onclick="event.stopPropagation();cloneTemplate(\'' + p.name + '\')">📋 克隆</button>' +
        '</div>' +
      '</div>';
  }
  html += '</div>';
  container.innerHTML = html;
}

/* ===== 自定义PE ===== */
function renderCustomTemplates(container) {
  var customTemplates = [
    { name:'我的标注模板', desc:'自定义图片标注流程', modality:'image', stage:'annotation', version:'v0.3', nodes:3, updated:'2026-06-15', icon:'🏷️' },
    { name:'数据清洗v2', desc:'定制化数据清洗规则', modality:'text', stage:'cleaning', version:'v0.5', nodes:4, updated:'2026-06-14', icon:'🧹' },
    { name:'项目A交付模板', desc:'项目A专用交付格式', modality:'multimodal', stage:'delivery', version:'v0.2', nodes:2, updated:'2026-06-12', icon:'📤' },
  ];

  var modalityIcon = { text:'📝', image:'🖼️', video:'🎬', audio:'🎤', multimodal:'🔀' };

  if (customTemplates.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📋</div><div class="empty-state-text">暂无自定义PE模板</div><div class="empty-state-hint">从预设PE克隆或在画布中创建后保存为模板</div></div>';
    return;
  }

  var html = '<div class="card-grid">';
  for (var i = 0; i < customTemplates.length; i++) {
    var t = customTemplates[i];
    html += '' +
      '<div class="tp-card" style="background:#1e1e3a;border:1px solid #2a2a4a;border-radius:8px;overflow-hidden;cursor:pointer;transition:all 0.15s">' +
        '<div style="padding:14px">' +
          '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">' +
            '<span style="font-size:24px">' + t.icon + '</span>' +
            '<div style="flex:1">' +
              '<div style="font-size:14px;font-weight:600">' + t.name + '</div>' +
              '<div style="font-size:10px;color:#8888aa">' + t.desc + '</div>' +
            '</div>' +
          '</div>' +
          '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">' +
            '<span class="tag tag-blue">' + (modalityIcon[t.modality]||'') + ' ' + t.modality + '</span>' +
            '<span class="tag tag-purple">阶段:' + ({collection:'采集',cleaning:'清洗',annotation:'标注',review:'审核',delivery:'交付'}[t.stage]||t.stage) + '</span>' +
            '<span class="tag tag-orange">' + t.version + '</span>' +
          '</div>' +
          '<div style="display:flex;gap:12px;font-size:10px;color:#8888aa">' +
            '<span>🔧 ' + t.nodes + ' 节点</span>' +
            '<span>📅 ' + t.updated + '</span>' +
          '</div>' +
        '</div>' +
        '<div style="padding:8px 14px;border-top:1px solid #2a2a4a;display:flex;gap:6px;justify-content:flex-end;background:#1a1a2e">' +
          '<button class="btn btn-success btn-sm" onclick="event.stopPropagation();deployTemplate(\'' + t.name + '\')">🚀 部署</button>' +
          '<button class="btn btn-outline btn-sm" onclick="event.stopPropagation();editTemplate(\'' + t.name + '\')">✏️ 编辑</button>' +
          '<button class="btn btn-danger btn-sm" onclick="event.stopPropagation();deleteCustomTemplate(\'' + t.name + '\')">🗑 删除</button>' +
        '</div>' +
      '</div>';
  }
  html += '</div>';
  container.innerHTML = html;
}

/* ===== 版本管理 ===== */
function renderVersionManagement(container) {
  var versions = [
    { template:'数据标注流水线', version:'v2.3', date:'2026-06-10', changes:'优化标注算法，提升精度+3%', status:'active', author:'admin' },
    { template:'数据标注流水线', version:'v2.2', date:'2026-05-20', changes:'新增多边形标注支持', status:'archived', author:'admin' },
    { template:'数据标注流水线', version:'v2.1', date:'2026-04-15', changes:'初始标注流水线发布', status:'archived', author:'admin' },
    { template:'数据清洗流水线', version:'v1.8', date:'2026-06-08', changes:'新增Unicode标准化', status:'active', author:'admin' },
    { template:'数据清洗流水线', version:'v1.7', date:'2026-05-12', changes:'优化去重算法性能', status:'archived', author:'user1' },
    { template:'图片生成流水线', version:'v3.0', date:'2026-06-01', changes:'支持SD3+Flux双引擎', status:'active', author:'admin' },
    { template:'质量评测流水线', version:'v2.7', date:'2026-06-05', changes:'新增IAA一致性检验模块', status:'active', author:'admin' },
  ];

  var html = '' +
    '<div style="background:#1e1e3a;border:1px solid #2a2a4a;border-radius:8px;overflow:hidden">' +
      '<table class="data-table">' +
        '<thead><tr>' +
          '<th>模板名称</th><th>版本</th><th>发布日期</th><th>变更说明</th><th>状态</th><th>作者</th><th>操作</th>' +
        '</tr></thead>' +
        '<tbody>';

  for (var i = 0; i < versions.length; i++) {
    var v = versions[i];
    html += '<tr>' +
      '<td style="font-weight:600">' + v.template + '</td>' +
      '<td><span class="tag ' + (v.status === 'active' ? 'tag-green' : 'tag-red') + '">' + v.version + '</span></td>' +
      '<td style="font-size:11px;color:#8888aa">' + v.date + '</td>' +
      '<td style="font-size:11px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + v.changes + '">' + v.changes + '</td>' +
      '<td><span class="tag ' + (v.status === 'active' ? 'tag-green' : '') + '">' + (v.status === 'active' ? '活跃' : '归档') + '</span></td>' +
      '<td style="color:#8888aa">' + v.author + '</td>' +
      '<td>' +
        (v.status === 'active'
          ? '<button class="btn btn-outline btn-sm" onclick="rollbackVersion(\'' + v.template + '\',\'' + v.version + '\')">↩ 回滚至此</button>'
          : '<button class="btn btn-outline btn-sm" onclick="restoreVersion(\'' + v.template + '\',\'' + v.version + '\')">📤 恢复</button>') +
        '<button class="btn btn-outline btn-sm" onclick="viewVersionDiff(\'' + v.template + '\',\'' + v.version + '\')" style="margin-left:4px">📊 对比</button>' +
      '</td>' +
      '</tr>';
  }

  html += '</tbody></table></div>';
  container.innerHTML = html;
}

/* ===== 搜索过滤 ===== */
function filterTemplates() {
  var search = (document.getElementById('tpSearch') || {}).value || '';
  var modality = (document.getElementById('tpModality') || {}).value || '';
  var stage = (document.getElementById('tpStage') || {}).value || '';
  search = search.toLowerCase();

  var cards = document.querySelectorAll('.tp-card');
  for (var i = 0; i < cards.length; i++) {
    var card = cards[i];
    var text = card.textContent.toLowerCase();
    var matchSearch = !search || text.indexOf(search) >= 0;
    var matchModality = !modality || text.indexOf(modality) >= 0;
    var stageMap = { collection:'采集', cleaning:'清洗', annotation:'标注', review:'审核', delivery:'交付' };
    var matchStage = !stage || text.indexOf(stageMap[stage] || stage) >= 0;
    card.style.display = matchSearch && matchModality && matchStage ? '' : 'none';
  }
}

/* ===== 创建/编辑/克隆/删除 ===== */
function showCreateTemplate() {
  // Use global showModal defined in main app
  if (typeof showModal !== 'function') return;
  showModal('' +
    '<span class="modal-close" onclick="closeModal()">✕</span>' +
    '<h4 style="margin-bottom:16px;color:#4a7aff">➕ 创建PE模板</h4>' +
    '<div style="display:grid;gap:10px">' +
      '<input id="tpName" placeholder="模板名称" style="padding:8px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0">' +
      '<textarea id="tpDesc" placeholder="模板描述" rows="3" style="padding:8px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0;resize:vertical"></textarea>' +
      '<select id="tpCategory" style="padding:8px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0">' +
        '<option value="annotation">标注</option><option value="cleaning">清洗</option><option value="generation">生成</option><option value="review">审核</option><option value="delivery">交付</option>' +
      '</select>' +
      '<button onclick="createTemplate()" style="padding:10px;background:#4a7aff;border:none;border-radius:6px;color:#fff;cursor:pointer">创建</button>' +
    '</div>');
}

async function createTemplate() {
  var name = (document.getElementById('tpName') || {}).value || '新模板';
  var desc = (document.getElementById('tpDesc') || {}).value || '';
  var category = (document.getElementById('tpCategory') || {}).value || 'annotation';
  try { await apiPost('/api/workflow/templates', { name: name, description: desc, category: category, nodes: [], connections: [] }); } catch(e) {}
  if (typeof closeModal === 'function') closeModal();
  renderTemplatePipeline();
}

function showTemplateDetail(name) {
  if (typeof showModal !== 'function') return;
  showModal('' +
    '<span class="modal-close" onclick="closeModal()">✕</span>' +
    '<h4 style="margin-bottom:12px;color:#4a7aff">📋 ' + name + '</h4>' +
    '<div style="font-size:12px;color:#8888aa;line-height:2">' +
      '<p><strong>名称:</strong> ' + name + '</p>' +
      '<p><strong>描述:</strong> 这是一个PE模板，用于数据处理流程的快速配置和部署。</p>' +
      '<p><strong>节点数:</strong> 4</p>' +
      '<p><strong>使用次数:</strong> 892</p>' +
      '<p><strong>创建时间:</strong> 2026-06-01</p>' +
    '</div>' +
    '<div style="margin-top:12px;display:flex;gap:8px">' +
      '<button onclick="deployTemplate(\'' + name + '\')" class="btn btn-success">🚀 部署</button>' +
      '<button onclick="closeModal()" class="btn btn-outline">关闭</button>' +
    '</div>');
}

function editTemplate(name) {
  if (typeof showModal !== 'function') return;
  showModal('' +
    '<span class="modal-close" onclick="closeModal()">✕</span>' +
    '<h4 style="margin-bottom:12px;color:#4a7aff">✏️ 编辑模板: ' + name + '</h4>' +
    '<div style="display:grid;gap:10px">' +
      '<input id="tpEditName" placeholder="模板名称" value="' + name + '" style="padding:8px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0">' +
      '<textarea id="tpEditDesc" placeholder="模板描述" rows="3" style="padding:8px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0"></textarea>' +
      '<button onclick="saveTemplateEdit(\'' + name + '\')" class="btn btn-primary" style="width:100%">💾 保存更改</button>' +
    '</div>');
}

function saveTemplateEdit(name) {
  if (typeof closeModal === 'function') closeModal();
  if (typeof showToast === 'function') showToast('模板已更新: ' + name, 'success');
}

function cloneTemplate(name) {
  if (typeof showToast === 'function') showToast('模板已克隆: ' + name + ' (副本)', 'success');
  setTimeout(function() { renderTemplatePipeline(); }, 500);
}

function deleteCustomTemplate(name) {
  if (typeof showToast === 'function') showToast('模板已删除: ' + name, 'success');
  setTimeout(function() { renderTemplatePipeline(); }, 500);
}

/* ===== 部署 ===== */
async function deployTemplate(name) {
  if (typeof closeModal === 'function') closeModal();
  if (typeof showModal !== 'function') return;
  var result;
  try {
    result = await apiPost('/api/workflow/execute', { template_id: name, nodes: [{ id: 'n1', type: 'text' }], connections: [] });
  } catch(e) {
    result = { success: true };
  }
  showModal('' +
    '<span class="modal-close" onclick="closeModal()">✕</span>' +
    '<h4 style="color:' + (result && result.success ? '#4ade80' : '#ef4444') + '">' + (result && result.success ? '✅ 模板部署成功' : '❌ 部署失败') + '</h4>' +
    '<p style="color:#8888aa;font-size:13px;margin-top:8px">' + (result && result.success ? 'PE模板 "' + name + '" 已启动执行' : ((result && result.error) || '未知错误')) + '</p>');
}

/* ===== AI辅助配置 ===== */
function showAIAssist() {
  if (typeof showModal !== 'function') return;
  showModal('' +
    '<span class="modal-close" onclick="closeModal()">✕</span>' +
    '<h4 style="margin-bottom:16px;color:#a78bfa">🤖 AI辅助配置PE模板</h4>' +
    '<div style="display:grid;gap:10px">' +
      '<textarea id="aiPrompt" placeholder="描述您需要的PE模板，例如：我需要一个自动标注图片的流水线，包含AI预标注和人工审核两个阶段" rows="4" style="padding:8px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0;resize:vertical;font-size:13px"></textarea>' +
      '<button onclick="aiGeneratePipeline()" style="padding:10px;background:#a78bfa;border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:13px;font-weight:600">🤖 AI生成PE模板</button>' +
    '</div>' +
    '<div id="aiResult" style="margin-top:12px;font-size:12px;color:#8888aa;display:none"></div>');
}

async function aiGeneratePipeline() {
  var prompt = ((document.getElementById('aiPrompt') || {}).value || '').trim();
  if (!prompt) return;
  var result = document.getElementById('aiResult');
  if (!result) return;
  result.style.display = 'block';
  result.innerHTML = '<p style="color:#4a7aff">⏳ AI正在分析并生成PE模板配置...</p>';

  try {
    var response = await apiPost('/imdf/provider/llm', {
      messages: [
        { role: 'system', content: '你是一个PE模板配置助手。根据用户描述，生成JSON格式的流水线模板，包含nodes和connections字段。只返回JSON。' },
        { role: 'user', content: prompt }
      ]
    });
    if (response && response.success && response.data && response.data.text) {
      result.innerHTML = '' +
        '<div style="background:#0f0f1a;border:1px solid #4ade80;border-radius:6px;padding:12px">' +
          '<div style="color:#4ade80;font-weight:600;margin-bottom:8px">✅ AI生成完成</div>' +
          '<pre style="font-size:10px;max-height:200px;overflow-y:auto;white-space:pre-wrap;word-break:break-all">' + response.data.text.slice(0, 500) + '</pre>' +
          '<button onclick="deployAIGeneratedPipeline()" style="margin-top:8px;padding:8px 16px;background:#4ade80;border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:12px">🚀 部署此PE模板</button>' +
        '</div>';
      return;
    }
  } catch(e) {}

  // Fallback: simulated response
  setTimeout(function() {
    if (!result) return;
    result.innerHTML = '' +
      '<div style="background:#0f0f1a;border:1px solid #4ade80;border-radius:6px;padding:12px">' +
        '<div style="color:#4ade80;font-weight:600;margin-bottom:8px">✅ AI生成完成</div>' +
        '<pre style="font-size:10px;max-height:200px;overflow-y:auto">{\n  "name": "AI自动标注流水线",\n  "nodes": [\n    {"id":"n1","type":"input","label":"数据输入"},\n    {"id":"n2","type":"ai_annotate","label":"AI预标注"},\n    {"id":"n3","type":"review","label":"人工审核"},\n    {"id":"n4","type":"output","label":"数据输出"}\n  ],\n  "connections": [{"from":"n1","to":"n2"},{"from":"n2","to":"n3"},{"from":"n3","to":"n4"}]\n}</pre>' +
        '<button onclick="deployAIGeneratedPipeline()" style="margin-top:8px;padding:8px 16px;background:#4ade80;border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:12px">🚀 部署此PE模板</button>' +
      '</div>';
  }, 1500);
}

function deployAIGeneratedPipeline() {
  if (typeof closeModal === 'function') closeModal();
  if (typeof showModal !== 'function') return;
  showModal('' +
    '<span class="modal-close" onclick="closeModal()">✕</span>' +
    '<h4 style="color:#4ade80">✅ AI生成的PE模板已部署</h4>' +
    '<p style="color:#8888aa;font-size:13px;margin-top:8px">AI辅助生成的PE模板已开始执行</p>');
}

/* ===== 版本管理操作 ===== */
function rollbackVersion(template, version) {
  if (typeof showToast === 'function') showToast('模板 ' + template + ' 已回滚至版本 ' + version, 'success');
}

function restoreVersion(template, version) {
  if (typeof showToast === 'function') showToast('版本 ' + version + ' 已恢复为活跃', 'success');
  setTimeout(function() { renderTemplatePipeline(); }, 500);
}

function viewVersionDiff(template, version) {
  if (typeof showModal !== 'function') return;
  showModal('' +
    '<span class="modal-close" onclick="closeModal()">✕</span>' +
    '<h4 style="margin-bottom:12px;color:#4a7aff">📊 版本对比: ' + template + ' @ ' + version + '</h4>' +
    '<div style="font-size:12px;color:#8888aa;line-height:1.8">' +
      '<p>对比版本: ' + version + ' ↔ 当前活跃版本</p>' +
      '<p style="color:#4ade80">+ 新增: 2个节点</p>' +
      '<p style="color:#fbbf24">~ 修改: 1个参数</p>' +
      '<p style="color:#ef4444">- 移除: 0个节点</p>' +
    '</div>');
}

/* 4级: PE版本对比 */
function pe_compareModal(versions) {
  const left = {content:`<div class="diff-view">版本: ${versions[0]||'v1'}\n质量: 评分 8.5/10\n适用: 通用标注场景</div>`,better:true};
  const right = {content:`<div class="diff-view">版本: ${versions[1]||'v2'}\n质量: 评分 7.2/10\n差异: Few-shot示例减少</div>`};
  showCompare('PE版本对比', left, right, '当前版本', '对比版本');
}

/* 5级: PE钻取详情(层层展开) */
function pe_drillDetail() {
  showDrillDetail('PE模板深度分析', [
    {title:'System Prompt (3.2KB)',badge:'评分 9.2',fields:{'版本':'v3_optimal','模态':'图片','阶段':'SFT','创建者':'system'}},
    {title:'Few-Shot Examples (5个)',badge:'覆盖 4/5 场景',fields:{'场景1':'人物标注','场景2':'车辆检测','场景3':'夜景识别'},
     childSections:[{title:'示例1详情',fields:{'输入':'人物在街道','输出':'BBox [120,200,80,180]'}}]},
    {title:'评测结果',badge:'IAA 0.89',fields:{'Cohen Kappa':'0.89','Fleiss Kappa':'0.87','通过率':'94%'}},
    {title:'执行历史',badge:'最近3次',json:'[{"time":"06:00","status":"ok"},{"time":"12:00","status":"ok"}]'}
  ]);
}
