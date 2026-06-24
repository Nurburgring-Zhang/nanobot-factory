/* IMDF v3 主应用 — 导航 + 页面路由 */

/* === 页面路由 ===
   说明: 页面渲染器在各自 js/pages/<page>.js 中定义,
   index.html 中按顺序加载这些脚本, 此 dict 在所有脚本之后定义,
   因此可直接引用函数名。函数名遵循 acronym-aware camelCase:
     oss-storage    -> renderOSSStorage
     dam-viewer     -> renderDAMViewer
     llm-training   -> renderLLMTrainingPipeline
     data-viewer    -> renderDataViewer
   若新增页面, 必须 (1) 在 pages/ 中实现函数, (2) 在 index.html 中加载,
   (3) 在此 dict 中登记。
*/
const PAGE_RENDERERS = {
  /* Phase1 核心页面 */
  dashboard: renderDashboard,
  datasets: renderDatasets,
  annotate: renderAnnotate,
  workflow: renderWorkflow,
  tasks: renderTasks,
  team: renderTeam,
  delivery: renderDelivery,
  review: renderReview,
  stats: renderStats,
  pipeline: renderPipeline,
  settings: renderSettings,

  /* PhaseA-F 扩展页面 */
  'data-browser-grid': renderDataBrowserGrid,
  'lifecycle-pipeline': renderLifecyclePipeline,
  'personal-workspace': renderPersonalWorkspace,
  'template-pipeline': renderTemplatePipeline,
  'media-production': renderMediaProduction,
  'llm-training': renderLLMTrainingPipeline,

  /* 创意工坊 */
  zhiying: renderZhiying,
  'drama-studio': renderDramaStudio,
  'data-viewer': renderDataViewer,
  'picture-book': renderPictureBook,
  'dam-viewer': renderDAMViewer,
  'image-editor': renderImageEditor,
  'data-collection': renderDataCollection,
  'eval-review': renderEvalReview,

  /* 模板与质量 */
  'template-market': renderTemplateMarket,

  /* R3 修复 — 10 个 Phase2 页面 (acronym-aware 命名) */
  'oss-storage': renderOSSStorage,
  'audio-tools': renderAudioTools,
  'enhanced-tools': renderEnhancedTools,
  'crowd-platform': renderCrowdPlatform,
  'transfer-center': renderTransferCenter,
  'audit-logs': renderAuditLogs,
  'quality-center': renderQualityCenter,
  'model-manager': renderModelManager,
  'scheduler-center': renderSchedulerCenter,
  'aesthetic-center': renderAestheticCenter,

  /* P1-C-W1 — 5 核心页 API 集成 */
  assets: renderAssets,
  projects: renderProjects,
  users: renderUsers,
};

/* === kebab-case pageId -> camelCase renderer 函数名 ===
   保留已知 acronym 的大写 (OSS / DAM / LLM / API / JSON 等),
   避免 camelCase 转换把 "OSS" 错误地写成 "Oss"。
   这是 R3 修复的核心: navigate() 的旧 fallback 逻辑会把
   'oss-storage' 错误地解析为 window.renderOssStorage,
   而实际函数名是 renderOSSStorage, 导致 fallback 路径死链。
   因此: PAGE_RENDERERS 才是 canonical 查找路径;
   fallback 仅作为防御, 且必须使用本函数统一规则。
*/
const _ACRONYM_SEGMENTS = new Set([
  'oss', 'dam', 'llm', 'api', 'id', 'url', 'json', 'xml',
  'css', 'html', 'fme', 'ai', 'pe', 'sql', 'gpu', 'cpu',
]);
function _toRendererName(pageId) {
  return 'render' + String(pageId).split('-').map(seg => {
    const low = seg.toLowerCase();
    if (_ACRONYM_SEGMENTS.has(low)) return low.toUpperCase();
    return seg.charAt(0).toUpperCase() + seg.slice(1);
  }).join('');
}

/* 页面占位渲染器(Phase2实现) */
function renderPlaceholder(title) {
  return `<div style="text-align:center;padding:80px 20px;color:var(--text-muted)">
    <div style="font-size:48px;margin-bottom:16px">🚧</div>
    <h3 style="margin-bottom:8px;color:var(--text-primary)">${title}</h3>
    <p style="font-size:13px">此功能正在建设中，将在Phase2实现</p>
  </div>`;
}

/* 函数在各自页面文件中定义(pipeline.js, business.js, stats.js, team.js, delivery.js, settings.js, datasets.js, annotate.js)。
   此处不再定义空占位，避免覆盖实际实现。 */
function renderWorkflow() {
  // 画布页面由 canvas.js 处理
  if (typeof renderWorkflowCanvas === 'function') {
    renderWorkflowCanvas();
  }
}

/* === 导航切换 === */
function navigate(page) {
  // 更新导航高亮
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  const navItem = document.querySelector(`.nav-item[data-page="${page}"]`);
  if (navItem) navItem.classList.add('active');

  // Close mobile sidebar on navigate
  const sidebar = document.getElementById('sidebar');
  if (sidebar && sidebar.classList.contains('open')) {
    sidebar.classList.remove('open');
  }

  // 渲染页面 - 带过渡动画
  const pageContent = $('page-content');
  if (pageContent) {
    pageContent.style.opacity = '0';
    pageContent.style.transform = 'translateY(8px)';
  }

  // R3 修复 — 统一 renderer 解析路径:
  //   1) 优先 PAGE_RENDERERS[page] (canonical, 含 acronym-aware 命名)
  //   2) fallback: window[_toRendererName(page)] (acronym-safe camelCase)
  // 旧版有 2 套不一致的转换 (line 85 + line 94), 且都把 'oss' 错误写成 'Oss'。
  let renderer = PAGE_RENDERERS[page];
  if (typeof renderer !== 'function') {
    renderer = window[_toRendererName(page)];
  }

  if (typeof renderer === 'function') {
    renderer();
  } else {
    // 找不到 renderer — 给开发者留可追溯线索, 不静默退化
    const expectedName = _toRendererName(page);
    console.error(
      `[navigate] renderer not found for page "${page}". ` +
      `Expected window.${expectedName}() or PAGE_RENDERERS["${page}"]. ` +
      `Check that pages/${page}.js is loaded in index.html and registered in PAGE_RENDERERS.`
    );
    if (pageContent) {
      pageContent.innerHTML =
        renderPlaceholder(page) +
        `<div style="margin-top:16px;padding:10px;background:var(--bg-hover);border-radius:6px;font-size:12px;color:var(--text-muted);text-align:center">` +
          `<strong style="color:var(--accent-red)">Dev Tip:</strong> ` +
          `页面开发中 (dev: <code>${page}</code>), 请到 <code>index.html</code> 查看进度<br>` +
          `<small>Renderer: <code>${expectedName}</code></small>` +
        `</div>`;
    }
  }
  // 触发淡入动画
  if (pageContent) {
    pageContent.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
    pageContent.style.opacity = '1';
    pageContent.style.transform = 'translateY(0)';
  }
}

/* === 全局搜索 (多模态 F1.14) === */
let searchMode = 'hybrid';  // vector | fts5 | hybrid | images

function setSearchMode(mode) {
  searchMode = mode;
  // Update visual indicator
  const modeBadge = document.getElementById('searchModeBadge');
  if (modeBadge) {
    const labels = { vector: '📊向量', fts5: '📝全文', hybrid: '🔀混合', images: '🖼️图片' };
    modeBadge.textContent = labels[mode] || mode;
  }
}

function cycleSearchMode() {
  const modes = ['hybrid', 'vector', 'fts5'];
  const idx = modes.indexOf(searchMode);
  const next = modes[(idx + 1) % modes.length];
  setSearchMode(next);
}

function globalSearch() {
  const query = document.getElementById('globalSearch')?.value?.trim();
  if (!query) return;

  // Show loading
  showModal(`
    <span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="margin-bottom:12px;color:var(--accent-blue)">🔍 多模态搜索: "${query}"</h4>
    <div id="searchResults" style="color:var(--text-muted);font-size:12px">
      <p>正在搜索... <span class="spinner"></span></p>
    </div>
  `);

  // Call the multimodal search API
  const payload = {
    query: query,
    collection: searchMode === 'images' ? 'image_index' : 'text_index',
    top_k: 20,
    search_type: searchMode
  };

  const endpoint = searchMode === 'images' ? '/api/search/images' :
                   searchMode === 'hybrid' ? '/api/search/hybrid' :
                   '/api/search';

  apiPost(endpoint, payload).then(data => {
    renderSearchResults(query, data, searchMode);
  }).catch(err => {
    const resultsEl = document.getElementById('searchResults');
    if (resultsEl) {
      resultsEl.innerHTML = `<p style="color:var(--accent-red)">搜索失败: ${err.message || err}</p>`;
    }
  });
}

function renderSearchResults(query, data, mode) {
  const container = document.getElementById('searchResults');
  if (!container) return;

  if (!data || !data.success) {
    container.innerHTML = `<p style="color:var(--accent-red)">搜索失败: ${data?.error || '未知错误'}</p>`;
    return;
  }

  const results = data.results || [];
  const total = data.total || results.length;

  if (results.length === 0) {
    container.innerHTML = `
      <p>未找到匹配结果</p>
      <div style="margin-top:12px;padding:8px;background:var(--bg-primary);border-radius:4px">
        <small>搜索模式: <strong>${mode}</strong> | 索引: <strong>${data.collection || '-'}</strong></small>
        <br><small>💡 提示: 尝试切换搜索模式 (右上角搜索栏) 或先索引数据</small>
      </div>
    `;
    return;
  }

  // Build results HTML
  const modeLabels = { vector: '📊向量匹配', fts5: '📝全文匹配', hybrid: '🔀混合排序', images: '🖼️图片匹配' };
  const modeLabel = modeLabels[mode] || mode;

  let html = `
    <div style="margin-bottom:8px;display:flex;justify-content:space-between;align-items:center">
      <span style="color:var(--accent-green);font-size:13px">找到 <strong>${total}</strong> 条结果 (${modeLabel})</span>
      <small style="color:var(--text-muted)">${data.collection || ''}</small>
    </div>
    <div style="max-height:500px;overflow-y:auto">
  `;

  results.forEach((r, i) => {
    const score = r.score != null ? (r.score * 100).toFixed(1) + '%' : '-';
    const preview = (r.preview || r.metadata?.original_text || '').substring(0, 150);
    const source = r.source || mode;
    const typeIcon = r.content_type === 'image' ? '🖼️' : '📄';
    const metadataStr = r.metadata ? Object.entries(r.metadata)
      .filter(([k]) => !['original_text', 'file_path', 'filename'].includes(k))
      .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`)
      .join(' | ').substring(0, 100) : '';

    html += `
      <div style="padding:10px;margin-bottom:6px;background:var(--bg-primary);border-radius:4px;border-left:3px solid var(--accent-blue)">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <span style="font-weight:600;font-size:13px">${typeIcon} ${r.doc_id?.substring(0, 16) || '#' + (i+1)}</span>
          <span style="font-size:11px;color:var(--accent-green);background:rgba(34,197,94,0.1);padding:2px 6px;border-radius:3px">${score}</span>
        </div>
        <div style="font-size:12px;color:var(--text-secondary);line-height:1.4">${preview || '(无预览)'}</div>
        ${metadataStr ? `<div style="font-size:10px;color:var(--text-muted);margin-top:4px">${metadataStr}</div>` : ''}
        <div style="font-size:10px;color:var(--text-muted);margin-top:2px">来源: ${source}</div>
      </div>
    `;
  });

  html += '</div>';

  // Add mode switcher
  html += `
    <div style="margin-top:12px;padding-top:8px;border-top:1px solid var(--border);display:flex;gap:6px;flex-wrap:wrap">
      <small style="color:var(--text-muted)">切换模式:</small>
      <button onclick="setSearchMode('hybrid');closeModal();globalSearchReplay('${query.replace(/'/g, "\\'")}')" 
              style="font-size:11px;padding:4px 8px;border:1px solid var(--border);border-radius:3px;background:${mode==='hybrid'?'var(--accent-blue)':'var(--bg-primary)'};color:${mode==='hybrid'?'#fff':'var(--text-primary)'};cursor:pointer">🔀 混合</button>
      <button onclick="setSearchMode('vector');closeModal();globalSearchReplay('${query.replace(/'/g, "\\'")}')" 
              style="font-size:11px;padding:4px 8px;border:1px solid var(--border);border-radius:3px;background:${mode==='vector'?'var(--accent-blue)':'var(--bg-primary)'};color:${mode==='vector'?'#fff':'var(--text-primary)'};cursor:pointer">📊 向量</button>
      <button onclick="setSearchMode('fts5');closeModal();globalSearchReplay('${query.replace(/'/g, "\\'")}')" 
              style="font-size:11px;padding:4px 8px;border:1px solid var(--border);border-radius:3px;background:${mode==='fts5'?'var(--accent-blue)':'var(--bg-primary)'};color:${mode==='fts5'?'#fff':'var(--text-primary)'};cursor:pointer">📝 全文</button>
    </div>
  `;

  container.innerHTML = html;
}

function globalSearchReplay(query) {
  document.getElementById('globalSearch').value = query;
  globalSearch();
}

/* === 通知 === */
let notifOpen = false;
function showNotifications() {
  const panel = $('notifPanel');
  notifOpen = !notifOpen;
  panel.style.display = notifOpen ? 'block' : 'none';
}
function closeNotif() { $('notifPanel').style.display = 'none'; notifOpen = false; }

/* === 用户菜单 === */
function showUserMenu() {
  const user = getCurrentUser();
  const userName = user?.username || 'admin';
  const userRole = user?.role || '管理员';

  showModal(`
    <span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="margin-bottom:16px;color:var(--accent-blue)">👤 用户</h4>
    <div style="display:grid;gap:8px;font-size:13px">
      <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
        <span style="color:var(--text-muted)">用户名</span><span>${userName}</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
        <span style="color:var(--text-muted)">角色</span><span style="color:var(--accent-blue)">${userRole}</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
        <span style="color:var(--text-muted)">API Key</span><span style="color:var(--accent-blue);cursor:pointer" onclick="showApiKeys()">管理</span>
      </div>
      <button style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);cursor:pointer;margin-top:4px" onclick="closeModal();navigate('settings')">
        ⚙️ 用户设置
      </button>
      <button style="padding:8px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:4px;color:var(--accent-red);cursor:pointer;margin-top:4px" onclick="doLogout()">
        🚪 退出登录
      </button>
    </div>
  `);
}

function doLogout() {
  clearTokens();
  window.location.href = LOGIN_PAGE;
}

function showApiKeys() {
  closeModal();
  showModal(`
    <span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="margin-bottom:12px;color:var(--accent-blue)">🔑 API Key 管理</h4>
    <div id="apiKeyList" style="color:var(--text-muted);font-size:12px">加载中...</div>
  `);
  // 加载API Key列表
  apiGet('/api/v1/api-keys').then(data => {
    const keys = data.data || data.keys || [];
    const list = $('apiKeyList');
    if (list) {
      if (keys.length === 0) {
        list.innerHTML = '<p>暂无API Key</p>';
      } else {
        list.innerHTML = keys.map(k => `
          <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)">
            <span>${k.name || k.key?.slice(0,16) || 'Key'}</span>
            <span style="color:${k.status === 'active' ? 'var(--accent-green)' : 'var(--text-muted)'}">${k.status || 'active'}</span>
          </div>
        `).join('');
      }
      list.innerHTML += '<button style="margin-top:12px;padding:6px 16px;background:var(--accent-blue);border:none;border-radius:4px;color:#fff;cursor:pointer" onclick="closeModal()">+ 创建新Key</button>';
    }
  });
}

/* === 设置页面 === */
function showSettings() {
  navigate('settings');
}

/* === 状态栏自动刷新 === */
async function refreshStatusBar() {
  const [health, monitor] = await Promise.all([
    apiGet('/api/v1/health').catch(() => ({})),
    apiGet('/api/monitor/pipeline').catch(() => ({})),
  ]);
  const s = (id, val) => { const el = $(id); if (el) el.textContent = val; };
  s('sRunning', monitor.running_tasks || 0);
  s('sQueue', monitor.queue_depth || 0);
}

/* === 键盘快捷键 === */
function initKeyboardShortcuts() {
  document.addEventListener('keydown', function(e) {
    // Ctrl+K / Cmd+K: 全局搜索命令面板
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      openGlobalSearchPanel();
      return;
    }
    // Ctrl+N / Cmd+N: 新建数据集
    if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
      e.preventDefault();
      navigate('datasets');
      return;
    }
    // Ctrl+S / Cmd+S: 保存当前页面 (触发页面内保存逻辑)
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      triggerCurrentPageSave();
      return;
    }
    // Esc: 关闭模态 / 搜索面板 / 通知
    if (e.key === 'Escape') {
      closeGlobalSearchPanel();
      closeModal();
      closeNotif();
      return;
    }
  });
}

/* === 命令面板 (Ctrl+K) === */
function openGlobalSearchPanel() {
  // 移除已有面板
  closeGlobalSearchPanel();

  const backdrop = document.createElement('div');
  backdrop.className = 'global-search-backdrop';
  backdrop.id = 'gspBackdrop';
  backdrop.onclick = closeGlobalSearchPanel;

  const panel = document.createElement('div');
  panel.className = 'global-search-panel';
  panel.id = 'gspPanel';
  panel.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
      <span style="font-size:16px">🔍</span>
      <span style="font-weight:600;font-size:14px;color:var(--text-primary)">全局搜索</span>
    </div>
    <input id="gspInput" placeholder="输入关键词搜索数据集、页面、功能..." autofocus>
    <div class="gsp-hint" id="gspHint">
      <span>Ctrl+K 打开搜索</span>
      <span>|</span>
      <span>Ctrl+N 新建数据集</span>
      <span>|</span>
      <span>Ctrl+S 保存</span>
      <span>|</span>
      <span>Esc 关闭</span>
    </div>
  `;

  document.body.appendChild(backdrop);
  document.body.appendChild(panel);

  const input = panel.querySelector('#gspInput');
  input.focus();

  // 实时搜索命令
  input.addEventListener('input', function() {
    const q = this.value.trim().toLowerCase();
    const hint = document.getElementById('gspHint');
    if (q) {
      // 匹配已知页面
      const pages = [
        { id: 'dashboard', label: '📊 今日概览', kw: 'dashboard home 首页 概览' },
        { id: 'datasets', label: '📁 数据集', kw: 'datasets 数据集 data' },
        { id: 'annotate', label: '🏷️ AI标注', kw: 'annotate 标注 annotation' },
        { id: 'workflow', label: '🚀 工作流画布', kw: 'workflow 工作流 canvas 画布' },
        { id: 'tasks', label: '📋 我的任务', kw: 'tasks 任务 task' },
        { id: 'review', label: '📋 审核管理', kw: 'review 审核' },
        { id: 'pipeline', label: '🔧 质量管线', kw: 'pipeline 管线 质量' },
        { id: 'stats', label: '📈 统计分析', kw: 'stats 统计 分析' },
        { id: 'team', label: '👥 团队管理', kw: 'team 团队' },
        { id: 'delivery', label: '📦 交付管理', kw: 'delivery 交付' },
        { id: 'settings', label: '⚙️ 系统设置', kw: 'settings 设置 系统' },
        { id: 'data-browser-grid', label: '🔍 数据浏览器', kw: 'browser 浏览器 数据' },
        { id: 'personal-workspace', label: '👤 个人工作台', kw: 'workspace 个人 工作台' },
        { id: 'media-production', label: '🎨 媒体生产', kw: 'media 媒体 生产' },
        { id: 'template-market', label: '🧩 模板市场', kw: 'template 模板' },
      ];
      const matches = pages.filter(p => p.kw.includes(q) || p.label.includes(q));
      if (matches.length > 0) {
        hint.innerHTML = matches.map(m =>
          `<span style="cursor:pointer;padding:3px 8px;background:var(--bg-hover);border-radius:4px;transition:background 0.15s"
                 onmouseover="this.style.background='var(--accent-blue)';this.style.color='#fff'"
                 onmouseout="this.style.background='var(--bg-hover)';this.style.color=''"
                 onclick="navigate('${m.id}');closeGlobalSearchPanel()">${m.label}</span>`
        ).join('');
      } else {
        // 回退到全局搜索
        hint.innerHTML = '<span>按Enter进行全局搜索</span>';
      }
    } else {
      hint.innerHTML = '<span>Ctrl+K 打开搜索</span> | <span>Ctrl+N 新建</span> | <span>Ctrl+S 保存</span> | <span>Esc 关闭</span>';
    }
  });

  // Enter触发搜索/导航
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      closeGlobalSearchPanel();
      return;
    }
    if (e.key === 'Enter') {
      const q = this.value.trim();
      if (q) {
        const searchEl = document.getElementById('globalSearch');
        if (searchEl) {
          searchEl.value = q;
          closeGlobalSearchPanel();
          globalSearch();
        }
      }
    }
  });
}

function closeGlobalSearchPanel() {
  const backdrop = document.getElementById('gspBackdrop');
  const panel = document.getElementById('gspPanel');
  if (backdrop) backdrop.remove();
  if (panel) panel.remove();
}

function triggerCurrentPageSave() {
  // 尝试调用页面内的保存函数（如果存在）
  const currentPage = document.querySelector('.nav-item.active');
  if (!currentPage) return;
  const page = currentPage.getAttribute('data-page');
  // 根据不同页面触发保存
  if (page === 'workflow' && typeof saveWorkflow === 'function') { saveWorkflow(); }
  else if (page === 'settings' && typeof saveSettings === 'function') { saveSettings(); }
  else if (typeof saveCurrentPage === 'function') { saveCurrentPage(); }
  else {
    // 通用toast提示
    const toast = document.createElement('div');
    toast.className = 'toast toast-success';
    toast.textContent = '💾 已保存';
    document.body.appendChild(toast);
    setTimeout(function() { toast.remove(); }, 2000);
  }
}

/* === 移动端侧边栏切换 === */
function toggleMobileSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (sidebar) {
    sidebar.classList.toggle('open');
  }
}

/* === 初始化 === */
document.addEventListener('DOMContentLoaded', () => {
  // 初始化主题
  initTheme();

  // 初始化键盘快捷键
  initKeyboardShortcuts();

  // Update topbar user name
  const user = getCurrentUser();
  const userNameEl = $('userName');
  if (userNameEl) {
    userNameEl.textContent = user?.username || '未登录';
  }

  // 默认显示首页
  navigate('dashboard');
  // 状态栏每30秒刷新
  refreshStatusBar();
  setInterval(refreshStatusBar, 30000);
});
