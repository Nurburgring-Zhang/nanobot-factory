/* IMDF 审美评分 — 三模型 Ensemble + Elo 排行榜
 * R3-Worker-2 重构 (2026-06-18): 删除硬编码,改 API 驱动 (health/score/elo-ranking/score-batch),含 loading/error/empty 状态
 */
const AC_DIMS = [
  { key: 'composition', label: '构图' }, { key: 'color', label: '色彩' }, { key: 'lighting', label: '光影' },
  { key: 'sharpness', label: '清晰度' }, { key: 'content', label: '内容' }, { key: 'creativity', label: '创意' },
];
const AC_MODELS = [
  { key: 'q_align', name: 'Q-Align (南洋理工)', weight: 45, color: 'green'  },
  { key: 'laion_aesthetic', name: 'LAION V2.5',  weight: 30, color: 'blue'   },
  { key: 'musiq',   name: 'MUSIQ (Google)',     weight: 25, color: 'purple' },
];
const AC_LOADING = '<div class="empty-state"><div class="loading-spinner"></div><div class="empty-state-text">加载中...</div></div>';
const AC_QBAR = (label, color, pct, val) => `<div class="qbar-row"><span class="qbar-label">${label}</span><div class="qbar-track"><div class="qbar-fill ${color}" style="width:${pct}%"></div></div><span class="qbar-val">${val}</span></div>`;
const ac_empty = (icon, text, retry) => `<div class="empty-state"><div class="empty-state-icon">${icon}</div><div class="empty-state-text">${text}</div>${retry?`<button class="btn btn-outline btn-sm" style="margin-top:8px" onclick="${retry}()">🔄 重试</button>`:''}</div>`;
async function renderAestheticCenter() {
  const c = $('page-content'); if (!c) return;
  c.innerHTML = `
    <div class="page-header">
      <div><div class="page-title">⭐ 审美评分</div><div class="page-subtitle">三模型 Ensemble + Elo 排行榜</div></div>
      <div class="page-stats">
        <div class="page-stat"><div class="page-stat-val" id="ac-stat-models">--</div><div class="page-stat-label">可用模型</div></div>
        <div class="page-stat"><div class="page-stat-val" id="ac-stat-elo">--</div><div class="page-stat-label">Elo注册</div></div>
        <div class="page-stat"><div class="page-stat-val" id="ac-stat-srcc">--</div><div class="page-stat-label">最高SRCC</div></div>
      </div>
      <div class="page-actions">
        <button class="btn btn-primary btn-sm" onclick="ac_scoreImage()">📷 评分图片</button>
        <button class="btn btn-outline btn-sm" onclick="ac_batchScore()">📊 批量评分</button>
      </div>
    </div>
    <div class="dashboard-grid">
      <div class="panel"><div class="panel-title">🏆 模型权重分配</div>
        <div class="quality-bars" id="ac-model-bars">${AC_LOADING}</div>
      </div>
      <div class="panel"><div class="panel-title">📐 6维度评分</div>
        <div class="quality-bars" id="ac-dim-bars">${ac_empty('📐', '请上传图片进行评分')}</div>
        <div id="ac-dim-meta" style="display:none;margin-top:10px;font-size:11px;color:var(--text-muted)"></div>
      </div>
      <div class="panel"><div class="panel-title">📈 Elo 排行榜</div>
        <div id="ac-elo-list">${AC_LOADING}</div>
      </div>
    </div>`;
  ac_loadHealth(); ac_loadElo();
}
async function ac_loadHealth() {
  const bars = $('ac-model-bars'); if (!bars) return;
  try {
    const r = await apiGet('/api/aesthetic/health');
    if (!r || !r.success) throw new Error((r && r.error) || 'health endpoint failed');
    const data = r.data || {};
    const sm = data.scoring_methods || {};
    const statModels = $('ac-stat-models');
    if (statModels) statModels.textContent = (data.available_models || 0) + '/' + AC_MODELS.length;
    const statElo = $('ac-stat-elo');
    if (statElo) statElo.textContent = ((data.elo && data.elo.total_entries) || 0);
    // R4-W4-others: 0.885 硬编码 → 真实后端 max_srcc (Q-Align @ SRCC 0.885 来自 aesthetic_engine.py)
    const statSrcc = $('ac-stat-srcc');
    if (statSrcc) {
      const srcc = data.max_srcc;
      statSrcc.textContent = (typeof srcc === 'number' && srcc > 0) ? srcc.toFixed(3) : '—';
    }
    bars.innerHTML = AC_MODELS.map(m => {
      const enabled =
        (m.key === 'q_align'         && (sm.heuristic || sm.llm_vision)) ||
        (m.key === 'laion_aesthetic' && sm.llm_vision) ||
        (m.key === 'musiq'           && sm.llm_vision);
      const tag = enabled
        ? '<span class="tag tag-green"  style="margin-left:6px;font-size:10px">就绪</span>'
        : '<span class="tag tag-orange" style="margin-left:6px;font-size:10px">未启用</span>';
      return AC_QBAR(m.name + tag, m.color, m.weight, m.weight + '%');
    }).join('');
  } catch (e) {
    bars.innerHTML = ac_empty('⚠️', '加载失败: ' + sanitizeHTML(e.message || String(e)), 'ac_loadHealth');
  }
}
async function ac_loadElo() {
  const list = $('ac-elo-list'); if (!list) return;
  try {
    const r = await apiGet('/api/aesthetic/elo-ranking?limit=20');
    if (!r || !r.success) throw new Error((r && r.error) || 'elo endpoint failed');
    const ranking = ((r.data || {}).ranking) || [];
    if (ranking.length === 0) { list.innerHTML = ac_empty('🏆', '评分后自动生成排行'); return; }
    list.innerHTML = ranking.slice(0, 10).map((e, i) => {
      const rating = e.rating || 1500;
      return `<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border-color,#2a2a4a)">
        <span style="min-width:24px;color:var(--text-muted);font-size:12px">#${i+1}</span>
        <span style="flex:1;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${sanitizeHTML(e.image_name || e.image_id || '(匿名)')}</span>
        <span style="font-weight:600;color:var(--accent-color,#5d9fff)">${rating.toFixed(0)}</span>
        <span style="font-size:10px;color:var(--text-muted)">${e.wins||0}W ${e.losses||0}L ${e.draws||0}D</span>
      </div>`;
    }).join('');
  } catch (e) {
    list.innerHTML = ac_empty('⚠️', '加载失败: ' + sanitizeHTML(e.message || String(e)), 'ac_loadElo');
  }
}
async function ac_scoreImage() {
  const path = (prompt('图片路径:') || '').trim();
  if (!path) return showToast('请输入图片路径', 'error');
  const bars = $('ac-dim-bars'); const meta = $('ac-dim-meta');
  if (bars) bars.innerHTML = AC_LOADING.replace('加载中', '评分中,请稍候');
  if (meta) meta.style.display = 'none';
  showGlobalLoading('审美评分中...');
  try {
    const r = await apiPost('/api/aesthetic/score', { image_path: path, use_llm: false });
    hideGlobalLoading();
    if (!r || !r.success) {
      const errMsg = (r && r.error) || '评分失败';
      if (bars) bars.innerHTML = ac_empty('❌', sanitizeHTML(errMsg), 'ac_scoreImage');
      return showToast('评分失败: ' + errMsg, 'error');
    }
    ac_renderDimensions(r.data || {});
    showToast('评分完成: ' + ((r.data && r.data.overall_score) || 0).toFixed(1) + '/10', 'success');
  } catch (e) {
    hideGlobalLoading();
    const msg = (e && e.message) || String(e);
    if (bars) bars.innerHTML = ac_empty('❌', '评分异常: ' + sanitizeHTML(msg), 'ac_scoreImage');
    showToast('评分异常: ' + msg, 'error');
  }
}
function ac_renderDimensions(data) {
  const bars = $('ac-dim-bars'); const meta = $('ac-dim-meta');
  if (!bars) return;
  const dims = data.dimensions || {};
  if (Object.keys(dims).length === 0) { bars.innerHTML = ac_empty('📐', '未返回维度数据'); return; }
  const overall = data.overall_score || 0;
  const confidence = data.confidence || 'low';
  const confColor = confidence === 'high' ? 'green' : confidence === 'medium' ? 'blue' : 'orange';
  const models = (data.models_used || []).join(', ') || '(无)';
  bars.innerHTML = AC_DIMS.map((d, i) => {
    const v = dims[d.key];
    if (typeof v !== 'number') return '';
    const pct = Math.max(0, Math.min(10, v)) * 10;
    const color = i < 2 ? 'green' : i < 4 ? 'blue' : 'purple';
    return AC_QBAR(d.label, color, pct, v.toFixed(1));
  }).join('');
  if (meta) {
    meta.style.display = 'block';
    meta.innerHTML = `<div>综合分: <strong>${overall.toFixed(1)}/10</strong> · 置信度: <span class="tag tag-${confColor}">${confidence}</span> · 模型: ${sanitizeHTML(models)}</div>`;
  }
}
async function ac_batchScore() {
  const path = (prompt('目录路径 (扫描 jpg/jpeg/png/webp/bmp):') || '').trim();
  if (!path) { showToast('请输入目录路径', 'error'); return; }
  showGlobalLoading('批量评分中...');
  try {
    const r = await apiPost('/api/aesthetic/score-batch', { directory: path });
    hideGlobalLoading();
    if (!r || !r.success) { showToast('批量评分失败: ' + ((r && r.error) || 'unknown'), 'error'); return; }
    const summary = ((r.data || {}).summary) || {};
    showToast('批量完成: ' + (summary.scored || 0) + '/' + (summary.total || 0) + ' 成功, 平均分 ' + (summary.avg || 0), 'success');
    ac_loadElo();
  } catch (e) {
    hideGlobalLoading();
    showToast('批量异常: ' + ((e && e.message) || String(e)), 'error');
  }
}
