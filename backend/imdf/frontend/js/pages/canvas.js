/* ================================================================
   IMDF v3 — 无限画布页面 (Workflow Canvas)
   纯DOM/CSS/SVG实现，无第三方依赖
   ================================================================ */

// ─── 48节点类型定义 (从后端canvas_web.py同步) ────────────────────
const WF_NT = {
  /* 基础维度 (维度) */
  text:       { l:'文本',     i:'📝', c:'#2d5d2d', cat:'dimension', p:{in:1,out:1} },
  image:      { l:'图片',     i:'🖼️', c:'#3d2d6d', cat:'dimension', p:{in:1,out:1} },
  video:      { l:'视频',     i:'🎬', c:'#2d4d6d', cat:'dimension', p:{in:1,out:1} },
  audio:      { l:'音频',     i:'🎵', c:'#2d5d5d', cat:'dimension', p:{in:1,out:1} },
  model3d:    { l:'3D模型',   i:'🎯', c:'#2d3d4d', cat:'dimension', p:{in:1,out:1} },
  /* AI能力 (能力) */
  llm:        { l:'AI对话',   i:'🤖', c:'#6d2d4d', cat:'ability', p:{in:2,out:1} },
  comfyui:    { l:'ComfyUI',  i:'⚡', c:'#4d2d4d', cat:'ability', p:{in:2,out:2} },
  seedance:   { l:'Seedance', i:'🎭', c:'#6d3d4d', cat:'ability', p:{in:2,out:1} },
  runninghub: { l:'RunningHub',i:'🏃',c:'#6d4d3d', cat:'ability', p:{in:2,out:1} },
  portrait:   { l:'人像大师', i:'👤', c:'#6d2d5d', cat:'ability', p:{in:2,out:1} },
  falbox:     { l:'Fal模型',  i:'🔮', c:'#5d3d4d', cat:'ability', p:{in:2,out:1} },
  rhtools:    { l:'RH工具箱', i:'🧰', c:'#5d4d4d', cat:'ability', p:{in:2,out:2} },
  grok:       { l:'Grok',     i:'🐦', c:'#4d3d6d', cat:'ability', p:{in:1,out:1} },
  /* 功能工具 (功能) */
  ppt:        { l:'PPT',      i:'📊', c:'#3d4d2d', cat:'function', p:{in:1,out:1} },
  script:     { l:'脚本',     i:'🔧', c:'#2d4d4d', cat:'function', p:{in:1,out:1} },
  output:     { l:'输出',     i:'💾', c:'#4d3d2d', cat:'function', p:{in:1,out:0} },
  upload:     { l:'上传',     i:'📤', c:'#3d5d4d', cat:'function', p:{in:0,out:1} },
  imgedit:    { l:'图片编辑', i:'🎨', c:'#5d2d6d', cat:'function', p:{in:1,out:1} },
  gridcrop:   { l:'网格裁剪', i:'🔲', c:'#5d2d5d', cat:'function', p:{in:1,out:1} },
  gridedit:   { l:'网格编辑', i:'📐', c:'#5d3d5d', cat:'function', p:{in:1,out:1} },
  imgcmp:     { l:'图片对比', i:'🔍', c:'#4d2d5d', cat:'function', p:{in:2,out:1} },
  presetimg:  { l:'预设图片', i:'🖼️', c:'#3d3d6d', cat:'function', p:{in:0,out:1} },
  resize:     { l:'缩放',     i:'📏', c:'#3d4d5d', cat:'function', p:{in:1,out:1} },
  upscale:    { l:'放大',     i:'🔍', c:'#4d3d5d', cat:'function', p:{in:1,out:1} },
  topazimg:   { l:'Topaz图片',i:'✨', c:'#5d4d3d', cat:'function', p:{in:1,out:1} },
  videoedit:  { l:'视频编辑', i:'✂️', c:'#2d5d6d', cat:'function', p:{in:1,out:1} },
  frameex:    { l:'帧提取',   i:'📸', c:'#3d5d6d', cat:'function', p:{in:1,out:1} },
  framepair:  { l:'帧对比',   i:'🎞️', c:'#4d5d6d', cat:'function', p:{in:1,out:1} },
  topazvid:   { l:'Topaz视频',i:'🌟', c:'#5d4d5d', cat:'function', p:{in:1,out:1} },
  textsplit:  { l:'文本分割', i:'✂️', c:'#4d5d4d', cat:'function', p:{in:1,out:1} },
  mention:    { l:'@引用',    i:'🔗', c:'#3d4d4d', cat:'function', p:{in:1,out:1} },
  loop:       { l:'循环',     i:'🔄', c:'#4d4d4d', cat:'function', p:{in:1,out:1} },
  relay:      { l:'中继',     i:'🔁', c:'#3d3d4d', cat:'function', p:{in:1,out:1} },
  groupbox:   { l:'分组',     i:'📦', c:'#4d4d5d', cat:'function', p:{in:2,out:1} },
  browser:    { l:'浏览器',   i:'🌐', c:'#2d3d5d', cat:'function', p:{in:1,out:1} },
  aggregate:  { l:'聚合解析', i:'🔀', c:'#4d3d4d', cat:'function', p:{in:2,out:1} },
  removebg:   { l:'去背景',   i:'✂️', c:'#5d5d3d', cat:'function', p:{in:1,out:1} },
  rmwatermark:{ l:'去水印',   i:'🚫', c:'#5d4d3d', cat:'function', p:{in:1,out:1} },
  drawboard:  { l:'绘图板',   i:'✏️', c:'#3d5d5d', cat:'function', p:{in:1,out:1} },
  storygrid:  { l:'故事板',   i:'📋', c:'#4d5d3d', cat:'function', p:{in:1,out:1} },
  combine:    { l:'合并',     i:'🔗', c:'#3d4d5d', cat:'function', p:{in:2,out:1} },
  panorama:   { l:'全景3D',   i:'🌍', c:'#2d3d5d', cat:'function', p:{in:1,out:1} },
  posemaster: { l:'姿势大师', i:'🧍', c:'#3d3d5d', cat:'function', p:{in:1,out:1} },
  materialset:{ l:'素材集',   i:'🗂️', c:'#4d4d3d', cat:'function', p:{in:1,out:1} },
  pickfromset:{ l:'从集选择', i:'🎯', c:'#3d4d3d', cat:'function', p:{in:1,out:1} },
  idea:       { l:'灵感',     i:'💡', c:'#5d5d4d', cat:'function', p:{in:0,out:1} },
  placeholder:{ l:'占位',     i:'⬜', c:'#3d3d3d', cat:'function', p:{in:0,out:1} },
  prelabel:   { l:'AI预标注', i:'🎯', c:'#9B59B6', cat:'ability', p:{in:1,out:2} },
};

// 分类组
const WF_CATEGORIES = [
  { id:'dimension', label:'📐 基础维度', types:['text','image','video','audio','model3d'] },
  { id:'ability',   label:'🤖 AI能力',   types:['llm','comfyui','seedance','runninghub','portrait','falbox','rhtools','grok','prelabel'] },
  { id:'function',  label:'🔧 功能工具', types:['ppt','script','output','upload','imgedit','gridcrop','gridedit','imgcmp','presetimg','resize','upscale','topazimg','videoedit','frameex','framepair','topazvid','textsplit','mention','loop','relay','groupbox','browser','aggregate','removebg','rmwatermark','drawboard','storygrid','combine','panorama','posemaster','materialset','pickfromset','idea','placeholder'] },
];

// ─── 全局状态 ────────────────────────────────────────────────────
let WF = {         // nodes: { id -> {id,type,x,y,data,ports,status} }
  nodes: {},
  connections: [], // [{from,fromP,to,toP}]
  canvasId: 'default', // P1-C-W1: 当前画布 id (用于 /api/canvas/{id}/save 等)
};
let WF_nextId = 1;
let WF_selected = null;
let WF_dragging = null;
let WF_dragOffset = { x:0, y:0 };
let WF_connecting = null; // {id,pt,pi}
let WF_zoom = 1;
let WF_panX = 0, WF_panY = 0;
let WF_isPanning = false;
let WF_panStart = { x:0, y:0 };
let WF_history = [];
let WF_historyIdx = -1;
let WF_logLines = 0;

// ─── DOM 引用 ────────────────────────────────────────────────────
let WF_el = {}; // populated in renderWorkflow

// ─── 默认数据 ────────────────────────────────────────────────────
function WF_defaultData(type) {
  const m = {
    text:       { content:'双击编辑内容' },
    image:      { src:'' },
    video:      { src:'', dur:5 },
    audio:      { src:'', dur:10 },
    model3d:    { model:'', pose:'standing' },
    llm:        { prompt:'', model:'auto' },
    comfyui:    { workflow:'' },
    seedance:   { prompt:'', model:'seedance2' },
    runninghub: { endpoint:'', params:'{}' },
    portrait:   { gender:'女', style:'写实' },
    falbox:     { endpoint:'', key:'' },
    rhtools:    { tool:'', params:'{}' },
    grok:       { prompt:'', model:'grok' },
    ppt:        { tpl:'clean-business', slides:5, title:'新建PPT' },
    script:     { code:'return input;' },
    output:     { fmt:'mp4' },
    upload:     { path:'' },
    imgedit:    { action:'裁剪', params:'{}' },
    gridcrop:   { rows:3, cols:3 },
    gridedit:   { rows:3, cols:3 },
    imgcmp:     { mode:'并排' },
    presetimg:  { preset:'samples' },
    resize:     { w:1024, h:1024 },
    upscale:    { scale:2 },
    topazimg:   { model:'standard' },
    videoedit:  { action:'裁剪' },
    frameex:    { fps:1 },
    framepair:  { mode:'对比' },
    topazvid:   { model:'standard' },
    textsplit:  { delimiter:'\\n' },
    mention:    { ref:'' },
    loop:       { count:3 },
    relay:      { target:'' },
    groupbox:   { label:'组' },
    browser:    { url:'https://' },
    aggregate:  { mode:'合并' },
    removebg:   { color:'green' },
    rmwatermark:{ method:'auto' },
    drawboard:  { strokes:[] },
    storygrid:  { scenes:5 },
    combine:    { mode:'拼接' },
    panorama:   { scene:'', quality:'high' },
    posemaster: { pose:'standing' },
    materialset:{ items:[] },
    pickfromset:{ options:[] },
    idea:       { note:'' },
    placeholder:{ text:'占位' },
    prelabel:   { prompt:'', task_type:'detection' },
  };
  return m[type] || {};
}

// ─── 渲染入口 ────────────────────────────────────────────────────
async function renderWorkflow() {
  const container = $('page-content');
  if (!container) return;

  container.innerHTML = `
    <div id="wf-container">
      <!-- 左侧：节点库 -->
      <div id="wf-sidebar">
        <div id="wf-sb-header">
          <span>📦 节点库</span>
          <input id="wf-sb-search" placeholder="搜索节点..." oninput="WF_filterNodes()">
        </div>
        <div id="wf-sb-list"></div>
      </div>
      <!-- 中间：画布 -->
      <div id="wf-canvas-wrap">
        <div id="wf-toolbar">
          <button class="wf-tb-btn wf-tb-exec" onclick="WF_execAll()" title="执行全部">▶ 执行全部</button>
          <button class="wf-tb-btn wf-tb-save" onclick="WF_save()" title="保存工作流">💾 保存</button>
          <button class="wf-tb-btn" onclick="document.getElementById('wf-import-input').click()" title="导入工作流">📂 导入</button>
          <input id="wf-import-input" type="file" accept=".json" style="display:none" onchange="WF_import(event)">
          <button class="wf-tb-btn" onclick="WF_export()" title="导出工作流">📤 导出</button>
          <button class="wf-tb-btn wf-tb-clear" onclick="WF_clearAll()" title="清空画布">🗑 清空</button>
          <!-- P1-C-W1: 模板 + 渲染 + canvasId -->
          <button class="wf-tb-btn" onclick="WF_showTemplates()" title="加载模板 (GET /api/canvas/templates)">🧩 模板</button>
          <button class="wf-tb-btn" onclick="WF_renderCanvas('png')" title="渲染画布 (POST /api/canvas/{id}/render)">🎨 渲染</button>
          <span style="margin-left:4px;font-size:11px;color:var(--text-muted)">画布ID:
            <input id="wf-canvas-id" value="default" style="width:90px;padding:2px 4px;background:#0f0f1a;color:#e0e0f0;border:1px solid #2a2a4a;border-radius:3px" onchange="WF.canvasId=this.value">
          </span>
          <span style="margin-left:8px;color:var(--text-muted);font-size:11px">
            <button class="wf-tb-btn" onclick="WF_zoomOut()" title="缩小">−</button>
            <span id="wf-zoom-label" style="padding:0 6px">100%</span>
            <button class="wf-tb-btn" onclick="WF_zoomIn()" title="放大">+</button>
            <button class="wf-tb-btn" onclick="WF_zoomReset()" title="重置缩放">⟲</button>
          </span>
          <span id="wf-status" class="wf-status">就绪</span>
        </div>
        <!-- 无限画布 -->
        <div id="wf-canvas" tabindex="0">
          <svg id="wf-svg" class="wf-svg-layer"></svg>
          <div id="wf-nodes"></div>
          <!-- 临时连线 -->
          <svg id="wf-temp-svg" class="wf-svg-layer" style="pointer-events:none;z-index:9999">
            <line id="wf-temp-line" style="display:none;stroke:#f90;stroke-width:2;stroke-dasharray:5,3" />
          </svg>
          <!-- 缩放控件 -->
          <div id="wf-zoom-ctl">
            <button onclick="WF_zoomOut()">−</button>
            <span id="wf-zoom-display">100%</span>
            <button onclick="WF_zoomIn()">+</button>
            <button onclick="WF_zoomReset()">⟲</button>
          </div>
          <!-- 执行日志 -->
          <div id="wf-log" style="display:none">
            <div id="wf-log-header">📋 执行日志 <span style="float:right;cursor:pointer" onclick="WF_toggleLog()">✕</span></div>
            <div id="wf-log-body"></div>
            <div id="wf-log-progress"><div id="wf-log-bar"></div></div>
          </div>
          <!-- 右键菜单 -->
          <div id="wf-ctxmenu" style="display:none"></div>
        </div>
      </div>
      <!-- 右侧：属性面板 -->
      <div id="wf-prop" style="display:none">
        <div id="wf-prop-header">📋 节点属性</div>
        <div id="wf-prop-body"></div>
      </div>
    </div>
  `;

  // 缓存DOM引用
  WF_el = {
    container: $('wf-container'),
    sidebar: $('wf-sidebar'),
    sbList: $('wf-sb-list'),
    sbSearch: $('wf-sb-search'),
    canvas: $('wf-canvas'),
    nodes: $('wf-nodes'),
    svg: $('wf-svg'),
    tempSvg: $('wf-temp-svg'),
    tempLine: $('wf-temp-line'),
    prop: $('wf-prop'),
    propBody: $('wf-prop-body'),
    log: $('wf-log'),
    logBody: $('wf-log-body'),
    logBar: $('wf-log-bar'),
    status: $('wf-status'),
    zoomLabel: $('wf-zoom-label'),
    zoomDisplay: $('wf-zoom-display'),
    ctxmenu: $('wf-ctxmenu'),
  };

  // 填充节点库
  WF_buildSidebar();

  // 画布事件
  WF_setupCanvasEvents();

  // 键盘事件
  document.addEventListener('keydown', WF_keydown);

  // 从后端加载
  await WF_loadFromBackend();

  // 更新状态
  WF_updateStatus('就绪 — 拖拽左侧节点到画布');
}

// ─── 节点库面板 ──────────────────────────────────────────────────
function WF_buildSidebar() {
  const el = WF_el.sbList;
  el.innerHTML = '';
  for (const cat of WF_CATEGORIES) {
    const section = document.createElement('div');
    section.className = 'wf-sb-section';
    section.innerHTML = `<div class="wf-sb-section-title">${cat.label} <span class="wf-sb-count">${cat.types.length}</span></div>`;
    const list = document.createElement('div');
    list.className = 'wf-sb-items';
    for (const typeId of cat.types) {
      const nd = WF_NT[typeId];
      if (!nd) continue;
      const item = document.createElement('div');
      item.className = 'wf-sb-item';
      item.dataset.type = typeId;
      item.draggable = true;
      item.innerHTML = `<span class="wf-sb-item-icon">${nd.i}</span><span class="wf-sb-item-label">${nd.l}</span>`;
      item.ondragstart = (e) => {
        e.dataTransfer.setData('text/plain', typeId);
        e.dataTransfer.effectAllowed = 'copy';
      };
      item.onclick = () => { WF_createNode(typeId, 100, 50); };
      list.appendChild(item);
    }
    section.appendChild(list);
    el.appendChild(section);
  }
}

function WF_filterNodes() {
  const q = (WF_el.sbSearch?.value || '').toLowerCase().trim();
  document.querySelectorAll('.wf-sb-section').forEach(section => {
    let visible = 0;
    section.querySelectorAll('.wf-sb-item').forEach(item => {
      const label = item.querySelector('.wf-sb-item-label')?.textContent || '';
      const type = item.dataset.type || '';
      const match = !q || label.toLowerCase().includes(q) || type.includes(q);
      item.style.display = match ? '' : 'none';
      if (match) visible++;
    });
    section.querySelector('.wf-sb-count').textContent = visible;
    section.style.display = visible === 0 ? 'none' : '';
  });
}

// ─── 画布事件 ────────────────────────────────────────────────────
function WF_setupCanvasEvents() {
  const cw = WF_el.canvas;
  if (!cw) return;

  // 拖放：从侧栏拖入
  cw.addEventListener('dragover', e => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
  cw.addEventListener('drop', e => {
    e.preventDefault();
    const type = e.dataTransfer.getData('text/plain');
    if (!type || !WF_NT[type]) return;
    const rect = cw.getBoundingClientRect();
    const x = (e.clientX - rect.left - 80) / WF_zoom - WF_panX;
    const y = (e.clientY - rect.top - 30) / WF_zoom - WF_panY;
    WF_createNode(type, x, y);
  });

  // 鼠标滚轮缩放
  cw.addEventListener('wheel', e => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      if (e.deltaY < 0) WF_zoomIn();
      else WF_zoomOut();
    }
  }, { passive: false });

  // 中键/空格拖拽平移
  cw.addEventListener('mousedown', e => {
    // 中键
    if (e.button === 1) {
      e.preventDefault();
      WF_isPanning = true;
      WF_panStart = { x: e.clientX - WF_panX * WF_zoom, y: e.clientY - WF_panY * WF_zoom };
      cw.style.cursor = 'grabbing';
      return;
    }
    // 点击空白取消选中
    if (e.target === cw || e.target.closest('#wf-nodes') === null && e.target.id === 'wf-nodes' || e.target === WF_el.nodes) {
      WF_deselect();
    }
  });

  document.addEventListener('mousemove', e => {
    // 平移
    if (WF_isPanning) {
      WF_panX = (e.clientX - WF_panStart.x) / WF_zoom;
      WF_panY = (e.clientY - WF_panStart.y) / WF_zoom;
      WF_updateTransform();
      return;
    }
    // 拖拽节点
    if (WF_dragging) {
      const cwRect = cw.getBoundingClientRect();
      const nx = (e.clientX - cwRect.left) / WF_zoom - WF_panX - WF_dragOffset.x;
      const ny = (e.clientY - cwRect.top) / WF_zoom - WF_panY - WF_dragOffset.y;
      WF_dragging.style.left = nx + 'px';
      WF_dragging.style.top = ny + 'px';
      const nd = WF.nodes[WF_dragging.dataset.id];
      if (nd) { nd.x = nx; nd.y = ny; }
      WF_updateLines();
    }
    // 拖拽连线
    if (WF_connecting) {
      WF_updateTempLine(e);
    }
  });

  document.addEventListener('mouseup', e => {
    if (WF_isPanning) {
      WF_isPanning = false;
      cw.style.cursor = '';
      return;
    }
    if (WF_dragging) {
      WF_dragging = null;
      WF_saveHistory();
      return;
    }
    if (WF_connecting) {
      // 检查是否落在某个输入端口上
      WF_endConnection(e);
    }
  });

  // 点击其他地方关闭右键菜单
  document.addEventListener('click', e => {
    if (WF_el.ctxmenu && !WF_el.ctxmenu.contains(e.target)) {
      WF_el.ctxmenu.style.display = 'none';
    }
  });
}

// ─── 节点创建 ────────────────────────────────────────────────────
function WF_createNode(type, x, y, data) {
  const id = 'n' + (WF_nextId++);
  const def = WF_NT[type];
  if (!def) return null;
  WF.nodes[id] = {
    id, type, x, y,
    data: data || WF_defaultData(type),
    ports: def.p,
    status: 'idle', // idle | running | done | error
  };
  WF_renderNode(id);
  WF_updateLines();
  WF_saveHistory();
  WF_updateStatus('+ ' + def.l);
  return id;
}

// ─── 节点渲染 ────────────────────────────────────────────────────
function WF_renderNode(id) {
  const nd = WF.nodes[id];
  if (!nd) return;
  const def = WF_NT[nd.type];
  const d = nd.data || {};
  const container = WF_el.nodes;
  if (!container) return;

  let el = document.getElementById('wf-node-' + id);
  if (!el) {
    el = document.createElement('div');
    el.id = 'wf-node-' + id;
    el.className = 'wf-node wf-tp-' + nd.type;
    el.dataset.id = id;
    container.appendChild(el);

    // mousedown：选中+拖拽
    el.addEventListener('mousedown', e => {
      if (e.target.closest('.wf-node-act') || e.target.closest('.wf-port') || e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
      WF_selectNode(id);
      WF_dragging = el;
      const rect = WF_el.canvas.getBoundingClientRect();
      WF_dragOffset.x = (e.clientX - rect.left) / WF_zoom - WF_panX - nd.x;
      WF_dragOffset.y = (e.clientY - rect.top) / WF_zoom - WF_panY - nd.y;
    });

    // 右键菜单
    el.addEventListener('contextmenu', e => {
      e.preventDefault();
      WF_selectNode(id);
      WF_showContextMenu(e.clientX, e.clientY, id);
    });
  }

  // 构建节点内容
  let bodyHtml = '';
  switch (nd.type) {
    case 'text':
      bodyHtml = `<textarea onchange="WF_updateData('${id}','content',this.value)" placeholder="输入文本...">${WF_esc(d.content||'')}</textarea>`;
      break;
    case 'image':
      bodyHtml = d.src ? `<img src="${WF_esc(d.src)}"><input value="${WF_esc(d.src)}" onchange="WF_updateData('${id}','src',this.value)" placeholder="图片URL">`
        : `<div class="wf-node-empty">🖼️ 拖放图片</div><input placeholder="图片URL" onchange="WF_updateData('${id}','src',this.value)">`;
      break;
    case 'video':
      bodyHtml = `<input value="${WF_esc(d.src||'')}" placeholder="视频URL" onchange="WF_updateData('${id}','src',this.value)"><div class="wf-node-meta">${d.dur||5}秒</div>`;
      break;
    case 'audio':
      bodyHtml = `<input value="${WF_esc(d.src||'')}" placeholder="音频URL" onchange="WF_updateData('${id}','src',this.value)"><div class="wf-node-meta">${d.dur||10}秒</div>`;
      break;
    case 'llm':
      bodyHtml = `<textarea onchange="WF_updateData('${id}','prompt',this.value)" placeholder="提示词...">${WF_esc(d.prompt||'')}</textarea><div class="wf-node-meta">🤖 ${d.model||'auto'}</div>`;
      break;
    case 'comfyui':
      bodyHtml = `<textarea style="font-family:monospace;font-size:10px" onchange="WF_updateData('${id}','workflow',this.value)" placeholder="Workflow JSON">${WF_esc(d.workflow||'')}</textarea>`;
      break;
    case 'ppt':
      bodyHtml = `<input value="${WF_esc(d.title||'')}" placeholder="标题" onchange="WF_updateData('${id}','title',this.value)"><div class="wf-node-meta">${d.slides||5}页 · ${d.tpl||'clean-business'}</div>`;
      break;
    case 'script':
      bodyHtml = `<textarea style="font-family:monospace;font-size:10px" onchange="WF_updateData('${id}','code',this.value)" placeholder="/* JS脚本 */">${WF_esc(d.code||'')}</textarea>`;
      break;
    case 'output':
      bodyHtml = `<div class="wf-node-meta">格式: ${d.fmt||'mp4'}</div><div id="wf-out-${id}" class="wf-node-output">等待中</div>`;
      break;
    case 'upload':
      bodyHtml = `<input value="${WF_esc(d.path||'')}" placeholder="文件路径" onchange="WF_updateData('${id}','path',this.value)">`;
      break;
    case 'prelabel':
      bodyHtml = `<textarea onchange="WF_updateData('${id}','prompt',this.value)" placeholder="图片描述...">${WF_esc(d.prompt||'')}</textarea><select onchange="WF_updateData('${id}','task_type',this.value)"><option value="detection"${d.task_type==='detection'?' selected':''}>目标检测</option><option value="classification"${d.task_type==='classification'?' selected':''}>分类</option><option value="tagging"${d.task_type==='tagging'?' selected':''}>标签</option></select>`;
      break;
    case 'resize':
      bodyHtml = `<div class="wf-node-row"><label>宽:</label><input type="number" value="${d.w||1024}" onchange="WF_updateData('${id}','w',Number(this.value))" style="width:60px"><label>高:</label><input type="number" value="${d.h||1024}" onchange="WF_updateData('${id}','h',Number(this.value))" style="width:60px"></div>`;
      break;
    case 'upscale':
      bodyHtml = `<div class="wf-node-row"><label>放大倍数:</label><input type="number" value="${d.scale||2}" min="1" max="4" onchange="WF_updateData('${id}','scale',Number(this.value))" style="width:60px">x</div>`;
      break;
    case 'loop':
      bodyHtml = `<div class="wf-node-row"><label>循环:</label><input type="number" value="${d.count||3}" min="1" onchange="WF_updateData('${id}','count',Number(this.value))" style="width:60px">次</div>`;
      break;
    case 'browser':
      bodyHtml = `<input value="${WF_esc(d.url||'')}" placeholder="https://" onchange="WF_updateData('${id}','url',this.value)">`;
      break;
    default:
      bodyHtml = `<div class="wf-node-meta">${nd.type}</div>`;
  }

  // 端口
  let portsHtml = '';
  for (let i = 0; i < nd.ports.in; i++) {
    portsHtml += `<span class="wf-port wf-port-in" data-nid="${id}" data-port="in" data-idx="${i}"><span class="wf-port-dot"></span>I${i+1}</span>`;
  }
  portsHtml += `<span class="wf-port-spacer"></span>`;
  for (let i = 0; i < nd.ports.out; i++) {
    portsHtml += `<span class="wf-port wf-port-out" data-nid="${id}" data-port="out" data-idx="${i}"><span class="wf-port-dot"></span>O${i+1}</span>`;
  }

  // 状态颜色
  const statusMap = { idle:'', running:'wf-status-running', done:'wf-status-done', error:'wf-status-error' };

  el.innerHTML = `
    <div class="wf-node-header" style="background:${def.c}">
      <span>${def.i} ${def.l}</span>
      <span class="wf-node-status ${statusMap[nd.status]||''}"></span>
    </div>
    <div class="wf-node-body">${bodyHtml}</div>
    <div class="wf-node-ports">${portsHtml}</div>
    <div class="wf-node-actions">
      <button class="wf-act-exec" onclick="WF_execNode('${id}')" title="执行此节点">▶</button>
      <button class="wf-act-del" onclick="WF_deleteNode('${id}')" title="删除">✕</button>
    </div>
  `;

  el.style.left = nd.x + 'px';
  el.style.top = nd.y + 'px';
  el.style.zIndex = WF_selected === id ? 100 : 1;

  // 端口事件：输出端口开始连线
  el.querySelectorAll('.wf-port-out').forEach(p => {
    p.addEventListener('mousedown', e => {
      e.stopPropagation();
      e.preventDefault();
      WF_startConnection(nd.id, 'out', parseInt(p.dataset.idx));
    });
  });
  // 输入端口接收连线
  el.querySelectorAll('.wf-port-in').forEach(p => {
    p.addEventListener('mouseup', e => {
      e.stopPropagation();
      if (WF_connecting) {
        WF_tryConnect(nd.id, 'in', parseInt(p.dataset.idx));
      }
    });
  });
}

// ─── 节点选中/取消 ───────────────────────────────────────────────
function WF_selectNode(id) {
  WF_selected = id;
  document.querySelectorAll('.wf-node').forEach(n => n.classList.remove('wf-sel'));
  const el = document.getElementById('wf-node-' + id);
  if (el) { el.classList.add('wf-sel'); el.style.zIndex = 100; }
  WF_showProperties(id);
}

function WF_deselect() {
  WF_selected = null;
  document.querySelectorAll('.wf-node').forEach(n => n.classList.remove('wf-sel'));
  if (WF_el.prop) WF_el.prop.style.display = 'none';
}

// ─── 属性面板 ────────────────────────────────────────────────────
function WF_showProperties(id) {
  const nd = WF.nodes[id];
  if (!nd || !WF_el.prop) return;
  const def = WF_NT[nd.type];
  const d = nd.data || {};
  WF_el.prop.style.display = 'flex';
  let html = `<div class="wf-prop-section">
    <div class="wf-prop-title">${def.i} ${def.l}</div>
    <div class="wf-prop-id">ID: ${id} · 类型: ${nd.type}</div>
    <div class="wf-prop-field"><label>位置 X</label><input type="number" value="${Math.round(nd.x)}" onchange="WF_updatePos('${id}','x',Number(this.value))"></div>
    <div class="wf-prop-field"><label>位置 Y</label><input type="number" value="${Math.round(nd.y)}" onchange="WF_updatePos('${id}','y',Number(this.value))"></div>
  </div>`;
  html += `<div class="wf-prop-section"><div class="wf-prop-title">参数</div>`;
  for (const [key, val] of Object.entries(d)) {
    if (key === 'output') continue;
    const strVal = typeof val === 'object' ? JSON.stringify(val) : String(val);
    html += `<div class="wf-prop-field">
      <label>${key}</label>
      <input value="${WF_esc(strVal)}" onchange="WF_updateData('${id}','${key}',this.value)">
    </div>`;
  }
  html += `</div>`;
  html += `<div class="wf-prop-actions">
    <button onclick="WF_execNode('${id}')" class="wf-act-exec">▶ 执行</button>
    <button onclick="WF_deleteNode('${id}')" class="wf-act-del">✕ 删除</button>
  </div>`;
  // 连线信息
  const conns = WF.connections.filter(c => c.from === id || c.to === id);
  if (conns.length > 0) {
    html += `<div class="wf-prop-section"><div class="wf-prop-title">连线 (${conns.length})</div>`;
    for (const c of conns) {
      const label = c.from === id ? `→ ${c.to}` : `← ${c.from}`;
      html += `<div class="wf-prop-conn">${label}</div>`;
    }
    html += `</div>`;
  }
  WF_el.propBody.innerHTML = html;
}

// ─── 节点数据更新 ────────────────────────────────────────────────
function WF_updateData(id, key, val) {
  const nd = WF.nodes[id];
  if (!nd) return;
  nd.data[key] = val;
  WF_saveHistory();
}

function WF_updatePos(id, axis, val) {
  const nd = WF.nodes[id];
  if (!nd) return;
  nd[axis] = val;
  const el = document.getElementById('wf-node-' + id);
  if (el) el.style[axis === 'x' ? 'left' : 'top'] = val + 'px';
  WF_updateLines();
}

function WF_deleteNode(id) {
  const el = document.getElementById('wf-node-' + id);
  if (el) el.remove();
  delete WF.nodes[id];
  WF.connections = WF.connections.filter(c => c.from !== id && c.to !== id);
  if (WF_selected === id) { WF_selected = null; if (WF_el.prop) WF_el.prop.style.display = 'none'; }
  WF_updateLines();
  WF_saveHistory();
  WF_updateStatus('✕ 删除');
}

// ─── 连线系统 ────────────────────────────────────────────────────
function WF_startConnection(id, port, idx) {
  WF_connecting = { id, port, idx };
  const line = WF_el.tempLine;
  if (line) line.style.display = '';
  // 初始位置
  const srcPort = document.querySelector(`.wf-port-out[data-nid="${id}"][data-idx="${idx}"]`);
  if (srcPort) {
    const rect = srcPort.getBoundingClientRect();
    const cwRect = WF_el.canvas.getBoundingClientRect();
    line.setAttribute('x1', rect.left + rect.width/2 - cwRect.left);
    line.setAttribute('y1', rect.top + rect.height/2 - cwRect.top);
    line.setAttribute('x2', rect.left + rect.width/2 - cwRect.left + 50);
    line.setAttribute('y2', rect.top + rect.height/2 - cwRect.top + 50);
  }
}

function WF_updateTempLine(e) {
  const line = WF_el.tempLine;
  if (!line) return;
  const cwRect = WF_el.canvas.getBoundingClientRect();
  // 源端口位置
  const srcPort = document.querySelector(`.wf-port-${WF_connecting.port}[data-nid="${WF_connecting.id}"][data-idx="${WF_connecting.idx}"]`);
  if (srcPort) {
    const rect = srcPort.getBoundingClientRect();
    line.setAttribute('x1', rect.left + rect.width/2 - cwRect.left);
    line.setAttribute('y1', rect.top + rect.height/2 - cwRect.top);
  }
  line.setAttribute('x2', e.clientX - cwRect.left);
  line.setAttribute('y2', e.clientY - cwRect.top);
}

function WF_tryConnect(toId, toPort, toIdx) {
  if (!WF_connecting) return;
  if (WF_connecting.id === toId) { WF_cancelConnection(); return; }
  // 不能重复连线
  const dup = WF.connections.some(c =>
    c.from === WF_connecting.id && c.fromP === WF_connecting.idx &&
    c.to === toId && c.toP === toIdx
  );
  if (dup) { WF_cancelConnection(); return; }
  WF.connections.push({
    from: WF_connecting.id,
    fromP: WF_connecting.idx,
    to: toId,
    toP: toIdx,
  });
  WF_cancelConnection();
  WF_updateLines();
  WF_saveHistory();
  WF_updateStatus('+ 连线');
}

function WF_endConnection(e) {
  if (!WF_connecting) return;
  // 检查e.target是否落在输入端口上
  const target = e.target;
  if (target && target.closest) {
    const port = target.closest('.wf-port-in');
    if (port) {
      const nid = port.dataset.nid;
      const idx = parseInt(port.dataset.idx);
      WF_tryConnect(nid, 'in', idx);
      return;
    }
  }
  WF_cancelConnection();
}

function WF_cancelConnection() {
  if (WF_el.tempLine) WF_el.tempLine.style.display = 'none';
  WF_connecting = null;
}

function WF_updateLines() {
  const svg = WF_el.svg;
  if (!svg) return;
  const cwRect = WF_el.canvas.getBoundingClientRect();
  let html = '';
  for (let i = 0; i < WF.connections.length; i++) {
    const c = WF.connections[i];
    const fEl = document.getElementById('wf-node-' + c.from);
    const tEl = document.getElementById('wf-node-' + c.to);
    if (!fEl || !tEl) continue;

    // 找到对应端口元素
    const srcPort = fEl.querySelector(`.wf-port-out[data-idx="${c.fromP}"]`);
    const tgtPort = tEl.querySelector(`.wf-port-in[data-idx="${c.toP}"]`);
    if (!srcPort || !tgtPort) continue;

    const srcRect = srcPort.getBoundingClientRect();
    const tgtRect = tgtPort.getBoundingClientRect();

    const x1 = srcRect.left + srcRect.width/2 - cwRect.left;
    const y1 = srcRect.top + srcRect.height/2 - cwRect.top;
    const x2 = tgtRect.left + tgtRect.width/2 - cwRect.left;
    const y2 = tgtRect.top + tgtRect.height/2 - cwRect.top;
    const mx = (x1 + x2) / 2;

    html += `<path d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}" class="wf-line" onclick="WF_deleteConnection(${i})"/>`;
  }
  svg.innerHTML = html;
}

function WF_deleteConnection(idx) {
  WF.connections.splice(idx, 1);
  WF_updateLines();
  WF_saveHistory();
}

// ─── 缩放与平移 ──────────────────────────────────────────────────
function WF_updateTransform() {
  const cw = WF_el.canvas;
  if (!cw) return;
  // 用CSS transform实现缩放+平移
  const nodes = WF_el.nodes;
  const svg = WF_el.svg;
  if (nodes) nodes.style.transform = `translate(${WF_panX * WF_zoom}px, ${WF_panY * WF_zoom}px) scale(${WF_zoom})`;
  if (svg) svg.style.transform = `translate(${WF_panX}px, ${WF_panY}px)`;
  // Note: SVG lines are in screen coords already, but nodes need zoom/pan
}

function WF_zoomIn() {
  WF_zoom = Math.min(3, WF_zoom * 1.2);
  WF_updateZoomUI();
}

function WF_zoomOut() {
  WF_zoom = Math.max(0.15, WF_zoom / 1.2);
  WF_updateZoomUI();
}

function WF_zoomReset() {
  WF_zoom = 1;
  WF_panX = 0;
  WF_panY = 0;
  WF_updateZoomUI();
}

function WF_updateZoomUI() {
  const pct = Math.round(WF_zoom * 100);
  if (WF_el.zoomLabel) WF_el.zoomLabel.textContent = pct + '%';
  if (WF_el.zoomDisplay) WF_el.zoomDisplay.textContent = pct + '%';
  WF_updateTransform();
  // 重新计算连线位置
  setTimeout(WF_updateLines, 10);
}

// ─── 节点执行 ────────────────────────────────────────────────────
async function WF_execNode(id) {
  const nd = WF.nodes[id];
  if (!nd) return;
  nd.status = 'running';
  WF_updateNodeStatus(id);
  WF_showLog();
  WF_addLog('info', `▶ 执行 ${WF_NT[nd.type]?.l||nd.type} 节点...`);

  try {
    let r;
    const data = nd.data || {};
    switch (nd.type) {
      case 'llm':
        r = await apiPost('/api/chat', { user_input: data.prompt || '你好' });
        WF_addLog('ok', '→ AI回复: ' + (r?.message || '无'));
        if (r?.message) { nd.data.output = r.message.substring(0, 500); WF_updateData(id, 'output', r.message.substring(0, 500)); }
        break;
      case 'image':
      case 'ppt':
        r = await apiPost('/api/' + nd.type + '/generate', { user_input: data.src || data.title || '' });
        WF_addLog('ok', `→ ${WF_NT[nd.type].l}已提交`);
        break;
      case 'seedance':
        r = await apiPost('/imdf/external/list', { type:'seedance', params:{ prompt: data.prompt, model: data.model || 'seedance2' } });
        WF_addLog('ok', '→ Seedance已提交');
        break;
      case 'runninghub':
        r = await apiPost('/imdf/external/list', { type:'runninghub', params:{ endpoint: data.endpoint } });
        WF_addLog('ok', '→ RunningHub已提交');
        break;
      case 'portrait':
        r = await apiPost('/imdf/external/list', { type:'portrait', params:{ gender: data.gender, style: data.style } });
        WF_addLog('ok', '→ 人像已提交');
        break;
      case 'falbox':
        WF_addLog('ok', '→ Fal模型');
        break;
      case 'grok':
        WF_addLog('ok', '→ Grok');
        break;
      case 'resize':
        r = await apiPost('/imdf/images/resize', { width: data.w, height: data.h });
        WF_addLog('ok', '→ 缩放已提交');
        break;
      case 'prelabel':
        r = await apiPost('/api/prelabel', { image_desc: data.prompt || '一张图片', task_type: data.task_type || 'detection' });
        WF_addLog('ok', '→ AI标注完成');
        break;
      case 'comfyui':
        r = await apiPost('/api/comfyui/run', { workflow: data.workflow || '' });
        WF_addLog('ok', '→ ComfyUI已提交');
        break;
      case 'panorama':
      case 'posemaster':
        r = await apiGet('/api/3d/' + (nd.type === 'panorama' ? 'scenes' : 'poses'));
        WF_addLog('ok', `→ ${WF_NT[nd.type].l}已就绪`);
        break;
      case 'output':
        WF_addLog('ok', '→ 输出就绪');
        break;
      case 'upload':
        WF_addLog('ok', '→ 上传准备就绪');
        break;
      default:
        WF_addLog('ok', `→ ${WF_NT[nd.type]?.l||nd.type}已提交`);
    }
    nd.status = 'done';
  } catch (e) {
    WF_addLog('er', '执行失败: ' + e.message);
    nd.status = 'error';
  }
  WF_updateNodeStatus(id);
  WF_updateLines();
}

function WF_updateNodeStatus(id) {
  const el = document.getElementById('wf-node-' + id);
  if (!el) return;
  const nd = WF.nodes[id];
  if (!nd) return;
  const statusEl = el.querySelector('.wf-node-status');
  if (!statusEl) return;
  statusEl.className = 'wf-node-status';
  if (nd.status === 'running') statusEl.classList.add('wf-status-running');
  else if (nd.status === 'done') statusEl.classList.add('wf-status-done');
  else if (nd.status === 'error') statusEl.classList.add('wf-status-error');
}

// ─── DAG执行 ─────────────────────────────────────────────────────
async function WF_execAll() {
  WF_showLog();
  WF_addLog('info', '=== 工作流执行 (DAG) ===');

  // 发送到后端API
  const nodesList = Object.values(WF.nodes).map(nd => ({
    id: nd.id,
    type: nd.type,
    data: nd.data,
  }));
  const connections = WF.connections;

  try {
    const result = await apiPost('/api/workflow/execute', {
      nodes: nodesList,
      connections: connections,
    });
    if (result.success) {
      WF_addLog('ok', `✅ DAG执行成功! ${Object.keys(WF.nodes).length}个节点`);
      // 更新所有节点状态为done
      for (const id of Object.keys(WF.nodes)) {
        WF.nodes[id].status = 'done';
        WF_updateNodeStatus(id);
      }
    } else {
      WF_addLog('er', 'DAG执行失败: ' + (result.error || '未知错误'));
      // 标记错误
      for (const id of Object.keys(WF.nodes)) {
        WF.nodes[id].status = 'error';
        WF_updateNodeStatus(id);
      }
    }
  } catch (e) {
    // P2-2-W1: 后端DAG失败时不再前端伪造执行, 标记所有节点为错误并提示用户
    WF_addLog('error', '❌ 后端工作流执行失败: ' + (e.message || e));
    (window.toastError || ((m) => alert(m)))('后端工作流执行失败, 请检查节点配置');
    for (const id of Object.keys(WF.nodes)) {
      WF.nodes[id].status = 'error';
      WF_updateNodeStatus(id);
    }
  }
}

// ─── 日志 ────────────────────────────────────────────────────────
function WF_showLog() {
  if (WF_el.log) WF_el.log.style.display = 'block';
}

function WF_toggleLog() {
  if (WF_el.log) WF_el.log.style.display = WF_el.log.style.display === 'none' ? 'block' : 'none';
}

function WF_addLog(type, msg) {
  const body = WF_el.logBody;
  if (!body) return;
  const d = document.createElement('div');
  d.className = 'wf-log-line ' + (type === 'ok' ? 'wf-log-ok' : type === 'er' ? 'wf-log-er' : 'wf-log-info');
  d.textContent = '[' + new Date().toLocaleTimeString() + '] ' + msg;
  body.appendChild(d);
  body.scrollTop = body.scrollHeight;
  WF_logLines++;
  // 更新进度条
  const bar = WF_el.logBar;
  if (bar) bar.style.width = Math.min(100, WF_logLines * 3) + '%';
}

// ─── 保存/加载 ───────────────────────────────────────────────────
async function WF_save() {
  const data = { nodes: WF.nodes, connections: WF.connections };
  // P1-C-W1: 用规范化的 canvas id (P1-C-W1 spec'd endpoint)
  const canvasId = WF.canvasId || 'default';
  try {
    // 保存到localStorage (兜底)
    localStorage.setItem('imdf_workflow', JSON.stringify(data));
    // P1-C-W1: 主路径 — POST /api/canvas/{id}/save (task spec)
    let saved = false;
    try {
      const r = await apiPost('/api/canvas/' + encodeURIComponent(canvasId) + '/save', data);
      if (r && r.success) { saved = true; WF_addLog('ok', `💾 已保存 (${Object.keys(WF.nodes).length}节点, id=${canvasId})`); }
    } catch (e) { /* fall through to legacy */ }
    // 兜底: 旧端点 /canvas/state (向后兼容)
    if (!saved) {
      try { await apiPost('/canvas/state', data); saved = true; } catch (e2) { /* ignore */ }
    }
    if (saved) {
      WF_updateStatus('已保存');
    } else {
      WF_addLog('er', '保存失败: 所有端点均不可达');
    }
  } catch (e) {
    WF_addLog('er', '保存失败: ' + e.message);
  }
}

async function WF_loadFromBackend() {
  // P1-C-W1: 主路径 — GET /api/canvas/{id} (task spec)
  const canvasId = WF.canvasId || 'default';
  let loaded = false;
  try {
    const r = await apiGet('/api/canvas/' + encodeURIComponent(canvasId));
    if (r && r.success && r.data) {
      const nodes = r.data.nodes || {};
      const conns = r.data.connections || [];
      if (Object.keys(nodes).length > 0) {
        _wfApplyLoadedState(nodes, conns);
        loaded = true;
        WF_addLog('ok', `📂 已从 /api/canvas/${canvasId} 加载 ${Object.keys(WF.nodes).length} 节点`);
      }
    } else if (r && r.code === 404) {
      WF_addLog('info', `画布 ${canvasId} 首次保存 — 空白画布`);
    }
  } catch (e) { /* fall through */ }
  // 兜底: 旧端点 /canvas/state
  if (!loaded) {
    try {
      const resp = await fetch('/canvas/state');
      if (resp.ok) {
        const state = await resp.json();
        const nodes = state?.nodes || state?.canvas?.elements || {};
        const conns = state?.connections || [];
        if (Object.keys(nodes).length > 0) {
          _wfApplyLoadedState(nodes, conns);
          loaded = true;
        }
      }
    } catch (e) {
    // Try localStorage
    try {
      const saved = localStorage.getItem('imdf_workflow');
      if (saved) {
        const data = JSON.parse(saved);
        if (data.nodes && Object.keys(data.nodes).length > 0) {
          for (const [id, nd] of Object.entries(data.nodes)) {
            WF_createNode(nd.type, nd.x || 100, nd.y || 50, nd.data);
          }
          WF.connections = (data.connections || []).filter(c => WF.nodes[c.from] && WF.nodes[c.to]);
          WF_updateLines();
          WF_updateStatus(`已从本地加载 ${Object.keys(WF.nodes).length} 节点`);
        }
      }
    } catch (e2) {}
  }
  }
}

function WF_export() {
  // P1-C-W1: 优先 POST /api/canvas/{id}/export (后端生成 download_url)
  // 兜底: 本地下载
  const data = { nodes: WF.nodes, connections: WF.connections, version: '1.0' };
  const canvasId = WF.canvasId || 'default';
  apiGet('/api/canvas/' + encodeURIComponent(canvasId) + '/export?format=json').then(function(r){
    if (r && r.success && r.data && r.data.download_url) {
      WF_addLog('ok', '📤 后端导出: ' + r.data.download_url);
      // 同时触发本地下载
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'workflow_' + canvasId + '_' + Date.now() + '.json';
      a.click();
      URL.revokeObjectURL(url);
    } else {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'workflow_' + Date.now() + '.json';
      a.click();
      URL.revokeObjectURL(url);
    }
    WF_updateStatus('已导出');
  }).catch(function(){
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'workflow_' + Date.now() + '.json';
    a.click();
    URL.revokeObjectURL(url);
    WF_updateStatus('已导出');
  });
}

// P1-C-W1: 加载画布模板 — 替换当前画布
async function WF_loadTemplate(tplId) {
  try {
    const r = await apiGet('/api/canvas/templates');
    if (!r || !r.success || !r.data || !r.data.templates) {
      WF_addLog('er', '模板列表加载失败');
      return;
    }
    const tpl = r.data.templates.find(t => t.id === tplId);
    if (!tpl) { WF_addLog('er', '模板不存在: ' + tplId); return; }
    // 清空当前画布
    WF_clearAll();
    // 加载模板节点
    const nodes = tpl.nodes || [];
    for (const nd of nodes) {
      if (nd && nd.type) {
        WF_createNode(nd.type, nd.x || 100, nd.y || 50, nd.data);
      }
    }
    WF.connections = (tpl.connections || []).filter(c => WF.nodes[c.from] && WF.nodes[c.to]);
    WF_updateLines();
    WF_addLog('ok', `🧩 已加载模板 ${tpl.name} (${nodes.length}节点)`);
    WF_updateStatus('模板已加载: ' + tpl.name);
  } catch (e) {
    WF_addLog('er', '加载模板失败: ' + e.message);
  }
}

// P1-C-W1: 触发画布渲染 (异步任务)
async function WF_renderCanvas(format) {
  const canvasId = WF.canvasId || 'default';
  try {
    const r = await apiPost('/api/canvas/' + encodeURIComponent(canvasId) + '/render', { format: format || 'png' });
    if (r && r.success && r.data) {
      WF_addLog('ok', `🎨 渲染已提交 — task_id=${r.data.task_id}`);
      WF_updateStatus('渲染中: ' + r.data.task_id);
    } else {
      WF_addLog('er', '渲染提交失败');
    }
  } catch (e) {
    WF_addLog('er', '渲染失败: ' + e.message);
  }
}

// P1-C-W1: 弹出模板选择 modal (GET /api/canvas/templates)
async function WF_showTemplates() {
  if (typeof showModal !== 'function') {
    WF_addLog('er', 'showModal 不可用');
    return;
  }
  showModal(
    '<span class="modal-close" onclick="closeModal()">✕</span>' +
    '<h4 style="margin-bottom:12px;color:#4a7aff">🧩 画布模板 <span style="font-size:11px;color:#8888aa">(GET /api/canvas/templates)</span></h4>' +
    '<div id="wf-tpl-list" style="color:#8888aa;font-size:12px;text-align:center;padding:20px 0">加载中...</div>'
  );
  try {
    const r = await apiGet('/api/canvas/templates');
    if (!r || !r.success || !r.data || !r.data.templates) {
      document.getElementById('wf-tpl-list').innerHTML = '⚠️ 模板列表加载失败: ' + (r?.error || '后端无响应');
      return;
    }
    const tpls = r.data.templates;
    if (tpls.length === 0) {
      document.getElementById('wf-tpl-list').innerHTML = '📭 暂无模板';
      return;
    }
    let html = '<div style="display:grid;gap:8px">';
    for (const t of tpls) {
      html += '<div style="padding:10px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:6px;cursor:pointer" onclick="WF_loadTemplate(\'' + t.id + '\')">' +
        '<div style="color:#4a7aff;font-weight:600">' + (t.name || t.id) + '</div>' +
        '<div style="color:#8888aa;font-size:11px;margin-top:4px">' + (t.desc || '—') + '</div>' +
        '<div style="color:#666;font-size:10px;margin-top:4px">节点: ' + (t.nodes?.length || 0) + ' · 连线: ' + (t.connections?.length || 0) + '</div>' +
        '</div>';
    }
    html += '</div>';
    document.getElementById('wf-tpl-list').innerHTML = html;
  } catch (e) {
    document.getElementById('wf-tpl-list').innerHTML = '❌ 加载失败: ' + e.message;
  }
}

// P1-C-W1: 内部 helper — 应用已加载的状态到画布
function _wfApplyLoadedState(nodes, conns) {
  for (const [id, nd] of Object.entries(nodes)) {
    if (nd && nd.type) {
      const newId = WF_createNode(nd.type, nd.x || 100, nd.y || 50, nd.data);
      if (newId && id !== newId && WF.nodes[newId]) {
        for (const c of conns) {
          if (c.from === id) c.from = newId;
          if (c.to === id) c.to = newId;
        }
      }
    }
  }
  WF.connections = conns.filter(c => WF.nodes[c.from] && WF.nodes[c.to]);
  WF_updateLines();
  WF_updateStatus(`已加载 ${Object.keys(WF.nodes).length} 节点`);
}

function WF_import(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const data = JSON.parse(e.target.result);
      if (data.nodes) {
        // Clear existing
        WF_clearAllNoConfirm();
        for (const [id, nd] of Object.entries(data.nodes)) {
          WF_createNode(nd.type, nd.x || 100 + Math.random() * 50, nd.y || 50 + Math.random() * 50, nd.data);
        }
        WF.connections = (data.connections || []).filter(c => WF.nodes[c.from] && WF.nodes[c.to]);
        WF_updateLines();
        WF_saveHistory();
        WF_addLog('ok', `📂 已导入: ${file.name} (${Object.keys(WF.nodes).length}节点)`);
        WF_updateStatus('已导入');
      }
    } catch (ex) {
      WF_addLog('er', '导入失败: ' + ex.message);
    }
  };
  reader.readAsText(file);
}

function WF_clearAll() {
  if (!confirm('确定清除所有节点和连线?')) return;
  WF_clearAllNoConfirm();
}

function WF_clearAllNoConfirm() {
  for (const id of Object.keys(WF.nodes)) {
    const el = document.getElementById('wf-node-' + id);
    if (el) el.remove();
  }
  WF.nodes = {};
  WF.connections = [];
  if (WF_el.svg) WF_el.svg.innerHTML = '';
  if (WF_el.logBody) WF_el.logBody.innerHTML = '';
  WF_logLines = 0;
  WF_selected = null;
  if (WF_el.prop) WF_el.prop.style.display = 'none';
  WF_updateStatus('已清空');
}

// ─── 历史(撤销/重做) ─────────────────────────────────────────────
function WF_saveHistory() {
  const snapshot = JSON.stringify({ nodes: WF.nodes, connections: WF.connections });
  if (WF_historyIdx < WF_history.length - 1) {
    WF_history = WF_history.slice(0, WF_historyIdx + 1);
  }
  WF_history.push(snapshot);
  if (WF_history.length > 50) WF_history.shift();
  WF_historyIdx = WF_history.length - 1;
}

function WF_undo() {
  if (WF_historyIdx > 0) {
    WF_historyIdx--;
    WF_restoreSnapshot(JSON.parse(WF_history[WF_historyIdx]));
  }
}

function WF_redo() {
  if (WF_historyIdx < WF_history.length - 1) {
    WF_historyIdx++;
    WF_restoreSnapshot(JSON.parse(WF_history[WF_historyIdx]));
  }
}

function WF_restoreSnapshot(data) {
  // Clear all nodes
  for (const id of Object.keys(WF.nodes)) {
    const el = document.getElementById('wf-node-' + id);
    if (el) el.remove();
  }
  WF.nodes = {};
  WF.connections = [];
  if (WF_el.svg) WF_el.svg.innerHTML = '';

  // Restore
  if (data.nodes) {
    for (const [id, nd] of Object.entries(data.nodes)) {
      WF.nodes[id] = nd;
      WF_renderNode(id);
    }
  }
  if (data.connections) {
    WF.connections = data.connections;
    WF_updateLines();
  }
}

// ─── 键盘快捷键 ──────────────────────────────────────────────────
function WF_keydown(e) {
  if (e.ctrlKey && e.key === 'z') { e.preventDefault(); WF_undo(); }
  if (e.ctrlKey && e.key === 'y') { e.preventDefault(); WF_redo(); }
  if (e.ctrlKey && e.key === 's') { e.preventDefault(); WF_save(); }
  if ((e.key === 'Delete' || e.key === 'Backspace') && WF_selected && !e.target.closest('input,textarea,select')) {
    e.preventDefault();
    WF_deleteNode(WF_selected);
  }
}

// ─── 右键菜单 ────────────────────────────────────────────────────
function WF_showContextMenu(x, y, id) {
  const menu = WF_el.ctxmenu;
  if (!menu) return;
  menu.style.display = 'block';
  menu.style.left = x + 'px';
  menu.style.top = y + 'px';
  menu.innerHTML = `
    <div onclick="WF_execNode('${id}');WF_el.ctxmenu.style.display='none'">▶ 执行</div>
    <div onclick="WF_deleteNode('${id}');WF_el.ctxmenu.style.display='none'">✕ 删除</div>
    <div onclick="WF_deselect();WF_el.ctxmenu.style.display='none'">取消选中</div>
  `;
}

// ─── 工具函数 ────────────────────────────────────────────────────
function WF_esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function WF_updateStatus(msg) {
  if (WF_el.status) WF_el.status.textContent = msg;
}

// ─── 入口函数（由app.js的renderWorkflow调用） ──────────────────
function renderWorkflowCanvas() {
  renderWorkflow();
}
