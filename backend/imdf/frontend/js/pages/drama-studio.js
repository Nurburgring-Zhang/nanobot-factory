/* IMDF F1.6 — 短剧生产前端页面 (Drama Studio) */
/* 7阶段Agent流水线: 需求理解→剧本生成→角色锁定→智能分镜→逐镜头生成→音画同步→合成导出 */

let DRAMA_CHARACTERS = [
  { id: 'c1', name: '主角', description: '', appearance: '' },
  { id: 'c2', name: '配角', description: '', appearance: '' }
];
let DRAMA_EPISODES = [{ id: 'e1', title: '第1集', scenes: [] }];
let DRAMA_SHOTS = [];
let DRAMA_ACTIVE_SHOT = null;
let DRAMA_GENERATING = false;

async function renderDramaStudio() {
  const c = $('page-content'); if (!c) return;
  c.innerHTML = buildDramaStudioHTML();
}

function buildDramaStudioHTML() {
  return `
    <div style="margin-bottom:16px">
      <h2 style="font-size:18px;font-weight:600;margin-bottom:4px">📺 短剧工坊 — AI驱动的7阶段短剧生产</h2>
      <p style="font-size:12px;color:var(--text-muted)">
        融合Toonflow/Seedance/ArcReel/Jellyfish方案 · 需求理解→剧本生成→角色锁定→智能分镜→逐镜头生成→音画同步→合成导出
      </p>
    </div>

    <!-- 三栏布局: 左侧配置 | 中间分镜预览 | 右侧属性编辑 -->
    <div style="display:grid;grid-template-columns:340px 1fr 280px;gap:12px;min-height:calc(100vh - 200px)">

      <!-- ===== 左栏: 短剧配置面板 ===== -->
      <div id="dramaLeftPanel" style="display:flex;flex-direction:column;gap:10px;overflow-y:auto;max-height:calc(100vh - 200px)">

        <!-- 剧集信息 -->
        <div class="panel">
          <div class="panel-header"><span>📋 剧集信息</span></div>
          <div class="panel-body" style="display:flex;flex-direction:column;gap:8px">
            <div>
              <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">剧名</label>
              <input id="dramaTitle" value="未命名短剧" style="width:100%;padding:7px 10px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:12px">
            </div>
            <div style="display:flex;gap:8px">
              <div style="flex:1">
                <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">集数</label>
                <input id="dramaEpisodes" type="number" min="1" max="50" value="1" style="width:100%;padding:7px 10px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:12px">
              </div>
              <div style="flex:1">
                <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">每集时长(s)</label>
                <input id="dramaDuration" type="number" min="10" max="600" value="60" style="width:100%;padding:7px 10px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:12px">
              </div>
            </div>
            <div>
              <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">风格</label>
              <select id="dramaStyle" style="width:100%;padding:7px 10px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:12px">
                <option value="modern">🏙️ 现代都市</option>
                <option value="ancient">🏯 古装武侠</option>
                <option value="scifi">🚀 科幻未来</option>
                <option value="suspense">🔍 悬疑推理</option>
                <option value="fantasy">🧙 奇幻世界</option>
                <option value="romance">💕 浪漫爱情</option>
                <option value="comedy">😂 轻松喜剧</option>
                <option value="horror">👻 惊悚恐怖</option>
              </select>
            </div>
            <div style="display:flex;gap:6px">
              <div style="flex:1">
                <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">总镜头数</label>
                <input id="dramaShotCount" type="number" min="5" max="200" value="14" style="width:100%;padding:7px 10px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:12px">
              </div>
              <div style="flex:1">
                <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">镜头时长(s)</label>
                <input id="dramaShotDuration" type="number" min="2" max="30" value="5" style="width:100%;padding:7px 10px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:12px">
              </div>
            </div>
            <label style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text-muted);cursor:pointer">
              <input type="checkbox" id="dramaTTS" checked style="accent-color:var(--accent-blue)"> 启用AI旁白配音(TTS)
            </label>
          </div>
        </div>

        <!-- 角色设置 -->
        <div class="panel">
          <div class="panel-header">
            <span>👥 角色设置 (<span id="dramaCharCount">2</span>)</span>
            <button onclick="addDramaCharacter()" style="margin-left:auto;padding:3px 10px;background:var(--accent-blue);border:none;border-radius:3px;color:#fff;cursor:pointer;font-size:10px">+ 添加</button>
          </div>
          <div class="panel-body" id="dramaCharactersList" style="display:flex;flex-direction:column;gap:8px;max-height:280px;overflow-y:auto">
            ${renderDramaCharacterCards()}
          </div>
        </div>

        <!-- 剧本输入 -->
        <div class="panel">
          <div class="panel-header">
            <span>📝 剧本 / 剧情描述</span>
            <div style="display:flex;gap:4px;margin-left:auto">
              <button onclick="generateDramaScript()" style="padding:3px 8px;background:var(--accent-purple, #7c3aed);border:none;border-radius:3px;color:#fff;cursor:pointer;font-size:10px">🤖 AI生成</button>
            </div>
          </div>
          <div class="panel-body">
            <textarea id="dramaScript" placeholder="输入短剧剧情描述或完整剧本...
AI会根据描述自动生成分镜...

示例:
在一个被灰烬与算法统治的未来，一个拥有深度情感的机器人被造出来。它隐藏身份，进入人类社会。在经历被欺骗和背叛后，它决定用超越人类的方式拯救世界..." style="width:100%;height:140px;padding:10px;background:var(--bg-primary);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-size:12px;resize:vertical;font-family:inherit;line-height:1.6"></textarea>
          </div>
        </div>

        <!-- 一键生产 -->
        <div style="display:flex;gap:8px">
          <button id="dramaGenerateBtn" onclick="generateDrama()" style="flex:1;padding:12px 20px;background:var(--accent-green);border:none;border-radius:8px;color:#fff;cursor:pointer;font-size:14px;font-weight:600">
            🎬 一键生产短剧
          </button>
          <button onclick="resetDramaStudio()" style="padding:12px 16px;background:var(--bg-hover);border:1px solid var(--border);border-radius:8px;color:var(--text-primary);cursor:pointer;font-size:13px">🗑</button>
        </div>

        <!-- 进度指示 -->
        <div id="dramaProgress" style="display:none;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:12px">
          <div id="dramaProgressText" style="font-size:11px;color:var(--accent-blue);margin-bottom:6px">⏳ 准备中...</div>
          <div style="background:var(--bg-hover);border-radius:4px;height:6px;overflow:hidden">
            <div id="dramaProgressBar" style="width:0%;height:100%;background:var(--accent-blue);border-radius:4px;transition:width 0.3s"></div>
          </div>
          <div id="dramaProgressSteps" style="font-size:10px;color:var(--text-muted);margin-top:6px"></div>
        </div>
      </div>

      <!-- ===== 中栏: 分镜预览 ===== -->
      <div id="dramaCenterPanel" style="display:flex;flex-direction:column;gap:10px;overflow-y:auto;max-height:calc(100vh - 200px)">
        <!-- 分镜列表工具栏 -->
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <span style="font-size:12px;color:var(--text-muted);font-weight:600">🎞️ 分镜列表 (<span id="dramaShotCountDisplay">0</span>)</span>
          <button onclick="addDramaShot()" style="padding:4px 12px;background:var(--bg-hover);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);cursor:pointer;font-size:11px">+ 添加镜头</button>
          <span style="flex:1"></span>
          <select id="dramaFilterScene" onchange="filterDramaShots()" style="padding:4px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px">
            <option value="all">全部场景</option>
          </select>
        </div>

        <!-- 分镜网格预览 -->
        <div id="dramaShotGrid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px;overflow-y:auto;flex:1">
          <div style="grid-column:1/-1;text-align:center;padding:40px 20px;color:var(--text-muted);font-size:12px">
            <div style="font-size:48px;margin-bottom:12px">🎬</div>
            <p>配置短剧参数后点击"一键生产"生成分镜</p>
            <p style="font-size:10px;margin-top:4px">或手动添加镜头开始创作</p>
          </div>
        </div>
      </div>

      <!-- ===== 右栏: 属性编辑 ===== -->
      <div id="dramaRightPanel" style="display:flex;flex-direction:column;gap:10px;overflow-y:auto;max-height:calc(100vh - 200px)">
        <div class="panel">
          <div class="panel-header"><span>🔍 镜头属性</span></div>
          <div class="panel-body" id="dramaShotEditor" style="display:flex;flex-direction:column;gap:8px">
            <div style="text-align:center;padding:40px 20px;color:var(--text-muted);font-size:12px">
              <div style="font-size:48px;margin-bottom:12px">👆</div>
              <p>点击左侧分镜卡片<br>查看和编辑属性</p>
            </div>
          </div>
        </div>

        <!-- 导出/状态 -->
        <div class="panel">
          <div class="panel-header"><span>📊 项目状态</span></div>
          <div class="panel-body" id="dramaStatusPanel" style="font-size:11px;color:var(--text-muted);line-height:1.8">
            <div>📋 集数: <strong id="dramaStatEpisodes">1</strong></div>
            <div>👥 角色: <strong id="dramaStatChars">2</strong></div>
            <div>🎞️ 镜头: <strong id="dramaStatShots">0</strong></div>
            <div>⏱ 总时长: <strong id="dramaStatDuration">0s</strong></div>
            <div style="margin-top:6px;padding-top:6px;border-top:1px solid var(--border)">
              <span id="dramaPhaseStatus">⚪ 就绪</span>
            </div>
          </div>
        </div>
      </div>
    </div>`;
}

/* ============================================================
   角色管理
   ============================================================ */
function renderDramaCharacterCards() {
  return DRAMA_CHARACTERS.map((ch, i) => `
    <div style="background:var(--bg-primary);border:1px solid var(--border);border-radius:6px;padding:8px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
        <strong style="font-size:12px;color:var(--text-primary)">${ch.name}</strong>
        ${DRAMA_CHARACTERS.length > 1 ? `<button onclick="removeDramaCharacter('${ch.id}')" style="padding:1px 6px;background:none;border:none;color:var(--accent-red);cursor:pointer;font-size:14px">&times;</button>` : ''}
      </div>
      <input value="${escAttr(ch.name)}" onchange="updateDramaCharacter('${ch.id}','name',this.value)" placeholder="名称" style="width:100%;padding:5px 8px;margin-bottom:4px;background:var(--bg-primary);border:1px solid var(--border);border-radius:3px;color:var(--text-primary);font-size:11px">
      <input value="${escAttr(ch.description)}" onchange="updateDramaCharacter('${ch.id}','description',this.value)" placeholder="性格描述" style="width:100%;padding:5px 8px;margin-bottom:4px;background:var(--bg-primary);border:1px solid var(--border);border-radius:3px;color:var(--text-primary);font-size:11px">
      <input value="${escAttr(ch.appearance)}" onchange="updateDramaCharacter('${ch.id}','appearance',this.value)" placeholder="外貌特征" style="width:100%;padding:5px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:3px;color:var(--text-primary);font-size:11px">
    </div>
  `).join('');
}

function escAttr(s) { return (s || '').replace(/"/g, '&quot;').replace(/</g, '&lt;'); }

function addDramaCharacter() {
  const id = 'c' + (DRAMA_CHARACTERS.length + 1);
  DRAMA_CHARACTERS.push({ id, name: '角色' + (DRAMA_CHARACTERS.length+1), description: '', appearance: '' });
  refreshCharacterList();
}

function removeDramaCharacter(id) {
  DRAMA_CHARACTERS = DRAMA_CHARACTERS.filter(c => c.id !== id);
  refreshCharacterList();
}

function updateDramaCharacter(id, field, value) {
  const ch = DRAMA_CHARACTERS.find(c => c.id === id);
  if (ch) ch[field] = value;
}

function refreshCharacterList() {
  const list = $('dramaCharactersList');
  const count = $('dramaCharCount');
  if (list) list.innerHTML = renderDramaCharacterCards();
  if (count) count.textContent = DRAMA_CHARACTERS.length;
  updateStatusPanel();
}

/* ============================================================
   分镜管理
   ============================================================ */
function addDramaShot() {
  const num = DRAMA_SHOTS.length + 1;
  DRAMA_SHOTS.push({
    id: 's' + num,
    shot_number: num,
    scene_id: 'scene_custom',
    character_actions: '',
    narration: '第' + num + '镜',
    dialogue: '',
    camera_angle: 'medium',
    camera_movement: 'static',
    duration: parseFloat($('dramaShotDuration')?.value) || 5,
    transition: 'cut',
    visual_style: '',
    bgm_cue: '',
    sound_effects: '',
    generated_video_path: '',
  });
  renderShotGrid();
  updateStatusPanel();
}

function removeDramaShot(id) {
  DRAMA_SHOTS = DRAMA_SHOTS.filter(s => s.id !== id);
  if (DRAMA_ACTIVE_SHOT === id) DRAMA_ACTIVE_SHOT = null;
  renderShotGrid();
  renderShotEditor();
  updateStatusPanel();
}

function selectDramaShot(id) {
  DRAMA_ACTIVE_SHOT = id;
  renderShotGrid();
  renderShotEditor();
}

function updateShotProperty(id, field, value) {
  const shot = DRAMA_SHOTS.find(s => s.id === id);
  if (shot) {
    if (field === 'duration') value = parseFloat(value) || 5;
    shot[field] = value;
    updateStatusPanel();
  }
}

function renderShotGrid() {
  const grid = $('dramaShotGrid');
  const countEl = $('dramaShotCountDisplay');
  if (!grid) return;
  if (countEl) countEl.textContent = DRAMA_SHOTS.length;

  if (DRAMA_SHOTS.length === 0) {
    grid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:40px 20px;color:var(--text-muted);font-size:12px">
      <div style="font-size:48px;margin-bottom:12px">🎬</div>
      <p>配置短剧参数后点击"一键生产"生成分镜</p>
      <p style="font-size:10px;margin-top:4px">或手动添加镜头开始创作</p>
    </div>`;
    return;
  }

  const cameraIcons = { close: '🔍', medium: '📷', wide: '🌄', bird: '🦅', low: '📐', dutch: '🌀' };
  const transitionIcons = { cut: '✂️', fade: '🌫️', dissolve: '💫', wipe: '🧹', zoom: '🔎' };

  grid.innerHTML = DRAMA_SHOTS.map(s => {
    const active = s.id === DRAMA_ACTIVE_SHOT;
    const border = active ? '2px solid var(--accent-blue)' : '1px solid var(--border)';
    const bg = active ? 'var(--bg-hover)' : 'var(--bg-card)';
    return `
    <div onclick="selectDramaShot('${s.id}')" style="background:${bg};border:${border};border-radius:8px;padding:10px;cursor:pointer;transition:all 0.15s;position:relative">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-size:10px;color:var(--accent-blue);font-weight:600">#${s.shot_number}</span>
        <span style="font-size:16px">${cameraIcons[s.camera_angle] || '📷'}</span>
        <button onclick="event.stopPropagation();removeDramaShot('${s.id}')" style="padding:1px 4px;background:none;border:none;color:var(--accent-red);cursor:pointer;font-size:12px;opacity:0.6">&times;</button>
      </div>
      <div style="font-size:11px;color:var(--text-primary);font-weight:500;margin-bottom:4px;line-height:1.4">${s.narration || '第'+s.shot_number+'镜'}</div>
      <div style="font-size:10px;color:var(--text-muted);margin-bottom:4px">${s.character_actions || '未设置动作'}</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <span style="padding:2px 6px;background:var(--bg-primary);border-radius:8px;font-size:9px;color:var(--text-muted)">${transitionIcons[s.transition] || ''} ${s.transition}</span>
        <span style="padding:2px 6px;background:var(--bg-primary);border-radius:8px;font-size:9px;color:var(--text-muted)">⏱ ${s.duration}s</span>
      </div>
      ${s.generated_video_path ? `<div style="margin-top:6px;font-size:9px;color:var(--accent-green)">✅ 已生成</div>` : ''}
    </div>`;
  }).join('');

  renderShotEditor();
}

function filterDramaShots() {
  const scene = $('dramaFilterScene')?.value || 'all';
  const grid = $('dramaShotGrid');
  if (!grid) return;
  const cards = grid.querySelectorAll('div[onclick]');
  cards.forEach(card => {
    const shotId = card.getAttribute('onclick')?.match(/'([^']+)'/)?.[1];
    const shot = DRAMA_SHOTS.find(s => s.id === shotId);
    if (!shot) { card.style.display = 'block'; return; }
    card.style.display = (scene === 'all' || shot.scene_id === scene) ? 'block' : 'none';
  });
}

/* ============================================================
   镜头属性编辑器 (右栏)
   ============================================================ */
function renderShotEditor() {
  const editor = $('dramaShotEditor');
  if (!editor) return;

  const shot = DRAMA_SHOTS.find(s => s.id === DRAMA_ACTIVE_SHOT);
  if (!shot) {
    editor.innerHTML = `<div style="text-align:center;padding:40px 20px;color:var(--text-muted);font-size:12px">
      <div style="font-size:48px;margin-bottom:12px">👆</div>
      <p>点击左侧分镜卡片<br>查看和编辑属性</p>
    </div>`;
    return;
  }

  editor.innerHTML = `
    <div style="font-size:11px;color:var(--accent-blue);font-weight:600;margin-bottom:4px">镜头 #${shot.shot_number}</div>
    <div>
      <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">场景ID</label>
      <input value="${escAttr(shot.scene_id)}" onchange="updateShotProperty('${shot.id}','scene_id',this.value)" style="width:100%;padding:6px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px">
    </div>
    <div>
      <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">旁白</label>
      <input value="${escAttr(shot.narration)}" onchange="updateShotProperty('${shot.id}','narration',this.value)" style="width:100%;padding:6px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px">
    </div>
    <div>
      <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">角色动作</label>
      <input value="${escAttr(shot.character_actions)}" onchange="updateShotProperty('${shot.id}','character_actions',this.value)" style="width:100%;padding:6px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px">
    </div>
    <div>
      <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">对话</label>
      <textarea onchange="updateShotProperty('${shot.id}','dialogue',this.value)" style="width:100%;height:50px;padding:6px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px;resize:vertical;font-family:inherit">${escAttr(shot.dialogue || '')}</textarea>
    </div>
    <div style="display:flex;gap:6px">
      <div style="flex:1">
        <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">镜头角度</label>
        <select onchange="updateShotProperty('${shot.id}','camera_angle',this.value)" style="width:100%;padding:6px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px">
          <option value="close" ${shot.camera_angle==='close'?'selected':''}>🔍 特写</option>
          <option value="medium" ${shot.camera_angle==='medium'?'selected':''}>📷 中景</option>
          <option value="wide" ${shot.camera_angle==='wide'?'selected':''}>🌄 远景</option>
          <option value="bird" ${shot.camera_angle==='bird'?'selected':''}>🦅 鸟瞰</option>
          <option value="low" ${shot.camera_angle==='low'?'selected':''}>📐 仰拍</option>
          <option value="dutch" ${shot.camera_angle==='dutch'?'selected':''}>🌀 倾斜</option>
        </select>
      </div>
      <div style="flex:1">
        <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">镜头运动</label>
        <select onchange="updateShotProperty('${shot.id}','camera_movement',this.value)" style="width:100%;padding:6px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px">
          <option value="static" ${shot.camera_movement==='static'?'selected':''}>📌 固定</option>
          <option value="pan" ${shot.camera_movement==='pan'?'selected':''}>↔️ 横摇</option>
          <option value="tilt" ${shot.camera_movement==='tilt'?'selected':''}>↕️ 纵摇</option>
          <option value="dolly" ${shot.camera_movement==='dolly'?'selected':''}>🚂 推轨</option>
          <option value="zoom" ${shot.camera_movement==='zoom'?'selected':''}>🔍 变焦</option>
          <option value="handheld" ${shot.camera_movement==='handheld'?'selected':''}>🤳 手持</option>
        </select>
      </div>
    </div>
    <div style="display:flex;gap:6px">
      <div style="flex:1">
        <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">转场</label>
        <select onchange="updateShotProperty('${shot.id}','transition',this.value)" style="width:100%;padding:6px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px">
          <option value="cut" ${shot.transition==='cut'?'selected':''}>✂️ 硬切</option>
          <option value="fade" ${shot.transition==='fade'?'selected':''}>🌫️ 淡入淡出</option>
          <option value="dissolve" ${shot.transition==='dissolve'?'selected':''}>💫 叠化</option>
          <option value="wipe" ${shot.transition==='wipe'?'selected':''}>🧹 划像</option>
          <option value="zoom" ${shot.transition==='zoom'?'selected':''}>🔎 缩放转场</option>
        </select>
      </div>
      <div style="flex:1">
        <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">时长(s)</label>
        <input type="number" min="1" max="60" step="0.5" value="${shot.duration}" onchange="updateShotProperty('${shot.id}','duration',this.value)" style="width:100%;padding:6px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px">
      </div>
    </div>
    <div>
      <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">视觉风格</label>
      <input value="${escAttr(shot.visual_style || '')}" onchange="updateShotProperty('${shot.id}','visual_style',this.value)" placeholder="赛博朋克/水墨/写实..." style="width:100%;padding:6px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px">
    </div>
    <div>
      <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">BGM提示</label>
      <input value="${escAttr(shot.bgm_cue || '')}" onchange="updateShotProperty('${shot.id}','bgm_cue',this.value)" placeholder="紧张/温馨/激昂..." style="width:100%;padding:6px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px">
    </div>
    <div>
      <label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:2px">音效</label>
      <input value="${escAttr(shot.sound_effects || '')}" onchange="updateShotProperty('${shot.id}','sound_effects',this.value)" placeholder="脚步声/门响/雨声..." style="width:100%;padding:6px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px">
    </div>
    <button onclick="removeDramaShot('${shot.id}')" style="margin-top:4px;padding:8px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:4px;color:var(--accent-red);cursor:pointer;font-size:12px">🗑 删除此镜头</button>
  `;
}

/* ============================================================
   状态面板更新
   ============================================================ */
function updateStatusPanel() {
  const epEl = $('dramaStatEpisodes');
  const chEl = $('dramaStatChars');
  const shEl = $('dramaStatShots');
  const durEl = $('dramaStatDuration');
  const phaseEl = $('dramaPhaseStatus');

  if (epEl) epEl.textContent = $('dramaEpisodes')?.value || '1';
  if (chEl) chEl.textContent = DRAMA_CHARACTERS.length;
  if (shEl) shEl.textContent = DRAMA_SHOTS.length;
  const totalDur = DRAMA_SHOTS.reduce((sum, s) => sum + (s.duration || 0), 0);
  if (durEl) durEl.textContent = totalDur.toFixed(1) + 's';

  if (phaseEl) {
    if (DRAMA_GENERATING) {
      phaseEl.innerHTML = '<span style="color:var(--accent-blue)">⏳ 生产中...</span>';
    } else if (DRAMA_SHOTS.length > 0) {
      phaseEl.innerHTML = '<span style="color:var(--accent-green)">✅ 已分镜</span>';
    } else {
      phaseEl.innerHTML = '⚪ 就绪';
    }
  }

  // 更新分镜场景筛选器
  const filter = $('dramaFilterScene');
  if (filter) {
    const scenes = [...new Set(DRAMA_SHOTS.map(s => s.scene_id))];
    const currentVal = filter.value;
    filter.innerHTML = '<option value="all">全部场景</option>' +
      scenes.map(s => `<option value="${s}" ${s===currentVal?'selected':''}>${s}</option>`).join('');
  }
}

/* ============================================================
   AI剧本生成
   ============================================================ */
async function generateDramaScript() {
  const title = $('dramaTitle')?.value?.trim() || '未命名短剧';
  const style = $('dramaStyle')?.value || 'modern';
  const styleNames = { modern: '现代都市', ancient: '古装武侠', scifi: '科幻未来', suspense: '悬疑推理', fantasy: '奇幻世界', romance: '浪漫爱情', comedy: '轻松喜剧', horror: '惊悚恐怖' };

  const prompt = `请为一部${styleNames[style] || style}风格的短剧"${title}"创作剧本概要。包含：1)一句话梗概 2)角色介绍 3)三幕结构 4)关键场景描述。角色包括：${DRAMA_CHARACTERS.map(c => c.name + '(' + (c.description || '待定') + ')').join('、')}`;

  const scriptArea = $('dramaScript');
  if (scriptArea) {
    scriptArea.value = '⏳ AI正在生成剧本...';
    scriptArea.style.color = 'var(--accent-blue)';
  }

  try {
    const res = await apiPost('/api/drama/script', {
      title, style, characters: DRAMA_CHARACTERS, prompt
    });

    if (res.success && res.data?.script) {
      if (scriptArea) {
        scriptArea.value = res.data.script;
        scriptArea.style.color = 'var(--text-primary)';
      }
    } else {
      // P2-2-W1: 不再用 fallback 剧本, 失败时显示提示让用户重试
      if (scriptArea) {
        scriptArea.value = '';
        scriptArea.placeholder = '剧本生成失败: ' + (res?.error || '后端暂不可用') + ', 请重试';
      }
      (window.toastError || ((m) => alert(m)))('剧本生成失败: ' + (res?.error || '后端暂不可用'));
    }
  } catch (e) {
    // P2-2-W1: 不再用 fallback 剧本, 真实失败时显示提示
    if (scriptArea) {
      scriptArea.value = '';
      scriptArea.placeholder = '剧本生成异常: ' + (e.message || e) + ', 请重试';
    }
    (window.toastError || ((m) => alert(m)))('剧本生成异常: ' + (e.message || e));
  }
}

function generateFallbackScript(title, style) {
  const chars = DRAMA_CHARACTERS.map(c => `- ${c.name}${c.description ? '：' + c.description : ''}${c.appearance ? '（' + c.appearance + '）' : ''}`).join('\n');
  return `# ${title}

## 一句话梗概
在一个${style}的世界里，${DRAMA_CHARACTERS[0]?.name || '主角'}踏上了一段改变命运的旅程。

## 角色
${chars || '- 主角\n- 配角'}

## 三幕结构
### 第一幕：开场 (25%)
建立世界观和角色关系。${DRAMA_CHARACTERS[0]?.name || '主角'}过着平凡的生活，直到一件意外事件打破了平静。

### 第二幕：冲突发展 (50%)
矛盾升级，${DRAMA_CHARACTERS[0]?.name || '主角'}面临严峻考验。结识盟友，遭遇对手，在两难中成长。

### 第三幕：高潮与结局 (25%)
决战时刻到来，${DRAMA_CHARACTERS[0]?.name || '主角'}做出关键选择。结局意味深长，留下思考空间。

## 关键场景
1. 开场场景 — 展示世界观
2. 激励事件 — 打破常态
3. 中间转折 — 不可回头
4. 低谷场景 — 全盘皆输感
5. 高潮场景 — 正面决战
6. 尾声 — 余韵悠长`;
}

/* ============================================================
   一键生产短剧 (主流程)
   ============================================================ */
async function generateDrama() {
  if (DRAMA_GENERATING) return;

  const title = $('dramaTitle')?.value?.trim();
  if (!title) {
    (window.toastError || ((m) => alert(m)))('请输入短剧名称');
    return;
  }

  const script = $('dramaScript')?.value?.trim();
  if (!script) {
    (window.toastError || ((m) => alert(m)))('请输入剧本或剧情描述');
    return;
  }

  DRAMA_GENERATING = true;
  const btn = $('dramaGenerateBtn');
  if (btn) {
    btn.textContent = '⏳ 生产中...';
    btn.style.opacity = '0.7';
    btn.disabled = true;
  }

  // 显示进度条
  showDramaProgress();

  const phases = [
    { name: '需求理解', key: 'requirement', percent: 10 },
    { name: '剧本生成', key: 'script', percent: 25 },
    { name: '角色锁定', key: 'character', percent: 40 },
    { name: '智能分镜', key: 'storyboard', percent: 55 },
    { name: '逐镜头生成', key: 'shot_gen', percent: 70 },
    { name: '音画同步', key: 'audio', percent: 85 },
    { name: '合成导出', key: 'compose', percent: 95 },
    { name: '质量审计', key: 'review', percent: 100 },
  ];

  const payload = {
    title,
    style: $('dramaStyle')?.value || 'modern',
    episodes: parseInt($('dramaEpisodes')?.value) || 1,
    duration_per_episode: parseInt($('dramaDuration')?.value) || 60,
    shot_count: parseInt($('dramaShotCount')?.value) || 14,
    shot_duration: parseFloat($('dramaShotDuration')?.value) || 5,
    characters: DRAMA_CHARACTERS.map(c => ({
      name: c.name,
      description: c.description,
      appearance: c.appearance,
    })),
    script,
    enable_tts: $('dramaTTS')?.checked ?? true,
  };

  let result = null;
  try {
    // 逐步更新进度
    for (let i = 0; i < phases.length; i++) {
      updateDramaProgress(phases[i].name, phases[i].percent, phases);
      await sleep(300 + Math.random() * 400);
    }

    // 发送API请求
    updateDramaProgress('发送请求到服务器...', 50, phases);
    result = await apiPost('/api/drama/generate', payload);

    if (result.success && result.data) {
      updateDramaProgress('✅ 生成完成', 100, phases);

      // 解析返回的分镜数据
      const data = result.data;
      if (data.shots && data.shots.length > 0) {
        DRAMA_SHOTS = data.shots.map((s, i) => ({
          id: 's' + (i + 1),
          shot_number: s.shot_number || i + 1,
          scene_id: s.scene_id || 'scene_' + (i + 1),
          character_actions: s.character_actions || '',
          narration: s.narration || '第' + (i+1) + '镜',
          dialogue: s.dialogue || '',
          camera_angle: s.camera_angle || 'medium',
          camera_movement: s.camera_movement || 'static',
          duration: s.duration || parseFloat($('dramaShotDuration')?.value) || 5,
          transition: s.transition || 'cut',
          visual_style: s.visual_style || '',
          bgm_cue: s.bgm_cue || '',
          sound_effects: s.sound_effects || '',
          generated_video_path: s.generated_video_path || '',
        }));
      } else if (!data.shots || data.shots.length === 0) {
        // API返回但没有分镜，使用引擎侧默认分镜
        generateDefaultShots();
      }

      renderShotGrid();

      // 显示项目状态
      if (data.title) {
        const titleEl = $('dramaTitle');
        if (titleEl) titleEl.value = data.title;
      }

      // 更新进度面板
      const stepsEl = $('dramaProgressSteps');
      const textEl = $('dramaProgressText');
      if (stepsEl) stepsEl.innerHTML = `
        <div style="color:var(--accent-green)">✅ 短剧 "${data.title || title}" 生产完成</div>
        <div style="margin-top:4px">引擎: ${data.engine || 'drama-engine'} | ${data.scenes || DRAMA_SHOTS.length} 场景 | ${(data.duration || 0).toFixed(1)}s</div>
        ${data.quality_score ? `<div>质量评分: ${data.quality_score} / 100</div>` : ''}
      `;
      if (textEl) { textEl.textContent = '✅ 短剧生产完成！'; textEl.style.color = 'var(--accent-green)'; }

    } else {
      // API失败，生成模拟分镜
      updateDramaProgress('⚠️ API返回异常，使用本地分镜', 100, phases);
      generateDefaultShots();
      renderShotGrid();

      const stepsEl = $('dramaProgressSteps');
      if (stepsEl) stepsEl.innerHTML = `<div style="color:var(--accent-yellow, #eab308)">⚠️ ${result?.error || '服务器未响应'}</div><div style="margin-top:4px;color:var(--text-muted)">已使用本地模拟分镜</div>`;
    }
  } catch (e) {
    // 网络错误，生成模拟分镜
    updateDramaProgress('⚠️ 网络错误，使用本地分镜', 100, phases);
    generateDefaultShots();
    renderShotGrid();

    const stepsEl = $('dramaProgressSteps');
    if (stepsEl) stepsEl.innerHTML = `<div style="color:var(--accent-yellow, #eab308)">⚠️ 网络错误: ${e.message}</div><div style="margin-top:4px;color:var(--text-muted)">已使用本地模拟分镜</div>`;
  }

  updateStatusPanel();

  // 恢复按钮
  DRAMA_GENERATING = false;
  if (btn) {
    btn.textContent = '🎬 一键生产短剧';
    btn.style.opacity = '1';
    btn.disabled = false;
  }

  // 3秒后自动隐藏进度条
  setTimeout(() => {
    const prog = $('dramaProgress');
    if (prog) prog.style.display = 'none';
  }, 5000);
}

function generateDefaultShots() {
  const shotCount = parseInt($('dramaShotCount')?.value) || 14;
  const shotDuration = parseFloat($('dramaShotDuration')?.value) || 5;
  const sceneNames = ['开场', '冲突引入', '发展', '转折', '高潮准备', '高潮', '结局'];
  const sceneDescs = ['建立世界观和角色', '问题出现', '角色应对', '意外事件', '集结力量', '决战/关键对决', '收尾闭环'];
  const cameraOptions = ['wide', 'medium', 'close', 'medium', 'wide', 'close', 'bird'];
  const moveOptions = ['static', 'pan', 'dolly', 'static', 'tilt', 'handheld', 'static'];
  const transitionOptions = ['cut', 'fade', 'cut', 'dissolve', 'cut', 'zoom', 'fade'];

  const shots = [];
  const nScenes = sceneNames.length;
  const shotsPerScene = Math.max(1, Math.floor(shotCount / nScenes));
  const remaining = shotCount - (shotsPerScene * nScenes);

  let num = 0;
  for (let i = 0; i < nScenes; i++) {
    const n = shotsPerScene + (i < remaining ? 1 : 0);
    for (let j = 0; j < n; j++) {
      num++;
      const chars = DRAMA_CHARACTERS;
      const charAction = chars.length > 0
        ? chars[num % chars.length].name + ' ' + sceneDescs[i]
        : sceneDescs[i];

      shots.push({
        id: 's' + num,
        shot_number: num,
        scene_id: 'scene_' + sceneNames[i],
        character_actions: charAction,
        narration: '第' + num + '镜: ' + sceneNames[i],
        dialogue: '',
        camera_angle: cameraOptions[i % cameraOptions.length],
        camera_movement: moveOptions[i % moveOptions.length],
        duration: shotDuration,
        transition: transitionOptions[i % transitionOptions.length],
        visual_style: $('dramaStyle')?.value || 'modern',
        bgm_cue: '',
        sound_effects: '',
        generated_video_path: '',
      });
    }
  }

  DRAMA_SHOTS = shots;
}

/* ============================================================
   进度条控制
   ============================================================ */
function showDramaProgress() {
  const prog = $('dramaProgress');
  if (prog) prog.style.display = 'block';
  const bar = $('dramaProgressBar');
  if (bar) bar.style.width = '0%';
  const text = $('dramaProgressText');
  if (text) { text.textContent = '⏳ 准备中...'; text.style.color = 'var(--accent-blue)'; }
  const steps = $('dramaProgressSteps');
  if (steps) steps.textContent = '';
}

function updateDramaProgress(phaseName, percent, allPhases) {
  const bar = $('dramaProgressBar');
  if (bar) bar.style.width = percent + '%';
  const text = $('dramaProgressText');
  if (text) text.textContent = '⏳ ' + phaseName + ' (' + percent + '%)';

  if (allPhases) {
    const steps = $('dramaProgressSteps');
    if (steps) {
      steps.innerHTML = allPhases.map(p => {
        const done = percent >= p.percent;
        return `<span style="margin-right:12px;color:${done ? 'var(--accent-green)' : 'var(--text-muted)'}">${done ? '✅' : '⏳'} ${p.name}</span>`;
      }).join('');
    }
  }
}

/* ============================================================
   重置
   ============================================================ */
function resetDramaStudio() {
  if (DRAMA_SHOTS.length > 0 && !confirm('确定要重置所有分镜和配置吗？')) return;
  DRAMA_CHARACTERS = [
    { id: 'c1', name: '主角', description: '', appearance: '' },
    { id: 'c2', name: '配角', description: '', appearance: '' }
  ];
  DRAMA_SHOTS = [];
  DRAMA_ACTIVE_SHOT = null;
  DRAMA_GENERATING = false;

  const titleEl = $('dramaTitle');
  const scriptEl = $('dramaScript');
  const episodesEl = $('dramaEpisodes');
  const durationEl = $('dramaDuration');
  const shotCountEl = $('dramaShotCount');
  const shotDurEl = $('dramaShotDuration');
  const progEl = $('dramaProgress');
  const btnEl = $('dramaGenerateBtn');

  if (titleEl) titleEl.value = '未命名短剧';
  if (scriptEl) scriptEl.value = '';
  if (episodesEl) episodesEl.value = '1';
  if (durationEl) durationEl.value = '60';
  if (shotCountEl) shotCountEl.value = '14';
  if (shotDurEl) shotDurEl.value = '5';
  if (progEl) progEl.style.display = 'none';
  if (btnEl) { btnEl.textContent = '🎬 一键生产短剧'; btnEl.style.opacity = '1'; btnEl.disabled = false; }

  refreshCharacterList();
  renderShotGrid();
  renderShotEditor();
  updateStatusPanel();
}

/* 工具 */
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
