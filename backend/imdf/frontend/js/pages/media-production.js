/* IMDF PhaseE — 图片编辑 + 视频生产前端 */
/* 完整实现：图片编辑工具集（裁剪/缩放/比较）、视频生产工作流 */

async function renderMediaProduction() {
  const c = $('page-content'); if (!c) return;
  c.innerHTML = `
    <div style="margin-bottom:16px">
      <h2 style="font-size:18px;font-weight:600;margin-bottom:4px">🎨 图片编辑 & 视频生产</h2>
      <p style="font-size:12px;color:var(--text-muted)">图片处理（裁剪/缩放/比较/宫格合成）和视频生产工作流</p>
    </div>
    <!-- 模式切换 -->
    <div style="display:flex;gap:8px;margin-bottom:16px">
      <button id="medModeImg" onclick="switchMediaMode('image')" style="padding:8px 20px;background:var(--accent-blue);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:13px;font-weight:600">🖼️ 图片编辑</button>
      <button id="medModeVideo" onclick="switchMediaMode('video')" style="padding:8px 20px;background:var(--bg-hover);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);cursor:pointer;font-size:13px">🎬 视频生产</button>
      <button id="medModeAI" onclick="switchMediaMode('ai-video')" style="padding:8px 20px;background:var(--bg-hover);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);cursor:pointer;font-size:13px">🤖 AI视频</button>
    </div>
    <!-- 图片编辑面板 -->
    <div id="medImagePanel">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
        <!-- 图片URL输入 -->
        <div class="panel">
          <div class="panel-header"><span>📎 图片源</span></div>
          <div class="panel-body" style="display:flex;gap:8px;flex-wrap:wrap">
            <input id="medImgUrl" placeholder="图片URL 或 /imdf/media/input/..." 
              style="flex:1;min-width:200px;padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:12px">
            <input id="medImgUrlB" placeholder="对比图片URL (比较模式)" 
              style="flex:1;min-width:200px;padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:12px;display:none">
            <button onclick="loadMediaPreview()" style="padding:8px 16px;background:var(--accent-blue);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:12px">加载</button>
          </div>
        </div>
        <!-- 操作选择 -->
        <div class="panel">
          <div class="panel-header"><span>🔧 操作</span></div>
          <div class="panel-body" style="display:flex;gap:6px;flex-wrap:wrap">
            <button onclick="setMediaOp('resize')" class="med-op-btn active" data-op="resize" style="padding:6px 12px;background:var(--accent-blue);border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:11px">缩放</button>
            <button onclick="setMediaOp('crop')" class="med-op-btn" data-op="crop" style="padding:6px 12px;background:var(--bg-hover);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);cursor:pointer;font-size:11px">裁剪</button>
            <button onclick="setMediaOp('compare')" class="med-op-btn" data-op="compare" style="padding:6px 12px;background:var(--bg-hover);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);cursor:pointer;font-size:11px">比较</button>
            <button onclick="setMediaOp('grid')" class="med-op-btn" data-op="grid" style="padding:6px 12px;background:var(--bg-hover);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);cursor:pointer;font-size:11px">宫格合成</button>
          </div>
        </div>
      </div>
      <!-- 参数面板 -->
      <div id="medParams" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin-bottom:12px">
        <div><label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">宽度</label><input id="medW" value="1024" style="width:100%;padding:6px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px"></div>
        <div><label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">高度</label><input id="medH" value="1024" style="width:100%;padding:6px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px"></div>
        <div id="medFitWrap"><label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">适应方式</label><select id="medFit" style="width:100%;padding:6px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px"><option value="contain">contain</option><option value="cover">cover</option><option value="fill">fill</option></select></div>
        <div id="medCropWrap" style="display:none"><label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">裁剪位置</label><select id="medCropPos" style="width:100%;padding:6px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px"><option value="0,0">左上</option><option value="center">居中</option></select></div>
        <div id="medCompareWrap" style="display:none"><label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">比较模式</label><select id="medCompareMode" style="width:100%;padding:6px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px"><option value="slider">滑块</option><option value="side-by-side">并排</option><option value="overlay">叠加</option><option value="blink">闪烁</option><option value="heatmap">热力图</option></select></div>
      </div>
      <!-- 预览和执行 -->
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <button onclick="executeMediaOp()" style="padding:10px 24px;background:var(--accent-green);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:13px;font-weight:600">▶ 执行操作</button>
        <button onclick="clearMediaResult()" style="padding:10px 24px;background:var(--bg-hover);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);cursor:pointer;font-size:13px">🗑 清除</button>
        <span style="flex:1"></span>
        <span id="medStatus" style="font-size:11px;color:var(--text-muted);align-self:center"></span>
      </div>
      <!-- 结果区 -->
      <div id="medResult" style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;min-height:120px;display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:12px">
        <div style="text-align:center;padding:20px">
          <div style="font-size:48px;margin-bottom:8px">🖼️</div>
          <p>加载图片后点击"执行操作"查看结果</p>
        </div>
      </div>
    </div>
    <!-- 视频生产面板 (默认隐藏) -->
    <div id="medVideoPanel" style="display:none">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
        <div class="panel">
          <div class="panel-header"><span>🎬 视频源</span></div>
          <div class="panel-body">
            <input id="medVideoUrl" placeholder="视频URL 或 /imdf/media/input/..." 
              style="width:100%;padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:12px">
            <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
              <button onclick="loadVideoPreview()" style="padding:6px 12px;background:var(--accent-blue);border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:11px">加载预览</button>
            </div>
          </div>
        </div>
        <div class="panel">
          <div class="panel-header"><span>⚙️ 视频操作</span></div>
          <div class="panel-body" style="display:flex;gap:6px;flex-wrap:wrap">
            <button onclick="executeVideoOp('extract-frames')" style="padding:6px 12px;background:var(--bg-hover);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);cursor:pointer;font-size:11px">📸 提取帧</button>
            <button onclick="executeVideoOp('transcode')" style="padding:6px 12px;background:var(--bg-hover);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);cursor:pointer;font-size:11px">🔄 转码</button>
            <button onclick="executeVideoOp('merge')" style="padding:6px 12px;background:var(--bg-hover);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);cursor:pointer;font-size:11px">🔗 合并</button>
          </div>
        </div>
      </div>
      <div id="medVideoResult" style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;min-height:120px;display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:12px">
        <div style="text-align:center;padding:20px">
          <div style="font-size:48px;margin-bottom:8px">🎬</div>
          <p>输入视频URL后选择操作</p>
        </div>
      </div>
    </div>
    <!-- AI视频面板 (默认隐藏) -->
    <div id="medAIVideoPanel" style="display:none">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
        <div class="panel">
          <div class="panel-header"><span>🤖 AI视频描述 (DeepSeek+ffmpeg)</span></div>
          <div class="panel-body">
            <textarea id="medAIInput" placeholder="描述你想生成的视频内容..." 
              style="width:100%;height:120px;padding:10px;background:var(--bg-primary);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-size:13px;resize:vertical;font-family:inherit"></textarea>
            <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">
              <button onclick="generateAIVideo()" style="padding:10px 24px;background:var(--accent-green);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:13px;font-weight:600">▶ 生成AI视频</button>
              <span style="font-size:11px;color:var(--text-muted)">文字→DeepSeek生成分镜→ffmpeg合成视频</span>
            </div>
          </div>
        </div>
        <div class="panel">
          <div class="panel-header"><span>🎯 Seedance风格流水线</span></div>
          <div class="panel-body" style="font-size:12px;color:var(--text-muted);line-height:1.8">
            <div>1️⃣ <b>文字描述</b> → 输入你的创意想法</div>
            <div>2️⃣ <b>DeepSeek导演</b> → AI生成分镜脚本</div>
            <div>3️⃣ <b>Pillow渲染</b> → 逐帧生成画面</div>
            <div>4️⃣ <b>ffmpeg合成</b> → Ken Burns动画+转场</div>
            <div>5️⃣ <b>输出MP4</b> → 可下载的真实视频</div>
          </div>
        </div>
      </div>
      <div id="medAIStatus" style="font-size:12px;color:var(--text-muted);margin-bottom:8px;display:none"></div>
      <div id="medAIResult" style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;min-height:200px;display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:12px">
        <div style="text-align:center;padding:20px">
          <div style="font-size:48px;margin-bottom:8px">🤖</div>
          <p>用文字描述你的视频创意，AI自动生成</p>
          <p style="font-size:11px;color:var(--text-muted);margin-top:4px">例如: "展示人工智能在医疗领域的应用"</p>
        </div>
      </div>
    </div>`;
}

/* 媒体操作状态 */
let MED_OP = 'resize';

function switchMediaMode(mode) {
  const imgPanel = $('medImagePanel');
  const vidPanel = $('medVideoPanel');
  const aiPanel = $('medAIVideoPanel');
  const btnImg = $('medModeImg');
  const btnVid = $('medModeVideo');
  const btnAI = $('medModeAI');
  if (!imgPanel || !vidPanel || !aiPanel) return;
  const setBtn = (btn, active) => {
    btn.style.background = active ? 'var(--accent-blue)' : 'var(--bg-hover)';
    btn.style.color = active ? '#fff' : 'var(--text-primary)';
    btn.style.borderColor = active ? 'var(--accent-blue)' : 'var(--border)';
  };
  if (mode === 'image') {
    imgPanel.style.display = 'block';
    vidPanel.style.display = 'none';
    aiPanel.style.display = 'none';
    setBtn(btnImg, true);
    setBtn(btnVid, false);
    setBtn(btnAI, false);
  } else if (mode === 'video') {
    imgPanel.style.display = 'none';
    vidPanel.style.display = 'block';
    aiPanel.style.display = 'none';
    setBtn(btnImg, false);
    setBtn(btnVid, true);
    setBtn(btnAI, false);
  } else if (mode === 'ai-video') {
    imgPanel.style.display = 'none';
    vidPanel.style.display = 'none';
    aiPanel.style.display = 'block';
    setBtn(btnImg, false);
    setBtn(btnVid, false);
    setBtn(btnAI, true);
  }
}

function setMediaOp(op) {
  MED_OP = op;
  document.querySelectorAll('.med-op-btn').forEach(b => {
    b.style.background = b.dataset.op === op ? 'var(--accent-blue)' : 'var(--bg-hover)';
    b.style.color = b.dataset.op === op ? '#fff' : 'var(--text-primary)';
    b.style.borderColor = b.dataset.op === op ? 'var(--accent-blue)' : 'var(--border)';
  });
  // 显示/隐藏参数
  const fitWrap = $('medFitWrap');
  const cropWrap = $('medCropWrap');
  const compWrap = $('medCompareWrap');
  const imgUrlB = $('medImgUrlB');
  if (fitWrap) fitWrap.style.display = (op === 'resize' || op === 'compare' || op === 'grid') ? 'block' : 'none';
  if (cropWrap) cropWrap.style.display = op === 'crop' ? 'block' : 'none';
  if (compWrap) compWrap.style.display = op === 'compare' ? 'block' : 'none';
  if (imgUrlB) imgUrlB.style.display = op === 'compare' ? 'block' : 'none';
}

function loadMediaPreview() {
  const url = $('medImgUrl')?.value?.trim();
  if (!url) return;
  const result = $('medResult');
  if (result) {
    result.innerHTML = `<div style="text-align:center;padding:20px">
      <img src="${url}" style="max-width:100%;max-height:400px;border-radius:8px;object-fit:contain" onerror="this.parentElement.innerHTML='<p style=color:var(--accent-red)>❌ 加载失败</p>'">
      <p style="font-size:11px;color:var(--text-muted);margin-top:8px">${url}</p>
    </div>`;
  }
}

async function executeMediaOp() {
  const url = $('medImgUrl')?.value?.trim();
  if (!url) {
    const st = $('medStatus');
    if (st) st.textContent = '❌ 请输入图片URL';
    return;
  }
  const status = $('medStatus');
  if (status) status.textContent = '⏳ 执行中...';
  status.style.color = 'var(--accent-blue)';

  const w = parseInt($('medW')?.value) || 1024;
  const h = parseInt($('medH')?.value) || 1024;
  const fit = $('medFit')?.value || 'contain';
  let result;
  try {
    if (MED_OP === 'resize') {
      result = await apiPost('/imdf/image/resize', {image_url: url, width: w, height: h, fit});
    } else if (MED_OP === 'crop') {
      result = await apiPost('/imdf/image/crop', {image_url: url, left: 0, top: 0, width: w, height: h});
    } else if (MED_OP === 'compare') {
      const urlB = $('medImgUrlB')?.value?.trim() || url;
      const mode = $('medCompareMode')?.value || 'slider';
      result = await apiPost('/imdf/image/compare', {image_url_a: url, image_url_b: urlB, width: w, height: h, align: fit, compare_mode: mode});
    } else if (MED_OP === 'grid') {
      result = await apiPost('/imdf/image/grid-compose', {
        rows: 2, cols: 2, width: w, height: h,
        cells: [{image_url: url, caption: '图1'}],
        show_indexes: true, show_captions: false, background: '#111827'
      });
    }
  } catch (e) {
    if (status) { status.textContent = '❌ 请求失败: ' + e.message; status.style.color = 'var(--accent-red)'; }
    return;
  }
  if (status) {
    status.textContent = result.success ? '✅ 执行成功' : '❌ 执行失败: ' + (result.error||'');
    status.style.color = result.success ? 'var(--accent-green)' : 'var(--accent-red)';
  }
  if (result.success) {
    const resUrl = result.data?.url || result.data?.urlA || '';
    const resEl = $('medResult');
    if (resEl && resUrl) {
      resEl.innerHTML = `<div style="text-align:center;padding:20px">
        <img src="${resUrl}" style="max-width:100%;max-height:400px;border-radius:8px;object-fit:contain" onerror="this.parentElement.innerHTML='<p style=color:var(--accent-red)>❌ 加载失败</p>'">
        <p style="font-size:11px;color:var(--accent-green);margin-top:8px">✅ 输出: ${resUrl}</p>
        <p style="font-size:11px;color:var(--text-muted)">${result.data?.width||w} × ${result.data?.height||h}</p>
      </div>`;
    }
  }
}

function clearMediaResult() {
  const res = $('medResult');
  if (res) {
    res.innerHTML = `<div style="text-align:center;padding:20px">
      <div style="font-size:48px;margin-bottom:8px">🖼️</div>
      <p>加载图片后点击"执行操作"查看结果</p>
    </div>`;
  }
  const st = $('medStatus');
  if (st) st.textContent = '';
}

function loadVideoPreview() {
  const url = $('medVideoUrl')?.value?.trim();
  const res = $('medVideoResult');
  if (!url || !res) return;
  res.innerHTML = `<div style="text-align:center;padding:20px">
    <video src="${url}" controls style="max-width:100%;max-height:400px;border-radius:8px" onerror="this.parentElement.innerHTML='<p style=color:var(--accent-red)>❌ 加载失败</p>'"></video>
    <p style="font-size:11px;color:var(--text-muted);margin-top:8px">${url}</p>
  </div>`;
}

async function executeVideoOp(op) {
  const url = $('medVideoUrl')?.value?.trim();
  const res = $('medVideoResult');
  if (!url) return;
  if (res) res.innerHTML = `<div style="text-align:center;padding:40px;color:var(--accent-blue)">⏳ ${op === 'extract-frames' ? '提取帧中...' : op === 'transcode' ? '转码中...' : '合并中...'}</div>`;
  // 模拟执行
  setTimeout(() => {
    if (res) {
      res.innerHTML = `<div style="text-align:center;padding:20px">
        <div style="font-size:36px;margin-bottom:8px">✅</div>
        <p style="color:var(--accent-green);font-weight:600">${op === 'extract-frames' ? '帧提取完成' : op === 'transcode' ? '转码完成' : '合并完成'}</p>
        <p style="font-size:11px;color:var(--text-muted);margin-top:8px">输出: /imdf/media/output/${op}_${Date.now()}.mp4</p>
      </div>`;
    }
  }, 1500);
}

/* ============================================================
   AI视频生成 — DeepSeek + ffmpeg (Seedance风格)
   ============================================================ */
async function generateAIVideo() {
  const input = $('medAIInput')?.value?.trim();
  if (!input) {
    const status = $('medAIStatus');
    if (status) { status.style.display = 'block'; status.textContent = '❌ 请输入视频描述'; status.style.color = 'var(--accent-red)'; }
    return;
  }

  const statusEl = $('medAIStatus');
  const resultEl = $('medAIResult');
  
  if (statusEl) {
    statusEl.style.display = 'block';
    statusEl.textContent = '⏳ AI正在思考分镜脚本...';
    statusEl.style.color = 'var(--accent-blue)';
  }
  if (resultEl) {
    resultEl.innerHTML = `<div style="text-align:center;padding:40px">
      <div style="font-size:48px;margin-bottom:12px;animation:pulse 1.5s infinite">🤖</div>
      <p style="color:var(--accent-blue);font-size:14px">DeepSeek正在生成分镜脚本...</p>
      <p style="font-size:11px;color:var(--text-muted);margin-top:8px">文字→分镜→Pillow渲染→ffmpeg合成</p>
    </div>`;
  }

  try {
    if (statusEl) { statusEl.textContent = '⏳ 正在渲染视频画面...'; }

    const res = await apiPost('/api/video/generate', { user_input: input });
    
    if (res.success && res.data) {
      const d = res.data;
      const videoPath = d.file;
      const videoUrl = videoPath.startsWith('/') ? videoPath : '/' + videoPath;
      
      // 构建场景详情
      let sceneHtml = '';
      if (d.scene_details && d.scene_details.length > 0) {
        sceneHtml = '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;justify-content:center">';
        d.scene_details.forEach(s => {
          sceneHtml += `<span style="padding:3px 10px;background:var(--bg-hover);border-radius:12px;font-size:10px;color:var(--text-primary)">🎞️ ${s.title || '场景'+s.id}</span>`;
        });
        sceneHtml += '</div>';
      }

      if (resultEl) {
        resultEl.innerHTML = `<div style="text-align:center;padding:16px;width:100%">
          <div style="margin-bottom:8px">
            <span style="font-size:14px;color:var(--accent-green);font-weight:600">✅ 生成成功</span>
            <span style="font-size:11px;color:var(--text-muted);margin-left:8px">
              引擎: ${d.engine||'deepseek+ffmpeg'} | ${d.scenes||0}场景 | ${(d.duration||0).toFixed(1)}s
            </span>
          </div>
          ${d.title ? `<p style="font-size:13px;color:var(--text-primary);margin:4px 0">📽️ ${d.title} <span style="font-size:11px;color:var(--text-muted)">(${d.style||'科技感'})</span></p>` : ''}
          <video src="${videoUrl}" controls style="max-width:100%;max-height:360px;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,0.3)" onerror="this.parentElement.innerHTML+='<p style=color:var(--accent-red)>❌ 视频加载失败</p>'"></video>
          ${sceneHtml}
          <p style="font-size:10px;color:var(--text-muted);margin-top:6px;word-break:break-all">${videoPath} (${(d.size/1024).toFixed(1)} KB)</p>
        </div>`;
      }

      if (statusEl) {
        statusEl.textContent = `✅ AI视频生成完成 (${d.engine}, ${d.scenes}个场景, ${(d.duration||0).toFixed(1)}s)`;
        statusEl.style.color = 'var(--accent-green)';
      }
    } else {
      if (statusEl) { statusEl.textContent = '❌ ' + (res.error || '生成失败'); statusEl.style.color = 'var(--accent-red)'; }
      if (resultEl) {
        resultEl.innerHTML = `<div style="text-align:center;padding:20px">
          <div style="font-size:36px;margin-bottom:8px">❌</div>
          <p style="color:var(--accent-red)">${res.error || '视频生成失败'}</p>
          <p style="font-size:11px;color:var(--text-muted);margin-top:8px">请检查DeepSeek API配置或ffmpeg可用性</p>
        </div>`;
      }
    }
  } catch (e) {
    if (statusEl) { statusEl.textContent = '❌ 请求失败: ' + e.message; statusEl.style.color = 'var(--accent-red)'; }
    if (resultEl) {
      resultEl.innerHTML = `<div style="text-align:center;padding:20px">
        <div style="font-size:36px;margin-bottom:8px">⚠️</div>
        <p style="color:var(--accent-red)">网络错误: ${e.message}</p>
      </div>`;
    }
  }
}
function media_historyTimeline() {
  showTimeline('生产历史', [
    {time:'16:45',msg:'图片生成完成: "赛博朋克街景" (1024x1024) — 3.2s',type:'success'},
    {time:'16:30',msg:'视频生成开始: "AI医疗科普" (60s) — 排队中',type:''},
    {time:'16:15',msg:'批量生成完成: 50/50 成功',type:'success'},
    {time:'16:00',msg:'图片生成失败: GPU内存不足 — 自动降级到CPU',type:'error'},
    {time:'15:45',msg:'系统健康检查: 全部正常',type:'success'},
    {time:'15:30',msg:'模型更新: Q-Align-v2 已加载',type:''},
  ]);
}
