/* IMDF v3 图片标注编辑器 — CVAT对标全功能版
   工具: BBox | Polygon | Keypoint | Tag | Freehand
   Canvas渲染 + 缩放/平移 + 图片编辑 + 标注管理 + 撤销/重做 */

// ========== 全局状态 ==========
const IE = {
  image: null,            // HTMLImageElement
  imageOriginal: null,   // 原始图片(用于重置编辑)
  imageFileName: null,   // 当前加载的文件名
  annotations: [],        // [{id, type, label, color, points:[{x,y}], visible:true}]
  history: [],            // 撤销历史快照
  historyIndex: -1,
  maxHistory: 50,

  // 工具状态
  currentTool: 'bbox',   // bbox | polygon | keypoint | tag | freehand
  isDrawing: false,
  drawingPoints: [],      // 当前绘制中的点
  previewPoint: null,     // 鼠标悬停预览点
  drawingBBox: null,      // {x,y,w,h} 拖拽中的bbox

  // 选中
  selectedId: null,

  // 视图
  zoom: 1,
  panX: 0,
  panY: 0,
  isPanning: false,
  panStartX: 0,
  panStartY: 0,

  // 图片编辑
  filters: {
    brightness: 100,  // %
    contrast: 100,
    saturation: 100,
    rotation: 0,      // 0|90|180|270
    flipH: false,
    flipV: false,
    grayscale: false,
  },

  // 颜色调色板
  palette: ['#e74c3c','#3498db','#2ecc71','#f39c12','#9b59b6','#1abc9c','#e67e22','#1dd1a1','#e84393','#00cec9'],
  paletteIdx: 0,
};

// ========== 主渲染函数 ==========
function renderImageEditor() {
  const c = $('page-content');
  if (!c) return;

  const annoCount = IE.annotations.length;
  const zoomPct = Math.round(IE.zoom * 100);
  const fileName = IE.imageFileName || '—';

  c.innerHTML = `
    <!-- ===== 页面头部 ===== -->
    <div class="page-header" style="margin-bottom:10px">
      <div>
        <div class="page-title">🖌️ 图片标注</div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px">CVAT对标 · BBox/多边形/关键点/标签/自由绘制</div>
      </div>
      <div class="page-stats">
        <div class="page-stat">
          <div class="page-stat-val" style="color:var(--accent-blue)" id="ie-stat-count">${annoCount}</div>
          <div class="page-stat-label">标注数</div>
        </div>
        <div class="page-stat">
          <div class="page-stat-val" style="color:var(--accent-green)" id="ie-stat-frame">${fileName}</div>
          <div class="page-stat-label">当前帧</div>
        </div>
        <div class="page-stat">
          <div class="page-stat-val" style="color:var(--accent-purple)" id="ie-stat-zoom">${zoomPct}%</div>
          <div class="page-stat-label">缩放比例</div>
        </div>
      </div>
    </div>

    <div id="ie-root" style="display:flex;flex-direction:column;height:calc(100vh - 270px)">
      <!-- 顶栏：工具切换 -->
      <div id="ie-toolbar" style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px 8px 0 0;flex-wrap:wrap">
        <span style="font-weight:600;font-size:12px;color:var(--accent-blue);margin-right:4px">🔧 工具</span>
        <button class="btn btn-sm ie-tool-btn active" data-tool="bbox" onclick="IE_setTool('bbox')" title="BBox矩形框 (B)">⬜ BBox</button>
        <button class="btn btn-sm ie-tool-btn" data-tool="polygon" onclick="IE_setTool('polygon')" title="多边形 (P)">🔷 多边形</button>
        <button class="btn btn-sm ie-tool-btn" data-tool="keypoint" onclick="IE_setTool('keypoint')" title="关键点 (K)">📍 关键点</button>
        <button class="btn btn-sm ie-tool-btn" data-tool="tag" onclick="IE_setTool('tag')" title="分类标签 (T)">🏷️ 标签</button>
        <button class="btn btn-sm ie-tool-btn" data-tool="freehand" onclick="IE_setTool('freehand')" title="自由绘制 (D)">✏️ 自由</button>
        <span style="flex:1"></span>
        <button class="btn btn-sm btn-outline ie-action-btn" onclick="document.getElementById('ie-file-input').click()" title="打开本地图片文件">📁 打开文件</button>
        <button class="btn btn-sm btn-outline ie-action-btn" onclick="IE_openServerFiles()" title="从服务器加载图片">📂 服务器</button>
        <input type="file" id="ie-file-input" accept="image/*" onchange="IE_loadImageFile(this)" style="display:none">
        <button class="btn btn-sm btn-outline ie-action-btn" onclick="IE_fitWindow()" title="适应窗口 (F)">🔍 适应</button>
        <button class="btn btn-sm btn-outline ie-action-btn" onclick="IE_resetView()" title="重置视图">🔄 重置</button>
        <button class="btn btn-sm btn-outline ie-action-btn" onclick="IE_undo()" title="撤销 Ctrl+Z">↩️ 撤销</button>
        <button class="btn btn-sm btn-outline ie-action-btn" onclick="IE_redo()" title="重做 Ctrl+Shift+Z">↪️ 重做</button>
        <button class="btn btn-sm btn-primary ie-btn-save" onclick="IE_saveAnnotations()" title="保存标注">💾 保存</button>
      </div>

      <!-- 主体：左侧图片编辑 + 画布 + 右侧面板 -->
      <div style="display:flex;flex:1;overflow:hidden">

        <!-- 左侧：图片编辑面板 -->
        <div id="ie-edit-panel" style="width:200px;min-width:200px;background:var(--bg-tertiary);border-left:1px solid var(--border);border-bottom:1px solid var(--border);overflow-y:auto;padding:10px;font-size:11px;display:flex;flex-direction:column;gap:10px">
          <div style="font-weight:600;font-size:12px;color:var(--text-primary);border-bottom:1px solid var(--border);padding-bottom:6px">🖼️ 图片编辑</div>

          <!-- 加载图片 -->
          <div>
            <label style="color:var(--text-muted);font-size:10px;display:block;margin-bottom:3px">加载图片</label>
            <input type="file" accept="image/*" onchange="IE_loadImageFile(this)" style="width:100%;font-size:10px;color:var(--text-secondary)">
            <div style="margin-top:4px;font-size:10px;color:var(--text-muted)">或输入URL:</div>
            <input id="ie-url-input" type="text" placeholder="https://..." style="width:100%;padding:4px 6px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:10px;margin-top:2px"
              onkeydown="if(event.key==='Enter')IE_loadFromUrl($('ie-url-input').value)">
          </div>

          <!-- 亮度 -->
          <div>
            <label style="color:var(--text-muted);font-size:10px;display:block;margin-bottom:2px">亮度 <span id="ie-bright-val">100%</span></label>
            <input type="range" min="0" max="200" value="100" oninput="IE_updateFilter('brightness',this.value)" style="width:100%">
          </div>

          <!-- 对比度 -->
          <div>
            <label style="color:var(--text-muted);font-size:10px;display:block;margin-bottom:2px">对比度 <span id="ie-contrast-val">100%</span></label>
            <input type="range" min="0" max="200" value="100" oninput="IE_updateFilter('contrast',this.value)" style="width:100%">
          </div>

          <!-- 饱和度 -->
          <div>
            <label style="color:var(--text-muted);font-size:10px;display:block;margin-bottom:2px">饱和度 <span id="ie-sat-val">100%</span></label>
            <input type="range" min="0" max="200" value="100" oninput="IE_updateFilter('saturation',this.value)" style="width:100%">
          </div>

          <!-- 旋转 -->
          <div>
            <label style="color:var(--text-muted);font-size:10px;display:block;margin-bottom:4px">旋转</label>
            <div style="display:flex;gap:4px">
              <button onclick="IE_rotate(0)" style="flex:1;padding:3px;background:var(--bg-primary);border:1px solid var(--border);border-radius:3px;color:var(--text-secondary);cursor:pointer;font-size:10px">0°</button>
              <button onclick="IE_rotate(90)" style="flex:1;padding:3px;background:var(--bg-primary);border:1px solid var(--border);border-radius:3px;color:var(--text-secondary);cursor:pointer;font-size:10px">90°</button>
              <button onclick="IE_rotate(180)" style="flex:1;padding:3px;background:var(--bg-primary);border:1px solid var(--border);border-radius:3px;color:var(--text-secondary);cursor:pointer;font-size:10px">180°</button>
              <button onclick="IE_rotate(270)" style="flex:1;padding:3px;background:var(--bg-primary);border:1px solid var(--border);border-radius:3px;color:var(--text-secondary);cursor:pointer;font-size:10px">270°</button>
            </div>
          </div>

          <!-- 翻转 -->
          <div>
            <label style="color:var(--text-muted);font-size:10px;display:block;margin-bottom:4px">翻转</label>
            <div style="display:flex;gap:4px">
              <button onclick="IE_flip('h')" style="flex:1;padding:4px;background:var(--bg-primary);border:1px solid var(--border);border-radius:3px;color:var(--text-secondary);cursor:pointer;font-size:10px">↔ 水平</button>
              <button onclick="IE_flip('v')" style="flex:1;padding:4px;background:var(--bg-primary);border:1px solid var(--border);border-radius:3px;color:var(--text-secondary);cursor:pointer;font-size:10px">↕ 垂直</button>
            </div>
          </div>

          <!-- 灰度 -->
          <div>
            <label style="color:var(--text-muted);font-size:10px;display:flex;align-items:center;gap:6px">
              <input type="checkbox" onchange="IE_updateFilter('grayscale',this.checked)" style="accent-color:var(--accent-blue)"> 灰度滤镜
            </label>
          </div>

          <!-- 重置编辑 -->
          <button onclick="IE_resetEdits()" style="padding:6px;background:var(--accent-red);border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:11px;margin-top:auto">🔄 重置编辑</button>
        </div>

        <!-- 中间：画布 -->
        <div id="ie-canvas-wrap" style="flex:1;position:relative;overflow:hidden;background:#0a0a15;border-bottom:1px solid var(--border);cursor:crosshair"
          onmousedown="IE_canvasMouseDown(event)"
          onmousemove="IE_canvasMouseMove(event)"
          onmouseup="IE_canvasMouseUp(event)"
          onmouseleave="IE_canvasMouseUp(event)"
          ondblclick="IE_canvasDblClick(event)"
          onwheel="IE_canvasWheel(event)"
          oncontextmenu="return false">
          <canvas id="ie-canvas" style="position:absolute;top:0;left:0"></canvas>
          <!-- 缩放指示器 -->
          <div id="ie-zoom-indicator" style="position:absolute;bottom:8px;left:8px;background:rgba(0,0,0,0.7);color:#aaa;padding:2px 8px;border-radius:4px;font-size:10px;pointer-events:none">100%</div>
          <!-- 坐标指示器 -->
          <div id="ie-coord-indicator" style="position:absolute;bottom:8px;right:8px;background:rgba(0,0,0,0.7);color:#aaa;padding:2px 8px;border-radius:4px;font-size:10px;pointer-events:none">x:0 y:0</div>
          <!-- 提示文字 -->
          <div id="ie-hint" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);color:var(--text-muted);font-size:13px;pointer-events:none;text-align:center">
            <div style="font-size:48px;margin-bottom:8px">🖼️</div>
            <div>加载图片开始标注</div>
          </div>
        </div>

        <!-- 右侧：标注列表面板 -->
        <div id="ie-right-panel" style="width:240px;min-width:240px;background:var(--bg-tertiary);border-left:1px solid var(--border);border-right:1px solid var(--border);border-bottom:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden">
          <div style="padding:8px 12px;border-bottom:1px solid var(--border);font-weight:600;font-size:12px;display:flex;justify-content:space-between;align-items:center">
            <span>📋 标注列表</span>
            <span id="ie-count" style="font-size:10px;color:var(--text-muted)">0项</span>
          </div>
          <div id="ie-filename-display" style="padding:4px 12px;font-size:10px;color:var(--accent-green);border-bottom:1px solid var(--border);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:none"></div>
          <div id="ie-anno-list" style="flex:1;overflow-y:auto;padding:6px">
            <div style="color:var(--text-muted);font-size:11px;text-align:center;padding:20px 0">暂无标注</div>
          </div>
          <!-- 属性编辑 -->
          <div id="ie-prop-panel" style="padding:8px;border-top:1px solid var(--border);display:none">
            <div style="font-size:10px;color:var(--text-muted);margin-bottom:4px">属性编辑</div>
            <div style="display:flex;gap:4px;margin-bottom:4px">
              <input id="ie-prop-label" placeholder="标签名" style="flex:1;padding:4px 6px;background:var(--bg-primary);border:1px solid var(--border);border-radius:3px;color:var(--text-primary);font-size:10px"
                onchange="IE_updateAnnotationProp('label',this.value)">
              <input id="ie-prop-color" type="color" value="#e74c3c" style="width:28px;height:28px;border:none;border-radius:3px;cursor:pointer;background:transparent"
                onchange="IE_updateAnnotationProp('color',this.value)">
            </div>
          </div>
          <div style="padding:8px;border-top:1px solid var(--border);display:flex;gap:4px">
            <button onclick="IE_deleteSelected()" style="flex:1;padding:5px;background:var(--accent-red);border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:10px">🗑 删除</button>
            <button onclick="IE_clearAll()" style="flex:1;padding:5px;background:#3a1a1a;border:1px solid #5a2a2a;border-radius:4px;color:#ef4444;cursor:pointer;font-size:10px">清空</button>
          </div>
        </div>
      </div>
    </div>
  `;

  // 初始化 Canvas
  IE_initCanvas();
  // 加载默认示例图片
  IE_loadDemoImage();
  // 更新按钮高亮
  IE_updateToolButtons();
}

// ========== Canvas 初始化 ==========
function IE_initCanvas() {
  const canvas = $('ie-canvas');
  const wrap = $('ie-canvas-wrap');
  if (!canvas || !wrap) return;

  IE.canvas = canvas;
  IE.ctx = canvas.getContext('2d');
  IE.wrap = wrap;

  // Canvas 尺寸跟随容器
  function resize() {
    canvas.width = wrap.clientWidth;
    canvas.height = wrap.clientHeight;
    IE_render();
  }
  resize();
  window.addEventListener('resize', () => {
    if (document.getElementById('ie-canvas-wrap')) resize();
  });

  // 初始渲染
  IE_render();
}

// ========== 图片加载 ==========
function IE_loadImageFile(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => IE_setImage(e.target.result, file.name);
  reader.readAsDataURL(file);
}

function IE_loadFromUrl(url) {
  if (!url || !url.trim()) return;
  IE_setImage(url, url.split('/').pop() || 'image');
}

async function IE_openServerFiles() {
  // 从服务器加载文件列表
  try {
    const resp = await apiGet('/api/v1/files/list?dir=data/output');
    if (!resp.success || !resp.data || resp.data.length === 0) {
      showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
        <h4 style="color:var(--accent-orange)">📂 服务器文件</h4>
        <p style="color:var(--text-muted);font-size:13px;margin-top:12px">data/output 目录中没有找到图片/视频文件</p>
        <div style="margin-top:12px;font-size:11px;color:var(--text-muted)">
          <p>💡 提示：将图片放到项目 data/output/ 目录下即可显示</p>
        </div>`);
      return;
    }

    const files = resp.data;
    const fileCards = files.map(f => {
      const sizeKB = Math.round(f.size / 1024);
      const ext = f.name.split('.').pop().toLowerCase();
      const isVideo = ['mp4','avi','mov','mkv','webm'].includes(ext);
      const htmlEscape = s => s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      return `
        <div class="ie-server-file-card" data-path="${htmlEscape(f.path)}" data-name="${htmlEscape(f.name)}"
          onclick="IE_loadServerFile(this.getAttribute('data-path'),this.getAttribute('data-name'))"
          style="display:flex;align-items:center;gap:10px;padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:6px;cursor:pointer;transition:all 0.15s">
          <div style="width:48px;height:48px;background:var(--bg-tertiary);border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0;overflow:hidden">
            <img src="/api/v1/preview/${encodeURIComponent(f.path)}" 
              style="width:100%;height:100%;object-fit:cover" 
              onerror="this.style.display='none';this.nextElementSibling.style.display='block'"
              loading="lazy">
            <span style="display:none">${isVideo ? '🎬' : '🖼️'}</span>
          </div>
          <div style="flex:1;min-width:0">
            <div style="font-size:12px;color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${f.name}</div>
            <div style="font-size:10px;color:var(--text-muted)">${sizeKB} KB · ${ext.toUpperCase()}</div>
          </div>
        </div>
      `;
    }).join('');

    showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
      <h4 style="color:var(--accent-blue);margin-bottom:12px">📂 服务器文件 (data/output)</h4>
      <div style="max-height:60vh;overflow-y:auto;display:flex;flex-direction:column;gap:4px">
        ${fileCards}
      </div>
      <div style="margin-top:8px;font-size:10px;color:var(--text-muted)">共 ${files.length} 个文件</div>
    `);

    // Add hover style
    const style = document.createElement('style');
    style.textContent = '.ie-server-file-card:hover { background: var(--bg-hover) !important; border-color: var(--accent-blue) !important; }';
    document.head.appendChild(style);
  } catch (e) {
    showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
      <h4 style="color:var(--accent-red)">❌ 加载失败</h4>
      <p style="color:var(--text-muted);font-size:13px;margin-top:8px">${e.message}</p>`);
  }
}

function IE_loadServerFile(path, name) {
  closeModal();
  // 用 serve 端点加载完整图片
  const url = `/api/v1/file/serve?path=${encodeURIComponent(path)}`;
  IE_setImage(url, name);
}

function IE_loadDemoImage() {
  // 生成一张彩色渐变占位图作为demo
  const c = document.createElement('canvas');
  c.width = 800; c.height = 600;
  const ctx = c.getContext('2d');
  // 渐变背景
  const grad = ctx.createLinearGradient(0,0,800,600);
  grad.addColorStop(0,'#667eea');
  grad.addColorStop(0.5,'#764ba2');
  grad.addColorStop(1,'#f093fb');
  ctx.fillStyle = grad;
  ctx.fillRect(0,0,800,600);
  // 网格线
  ctx.strokeStyle = 'rgba(255,255,255,0.15)';
  ctx.lineWidth = 1;
  for (let x=0;x<=800;x+=50) { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,600); ctx.stroke(); }
  for (let y=0;y<=600;y+=50) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(800,y); ctx.stroke(); }
  // 文字
  ctx.fillStyle = 'rgba(255,255,255,0.8)';
  ctx.font = 'bold 28px sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('🖼️ 示例图片 - 开始标注', 400, 280);
  ctx.font = '14px sans-serif';
  ctx.fillText('支持 BBox / Polygon / Keypoint / Tag / Freehand', 400, 320);
  // 一些形状供标注练习
  ctx.fillStyle = 'rgba(255,255,255,0.2)';
  ctx.fillRect(100,100,120,80);
  ctx.beginPath(); ctx.arc(500,200,50,0,Math.PI*2); ctx.fill();
  ctx.fillStyle = 'rgba(0,0,0,0.15)';
  ctx.fillRect(300,350,90,60);

  IE_setImage(c.toDataURL(), 'demo-image.png');
}

function IE_setImage(src, name) {
  const img = new Image();
  img.onload = () => {
    // 保存原始图片(用于重置编辑)
    IE.imageOriginal = img;
    IE.image = img;
    IE.imageFileName = name || 'unnamed';
    IE.filters = { brightness:100, contrast:100, saturation:100, rotation:0, flipH:false, flipV:false, grayscale:false };
    IE.annotations = [];
    IE.selectedId = null;
    IE.clearHistory();
    IE_fitWindow();
    IE_updateAnnotationList();
    IE_updatePropPanel();
    // 更新文件名显示
    const fnEl = $('ie-filename-display');
    if (fnEl) {
      fnEl.textContent = '📄 ' + IE.imageFileName;
      fnEl.style.display = 'block';
    }
    // 更新头部当前帧
    const statFrame = $('ie-stat-frame');
    if (statFrame) statFrame.textContent = IE.imageFileName;
    // 隐藏提示
    const hint = $('ie-hint');
    if (hint) hint.style.display = 'none';
    IE_render();
  };
  img.onerror = () => {
    (window.toastError || ((m) => alert(m)))('图片加载失败,请检查URL或文件格式');
  };
  img.src = src;
}

// ========== Canvas 渲染 ==========
function IE_render() {
  const canvas = IE.canvas;
  const ctx = IE.ctx;
  if (!canvas || !ctx) return;

  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  // 背景
  ctx.fillStyle = '#0a0a15';
  ctx.fillRect(0, 0, w, h);

  if (!IE.image) return;

  // 计算图片在canvas中的位置和尺寸(考虑缩放平移旋转翻转)
  const img = IE.image;
  let iw = img.naturalWidth || img.width;
  let ih = img.naturalHeight || img.height;

  // 应用旋转 (交换宽高)
  const rot = IE.filters.rotation;
  if (rot === 90 || rot === 270) {
    [iw, ih] = [ih, iw];
  }

  // 应用缩放
  const scale = IE.zoom;
  const dw = iw * scale;
  const dh = ih * scale;

  // 居中偏移 + 平移
  const cx = w / 2 + IE.panX;
  const cy = h / 2 + IE.panY;
  const dx = cx - dw / 2;
  const dy = cy - dh / 2;

  IE._imgRect = { x: dx, y: dy, w: dw, h: dh, scale: scale, cx: cx, cy: cy };

  // 保存状态
  ctx.save();

  // 裁剪到图片区域
  ctx.beginPath();
  ctx.rect(dx, dy, dw, dh);
  ctx.clip();

  // 图片变换
  ctx.translate(cx, cy);
  ctx.rotate((rot * Math.PI) / 180);
  if (IE.filters.flipH) ctx.scale(-1, 1);
  if (IE.filters.flipV) ctx.scale(1, -1);

  // 应用CSS滤镜(通过ctx.filter)
  let filterStr = '';
  const b = IE.filters.brightness / 100;
  const c = IE.filters.contrast / 100;
  const s = IE.filters.saturation / 100;
  filterStr += `brightness(${b}) contrast(${c}) saturate(${s})`;
  if (IE.filters.grayscale) filterStr += ' grayscale(1)';
  ctx.filter = filterStr;

  // 绘制图片
  ctx.drawImage(img,
    -img.naturalWidth * scale / 2,
    -img.naturalHeight * scale / 2,
    img.naturalWidth * scale,
    img.naturalHeight * scale
  );

  ctx.restore();

  // 绘制图片边框
  ctx.save();
  ctx.strokeStyle = 'rgba(255,255,255,0.3)';
  ctx.lineWidth = 1;
  ctx.strokeRect(dx, dy, dw, dh);
  ctx.restore();

  // 绘制标注
  IE.annotations.forEach((anno) => {
    if (anno.visible === false) return;
    IE_drawAnnotation(ctx, anno, dx, dy, scale, rot, iw, ih);
  });

  // 绘制正在绘制中的形状
  if (IE.isDrawing && IE.currentTool !== 'pan') {
    IE_drawCurrentShape(ctx, dx, dy, scale, rot, iw, ih);
  }
}

function IE_imageToCanvas(px, py) {
  // 将图片坐标转换为canvas坐标
  const r = IE._imgRect;
  if (!r) return { x: 0, y: 0 };
  return {
    x: r.x + px * r.scale,
    y: r.y + py * r.scale,
  };
}

function IE_canvasToImage(cx, cy) {
  const r = IE._imgRect;
  if (!r) return { x: 0, y: 0 };
  return {
    x: (cx - r.x) / r.scale,
    y: (cy - r.y) / r.scale,
  };
}

function IE_drawAnnotation(ctx, anno, dx, dy, scale, rot, iw, ih) {
  const color = anno.color || '#e74c3c';
  const isSelected = anno.id === IE.selectedId;

  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = isSelected ? 3 : 2;

  switch (anno.type) {
    case 'bbox': {
      const [p1, p2] = anno.points;
      const x = dx + p1.x * scale;
      const y = dy + p1.y * scale;
      const w = (p2.x - p1.x) * scale;
      const h = (p2.y - p1.y) * scale;

      // 填充
      ctx.fillStyle = color + '20';
      ctx.fillRect(x, y, w, h);

      // 边框
      ctx.strokeStyle = color;
      ctx.setLineDash(isSelected ? [] : [4, 2]);
      ctx.strokeRect(x, y, w, h);
      ctx.setLineDash([]);

      // 标签
      if (anno.label) {
        ctx.fillStyle = color;
        ctx.font = 'bold 11px sans-serif';
        const text = anno.label;
        const tm = ctx.measureText(text);
        const tx = x;
        const ty = y - 6;
        ctx.fillStyle = color + 'CC';
        ctx.fillRect(tx - 1, ty - 12, tm.width + 4, 14);
        ctx.fillStyle = '#fff';
        ctx.fillText(text, tx + 1, ty);
      }

      // 选中时绘制控制点
      if (isSelected) {
        IE_drawHandle(ctx, x, y, color);         // TL
        IE_drawHandle(ctx, x + w, y, color);     // TR
        IE_drawHandle(ctx, x, y + h, color);     // BL
        IE_drawHandle(ctx, x + w, y + h, color); // BR
      }
      break;
    }

    case 'polygon': {
      if (anno.points.length < 2) break;
      ctx.beginPath();
      const first = IE_imageToCanvas(anno.points[0].x, anno.points[0].y);
      ctx.moveTo(first.x, first.y);
      for (let i = 1; i < anno.points.length; i++) {
        const pt = IE_imageToCanvas(anno.points[i].x, anno.points[i].y);
        ctx.lineTo(pt.x, pt.y);
      }
      ctx.closePath();

      // 填充
      ctx.fillStyle = color + '15';
      ctx.fill();

      // 描边
      ctx.strokeStyle = color;
      ctx.setLineDash(isSelected ? [] : [5, 3]);
      ctx.stroke();
      ctx.setLineDash([]);

      // 顶点
      anno.points.forEach(p => {
        const pt = IE_imageToCanvas(p.x, p.y);
        IE_drawHandle(ctx, pt.x, pt.y, color, 4);
      });

      // 标签在第一个顶点
      if (anno.label && anno.points.length > 0) {
        const pt = IE_imageToCanvas(anno.points[0].x, anno.points[0].y);
        ctx.fillStyle = color + 'CC';
        ctx.font = 'bold 11px sans-serif';
        const tm = ctx.measureText(anno.label);
        ctx.fillRect(pt.x - 1, pt.y - 16, tm.width + 4, 14);
        ctx.fillStyle = '#fff';
        ctx.fillText(anno.label, pt.x + 1, pt.y - 4);
      }
      break;
    }

    case 'keypoint': {
      anno.points.forEach((p, i) => {
        const pt = IE_imageToCanvas(p.x, p.y);
        // 光晕
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, isSelected ? 8 : 6, 0, Math.PI * 2);
        ctx.fillStyle = color + '30';
        ctx.fill();

        // 实心圆
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, isSelected ? 5 : 4, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();

        // 外环
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, isSelected ? 7 : 5, 0, Math.PI * 2);
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // 编号
        if (anno.points.length > 1) {
          ctx.fillStyle = '#fff';
          ctx.font = 'bold 9px sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(i + 1, pt.x, pt.y - 9);
          ctx.textAlign = 'start';
        }
      });

      // 标签
      if (anno.label && anno.points.length > 0) {
        const pt = IE_imageToCanvas(anno.points[0].x, anno.points[0].y);
        ctx.fillStyle = color + 'CC';
        ctx.font = 'bold 11px sans-serif';
        const tm = ctx.measureText(anno.label);
        ctx.fillRect(pt.x + 8, pt.y - 6, tm.width + 4, 14);
        ctx.fillStyle = '#fff';
        ctx.fillText(anno.label, pt.x + 10, pt.y + 4);
      }
      break;
    }

    case 'tag': {
      anno.points.forEach(p => {
        const pt = IE_imageToCanvas(p.x, p.y);
        const text = anno.label || 'tag';
        ctx.font = 'bold 12px sans-serif';
        const tm = ctx.measureText(text);

        // 背景标签气泡
        const bw = tm.width + 12;
        const bh = 20;
        const bx = pt.x - bw / 2;
        const by = pt.y - bh - 8;
        ctx.fillStyle = color + 'DD';
        IE_roundRect(ctx, bx, by, bw, bh, 4);
        ctx.fill();

        // 小三角
        ctx.beginPath();
        ctx.moveTo(pt.x - 5, by + bh);
        ctx.lineTo(pt.x + 5, by + bh);
        ctx.lineTo(pt.x, pt.y);
        ctx.fill();

        // 文字
        ctx.fillStyle = '#fff';
        ctx.textAlign = 'center';
        ctx.fillText(text, pt.x, by + bh - 5);
        ctx.textAlign = 'start';
      });
      break;
    }

    case 'freehand': {
      if (anno.points.length < 2) break;
      ctx.beginPath();
      const first = IE_imageToCanvas(anno.points[0].x, anno.points[0].y);
      ctx.moveTo(first.x, first.y);
      for (let i = 1; i < anno.points.length; i++) {
        const pt = IE_imageToCanvas(anno.points[i].x, anno.points[i].y);
        ctx.lineTo(pt.x, pt.y);
      }
      ctx.strokeStyle = color;
      ctx.lineWidth = isSelected ? 3 : 2;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.setLineDash([]);
      ctx.stroke();

      // 标签在最开始处
      if (anno.label && anno.points.length > 0) {
        const pt = IE_imageToCanvas(anno.points[0].x, anno.points[0].y);
        ctx.fillStyle = color + 'CC';
        ctx.font = 'bold 11px sans-serif';
        const tm = ctx.measureText(anno.label);
        ctx.fillRect(pt.x - 1, pt.y - 16, tm.width + 4, 14);
        ctx.fillStyle = '#fff';
        ctx.fillText(anno.label, pt.x + 1, pt.y - 4);
      }
      break;
    }
  }

  ctx.restore();
}

function IE_drawHandle(ctx, x, y, color, size) {
  size = size || 5;
  ctx.fillStyle = '#fff';
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.fillRect(x - size, y - size, size * 2, size * 2);
  ctx.strokeRect(x - size, y - size, size * 2, size * 2);
}

function IE_roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

function IE_drawCurrentShape(ctx, dx, dy, scale, rot, iw, ih) {
  const color = IE.palette[IE.paletteIdx % IE.palette.length];

  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color + '20';
  ctx.lineWidth = 2;
  ctx.setLineDash([4, 2]);

  switch (IE.currentTool) {
    case 'bbox': {
      if (IE.drawingBBox) {
        const b = IE.drawingBBox;
        const x = dx + Math.min(b.x, b.x + b.w) * scale;
        const y = dy + Math.min(b.y, b.y + b.h) * scale;
        const w = Math.abs(b.w) * scale;
        const h = Math.abs(b.h) * scale;
        ctx.fillRect(x, y, w, h);
        ctx.strokeRect(x, y, w, h);
      }
      break;
    }

    case 'polygon': {
      if (IE.drawingPoints.length >= 1) {
        ctx.beginPath();
        const first = IE_imageToCanvas(IE.drawingPoints[0].x, IE.drawingPoints[0].y);
        ctx.moveTo(first.x, first.y);
        for (let i = 1; i < IE.drawingPoints.length; i++) {
          const pt = IE_imageToCanvas(IE.drawingPoints[i].x, IE.drawingPoints[i].y);
          ctx.lineTo(pt.x, pt.y);
        }
        // 连接到预览点
        if (IE.previewPoint) {
          const pp = IE_imageToCanvas(IE.previewPoint.x, IE.previewPoint.y);
          ctx.lineTo(pp.x, pp.y);
        }
        ctx.stroke();

        // 顶点
        IE.drawingPoints.forEach(p => {
          const pt = IE_imageToCanvas(p.x, p.y);
          IE_drawHandle(ctx, pt.x, pt.y, color, 3);
        });
      }
      break;
    }

    case 'keypoint': {
      // 预览十字
      if (IE.previewPoint) {
        const pt = IE_imageToCanvas(IE.previewPoint.x, IE.previewPoint.y);
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 5, 0, Math.PI * 2);
        ctx.strokeStyle = color;
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(pt.x - 10, pt.y);
        ctx.lineTo(pt.x + 10, pt.y);
        ctx.moveTo(pt.x, pt.y - 10);
        ctx.lineTo(pt.x, pt.y + 10);
        ctx.stroke();
      }
      break;
    }

    case 'tag': {
      if (IE.previewPoint) {
        const pt = IE_imageToCanvas(IE.previewPoint.x, IE.previewPoint.y);
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.beginPath();
        ctx.moveTo(pt.x - 8, pt.y);
        ctx.lineTo(pt.x + 8, pt.y);
        ctx.moveTo(pt.x, pt.y - 8);
        ctx.lineTo(pt.x, pt.y + 8);
        ctx.stroke();
      }
      break;
    }

    case 'freehand': {
      if (IE.drawingPoints.length >= 1) {
        ctx.beginPath();
        const first = IE_imageToCanvas(IE.drawingPoints[0].x, IE.drawingPoints[0].y);
        ctx.moveTo(first.x, first.y);
        for (let i = 1; i < IE.drawingPoints.length; i++) {
          const pt = IE_imageToCanvas(IE.drawingPoints[i].x, IE.drawingPoints[i].y);
          ctx.lineTo(pt.x, pt.y);
        }
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.stroke();
      }
      break;
    }
  }

  ctx.setLineDash([]);
  ctx.restore();
}

// ========== 工具切换 ==========
function IE_setTool(tool) {
  IE.currentTool = tool;
  IE.isDrawing = false;
  IE.drawingPoints = [];
  IE.drawingBBox = null;
  IE.previewPoint = null;
  IE_updateToolButtons();
  IE_render();

  // 更新光标
  const wrap = IE.wrap;
  if (wrap) {
    wrap.style.cursor = 'crosshair';
  }
}

function IE_updateToolButtons() {
  document.querySelectorAll('.ie-tool-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tool === IE.currentTool);
  });
}

// ========== 鼠标事件 ==========
function IE_canvasMouseDown(e) {
  if (!IE.image) return;
  const pos = IE_getMousePos(e);
  if (!pos) return;

  // 中键或Alt+左键 = 平移
  if (e.button === 1 || (e.button === 0 && e.altKey)) {
    IE.isPanning = true;
    IE.panStartX = e.clientX - IE.panX;
    IE.panStartY = e.clientY - IE.panY;
    IE.wrap.style.cursor = 'grabbing';
    return;
  }

  // 空格+拖拽 = 平移
  if (e.button === 0 && IE.spaceDown) {
    IE.isPanning = true;
    IE.panStartX = e.clientX - IE.panX;
    IE.panStartY = e.clientY - IE.panY;
    IE.wrap.style.cursor = 'grabbing';
    return;
  }

  if (e.button !== 0) return;

  const imgPos = IE_canvasToImage(pos.x, pos.y);

  // 检查是否点击了已有标注
  const clicked = IE_hitTest(imgPos.x, imgPos.y);
  if (clicked && !IE.isDrawing) {
    IE.selectedId = clicked.id;
    IE_updateAnnotationList();
    IE_updatePropPanel();
    IE_render();
    return;
  }

  IE.saveHistory();
  IE.selectedId = null;
  IE.isDrawing = true;

  switch (IE.currentTool) {
    case 'bbox':
      IE.drawingBBox = { x: imgPos.x, y: imgPos.y, w: 0, h: 0 };
      break;
    case 'polygon':
      IE.drawingPoints.push({ x: imgPos.x, y: imgPos.y });
      break;
    case 'keypoint':
      IE_addAnnotation('keypoint', [{ x: imgPos.x, y: imgPos.y }]);
      IE.isDrawing = false;
      break;
    case 'tag':
      // 弹出标签名输入
      IE_addAnnotation('tag', [{ x: imgPos.x, y: imgPos.y }]);
      IE.isDrawing = false;
      break;
    case 'freehand':
      IE.drawingPoints = [{ x: imgPos.x, y: imgPos.y }];
      break;
  }

  IE_updatePropPanel();
  IE_render();
}

function IE_canvasMouseMove(e) {
  if (!IE.image) return;

  const pos = IE_getMousePos(e);
  if (!pos) return;

  // 更新坐标指示器
  const imgPos = IE_canvasToImage(pos.x, pos.y);
  const coordEl = $('ie-coord-indicator');
  if (coordEl) {
    coordEl.textContent = `x:${Math.round(imgPos.x)} y:${Math.round(imgPos.y)}`;
  }

  // 平移
  if (IE.isPanning) {
    IE.panX = e.clientX - IE.panStartX;
    IE.panY = e.clientY - IE.panStartY;
    IE_render();
    return;
  }

  // 预览点
  IE.previewPoint = imgPos;

  if (!IE.isDrawing) {
    IE_render();
    return;
  }

  switch (IE.currentTool) {
    case 'bbox':
      if (IE.drawingBBox) {
        IE.drawingBBox.w = imgPos.x - IE.drawingBBox.x;
        IE.drawingBBox.h = imgPos.y - IE.drawingBBox.y;
      }
      break;
    case 'polygon':
      // 仅预览,不添加点
      break;
    case 'freehand':
      IE.drawingPoints.push({ x: imgPos.x, y: imgPos.y });
      break;
  }

  IE_render();
}

function IE_canvasMouseUp(e) {
  if (IE.isPanning) {
    IE.isPanning = false;
    IE.wrap.style.cursor = 'crosshair';
    IE.panStartX = IE.panX;
    IE.panStartY = IE.panY;
    return;
  }

  if (!IE.isDrawing) return;

  const pos = IE_getMousePos(e);
  if (!pos) return;

  const imgPos = IE_canvasToImage(pos.x, pos.y);

  switch (IE.currentTool) {
    case 'bbox':
      if (IE.drawingBBox && (Math.abs(IE.drawingBBox.w) > 2 || Math.abs(IE.drawingBBox.h) > 2)) {
        const b = IE.drawingBBox;
        const x1 = Math.min(b.x, b.x + b.w);
        const y1 = Math.min(b.y, b.y + b.h);
        const x2 = Math.max(b.x, b.x + b.w);
        const y2 = Math.max(b.y, b.y + b.h);
        IE_addAnnotation('bbox', [{ x: x1, y: y1 }, { x: x2, y: y2 }]);
      }
      IE.drawingBBox = null;
      IE.isDrawing = false;
      break;

    case 'polygon':
      // 不在这里闭合,留给双击
      break;

    case 'freehand':
      if (IE.drawingPoints.length >= 2) {
        IE_addAnnotation('freehand', [...IE.drawingPoints]);
      }
      IE.drawingPoints = [];
      IE.isDrawing = false;
      break;
  }

  IE_render();
}

function IE_canvasDblClick(e) {
  if (!IE.isDrawing || IE.currentTool !== 'polygon') return;

  // 闭合多边形
  if (IE.drawingPoints.length >= 3) {
    IE_addAnnotation('polygon', [...IE.drawingPoints]);
  }
  IE.drawingPoints = [];
  IE.isDrawing = false;
  IE.previewPoint = null;
  IE_render();
}

function IE_canvasWheel(e) {
  if (!IE.image) return;
  e.preventDefault();

  const delta = e.deltaY > 0 ? 0.9 : 1.1;
  const newZoom = Math.max(0.1, Math.min(10, IE.zoom * delta));
  IE.zoom = newZoom;
  IE_render();

  const zoomEl = $('ie-zoom-indicator');
  if (zoomEl) zoomEl.textContent = Math.round(IE.zoom * 100) + '%';
  // 更新头部缩放统计
  const statZoom = $('ie-stat-zoom');
  if (statZoom) statZoom.textContent = Math.round(IE.zoom * 100) + '%';
}

function IE_getMousePos(e) {
  const rect = IE.canvas.getBoundingClientRect();
  return {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top,
  };
}

// ========== 标注命中检测 ==========
function IE_hitTest(ix, iy) {
  // 从后向前检查(后画的在上层)
  for (let i = IE.annotations.length - 1; i >= 0; i--) {
    const a = IE.annotations[i];
    if (a.visible === false) continue;

    switch (a.type) {
      case 'bbox': {
        const [p1, p2] = a.points;
        if (ix >= p1.x && ix <= p2.x && iy >= p1.y && iy <= p2.y) return a;
        break;
      }
      case 'polygon':
      case 'freehand': {
        if (IE_pointInPolygon(ix, iy, a.points)) return a;
        break;
      }
      case 'keypoint':
      case 'tag': {
        for (const p of a.points) {
          const dist = Math.hypot(ix - p.x, iy - p.y);
          if (dist < 8 / IE.zoom) return a;
        }
        break;
      }
    }
  }
  return null;
}

function IE_pointInPolygon(x, y, points) {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const xi = points[i].x, yi = points[i].y;
    const xj = points[j].x, yj = points[j].y;
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

// ========== 标注增删改 ==========
function IE_addAnnotation(type, points) {
  const color = IE.palette[IE.paletteIdx % IE.palette.length];
  IE.paletteIdx++;
  const id = 'anno_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
  const label = type === 'tag' ? '标签' : type === 'keypoint' ? '关键点' : type.charAt(0).toUpperCase() + type.slice(1);

  IE.annotations.push({
    id,
    type,
    label,
    color,
    points,
    visible: true,
  });

  IE.selectedId = id;
  IE_updateAnnotationList();
  IE_updatePropPanel();
  IE_saveHistoryAfterOp();
}

function IE_deleteSelected() {
  if (!IE.selectedId) {
    // 尝试删除最后选中的
    if (IE.annotations.length > 0) {
      IE.selectedId = IE.annotations[IE.annotations.length - 1].id;
    } else return;
  }
  IE.saveHistory();
  IE.annotations = IE.annotations.filter(a => a.id !== IE.selectedId);
  IE.selectedId = null;
  IE_updateAnnotationList();
  IE_updatePropPanel();
  IE_render();
}

function IE_clearAll() {
  if (IE.annotations.length === 0) return;
  if (!confirm('确定清空所有标注？此操作可撤销。')) return;
  IE.saveHistory();
  IE.annotations = [];
  IE.selectedId = null;
  IE_updateAnnotationList();
  IE_updatePropPanel();
  IE_render();
}

function IE_updateAnnotationProp(prop, value) {
  const anno = IE.annotations.find(a => a.id === IE.selectedId);
  if (!anno) return;
  anno[prop] = value;
  IE_updateAnnotationList();
  IE_render();
}

// ========== 右侧面板更新 ==========
function IE_updateAnnotationList() {
  const list = $('ie-anno-list');
  const count = $('ie-count');
  if (!list) return;

  if (count) count.textContent = IE.annotations.length + '项';

  // 更新头部统计
  const statCount = $('ie-stat-count');
  if (statCount) statCount.textContent = IE.annotations.length;

  if (IE.annotations.length === 0) {
    list.innerHTML = '<div style="color:var(--text-muted);font-size:11px;text-align:center;padding:20px 0">暂无标注</div>';
    return;
  }

  list.innerHTML = IE.annotations.map((a, i) => `
    <div class="ie-anno-item ${a.id === IE.selectedId ? 'ie-anno-sel' : ''}"
      onclick="IE_selectAnnotation('${a.id}')"
      style="display:flex;align-items:center;gap:8px;padding:6px 8px;margin-bottom:3px;background:${a.id===IE.selectedId?'var(--bg-hover)':'var(--bg-primary)'};border-radius:4px;cursor:pointer;font-size:11px;border:1px solid ${a.id===IE.selectedId?a.color:'transparent'}">
      <span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${a.color};flex-shrink:0"></span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-primary)">${a.label || a.type}</span>
      <span style="font-size:9px;color:var(--text-muted);flex-shrink:0">${a.type}</span>
      <span onclick="event.stopPropagation();IE_toggleVisibility('${a.id}')" style="cursor:pointer;flex-shrink:0;opacity:0.7" title="切换可见">${a.visible !== false ? '👁' : '👁‍🗨'}</span>
    </div>
  `).join('');
}

function IE_selectAnnotation(id) {
  IE.selectedId = id;
  IE_updateAnnotationList();
  IE_updatePropPanel();
  IE_render();
}

function IE_updatePropPanel() {
  const panel = $('ie-prop-panel');
  if (!panel) return;

  const anno = IE.annotations.find(a => a.id === IE.selectedId);
  if (!anno) {
    panel.style.display = 'none';
    return;
  }

  panel.style.display = 'block';
  const labelInput = $('ie-prop-label');
  const colorInput = $('ie-prop-color');
  if (labelInput) labelInput.value = anno.label || '';
  if (colorInput) colorInput.value = anno.color || '#e74c3c';
}

function IE_toggleVisibility(id) {
  const anno = IE.annotations.find(a => a.id === id);
  if (anno) {
    anno.visible = anno.visible === false ? true : false;
    IE_updateAnnotationList();
    IE_render();
  }
}

// ========== 视图操作 ==========
function IE_fitWindow() {
  if (!IE.image) return;
  const wrap = IE.wrap;
  if (!wrap) return;

  let iw = IE.image.naturalWidth || IE.image.width;
  let ih = IE.image.naturalHeight || IE.image.height;
  if (IE.filters.rotation === 90 || IE.filters.rotation === 270) {
    [iw, ih] = [ih, iw];
  }

  const cw = wrap.clientWidth;
  const ch = wrap.clientHeight;
  const scaleX = (cw - 60) / iw;
  const scaleY = (ch - 60) / ih;
  IE.zoom = Math.min(scaleX, scaleY, 1);
  IE.panX = 0;
  IE.panY = 0;

  const zoomEl = $('ie-zoom-indicator');
  if (zoomEl) zoomEl.textContent = Math.round(IE.zoom * 100) + '%';
  IE_render();
}

function IE_resetView() {
  IE.zoom = 1;
  IE.panX = 0;
  IE.panY = 0;
  const zoomEl = $('ie-zoom-indicator');
  if (zoomEl) zoomEl.textContent = '100%';
  IE_render();
}

// ========== 图片编辑 ==========
function IE_updateFilter(filter, value) {
  switch (filter) {
    case 'brightness':
      IE.filters.brightness = parseInt(value);
      const bv = $('ie-bright-val'); if (bv) bv.textContent = value + '%';
      break;
    case 'contrast':
      IE.filters.contrast = parseInt(value);
      const cv = $('ie-contrast-val'); if (cv) cv.textContent = value + '%';
      break;
    case 'saturation':
      IE.filters.saturation = parseInt(value);
      const sv = $('ie-sat-val'); if (sv) sv.textContent = value + '%';
      break;
    case 'grayscale':
      IE.filters.grayscale = !!value;
      break;
  }
  IE_render();
}

function IE_rotate(deg) {
  IE.filters.rotation = deg;
  IE_fitWindow();
  IE_render();
}

function IE_flip(dir) {
  if (dir === 'h') IE.filters.flipH = !IE.filters.flipH;
  if (dir === 'v') IE.filters.flipV = !IE.filters.flipV;
  IE_render();
}

function IE_resetEdits() {
  IE.filters = { brightness: 100, contrast: 100, saturation: 100, rotation: 0, flipH: false, flipV: false, grayscale: false };
  // 重置滑块
  const sliders = document.querySelectorAll('#ie-edit-panel input[type=range]');
  sliders.forEach(s => { s.value = 100; });
  const bv = $('ie-bright-val'); if (bv) bv.textContent = '100%';
  const cv = $('ie-contrast-val'); if (cv) cv.textContent = '100%';
  const sv = $('ie-sat-val'); if (sv) sv.textContent = '100%';
  const cb = document.querySelector('#ie-edit-panel input[type=checkbox]');
  if (cb) cb.checked = false;
  IE_render();
}

// ========== 撤销/重做 ==========
function IE_saveHistory() {
  // 截断后续历史
  IE.history = IE.history.slice(0, IE.historyIndex + 1);
  // 保存快照
  IE.history.push(JSON.parse(JSON.stringify(IE.annotations)));
  IE.historyIndex++;
  // 限制历史长度
  if (IE.history.length > IE.maxHistory) {
    IE.history.shift();
    IE.historyIndex--;
  }
}

function IE_saveHistoryAfterOp() {
  IE.history = IE.history.slice(0, IE.historyIndex + 1);
  IE.history.push(JSON.parse(JSON.stringify(IE.annotations)));
  IE.historyIndex++;
  if (IE.history.length > IE.maxHistory) {
    IE.history.shift();
    IE.historyIndex--;
  }
}

function IE_clearHistory() {
  IE.history = [JSON.parse(JSON.stringify(IE.annotations))];
  IE.historyIndex = 0;
}

function IE_undo() {
  if (IE.historyIndex <= 0) return;
  IE.historyIndex--;
  IE.annotations = JSON.parse(JSON.stringify(IE.history[IE.historyIndex]));
  IE.selectedId = null;
  IE_updateAnnotationList();
  IE_updatePropPanel();
  IE_render();
}

function IE_redo() {
  if (IE.historyIndex >= IE.history.length - 1) return;
  IE.historyIndex++;
  IE.annotations = JSON.parse(JSON.stringify(IE.history[IE.historyIndex]));
  IE.selectedId = null;
  IE_updateAnnotationList();
  IE_updatePropPanel();
  IE_render();
}

// ========== 保存标注 ==========
function IE_saveAnnotations() {
  if (IE.annotations.length === 0) {
    showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
      <h4 style="color:var(--accent-orange)">⚠️ 无可保存的标注</h4>
      <p style="color:var(--text-muted);font-size:13px;margin-top:8px">请先在图片上添加标注</p>`);
    return;
  }

  const payload = {
    image_name: IE.imageFileName || 'unknown',
    annotations: IE.annotations.map(a => ({
      type: a.type,
      label: a.label,
      points: a.points,
      color: a.color,
    })),
    filters: IE.filters,
    timestamp: new Date().toISOString(),
  };

  // 尝试调用API保存
  apiPost('/api/annotations/save', payload)
    .then(result => {
      if (result.success) {
        showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
          <h4 style="color:var(--accent-green)">✅ 标注已保存</h4>
          <p style="color:var(--text-muted);font-size:13px;margin-top:8px">保存 ${IE.annotations.length} 个标注项</p>
          <pre style="background:var(--bg-primary);padding:8px;border-radius:4px;margin-top:8px;font-size:10px;overflow:auto;max-height:200px">${JSON.stringify(payload.annotations, null, 2)}</pre>`);
      } else {
        // 即使API失败也显示本地保存结果
        showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
          <h4 style="color:var(--accent-orange)">⚠️ API保存失败，显示本地数据</h4>
          <p style="color:var(--text-muted);font-size:13px;margin-top:8px">保存 ${IE.annotations.length} 个标注项</p>
          <pre style="background:var(--bg-primary);padding:8px;border-radius:4px;margin-top:8px;font-size:10px;overflow:auto;max-height:200px">${JSON.stringify(payload.annotations, null, 2)}</pre>`);
      }
    })
    .catch(() => {
      showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
        <h4 style="color:var(--accent-orange)">⚠️ 离线保存</h4>
        <p style="color:var(--text-muted);font-size:13px;margin-top:8px">保存 ${IE.annotations.length} 个标注项 (本地)</p>
        <pre style="background:var(--bg-primary);padding:8px;border-radius:4px;margin-top:8px;font-size:10px;overflow:auto;max-height:200px">${JSON.stringify(payload.annotations, null, 2)}</pre>`);
    });
}

// ========== 键盘快捷键 ==========
document.addEventListener('keydown', (e) => {
  // 只在图片编辑器页面激活时处理
  if (!document.getElementById('ie-root')) return;

  // 全局快捷键
  if (e.ctrlKey && e.key === 'z' && !e.shiftKey) {
    e.preventDefault();
    IE_undo();
    return;
  }

  if (e.ctrlKey && e.key === 'Z' || (e.ctrlKey && e.shiftKey && e.key === 'z')) {
    e.preventDefault();
    IE_redo();
    return;
  }

  // Delete键 - 删除选中
  if (e.key === 'Delete' || e.key === 'Backspace') {
    // 不在input/textarea中
    if (document.activeElement && ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)) return;
    e.preventDefault();
    IE_deleteSelected();
    return;
  }

  // Esc - 取消当前绘制
  if (e.key === 'Escape') {
    IE.isDrawing = false;
    IE.drawingPoints = [];
    IE.drawingBBox = null;
    IE.previewPoint = null;
    IE_render();
    return;
  }

  // F - 适应窗口
  if (e.key === 'f' || e.key === 'F') {
    if (document.activeElement && ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)) return;
    e.preventDefault();
    IE_fitWindow();
    return;
  }

  // N - 循环切换工具
  if (e.key === 'n' || e.key === 'N') {
    if (document.activeElement && ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)) return;
    const tools = ['bbox', 'polygon', 'keypoint', 'tag', 'freehand'];
    const idx = tools.indexOf(IE.currentTool);
    IE_setTool(tools[(idx + 1) % tools.length]);
    return;
  }

  // B - BBox
  if (e.key === 'b' || e.key === 'B') {
    if (document.activeElement && ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)) return;
    IE_setTool('bbox');
    return;
  }

  // P - Polygon
  if (e.key === 'p' || e.key === 'P') {
    if (document.activeElement && ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)) return;
    IE_setTool('polygon');
    return;
  }

  // K - Keypoint
  if (e.key === 'k' || e.key === 'K') {
    if (document.activeElement && ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)) return;
    IE_setTool('keypoint');
    return;
  }

  // T - Tag
  if (e.key === 't' || e.key === 'T') {
    if (document.activeElement && ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)) return;
    IE_setTool('tag');
    return;
  }

  // D - Freehand (Draw)
  if (e.key === 'd' || e.key === 'D') {
    if (document.activeElement && ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)) return;
    IE_setTool('freehand');
    return;
  }

  // 空格按下(用于平移)
  if (e.key === ' ' && !e.repeat) {
    if (document.activeElement && ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)) return;
    IE.spaceDown = true;
    e.preventDefault();
    if (IE.wrap) IE.wrap.style.cursor = 'grab';
  }
});

document.addEventListener('keyup', (e) => {
  if (e.key === ' ' && IE.spaceDown) {
    IE.spaceDown = false;
    IE.isPanning = false;
    if (IE.wrap) IE.wrap.style.cursor = 'crosshair';
  }
});

// ========== 样式注入 ==========
function IE_injectStyles() {
  if (document.getElementById('ie-styles')) return;
  const style = document.createElement('style');
  style.id = 'ie-styles';
  style.textContent = `
    .ie-tool-btn {
      padding: 5px 10px;
      background: var(--bg-tertiary);
      border: 1px solid var(--border);
      border-radius: 4px;
      color: var(--text-secondary);
      cursor: pointer;
      font-size: 11px;
      white-space: nowrap;
      transition: all 0.15s;
    }
    .ie-tool-btn:hover {
      background: var(--bg-hover);
      color: var(--text-primary);
      border-color: var(--accent-blue);
    }
    .ie-tool-btn.active {
      background: var(--accent-blue);
      color: #fff;
      border-color: var(--accent-blue);
    }
    .ie-action-btn {
      padding: 5px 8px;
      background: var(--bg-tertiary);
      border: 1px solid var(--border);
      border-radius: 4px;
      color: var(--text-secondary);
      cursor: pointer;
      font-size: 11px;
      white-space: nowrap;
      transition: all 0.15s;
    }
    .ie-action-btn:hover {
      background: var(--bg-hover);
      color: var(--text-primary);
      border-color: var(--accent-blue);
    }
    .ie-btn-save {
      background: #1a2a4a;
      border-color: #2a3a5a;
      color: #4a7aff;
    }
    .ie-btn-save:hover {
      background: #2a3a5a;
    }
    .ie-anno-item:hover {
      background: var(--bg-hover) !important;
    }
    #ie-edit-panel input[type=range] {
      -webkit-appearance: none;
      appearance: none;
      width: 100%;
      height: 4px;
      background: var(--bg-primary);
      border-radius: 2px;
      outline: none;
    }
    #ie-edit-panel input[type=range]::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: var(--accent-blue);
      cursor: pointer;
    }
  `;
  document.head.appendChild(style);
}

// 页面加载时注入样式
IE_injectStyles();
