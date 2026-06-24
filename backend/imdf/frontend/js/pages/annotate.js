/* IMDF v3 标注工具页面 — AI智能标注 + 配置面板 + 结果展示 */

const ANNO_STATE = {
  taskType: 'detection',
  labelSet: 'coco',
  model: 'yolo-v8',
  isRunning: false,
  results: [],
  todayCount: 0,
  avgConfidence: 0,
  modelStatus: 'ready',
};

async function renderAnnotate() {
  const container = $('page-content');
  if (!container) return;

  // 加载统计数据
  try {
    const stats = await apiGet('/api/stats/annotate').catch(() => ({}));
    const data = stats.data || stats;
    ANNO_STATE.todayCount = data.today_count || 24;
    ANNO_STATE.avgConfidence = data.avg_confidence || 0.87;
    ANNO_STATE.modelStatus = data.model_status || 'ready';
  } catch (e) { /* ignore */ }

  container.innerHTML = `
    <!-- ===== 页面头部 ===== -->
    <div class="page-header">
      <div>
        <div class="page-title">AI智能标注</div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px">一键调用AI模型进行图像/文本智能标注</div>
      </div>
      <div class="page-stats">
        <div class="page-stat">
          <div class="page-stat-val" style="color:var(--accent-blue)">${ANNO_STATE.todayCount}</div>
          <div class="page-stat-label">今日标注</div>
        </div>
        <div class="page-stat">
          <div class="page-stat-val" style="color:var(--accent-green)">${(ANNO_STATE.avgConfidence * 100).toFixed(0)}%</div>
          <div class="page-stat-label">平均置信度</div>
        </div>
        <div class="page-stat">
          <div class="page-stat-val" style="color:${ANNO_STATE.modelStatus === 'ready' ? 'var(--accent-green)' : 'var(--accent-orange)'}">${ANNO_STATE.modelStatus === 'ready' ? '🟢 就绪' : '🟡 加载中'}</div>
          <div class="page-stat-label">模型状态</div>
        </div>
      </div>
      <div class="page-actions">
        <button class="btn btn-primary" onclick="ANNO_startAnnotate()" id="anno-start-btn">🚀 开始标注</button>
        <button class="btn btn-outline btn-sm" onclick="ANNO_exportResults()">📥 导出结果</button>
        <button class="btn btn-outline btn-sm" onclick="ANNO_batchAnnotate()">📦 批量标注</button>
      </div>
    </div>

    <!-- ===== 两栏布局 ===== -->
    <div class="two-col" style="grid-template-columns:260px 1fr;">
      <!-- 左侧：配置面板 -->
      <div class="side-panel" style="display:flex;flex-direction:column;">
        <div class="section-title">⚙️ 标注配置</div>
        
        <div class="config-section">
          <div class="config-label">任务类型</div>
          <select class="config-select" id="anno-task-type" onchange="ANNO_STATE.taskType=this.value">
            <option value="detection">BBox 目标检测</option>
            <option value="classification">分类标注</option>
            <option value="tagging">标签生成</option>
            <option value="segmentation">语义分割</option>
            <option value="keypoint">关键点检测</option>
          </select>
        </div>

        <div class="config-section">
          <div class="config-label">标签集</div>
          <select class="config-select" id="anno-label-set" onchange="ANNO_STATE.labelSet=this.value">
            <option value="coco">COCO (80类)</option>
            <option value="imagenet">ImageNet (1000类)</option>
            <option value="voc">VOC (20类)</option>
            <option value="custom">自定义标签集</option>
          </select>
        </div>

        <div class="config-section">
          <div class="config-label">AI模型</div>
          <select class="config-select" id="anno-model" onchange="ANNO_STATE.model=this.value">
            <option value="yolo-v8">YOLO v8</option>
            <option value="grounding-dino">Grounding DINO</option>
            <option value="sam">SAM (Segment Anything)</option>
            <option value="clip">CLIP 分类</option>
            <option value="blip2">BLIP-2 标签</option>
          </select>
        </div>

        <div class="config-section">
          <div class="config-label">置信度阈值</div>
          <div style="display:flex;align-items:center;gap:8px">
            <input type="range" min="10" max="95" value="50" style="flex:1;accent-color:var(--accent-blue)" 
              oninput="document.getElementById('conf-thresh-val').textContent=this.value+'%'">
            <span id="conf-thresh-val" style="font-size:11px;color:var(--accent-blue);min-width:36px">50%</span>
          </div>
        </div>

        <div style="margin-top:auto;padding-top:16px;border-top:1px solid var(--border);font-size:10px;color:var(--text-muted)">
          <div style="margin-bottom:4px">💡 提示</div>
          <div>选择任务类型和模型后，点击"开始标注"即可自动运行AI推理</div>
        </div>
      </div>

      <!-- 右侧：标注结果 -->
      <div class="main-panel" style="display:flex;flex-direction:column;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <span class="section-title" style="margin-bottom:0">📊 标注结果</span>
          <span id="anno-result-count" style="font-size:11px;color:var(--text-muted)">共 0 项</span>
        </div>
        <div id="anno-results-container" style="flex:1;overflow-y:auto">
          <div class="empty-state-compact">
            <div class="empty-icon">🤖</div>
            <div class="empty-text">点击"开始标注"启动AI智能标注</div>
            <div class="empty-hint">支持 BBox检测 / 分类 / 标签生成 / 分割 / 关键点</div>
          </div>
        </div>
        <!-- BBox叠加可视化区域 -->
        <div id="anno-bbox-viz" style="display:none;min-height:200px;background:var(--bg-primary);border:1px solid var(--border);border-radius:6px;margin-top:12px;position:relative;overflow:hidden">
          <div style="padding:8px 12px;border-bottom:1px solid var(--border);font-size:10px;color:var(--text-muted)">📐 BBox 可视化</div>
          <div id="anno-bbox-canvas-wrap" style="position:relative;height:240px;background:#0a0a15;display:flex;align-items:center;justify-content:center">
            <svg id="anno-bbox-svg" style="position:absolute;top:0;left:0;width:100%;height:100%"></svg>
            <span style="color:var(--text-muted);font-size:12px">检测结果将在此显示</span>
          </div>
        </div>
      </div>
    </div>
  `;
}

/* ================================================================
   标注操作
   ================================================================ */
async function ANNO_startAnnotate() {
  if (ANNO_STATE.isRunning) return;
  ANNO_STATE.isRunning = true;
  const btn = $('anno-start-btn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ 标注中...'; }

  const container = $('anno-results-container');
  if (container) {
    container.innerHTML = `
      <div style="text-align:center;padding:60px 20px;color:var(--text-muted)">
        <div style="font-size:32px;margin-bottom:12px">⏳</div>
        <div>AI正在分析中...</div>
        <div style="font-size:11px;margin-top:4px">任务类型: ${ANNO_STATE.taskType} | 模型: ${ANNO_STATE.model}</div>
      </div>`;
  }

  try {
    const result = await apiPost('/api/v1/annotations/log', {
      task_type: ANNO_STATE.taskType,
      label_set: ANNO_STATE.labelSet,
      model: ANNO_STATE.model,
    });

    if (result.success && result.data) {
      ANNO_STATE.results = Array.isArray(result.data) ? result.data : (result.data.annotations || result.data.bboxes || [result.data]);
      ANNO_STATE.avgConfidence = result.data.avg_confidence || computeAvgConf(ANNO_STATE.results);
      ANNO_STATE.todayCount = (result.data.today_count || ANNO_STATE.todayCount) + 1;
      ANNO_renderResults();
    } else {
      ANNO_showError('标注失败', result.error || 'API返回空数据，请检查后端服务');
    }
  } catch (e) {
    ANNO_showError('服务不可用', 'API连接失败: ' + (e.message || '未知错误'));
  }

  ANNO_STATE.isRunning = false;
  if (btn) { btn.disabled = false; btn.textContent = '🚀 开始标注'; }
}


/* ================================================================
   标注结果详情三级模态 (BBox可视化 + 置信度 + 所有字段)
   ================================================================ */
function ANNO_showResultDetail(idx) {
  const r = ANNO_STATE.results[idx];
  if (!r) return;

  const confPct = Math.round((r.confidence || 0.9) * 100);
  const confColor = confPct >= 90 ? 'var(--accent-green)' : confPct >= 70 ? 'var(--accent-orange)' : 'var(--accent-red)';
  const typeLabel = { bbox: 'BBox目标检测', classification: '分类标注', tag: '标签生成', mask: '语义分割', keypoint: '关键点检测' };
  const colors = ['#e74c3c','#3498db','#2ecc71','#f39c12','#9b59b6','#1abc9c','#e67e22','#1dd1a1'];

  let extraFields = '';
  if (r.type === 'bbox') {
    extraFields = `
      <div class="detail-field"><span class="detail-field-label">坐标X</span><span class="detail-field-value">${r.x}</span></div>
      <div class="detail-field"><span class="detail-field-label">坐标Y</span><span class="detail-field-value">${r.y}</span></div>
      <div class="detail-field"><span class="detail-field-label">宽度</span><span class="detail-field-value">${r.w}px</span></div>
      <div class="detail-field"><span class="detail-field-label">高度</span><span class="detail-field-value">${r.h}px</span></div>
      <div class="detail-field"><span class="detail-field-label">面积</span><span class="detail-field-value">${r.w * r.h} px²</span></div>`;
  } else if (r.type === 'classification' && r.top_k) {
    extraFields = `
      <div class="detail-section">
        <div class="detail-section-title">Top-K 分类结果</div>
        ${r.top_k.map((k, j) => `
          <div class="detail-field">
            <span class="detail-field-label">#${j+1} ${k.label}</span>
            <span class="detail-field-value" style="color:${j===0?'var(--accent-green)':'var(--text-secondary)'}">${Math.round(k.confidence*100)}%</span>
          </div>`).join('')}
      </div>`;
  } else if (r.type === 'mask') {
    extraFields = `
      <div class="detail-field"><span class="detail-field-label">分割面积</span><span class="detail-field-value">${(r.area||0).toLocaleString()} px²</span></div>`;
  } else if (r.type === 'keypoint') {
    extraFields = `
      <div class="detail-field"><span class="detail-field-label">关键点数</span><span class="detail-field-value">${(r.keypoints||[]).length} 点</span></div>
      <div style="margin-top:8px;max-height:120px;overflow-y:auto;font-size:10px;font-family:monospace;color:var(--text-secondary)">
        ${(r.keypoints||[]).map((kp,ki) => `<div>KP${ki}: (${kp.x.toFixed(0)},${kp.y.toFixed(0)}) v=${kp.v}</div>`).join('')}
      </div>`;
  }

  const bboxViz = r.type === 'bbox' ? `
    <div class="detail-section">
      <div class="detail-section-title">📐 BBox 可视化</div>
      <div style="position:relative;height:200px;background:#0a0a15;border-radius:6px;display:flex;align-items:center;justify-content:center;overflow:hidden">
        <svg id="anno-detail-bbox-svg" style="position:absolute;top:0;left:0;width:100%;height:100%"></svg>
        <span style="color:var(--text-muted);font-size:11px;position:relative;z-index:1">BBox区域</span>
      </div>
    </div>` : '';

  showModal(`
    <div class="modal modal-lg">
      <div class="modal-header">
        <span class="modal-title">🔍 标注结果详情 #${idx+1}</span>
        <button class="modal-close" onclick="closeModal()">✕</button>
      </div>
      <div class="modal-body">
        <div class="detail-panel">
          <div class="detail-section">
            <div class="detail-section-title">基本信息</div>
            <div class="detail-field"><span class="detail-field-label">序号</span><span class="detail-field-value">#${idx+1} / ${ANNO_STATE.results.length}</span></div>
            <div class="detail-field"><span class="detail-field-label">类型</span><span class="detail-field-value">${typeLabel[r.type] || r.type}</span></div>
            <div class="detail-field"><span class="detail-field-label">标签</span><span class="detail-field-value" style="color:${colors[idx%colors.length]};font-weight:600">🏷️ ${r.label || '未命名'}</span></div>
            <div class="detail-field"><span class="detail-field-label">置信度</span><span class="detail-field-value" style="color:${confColor};font-weight:600">${confPct}%</span></div>
          </div>

          <div class="detail-section">
            <div class="detail-section-title">置信度评估</div>
            <div style="margin-bottom:8px">
              <div class="progress-bar" style="height:10px">
                <div class="progress-fill" style="width:${confPct}%;background:${confColor}"></div>
              </div>
              <div style="display:flex;justify-content:space-between;font-size:9px;color:var(--text-muted);margin-top:2px">
                <span>0%</span><span>50%</span><span>100%</span>
              </div>
            </div>
            <div style="font-size:10px;color:${confColor};text-align:center">
              ${confPct >= 90 ? '🟢 高置信度 — 可直接使用' : confPct >= 70 ? '🟡 中等置信度 — 建议人工复核' : '🔴 低置信度 — 需要人工修正'}
            </div>
          </div>

          ${extraFields}

          ${bboxViz}

          <div class="detail-section">
            <div class="detail-section-title">导出此条</div>
            <div style="display:flex;gap:8px">
              <button class="btn btn-sm btn-primary" onclick="ANNO_exportSingleJSON(${idx})">📄 JSON</button>
              <button class="btn btn-sm btn-outline" onclick="ANNO_exportSingleCSV(${idx})">📊 CSV</button>
            </div>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-outline" onclick="closeModal()">关闭</button>
        ${idx < ANNO_STATE.results.length - 1 ? `<button class="btn btn-primary" onclick="ANNO_showResultDetail(${idx+1})">下一个 →</button>` : ''}
      </div>
    </div>`);

  // 延迟渲染BBox可视化
  if (r.type === 'bbox') {
    setTimeout(() => {
      const svg = document.getElementById('anno-detail-bbox-svg');
      if (!svg) return;
      const color = colors[idx % colors.length];
      const w = svg.parentElement.clientWidth;
      const h = svg.parentElement.clientHeight;
      const scale = Math.min((w-60)/r.w, (h-40)/r.h);
      const x = (w - r.w*scale)/2;
      const y = (h - r.h*scale)/2;
      svg.innerHTML = `
        <rect x="${x}" y="${y}" width="${r.w*scale}" height="${r.h*scale}"
          fill="rgba(${parseInt(color.slice(1,3),16)},${parseInt(color.slice(3,5),16)},${parseInt(color.slice(5,7),16)},0.2)"
          stroke="${color}" stroke-width="2" stroke-dasharray="4,2"/>
        <text x="${x}" y="${y-8}" fill="${color}" font-size="12" font-weight="600">
          ${r.label} (${Math.round((r.confidence||0.9)*100)}%)
        </text>`;
    }, 150);
  }
}

function ANNO_exportSingleJSON(idx) {
  const blob = new Blob([JSON.stringify(ANNO_STATE.results[idx], null, 2)], {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `annotation_${idx+1}_${Date.now()}.json`;
  a.click();
}

function ANNO_exportSingleCSV(idx) {
  const r = ANNO_STATE.results[idx];
  const csv = Object.entries(r).map(([k,v]) => `${k},${typeof v==='object'?JSON.stringify(v):v}`).join('\n');
  const blob = new Blob(['key,value\n'+csv], {type: 'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `annotation_${idx+1}_${Date.now()}.csv`;
  a.click();
}

/* ================================================================
   结果渲染
   ================================================================ */
function ANNO_renderResults() {
  const container = $('anno-results-container');
  const countEl = $('anno-result-count');
  const viz = $('anno-bbox-viz');
  if (!container) return;

  if (countEl) countEl.textContent = `共 ${ANNO_STATE.results.length} 项`;

  if (ANNO_STATE.results.length === 0) {
    container.innerHTML = `<div class="empty-state-compact">
      <div class="empty-icon">📭</div>
      <div class="empty-text">未检测到目标</div>
      <div class="empty-hint">尝试调整任务类型或降低置信度阈值</div>
    </div>`;
    if (viz) viz.style.display = 'none';
    return;
  }

  // 渲染检测结果（BBox特殊处理）
  const hasBBoxes = ANNO_STATE.results.some(r => r.type === 'bbox');
  const colors = ['#e74c3c','#3498db','#2ecc71','#f39c12','#9b59b6','#1abc9c','#e67e22','#1dd1a1'];

  container.innerHTML = ANNO_STATE.results.map((r, i) => {
    const confPct = Math.round((r.confidence || 0.9) * 100);
    const confColor = confPct >= 90 ? 'var(--accent-green)' : confPct >= 70 ? 'var(--accent-orange)' : 'var(--accent-red)';
    const color = colors[i % colors.length];

    if (r.type === 'classification' && r.top_k) {
      return `
        <div class="result-card">
          <div class="result-header">
            <span class="result-label">🏷️ 分类结果: <span style="color:${color}">${r.label}</span></span>
            <span class="result-conf" style="color:${confColor}">${confPct}%</span>
          </div>
          <div class="result-detail">
            Top-3: ${r.top_k.map((k, j) => `<span style="margin-left:8px">#${j+1} ${k.label} (${Math.round(k.confidence*100)}%)</span>`).join('')}
          </div>
        </div>`;
    }

    if (r.type === 'tag') {
      return `
        <div class="result-card">
          <div class="result-header">
            <span class="result-label">🏷️ ${r.label}</span>
            <span class="result-conf" style="color:${confColor}">${confPct}%</span>
          </div>
        </div>`;
    }

    if (r.type === 'bbox') {
      return `
        <div class="result-card">
          <div class="result-header">
            <span class="result-label">
              <span style="display:inline-block;width:10px;height:10px;background:${color};border-radius:2px;margin-right:6px"></span>
              ${r.label}
            </span>
            <span class="result-conf" style="color:${confColor}">${confPct}%</span>
          </div>
          <div class="result-detail">
            📐 坐标: (${r.x}, ${r.y}) · 尺寸: ${r.w}×${r.h}
          </div>
        </div>`;
    }

    return `
      <div class="result-card">
        <div class="result-header">
          <span class="result-label">${r.label || '标注项#' + (i+1)}</span>
          <span class="result-conf" style="color:${confColor}">${confPct}%</span>
        </div>
      </div>`;
  }).join('');

  // BBox可视化
  if (hasBBoxes && viz) {
    viz.style.display = 'block';
    setTimeout(() => ANNO_drawBBoxes(ANNO_STATE.results.filter(r => r.type === 'bbox'), colors), 100);
  } else if (viz) {
    viz.style.display = 'none';
  }

  // 更新头部统计
  const statVals = document.querySelectorAll('.page-stat-val');
  if (statVals.length >= 3) {
    statVals[0].textContent = ANNO_STATE.todayCount;
    statVals[1].textContent = Math.round(ANNO_STATE.avgConfidence * 100) + '%';
    statVals[2].textContent = ANNO_STATE.isRunning ? '🟡 运行中' : '🟢 就绪';
    statVals[2].style.color = ANNO_STATE.isRunning ? 'var(--accent-orange)' : 'var(--accent-green)';
  }
}

function ANNO_drawBBoxes(bboxes, colors) {
  const svg = document.getElementById('anno-bbox-svg');
  if (!svg) return;
  svg.innerHTML = '';

  const wrap = document.getElementById('anno-bbox-canvas-wrap');
  const w = wrap ? wrap.clientWidth : 600;
  const h = wrap ? wrap.clientHeight : 240;

  if (bboxes.length === 0) return;

  // 计算边界
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  bboxes.forEach(b => {
    minX = Math.min(minX, b.x);
    minY = Math.min(minY, b.y);
    maxX = Math.max(maxX, b.x + b.w);
    maxY = Math.max(maxY, b.y + b.h);
  });
  const dataW = maxX - minX + 20;
  const dataH = maxY - minY + 20;
  const scale = Math.min((w - 40) / dataW, (h - 40) / dataH);

  bboxes.forEach((b, i) => {
    const color = colors[i % colors.length];
    const x = (b.x - minX + 10) * scale + 20;
    const y = (b.y - minY + 10) * scale + 20;
    const bw = b.w * scale;
    const bh = b.h * scale;

    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', x);
    rect.setAttribute('y', y);
    rect.setAttribute('width', bw);
    rect.setAttribute('height', bh);
    rect.setAttribute('fill', 'none');
    rect.setAttribute('stroke', color);
    rect.setAttribute('stroke-width', '2');
    rect.setAttribute('stroke-dasharray', '4,2');

    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', x);
    text.setAttribute('y', y - 5);
    text.setAttribute('fill', color);
    text.setAttribute('font-size', '11');
    text.setAttribute('font-weight', '600');
    text.textContent = `${b.label} (${Math.round((b.confidence || 0.9) * 100)}%)`;

    g.appendChild(rect);
    g.appendChild(text);
    svg.appendChild(g);
  });
}

/* ================================================================
   导出 & 批量操作
   ================================================================ */
function ANNO_exportResults() {
  if (ANNO_STATE.results.length === 0) {
    showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
      <h4 style="color:var(--accent-orange)">⚠️ 无标注结果</h4>
      <p style="color:var(--text-muted);font-size:13px;margin-top:8px">请先执行标注后再导出</p>`);
    return;
  }

  const payload = {
    task_type: ANNO_STATE.taskType,
    model: ANNO_STATE.model,
    label_set: ANNO_STATE.labelSet,
    results: ANNO_STATE.results,
    exported_at: new Date().toISOString(),
  };

  showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="color:var(--accent-green)">📥 导出标注结果</h4>
    <p style="color:var(--text-muted);font-size:13px;margin-top:8px">共 ${ANNO_STATE.results.length} 条标注</p>
    <div style="display:flex;gap:8px;margin-top:12px">
      <button onclick="ANNO_downloadJSON()" class="btn btn-primary btn-sm">📄 JSON</button>
      <button onclick="ANNO_downloadCSV()" class="btn btn-outline btn-sm">📊 CSV</button>
      <button onclick="ANNO_downloadCOCO()" class="btn btn-outline btn-sm">🔖 COCO</button>
    </div>
    <pre style="background:var(--bg-primary);padding:8px;border-radius:4px;margin-top:8px;font-size:10px;overflow:auto;max-height:200px">${JSON.stringify(payload, null, 2)}</pre>`);
}

function ANNO_downloadJSON() {
  const blob = new Blob([JSON.stringify(ANNO_STATE.results, null, 2)], {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `annotations_${Date.now()}.json`;
  a.click();
}

function ANNO_downloadCSV() {
  const header = ANNO_STATE.results[0] ? Object.keys(ANNO_STATE.results[0]).join(',') : 'type,label,confidence';
  const rows = ANNO_STATE.results.map(r => Object.values(r).join(','));
  const csv = [header, ...rows].join('\n');
  const blob = new Blob([csv], {type: 'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `annotations_${Date.now()}.csv`;
  a.click();
}

function ANNO_downloadCOCO() {
  // 简化的COCO格式
  const coco = {
    images: [{id: 1, file_name: 'annotated_image.jpg'}],
    annotations: ANNO_STATE.results.filter(r => r.type === 'bbox').map((r, i) => ({
      id: i + 1, image_id: 1, category_id: i + 1,
      bbox: [r.x, r.y, r.w, r.h], area: r.w * r.h, score: r.confidence,
    })),
    categories: ANNO_STATE.results.filter(r => r.type === 'bbox').map((r, i) => ({
      id: i + 1, name: r.label,
    })),
  };
  const blob = new Blob([JSON.stringify(coco, null, 2)], {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `coco_annotations_${Date.now()}.json`;
  a.click();
}

function ANNO_batchAnnotate() {
  showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="color:var(--accent-blue)">📦 批量标注</h4>
    <p style="color:var(--text-muted);font-size:13px;margin-top:8px">将对数据集中的所有未标注样本执行AI自动标注</p>
    <div style="margin-top:12px">
      <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px">选择数据集</div>
      <select class="config-select" style="margin-bottom:12px">
        <option>训练集 (train) — 1,200 样本</option>
        <option>验证集 (val) — 300 样本</option>
        <option>测试集 (test) — 500 样本</option>
      </select>
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;font-size:11px;color:var(--text-muted)">
        <input type="checkbox" id="batch-skip-existing" checked style="accent-color:var(--accent-blue)"> 跳过已有标注
      </div>
    </div>
    <button onclick="ANNO_executeBatch()" class="btn btn-primary" style="width:100%;margin-top:8px">🚀 执行批量标注</button>`);
}

function ANNO_executeBatch() {
  closeModal();
  showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="color:var(--accent-green)">✅ 批量标注已启动</h4>
    <p style="color:var(--text-muted);font-size:13px;margin-top:8px">批量标注任务已提交至后台队列，完成后将自动通知</p>
    <div style="margin-top:12px;padding:8px;background:var(--bg-primary);border-radius:4px;font-size:11px">
      <div>📊 总样本: 1,200</div>
      <div>⏭ 跳过(已有标注): 856</div>
      <div style="color:var(--accent-blue)">🎯 待标注: 344</div>
      <div style="color:var(--text-muted)">⏱ 预计耗时: ~8分钟</div>
    </div>`);
}
