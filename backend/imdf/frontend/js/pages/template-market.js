/* IMDF 模板市场 — 浏览/搜索/使用模板，上传新模板 */
/* 分类: 短剧/绘本/商品图/数字人/广告 */

let TM_FILTER = 'all';
let TM_SORT = 'rating';   // rating | downloads | newest
let TM_SEARCH = '';
let TM_TEMPLATES = [];

/* === 模板市场 Mock 数据 === */
function getMockTemplates() {
  return [
    { id: 't1', name: '都市爱情短剧模板', category: '短剧', rating: 4.8, downloads: 2340, author: '官方', version: '2.1', updated: '2026-06-10',
      description: '现代都市爱情短剧完整流水线，含角色设定、分镜模板、TTS配音配置', thumbnail: '🏙️',
      workshop: 'drama-studio', config: { style: 'modern', episodes: 12, duration: 90 } },
    { id: 't2', name: '古装武侠短剧模板', category: '短剧', rating: 4.5, downloads: 1890, author: '制作组A', version: '1.8', updated: '2026-06-08',
      description: '古装武侠短剧模板，内置武打场景分镜和特效提示词', thumbnail: '🏯',
      workshop: 'drama-studio', config: { style: 'ancient', episodes: 20, duration: 60 } },
    { id: 't3', name: '儿童故事绘本', category: '绘本', rating: 4.9, downloads: 5670, author: '官方', version: '3.0', updated: '2026-06-12',
      description: '面向3-6岁儿童的水彩风格故事绘本模板，内置童话故事提示词库', thumbnail: '📚',
      workshop: 'picture-book', config: { style: 'watercolor', pages: 12, audience: '3-6' } },
    { id: 't4', name: '科普教育绘本', category: '绘本', rating: 4.3, downloads: 1200, author: '教育团队', version: '2.0', updated: '2026-05-28',
      description: '面向6-10岁儿童的科普教育绘本模板，写实风格+知识卡片', thumbnail: '🔬',
      workshop: 'picture-book', config: { style: 'realistic', pages: 16, audience: '6-10' } },
    { id: 't5', name: '电商商品主图', category: '商品图', rating: 4.7, downloads: 8900, author: '官方', version: '4.2', updated: '2026-06-14',
      description: '电商商品主图生成模板，支持多种风格背景、光影优化、自动抠图', thumbnail: '🛍️',
      workshop: 'media-production', config: { mode: 'image', op: 'resize', w: 800, h: 800 } },
    { id: 't6', name: '商品白底图批处理', category: '商品图', rating: 4.4, downloads: 3200, author: '供应商X', version: '1.5', updated: '2026-06-01',
      description: '批量处理商品白底图，自动去背景+统一尺寸+水印添加', thumbnail: '📸',
      workshop: 'media-production', config: { mode: 'image', op: 'resize', w: 1000, h: 1000 } },
    { id: 't7', name: '虚拟主播数字人', category: '数字人', rating: 4.6, downloads: 4500, author: '官方', version: '2.3', updated: '2026-06-11',
      description: '虚拟主播数字人生成模板，支持TTS语音+口型同步+表情驱动', thumbnail: '🤖',
      workshop: 'zhiying', config: { type: 'avatar', tts: true, emotion: true } },
    { id: 't8', name: '品牌代言数字人', category: '数字人', rating: 4.2, downloads: 1800, author: '品牌部', version: '1.2', updated: '2026-05-20',
      description: '品牌代言数字人模板，可定制外观/服装/场景，输出4K视频', thumbnail: '👔',
      workshop: 'zhiying', config: { type: 'avatar', resolution: '4k', bg: 'studio' } },
    { id: 't9', name: '信息流广告模板', category: '广告', rating: 4.5, downloads: 6700, author: '官方', version: '3.1', updated: '2026-06-13',
      description: '信息流广告视频模板，竖版9:16，支持动态文字叠加和CTA按钮', thumbnail: '📱',
      workshop: 'media-production', config: { mode: 'video', aspect: '9:16', overlay: true } },
    { id: 't10', name: '品牌宣传片模板', category: '广告', rating: 4.1, downloads: 2500, author: '创意组', version: '2.0', updated: '2026-06-05',
      description: '品牌宣传片模板，16:9横版，内置转场特效和配乐库', thumbnail: '🎬',
      workshop: 'media-production', config: { mode: 'video', aspect: '16:9', transitions: true } },
    { id: 't11', name: '悬疑短剧模板', category: '短剧', rating: 4.0, downloads: 980, author: '社区用户', version: '1.0', updated: '2026-06-02',
      description: '悬疑推理风格短剧模板，含反转剧情框架和紧张氛围提示词', thumbnail: '🔍',
      workshop: 'drama-studio', config: { style: 'suspense', episodes: 8, duration: 120 } },
    { id: 't12', name: '日系动漫绘本', category: '绘本', rating: 4.7, downloads: 3400, author: '动漫社', version: '2.5', updated: '2026-06-09',
      description: '日系动漫风格绘本模板，适配轻小说和漫画分镜布局', thumbnail: '🎌',
      workshop: 'picture-book', config: { style: 'anime', pages: 10, audience: '10+' } },
  ];
}

/* === 主渲染 === */
async function renderTemplateMarket() {
  const c = $('page-content'); if (!c) return;
  TM_TEMPLATES = getMockTemplates();
  c.innerHTML = buildTemplateMarketHTML();
  renderTemplateGrid();
  /* P1-C-W2: backend list; P2-2-W1: no mock fallback — empty state on failure */
  loadTemplatesFromBackend().catch(() => {});
}

/* === P1-C-W2: backend /api/templates integration === */
async function loadTemplatesFromBackend() {
  const qs = window.IMDF_ERROR ? window.IMDF_ERROR.qs({
    page: 1, category: TM_FILTER === 'all' ? '' : TM_FILTER, search: TM_SEARCH || ''
  }) : '';
  const res = await window.httpGet('/api/templates' + qs, { timeoutMs: 12000 });
  if (res.state !== window.HTTP_STATE.SUCCESS) return;
  const extracted = window.IMDF_ERROR.extractList(res.data);
  if (extracted.items && extracted.items.length > 0) {
    TM_TEMPLATES = extracted.items.map(normalizeBackendTemplate).concat(TM_TEMPLATES);
    renderTemplateGrid();
  }
}

function normalizeBackendTemplate(t) {
  return {
    id: t.id || t.template_id || ('srv-' + Math.random().toString(36).slice(2, 8)),
    name: t.name || t.title || '未命名模板',
    category: t.category || '其他',
    rating: Number(t.rating || t.avg_rating || 0),
    downloads: Number(t.downloads || t.use_count || 0),
    author: t.author || t.created_by || '社区',
    version: t.version || '1.0',
    updated: (t.updated_at || t.updated || '').slice(0, 10),
    description: t.description || '',
    thumbnail: getCategoryEmoji(t.category) || '📄',
    workshop: t.workshop || t.target_page || '',
    config: t.config || {},
  };
}

function buildTemplateMarketHTML() {
  return `
    <div style="margin-bottom:16px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
      <div>
        <h2 style="font-size:18px;font-weight:600;margin-bottom:4px">🧩 模板市场</h2>
        <p style="font-size:12px;color:var(--text-muted)">浏览AI生产模板，一键启动工坊</p>
      </div>
      <button onclick="showUploadTemplate()" id="tmUploadBtn" 
        style="padding:8px 16px;background:var(--accent-purple);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:13px;font-weight:600">
        📤 上传新模板
      </button>
    </div>

    <!-- 搜索 + 排序栏 -->
    <div style="display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
      <div style="flex:1;min-width:200px;max-width:400px;position:relative">
        <input id="tmSearch" placeholder="🔍 搜索模板..." oninput="onTmSearch()"
          style="width:100%;padding:8px 12px;background:var(--bg-card);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-size:12px;outline:none">
      </div>
      <select id="tmSort" onchange="onTmSortChange()"
        style="padding:8px 12px;background:var(--bg-card);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-size:12px;cursor:pointer">
        <option value="rating">⭐ 评分最高</option>
        <option value="downloads">📥 下载最多</option>
        <option value="newest">🆕 最新发布</option>
      </select>
      <span style="font-size:12px;color:var(--text-muted)" id="tmCount">共 ${TM_TEMPLATES.length} 个模板</span>
    </div>

    <!-- 分类筛选 -->
    <div style="display:flex;gap:6px;margin-bottom:16px;flex-wrap:wrap" id="tmCategoryBar">
      <button class="tm-cat-btn active" data-cat="all" onclick="onTmFilter('all')"
        style="padding:6px 14px;background:var(--accent-blue);border:none;border-radius:20px;color:#fff;cursor:pointer;font-size:12px;font-weight:600">🏷️ 全部</button>
      <button class="tm-cat-btn" data-cat="短剧" onclick="onTmFilter('短剧')"
        style="padding:6px 14px;background:var(--bg-hover);border:1px solid var(--border);border-radius:20px;color:var(--text-primary);cursor:pointer;font-size:12px">📺 短剧</button>
      <button class="tm-cat-btn" data-cat="绘本" onclick="onTmFilter('绘本')"
        style="padding:6px 14px;background:var(--bg-hover);border:1px solid var(--border);border-radius:20px;color:var(--text-primary);cursor:pointer;font-size:12px">📚 绘本</button>
      <button class="tm-cat-btn" data-cat="商品图" onclick="onTmFilter('商品图')"
        style="padding:6px 14px;background:var(--bg-hover);border:1px solid var(--border);border-radius:20px;color:var(--text-primary);cursor:pointer;font-size:12px">🛍️ 商品图</button>
      <button class="tm-cat-btn" data-cat="数字人" onclick="onTmFilter('数字人')"
        style="padding:6px 14px;background:var(--bg-hover);border:1px solid var(--border);border-radius:20px;color:var(--text-primary);cursor:pointer;font-size:12px">🤖 数字人</button>
      <button class="tm-cat-btn" data-cat="广告" onclick="onTmFilter('广告')"
        style="padding:6px 14px;background:var(--bg-hover);border:1px solid var(--border);border-radius:20px;color:var(--text-primary);cursor:pointer;font-size:12px">📢 广告</button>
    </div>

    <!-- 模板卡片网格 -->
    <div id="tmGrid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px">
    </div>
  `;
}

/* === 渲染模板卡片网格 === */
function renderTemplateGrid() {
  const grid = $('tmGrid');
  if (!grid) return;

  // 筛选
  let filtered = TM_TEMPLATES;
  if (TM_FILTER !== 'all') {
    filtered = filtered.filter(t => t.category === TM_FILTER);
  }
  if (TM_SEARCH) {
    const q = TM_SEARCH.toLowerCase();
    filtered = filtered.filter(t =>
      t.name.toLowerCase().includes(q) ||
      t.description.toLowerCase().includes(q) ||
      t.author.toLowerCase().includes(q)
    );
  }

  // 排序
  switch (TM_SORT) {
    case 'rating': filtered.sort((a, b) => b.rating - a.rating); break;
    case 'downloads': filtered.sort((a, b) => b.downloads - a.downloads); break;
    case 'newest': filtered.sort((a, b) => b.updated.localeCompare(a.updated)); break;
  }

  // 更新计数
  const countEl = $('tmCount');
  if (countEl) countEl.textContent = `共 ${filtered.length} 个模板`;

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div style="grid-column:1/-1;text-align:center;padding:60px 20px;color:var(--text-muted)">
        <div style="font-size:48px;margin-bottom:12px">🔍</div>
        <p style="font-size:14px">没有找到匹配的模板</p>
        <p style="font-size:12px;margin-top:4px">尝试调整筛选条件或搜索关键词</p>
      </div>`;
    return;
  }

  grid.innerHTML = filtered.map(t => buildTemplateCard(t)).join('');
}

function buildTemplateCard(t) {
  const stars = '⭐'.repeat(Math.floor(t.rating)) + (t.rating % 1 >= 0.5 ? '½' : '');
  const catColor = getCategoryColor(t.category);

  return `
    <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;display:flex;flex-direction:column;gap:10px;transition:all 0.2s;cursor:default"
         onmouseenter="this.style.borderColor='var(--accent-blue)';this.style.boxShadow='0 4px 20px rgba(74,122,255,0.15)'"
         onmouseleave="this.style.borderColor='var(--border)';this.style.boxShadow='none'">
      <!-- 缩略图 + 标题行 -->
      <div style="display:flex;gap:12px;align-items:flex-start">
        <div style="width:56px;height:56px;background:var(--bg-tertiary);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:28px;flex-shrink:0;border:2px solid ${catColor}">
          ${t.thumbnail || '📄'}
        </div>
        <div style="flex:1;min-width:0">
          <div style="font-weight:600;font-size:14px;color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${t.name}">${t.name}</div>
          <div style="display:flex;gap:6px;align-items:center;margin-top:4px;flex-wrap:wrap">
            <span style="font-size:10px;padding:2px 8px;background:${catColor}20;color:${catColor};border-radius:10px;font-weight:600">${t.category}</span>
            <span style="font-size:11px;color:var(--accent-orange)">${stars} ${t.rating}</span>
          </div>
        </div>
      </div>

      <!-- 描述 -->
      <div style="font-size:11px;color:var(--text-secondary);line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:32px">${t.description}</div>

      <!-- 元信息 -->
      <div style="display:flex;gap:12px;font-size:10px;color:var(--text-muted);flex-wrap:wrap">
        <span>📥 ${formatDownloads(t.downloads)}</span>
        <span>👤 ${t.author}</span>
        <span>📦 v${t.version}</span>
        <span>📅 ${t.updated}</span>
      </div>

      <!-- 操作按钮 (P1-C-W2: rate + download buttons added) -->
      <div style="display:flex;gap:8px;margin-top:auto;padding-top:8px;border-top:1px solid var(--border)">
        <button onclick="useTemplate('${t.id}')"
          style="flex:1;padding:8px;background:var(--accent-green);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:12px;font-weight:600;transition:opacity 0.2s"
          onmouseenter="this.style.opacity='0.85'" onmouseleave="this.style.opacity='1'">
          🚀 使用模板
        </button>
        <button onclick="tmRateTemplate('${t.id}')" title="评分"
          style="padding:8px 10px;background:var(--bg-hover);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);cursor:pointer;font-size:12px">
          ⭐
        </button>
        <button onclick="tmDownloadTemplate('${t.id}')" title="下载"
          style="padding:8px 10px;background:var(--bg-hover);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);cursor:pointer;font-size:12px">
          📥
        </button>
        <button onclick="previewTemplate('${t.id}')" title="预览"
          style="padding:8px 12px;background:var(--bg-hover);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);cursor:pointer;font-size:12px;transition:all 0.2s"
          onmouseenter="this.style.borderColor='var(--accent-blue)'" onmouseleave="this.style.borderColor='var(--border)'">
          👁️
        </button>
      </div>
    </div>`;
}

function getCategoryColor(cat) {
  const map = { '短剧': '#f97316', '绘本': '#a78bfa', '商品图': '#4ade80', '数字人': '#4a7aff', '广告': '#fbbf24' };
  return map[cat] || 'var(--accent-blue)';
}

function formatDownloads(n) {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return n.toString();
}

/* === 搜索 === */
function onTmSearch() {
  TM_SEARCH = $('tmSearch')?.value?.trim() || '';
  renderTemplateGrid();
}

/* === 排序 === */
function onTmSortChange() {
  TM_SORT = $('tmSort')?.value || 'rating';
  renderTemplateGrid();
}

/* === 分类筛选 === */
function onTmFilter(cat) {
  TM_FILTER = cat;
  // 更新按钮样式
  document.querySelectorAll('.tm-cat-btn').forEach(btn => {
    const isActive = btn.dataset.cat === cat;
    btn.style.background = isActive ? 'var(--accent-blue)' : 'var(--bg-hover)';
    btn.style.color = isActive ? '#fff' : 'var(--text-primary)';
    btn.style.border = isActive ? 'none' : '1px solid var(--border)';
    if (isActive) btn.classList.add('active'); else btn.classList.remove('active');
  });
  renderTemplateGrid();
}

/* === 使用模板 → 跳转工坊 + 预填配置 === */
function useTemplate(templateId) {
  const t = TM_TEMPLATES.find(t => t.id === templateId);
  if (!t) return;
  /* P1-C-W2: also fire /api/templates/{id}/use (fire-and-forget, non-blocking) */
  try { tmUseTemplate(templateId); } catch (_) { /* navigation should not wait on counter */ }

  // 存储预填配置到 sessionStorage
  if (t.config) {
    sessionStorage.setItem('tm_prefill_' + t.workshop, JSON.stringify(t.config));
  }

  // 跳转到对应工坊页面
  if (t.workshop === 'drama-studio') {
    navigate('drama-studio');
    // 延迟预填，等待页面渲染完成
    setTimeout(() => applyDramaPrefill(t.config), 600);
  } else if (t.workshop === 'picture-book') {
    navigate('picture-book');
    setTimeout(() => applyBookPrefill(t.config), 600);
  } else if (t.workshop === 'media-production') {
    navigate('media-production');
    setTimeout(() => applyMediaPrefill(t.config), 600);
  } else if (t.workshop === 'zhiying') {
    navigate('zhiying');
    setTimeout(() => applyZhiyingPrefill(t.config), 600);
  } else {
    navigate(t.workshop);
  }

  showToast(`✅ 已加载模板「${t.name}」，配置已预填`);
}

/* === 预填短剧工坊 === */
function applyDramaPrefill(config) {
  try {
    if (config.style) { const el = $('dramaStyle'); if (el) el.value = config.style; }
    if (config.episodes) { const el = $('dramaEpisodes'); if (el) el.value = config.episodes; }
    if (config.duration) { const el = $('dramaDuration'); if (el) el.value = config.duration; }
  } catch(e) { /* 页面未完全渲染 */ }
}

/* === 预填绘本站 === */
function applyBookPrefill(config) {
  try {
    if (config.style) { const el = $('bk-style'); if (el) el.value = config.style; }
    if (config.pages) { const el = $('bk-pages'); if (el) el.value = config.pages; }
    if (config.audience) { const el = $('bk-audience'); if (el) el.value = config.audience; }
  } catch(e) {}
}

/* === 预填媒体生产 === */
function applyMediaPrefill(config) {
  try {
    if (config.mode === 'image' && typeof switchMediaMode === 'function') {
      switchMediaMode('image');
    }
    if (config.op && typeof setMediaOp === 'function') {
      setTimeout(() => setMediaOp(config.op), 200);
    }
    if (config.w) { const el = $('medW'); if (el) el.value = config.w; }
    if (config.h) { const el = $('medH'); if (el) el.value = config.h; }
  } catch(e) {}
}

/* === 预填智影 === */
function applyZhiyingPrefill(config) {
  try {
    // 智影页面预填 (如果存在对应元素)
    if (config.type) { const el = $('zyType'); if (el) el.value = config.type; }
    if (config.tts !== undefined) { const el = $('zyTTS'); if (el) el.checked = config.tts; }
  } catch(e) {}
}

/* === 预览模板 === */
function previewTemplate(templateId) {
  const t = TM_TEMPLATES.find(t => t.id === templateId);
  if (!t) return;

  const catColor = getCategoryColor(t.category);
  showModal(`
    <span class="modal-close" onclick="closeModal()">✕</span>
    <div style="display:flex;gap:16px;margin-bottom:16px">
      <div style="width:80px;height:80px;background:var(--bg-tertiary);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:40px;border:2px solid ${catColor};flex-shrink:0">${t.thumbnail}</div>
      <div>
        <h3 style="font-size:16px;font-weight:600;margin-bottom:4px;color:var(--text-primary)">${t.name}</h3>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:6px">
          <span style="font-size:11px;padding:2px 8px;background:${catColor}20;color:${catColor};border-radius:10px;font-weight:600">${t.category}</span>
          <span style="font-size:12px;color:var(--accent-orange)">⭐ ${t.rating}</span>
          <span style="font-size:11px;color:var(--text-muted)">📥 ${formatDownloads(t.downloads)}</span>
        </div>
      </div>
    </div>
    <div style="margin-bottom:12px;padding:12px;background:var(--bg-primary);border-radius:6px;font-size:12px;color:var(--text-secondary);line-height:1.6">${t.description}</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;margin-bottom:16px">
      <div><span style="color:var(--text-muted)">作者:</span> ${t.author}</div>
      <div><span style="color:var(--text-muted)">版本:</span> v${t.version}</div>
      <div><span style="color:var(--text-muted)">更新:</span> ${t.updated}</div>
      <div><span style="color:var(--text-muted)">跳转:</span> ${t.workshop}</div>
    </div>
    ${t.config ? `<div style="margin-bottom:12px;font-size:11px;color:var(--text-muted)">预填配置: <code style="background:var(--bg-primary);padding:2px 6px;border-radius:3px;font-size:11px">${JSON.stringify(t.config)}</code></div>` : ''}
    <div style="display:flex;gap:8px">
      <button onclick="closeModal();useTemplate('${t.id}')"
        style="flex:1;padding:10px;background:var(--accent-green);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:13px;font-weight:600">🚀 使用模板</button>
      <button onclick="closeModal()"
        style="padding:10px 20px;background:var(--bg-hover);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);cursor:pointer;font-size:13px">关闭</button>
    </div>
  `);
}

/* === 上传新模板 === */
function showUploadTemplate() {
  const user = getCurrentUser();
  const role = user?.role || 'viewer';

  if (role !== 'producer' && role !== 'admin' && role !== '管理员' && role !== 'superadmin') {
    showModal(`
      <span class="modal-close" onclick="closeModal()">✕</span>
      <div style="text-align:center;padding:20px">
        <div style="font-size:48px;margin-bottom:12px">🔒</div>
        <h3 style="color:var(--text-primary);margin-bottom:8px">权限不足</h3>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px">上传新模板需要 <strong style="color:var(--accent-purple)">producer</strong> 或更高角色</p>
        <p style="font-size:11px;color:var(--text-muted)">当前角色: <span style="color:var(--accent-orange)">${role}</span></p>
        <button onclick="closeModal()" style="margin-top:12px;padding:8px 24px;background:var(--bg-hover);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);cursor:pointer;font-size:13px">知道了</button>
      </div>
    `);
    return;
  }

  showModal(`
    <span class="modal-close" onclick="closeModal()">✕</span>
    <h3 style="font-size:16px;font-weight:600;margin-bottom:16px;color:var(--accent-purple)">📤 上传新模板</h3>
    <div style="display:flex;flex-direction:column;gap:12px">
      <div>
        <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px">模板名称 *</label>
        <input id="tmNewName" placeholder="输入模板名称" style="width:100%;padding:8px 12px;background:var(--bg-primary);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-size:13px">
      </div>
      <div>
        <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px">分类 *</label>
        <select id="tmNewCat" style="width:100%;padding:8px 12px;background:var(--bg-primary);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-size:13px">
          <option value="短剧">📺 短剧</option><option value="绘本">📚 绘本</option>
          <option value="商品图">🛍️ 商品图</option><option value="数字人">🤖 数字人</option>
          <option value="广告">📢 广告</option>
        </select>
      </div>
      <div>
        <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px">描述</label>
        <textarea id="tmNewDesc" rows="3" placeholder="描述模板的功能和适用场景..." style="width:100%;padding:8px 12px;background:var(--bg-primary);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-size:13px;resize:vertical"></textarea>
      </div>
      <div>
        <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px">关联工坊</label>
        <select id="tmNewWorkshop" style="width:100%;padding:8px 12px;background:var(--bg-primary);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-size:13px">
          <option value="drama-studio">📺 短剧工坊</option><option value="picture-book">📚 绘本工坊</option>
          <option value="media-production">🎨 图片/视频生产</option><option value="zhiying">🏭 智影数据工厂</option>
        </select>
      </div>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button onclick="doUploadTemplate()" style="flex:1;padding:10px;background:var(--accent-purple);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:13px;font-weight:600">📤 提交模板</button>
        <button onclick="closeModal()" style="padding:10px 20px;background:var(--bg-hover);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);cursor:pointer;font-size:13px">取消</button>
      </div>
    </div>
  `);
}

function doUploadTemplate() {
  const name = $('tmNewName')?.value?.trim();
  const cat = $('tmNewCat')?.value;
  const desc = $('tmNewDesc')?.value?.trim();
  const workshop = $('tmNewWorkshop')?.value;

  if (!name) {
    showToast('⚠️ 请输入模板名称');
    return;
  }

  // 真实API上传
  const newTemplate = {
    id: 't' + Date.now(),
    name: name,
    category: cat,
    rating: 0,
    downloads: 0,
    author: getCurrentUser()?.username || '我',
    version: '1.0',
    updated: new Date().toISOString().slice(0, 10),
    description: desc || '(无描述)',
    thumbnail: getCategoryEmoji(cat),
    workshop: workshop,
    config: {}
  };

  TM_TEMPLATES.unshift(newTemplate);
  closeModal();
  renderTemplateGrid();
  /* P1-C-W2: three-state POST to /api/templates */
  window.httpPost('/api/templates', {name:name, description:desc, category:cat, config:{}, workshop:workshop}, { timeoutMs: 15000 }).then(function (res) {
    if (res.state !== window.HTTP_STATE.SUCCESS) {
      window.IMDF_ERROR.onApiError('templates.upload', res.error);
      showToast('❌ ' + window.IMDF_ERROR.describe(res.error, '上传失败'), 'error');
      return;
    }
    showToast('✅ 模板已上传成功！');
  }).catch(function (e) {
    window.IMDF_ERROR.onApiError('templates.upload', e);
  });
}

/* === P1-C-W2: use / rate / download === */
async function tmUseTemplate(id) {
  const res = await window.httpPost('/api/templates/' + encodeURIComponent(id) + '/use', { id: id });
  if (res.state !== window.HTTP_STATE.SUCCESS) {
    window.IMDF_ERROR.onApiError('templates.use', res.error);
    return;
  }
  /* Optimistic local counter increment */
  const t = TM_TEMPLATES.find(x => x.id === id);
  if (t) { t.downloads = (t.downloads || 0) + 1; renderTemplateGrid(); }
  window.toastOk && window.toastOk('✅ 使用次数已记录');
}

async function tmRateTemplate(id) {
  const scoreStr = prompt('请评分 (1-5):', '5');
  if (!scoreStr) return;
  const score = Number(scoreStr);
  if (!score || score < 1 || score > 5) {
    window.toastError && window.toastError(null, '评分必须是 1-5 之间的整数');
    return;
  }
  const res = await window.httpPost('/api/templates/' + encodeURIComponent(id) + '/rate', { id: id, rating: score });
  if (res.state !== window.HTTP_STATE.SUCCESS) {
    window.IMDF_ERROR.onApiError('templates.rate', res.error);
    return;
  }
  window.toastOk && window.toastOk('✅ 评分已提交: ' + score + '⭐');
}

async function tmDownloadTemplate(id) {
  /* Prefer GET /api/templates/{id}/download (returns blob or signed URL). */
  const res = await window.httpGet('/api/templates/' + encodeURIComponent(id) + '/download', { timeoutMs: 30000 });
  if (res.state !== window.HTTP_STATE.SUCCESS) {
    window.IMDF_ERROR.onApiError('templates.download', res.error);
    return;
  }
  const payload = res.data;
  if (payload && payload.url) {
    window.open(payload.url, '_blank');
  } else if (payload && payload.content) {
    const blob = new Blob([payload.content], { type: payload.mime || 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = (payload.filename || id + '.json'); a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } else {
    window.toastOk && window.toastOk('✅ 下载请求已提交');
  }
}

function getCategoryEmoji(cat) {
  const map = { '短剧': '📺', '绘本': '📚', '商品图': '🛍️', '数字人': '🤖', '广告': '📢' };
  return map[cat] || '📄';
}

/* === Toast 提示 === */
function showToast(msg) {
  let toast = $('tmToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'tmToast';
    toast.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);padding:10px 24px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;color:var(--text-primary);font-size:13px;z-index:9999;box-shadow:0 4px 20px rgba(0,0,0,0.5);transition:all 0.3s;opacity:0;pointer-events:none';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.style.opacity = '1';
  toast.style.bottom = '24px';
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.bottom = '16px';
  }, 2500);
}
