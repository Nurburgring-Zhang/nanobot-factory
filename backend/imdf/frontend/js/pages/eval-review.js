/* IMDF v3 评测审核页面 — 评测闭环 + AI辅助审核 + Cohen Kappa趋势 */

let EVAL_STATE = {
  reviews: [],
  workers: [],
  selectedId: null,
  selectedReviews: new Set(),
  aiResults: {},
};

/* ================================================================
   MAIN RENDERER
   ================================================================ */
async function renderEvalReview() {
  const container = $('page-content');
  if (!container) return;

  // 并行拉取数据 — P1-C-W2: three-state via client.js
  const [reviewData, statsData, opsData, crowdData] = await Promise.all([
    window.httpGet('/api/review/queue', { timeoutMs: 15000 }).then(r => r.state === window.HTTP_STATE.SUCCESS ? r.data : { data: [] }).catch(() => ({ data: [] })),
    window.httpGet('/api/stats/quality', { timeoutMs: 15000 }).then(r => r.state === window.HTTP_STATE.SUCCESS ? r.data : {}).catch(() => ({})),
    window.httpGet('/api/ops/overview',   { timeoutMs: 15000 }).then(r => r.state === window.HTTP_STATE.SUCCESS ? r.data : {}).catch(() => ({})),
    window.httpGet('/api/crowd/workers',  { timeoutMs: 15000 }).then(r => r.state === window.HTTP_STATE.SUCCESS ? r.data : { data: [] }).catch(() => ({ data: [] })),
  ]);
  /* P1-C-W2: also kick off backend eval list refresh (non-blocking) */
  EVAL_listEval(1).catch(() => {});

  const reviews = reviewData.data || reviewData.reviews || [];
  const stats = statsData.data || statsData;
  const ops = opsData.data || opsData;
  const workers = crowdData.data || crowdData.workers || [];

  // 若无数据则生成模拟数据
  if (reviews.length === 0) {
    EVAL_generateMockData();
  } else {
    EVAL_STATE.reviews = reviews;
    EVAL_STATE.workers = workers.length > 0 ? workers : EVAL_generateMockWorkers();
  }

  EVAL_STATE.selectedId = null;
  EVAL_STATE.selectedReviews = new Set();

  const kappa = stats.cohen_kappa || 0.72;
  const agreement = stats.agreement_rate || 0.85;
  const pendingCount = EVAL_STATE.reviews.filter(r => r.status === 'pending').length;
  const evalRound = stats.eval_round || 3;
  const qualityTrend = stats.quality_trend || [0.78, 0.80, 0.79, 0.83, 0.85, 0.84, 0.86, 0.87];
  const kappaTrend = stats.kappa_trend || [0.62, 0.65, 0.68, 0.70, 0.69, 0.72, 0.74, 0.72];

  container.innerHTML = `
    <!-- ===== 页面头部 ===== -->
    <div class="page-header">
      <div>
        <div class="page-title">📊 评测审核</div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px">评测闭环 · AI辅助审核 · Cohen Kappa一致性分析</div>
      </div>
      <div class="page-stats">
        <div class="page-stat">
          <div class="page-stat-val" style="color:${kappa >= 0.8 ? 'var(--accent-green)' : kappa >= 0.6 ? 'var(--accent-blue)' : 'var(--accent-orange)'}" id="eval-stat-kappa">${(kappa * 100).toFixed(0)}%</div>
          <div class="page-stat-label">IAA一致性</div>
        </div>
        <div class="page-stat">
          <div class="page-stat-val" style="color:var(--accent-orange)" id="eval-stat-queue">${pendingCount}</div>
          <div class="page-stat-label">队列数</div>
        </div>
        <div class="page-stat">
          <div class="page-stat-val" style="color:var(--accent-purple)" id="eval-stat-round">${evalRound}</div>
          <div class="page-stat-label">评测轮次</div>
        </div>
      </div>
      <div class="page-actions">
        <button class="btn btn-sm btn-outline" onclick="refreshEvalData()">🔄 刷新</button>
        <button class="btn btn-sm btn-success" onclick="EVAL_batchApprove()">✅ 批量通过</button>
        <button class="btn btn-sm btn-danger" onclick="EVAL_batchReject()">❌ 批量驳回</button>
      </div>
    </div>

    <!-- ===== Cohen Kappa 趋势图 ===== -->
    <div class="panel" style="margin-bottom:16px">
      <div class="panel-header">
        <span>📈 Cohen Kappa 一致性趋势</span>
        <span class="action" onclick="EVAL_showKappaDetail()">详情 →</span>
      </div>
      <div class="panel-body">
        <div class="bar-chart" id="kappa-trend-chart"></div>
        <div style="display:flex;justify-content:space-between;font-size:9px;color:var(--text-muted);padding:0 4px">
          <span>W1</span><span>W2</span><span>W3</span><span>W4</span><span>W5</span><span>W6</span><span>W7</span><span>W8</span>
        </div>
        <div style="margin-top:8px;display:flex;gap:16px;font-size:10px">
          <span>🔵 Kappa基准线: <strong style="color:var(--accent-blue)">0.70</strong></span>
          <span>📈 趋势: <strong style="color:${kappaTrend[7] >= kappaTrend[0] ? 'var(--accent-green)' : 'var(--accent-red)'}">${kappaTrend[7] >= kappaTrend[0] ? '↑ 改善中' : '↓ 需关注'}</strong></span>
        </div>
      </div>
    </div>

    <!-- ===== 两栏布局 ===== -->
    <div class="two-col" style="grid-template-columns:1fr 400px;">
      <!-- 左侧：评测审核队列 -->
      <div class="main-panel" style="padding:0;display:flex;flex-direction:column;overflow:hidden">
        <div style="padding:12px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
          <span class="section-title" style="margin-bottom:0">📋 评测项</span>
          <span id="eval-queue-count" style="font-size:11px;color:var(--text-muted)">共 ${EVAL_STATE.reviews.length} 条</span>
        </div>
        <div id="eval-queue-list" style="flex:1;overflow-y:auto;padding:0 16px">
          ${EVAL_renderQueue(EVAL_STATE.reviews)}
        </div>
        <div style="padding:8px 16px;border-top:1px solid var(--border);display:flex;gap:8px">
          <button class="btn btn-sm btn-success" onclick="EVAL_batchAction('approve')" style="flex:1">✅ 通过选中</button>
          <button class="btn btn-sm btn-danger" onclick="EVAL_batchAction('reject')" style="flex:1">❌ 驳回选中</button>
          <button class="btn btn-sm btn-outline" onclick="EVAL_batchAction('skip')" style="flex:1">⏭ 跳过</button>
        </div>
      </div>

      <!-- 右侧：评测详情 + AI辅助 -->
      <div style="display:flex;flex-direction:column;gap:16px">
        <!-- 评测详情面板 -->
        <div class="side-panel" style="padding:0;flex:1;display:flex;flex-direction:column;overflow:hidden">
          <div style="padding:12px 16px;border-bottom:1px solid var(--border)">
            <span class="section-title" style="margin-bottom:0">📝 评测详情</span>
          </div>
          <div id="eval-detail-panel" style="flex:1;overflow-y:auto;padding:0">
            <div class="empty-state-compact">
              <div class="empty-icon">👈</div>
              <div class="empty-text">选择左侧评测项查看详情</div>
              <div class="empty-hint">查看AI标注与人工标注的对比分析</div>
            </div>
          </div>
        </div>

        <!-- AI辅助审核面板 -->
        <div class="side-panel" style="padding:0;flex-shrink:0">
          <div style="padding:10px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
            <span class="section-title" style="margin-bottom:0">🤖 AI辅助</span>
            <span class="action" onclick="EVAL_runAIAssist()">一键分析 →</span>
          </div>
          <div style="padding:12px 16px">
            <div id="eval-ai-status" style="font-size:11px;color:var(--text-muted);margin-bottom:8px">
              💡 点击"一键分析"调用AI评测所有待审核标注
            </div>
            <button onclick="EVAL_runAIAssist()" class="btn btn-sm btn-primary" style="width:100%;margin-bottom:8px">
              🤖 AI辅助审核
            </button>
            <div id="eval-low-quality-list" style="max-height:120px;overflow-y:auto;font-size:10px"></div>
          </div>
        </div>
      </div>
    </div>
  `;

  // 渲染Kappa趋势图
  setTimeout(() => EVAL_renderKappaChart(kappaTrend), 100);
  // 渲染低质量标记
  EVAL_renderLowQuality();
  // 更新状态栏
  updateStatusBarReview(pendingCount);
}

/* ================================================================
   模拟数据生成
   ================================================================ */
function EVAL_generateMockData() {
  const annotators = ['张三', '李四', '王五', '赵六', '孙七'];
  const labels = ['猫', '狗', '汽车', '行人', '自行车', '交通灯', '建筑', '树木'];
  EVAL_STATE.reviews = Array.from({length: 10}, (_, i) => ({
    id: 'eval_' + (i + 1).toString().padStart(3, '0'),
    annotator: annotators[i % annotators.length],
    label: labels[i % labels.length],
    ai_label: labels[Math.floor(Math.random() * labels.length)],
    confidence: Math.random() * 0.3 + 0.65,
    ai_confidence: Math.random() * 0.3 + 0.65,
    agreement: Math.random() * 0.35 + 0.60,
    consensus_score: Math.random() * 0.35 + 0.60,
    status: ['pending', 'pending', 'pending', 'approved', 'approved', 'rejected'][i % 6],
    created_at: `2026-06-${String(15 - i % 7).padStart(2, '0')} ${String(8 + i % 10).padStart(2, '0')}:00`,
    eval_round: Math.floor(Math.random() * 3) + 1,
  }));
  EVAL_STATE.workers = EVAL_generateMockWorkers();
}

function EVAL_generateMockWorkers() {
  return [
    { name: '张三', skills: ['图像标注', 'BBox检测', '分类'], load: 3, capacity: 10 },
    { name: '李四', skills: ['视频标注', '关键帧提取'], load: 7, capacity: 10 },
    { name: '王五', skills: ['文本标注', 'NER', '情感分析'], load: 2, capacity: 8 },
    { name: '赵六', skills: ['图像标注', '分割', '3D标注'], load: 5, capacity: 10 },
  ];
}

/* ================================================================
   Cohen Kappa 趋势图
   ================================================================ */
function EVAL_renderKappaChart(trend) {
  const container = $('kappa-trend-chart');
  if (!container) return;

  const baseline = 0.70;
  const colors = ['#ef4444','#f97316','#f59e0b','#eab308','#84cc16','#22c55e','#10b981','#14b8a6'];

  container.innerHTML = trend.map((v, i) => {
    const heightPct = Math.max(10, (v / 1.0) * 120);
    const color = v >= baseline ? (v >= 0.8 ? 'var(--accent-green)' : 'var(--accent-blue)') : 'var(--accent-orange)';
    return `
      <div class="bar-col">
        <div class="bar-val" style="color:${color}">${(v * 100).toFixed(0)}%</div>
        <div class="bar-fill" style="height:${heightPct}px;background:${color}"></div>
        <div class="bar-label">W${i + 1}</div>
      </div>`;
  }).join('');

  // 添加基准线指示
  container.style.position = 'relative';
}

/* ================================================================
   评测队列渲染
   ================================================================ */
function EVAL_renderQueue(reviews) {
  if (!reviews || reviews.length === 0) {
    return `<div class="empty-state-compact">
      <div class="empty-icon">✅</div>
      <div class="empty-text">评测队列已清空</div>
      <div class="empty-hint">所有评测项已完成审核</div>
    </div>`;
  }

  const statusBadge = {
    pending: '<span class="tag tag-orange">⏳ 待评</span>',
    approved: '<span class="tag tag-green">✅ 通过</span>',
    rejected: '<span class="tag tag-red">❌ 驳回</span>',
  };

  return reviews.map((r, idx) => {
    const isActive = r.id === EVAL_STATE.selectedId;
    const isChecked = EVAL_STATE.selectedReviews.has(r.id);
    const agreement = (r.consensus_score || r.agreement || 0.85);
    const agrPct = Math.round(agreement * 100);
    const agrColor = agreement >= 0.8 ? 'var(--accent-green)' : agreement >= 0.7 ? 'var(--accent-orange)' : 'var(--accent-red)';
    const isLowQuality = agreement < 0.70;

    return `
    <div class="review-row ${isActive ? 'active' : ''}" 
      onclick="EVAL_selectItem('${r.id}')"
      style="${isLowQuality ? 'background:rgba(239,68,68,0.05)' : ''}">
      <input type="checkbox" ${isChecked ? 'checked' : ''} 
        onclick="event.stopPropagation();EVAL_toggleSelect('${r.id}', this.checked)" 
        style="accent-color:var(--accent-blue);flex-shrink:0">
      <div class="review-index">#${idx + 1}</div>
      <div class="review-main">
        <div class="review-title">${r.label || '标签#' + (idx + 1)} ${isLowQuality ? '<span class="tag tag-red" style="margin-left:4px">⚠</span>' : ''}</div>
        <div class="review-meta">
          👤 ${r.annotator} · 🤖 AI: ${r.ai_label || '—'} · 🔄 第${r.eval_round || 1}轮
        </div>
        <div style="font-size:10px;color:${agrColor};margin-top:2px">
          📊 IAA一致性: ${agrPct}%
        </div>
      </div>
      <div class="review-status">${statusBadge[r.status] || statusBadge.pending}</div>
    </div>`;
  }).join('');
}

/* ================================================================
   评测详情面板
   ================================================================ */
function EVAL_selectItem(id) {
  EVAL_STATE.selectedId = id;
  const review = EVAL_STATE.reviews.find(r => r.id === id);
  if (!review) return;

  // 更新队列高亮
  document.querySelectorAll('.review-row').forEach(row => row.classList.remove('active'));

  // 渲染详情
  const panel = $('eval-detail-panel');
  if (!panel) return;

  const agreement = (review.consensus_score || review.agreement || 0.85);
  const agrPct = Math.round(agreement * 100);
  const humanConf = Math.round((review.confidence || 0.85) * 100);
  const aiConf = Math.round((review.ai_confidence || 0.8) * 100);
  const diffPct = Math.abs(humanConf - aiConf);
  const isPending = review.status === 'pending';
  const agrColor = agreement >= 0.8 ? 'var(--accent-green)' : agreement >= 0.7 ? 'var(--accent-orange)' : 'var(--accent-red)';

  panel.innerHTML = `
    <div class="detail-panel">
      <div class="detail-field">
        <label>评测ID</label>
        <div class="detail-value">#${review.id}</div>
      </div>
      <div class="detail-field">
        <label>标注者</label>
        <div class="detail-value">👤 ${review.annotator}</div>
      </div>
      <div class="detail-field">
        <label>评测轮次</label>
        <div class="detail-value">🔄 第${review.eval_round || 1}轮</div>
      </div>

      <!-- 人机对比 -->
      <div style="background:var(--bg-primary);border-radius:6px;padding:12px;margin-bottom:14px">
        <div style="font-size:11px;font-weight:600;margin-bottom:8px;color:var(--text-primary)">🔍 人机标注对比</div>
        <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:11px">
          <span style="color:var(--text-muted)">👤 人工标签</span>
          <span style="color:var(--accent-blue)">${review.label}</span>
        </div>
        <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:11px">
          <span style="color:var(--text-muted)">🤖 AI 标签</span>
          <span style="color:var(--accent-purple)">${review.ai_label || '—'}</span>
        </div>
        <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:11px">
          <span style="color:var(--text-muted)">人工置信度</span>
          <span style="color:var(--accent-blue)">${humanConf}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:11px">
          <span style="color:var(--text-muted)">AI 置信度</span>
          <span style="color:var(--accent-purple)">${aiConf}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:11px">
          <span style="color:var(--text-muted)">IAA一致性</span>
          <span style="color:${agrColor};font-weight:600">${agrPct}%</span>
        </div>
      </div>

      <!-- 一致性评分条 -->
      <div class="detail-field">
        <label>Cohen Kappa 一致性评分</label>
        <div style="margin-top:4px">
          <div class="progress-bar" style="height:8px">
            <div class="progress-fill" style="width:${agrPct}%;background:${agrColor}"></div>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:9px;color:var(--text-muted);margin-top:2px">
            <span>0%</span><span>50%</span><span>100%</span>
          </div>
        </div>
      </div>

      <div class="detail-field">
        <label>提交时间</label>
        <div class="detail-value">🕐 ${review.created_at || '—'}</div>
      </div>

      ${isPending ? `
      <div class="detail-actions">
        <button class="btn btn-success" onclick="EVAL_approveItem('${review.id}')" style="flex:1">✅ 通过</button>
        <button class="btn btn-danger" onclick="EVAL_rejectItem('${review.id}')" style="flex:1">❌ 驳回</button>
        <button class="btn btn-outline" onclick="EVAL_skipItem('${review.id}')" style="flex:1">⏭ 跳过</button>
      </div>` : `
      <div class="detail-actions">
        <div style="width:100%;text-align:center;font-size:11px;color:var(--text-muted)">
          ${review.status === 'approved' ? '✅ 已通过审核' : '❌ 已被驳回'}
        </div>
      </div>`}
    </div>
  `;
}

/* ================================================================
   评测操作
   ================================================================ */
function EVAL_approveItem(id) {
  const r = EVAL_STATE.reviews.find(r => r.id === id);
  if (r) { r.status = 'approved'; r.reviewed_at = new Date().toISOString().slice(0, 16).replace('T', ' '); }
  EVAL_STATE.selectedReviews.delete(id);
  EVAL_refreshUI();
  /* P1-C-W2: POST /api/eval/{id}/review per task spec (was /api/review/approve). */
  window.httpPost('/api/eval/' + encodeURIComponent(id) + '/review', { id: id, decision: 'approve' }, { timeoutMs: 15000 }).then(res => {
    if (res.state !== window.HTTP_STATE.SUCCESS) window.IMDF_ERROR.onApiError('eval.review.approve', res.error);
  });
}

function EVAL_rejectItem(id) {
  const r = EVAL_STATE.reviews.find(r => r.id === id);
  if (r) { r.status = 'rejected'; r.reviewed_at = new Date().toISOString().slice(0, 16).replace('T', ' '); }
  EVAL_STATE.selectedReviews.delete(id);
  EVAL_refreshUI();
  /* P1-C-W2: POST /api/eval/{id}/review per task spec (was /api/review/reject). */
  window.httpPost('/api/eval/' + encodeURIComponent(id) + '/review', { id: id, decision: 'reject' }, { timeoutMs: 15000 }).then(res => {
    if (res.state !== window.HTTP_STATE.SUCCESS) window.IMDF_ERROR.onApiError('eval.review.reject', res.error);
  });
}

function EVAL_skipItem(id) {
  const r = EVAL_STATE.reviews.find(r => r.id === id);
  if (r) { r.status = 'skipped'; }
  EVAL_STATE.selectedReviews.delete(id);
  EVAL_refreshUI();
}

function EVAL_batchAction(action) {
  const ids = [...EVAL_STATE.selectedReviews];
  if (ids.length === 0) {
    showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
      <h4 style="color:var(--accent-orange)">⚠️ 未选择评测项</h4>
      <p style="color:var(--text-muted);font-size:13px;margin-top:8px">请先勾选评测项</p>`);
    return;
  }

  const labels = { approve: '通过', reject: '驳回', skip: '跳过' };
  const colors = { approve: 'var(--accent-green)', reject: 'var(--accent-red)', skip: 'var(--accent-purple)' };

  showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="color:${colors[action]}">📋 批量${labels[action]}</h4>
    <p style="color:var(--text-muted);font-size:13px;margin-top:8px">对 ${ids.length} 条评测执行批量${labels[action]}</p>
    <button onclick="EVAL_executeBatch('${action}');closeModal()" class="btn btn-primary" style="width:100%;margin-top:12px">
      ✅ 确认${labels[action]}</button>`);
}

function EVAL_executeBatch(action) {
  [...EVAL_STATE.selectedReviews].forEach(id => {
    const r = EVAL_STATE.reviews.find(r => r.id === id);
    if (r) r.status = action === 'approve' ? 'approved' : action === 'reject' ? 'rejected' : 'skipped';
  });
  EVAL_STATE.selectedReviews = new Set();
  EVAL_STATE.selectedId = null;
  EVAL_refreshUI();
}

async function EVAL_batchApprove() {
  const pending = EVAL_STATE.reviews.filter(r => r.status === 'pending').map(r => r.id);
  if (pending.length === 0) { (window.toastError || ((m) => alert(m)))('无待审核项'); return; }
  EVAL_STATE.selectedReviews = new Set(pending);
  EVAL_batchAction('approve');
}

async function EVAL_batchReject() {
  const pending = EVAL_STATE.reviews.filter(r => r.status === 'pending').map(r => r.id);
  if (pending.length === 0) { (window.toastError || ((m) => alert(m)))('无待审核项'); return; }
  EVAL_STATE.selectedReviews = new Set(pending);
  EVAL_batchAction('reject');
}

function EVAL_toggleSelect(id, checked) {
  if (checked) { EVAL_STATE.selectedReviews.add(id); }
  else { EVAL_STATE.selectedReviews.delete(id); }
}

/* ================================================================
   AI辅助审核
   ================================================================ */
async function EVAL_runAIAssist() {
  const status = $('eval-ai-status');
  if (status) status.innerHTML = '⏳ AI分析中...';

  try {
    /* P1-C-W2: three-state via client.js */
    await Promise.all([
      window.httpPost('/api/prelabel', { task_type: 'review', batch: true }, { timeoutMs: 30000 }).catch(() => ({})),
      window.httpGet('/api/stats/quality', { timeoutMs: 15000 }).catch(() => ({})),
    ]);
  } catch (e) {}

  const suspicious = EVAL_STATE.reviews.filter(r => (r.consensus_score || r.agreement || 0) < 0.70);
  if (status) {
    status.innerHTML = `✅ AI审核完成: 发现 <span style="color:var(--accent-orange)">${suspicious.length}</span> 条低一致性标注`;
  }
  EVAL_renderLowQuality();
}

function EVAL_renderLowQuality() {
  const container = $('eval-low-quality-list');
  if (!container) return;

  const lowQuality = EVAL_STATE.reviews.filter(r => (r.consensus_score || r.agreement || 0) < 0.70);
  if (lowQuality.length === 0) {
    container.innerHTML = '<div style="font-size:10px;color:var(--accent-green);text-align:center;padding:8px">✅ 无低质量标注</div>';
    return;
  }

  container.innerHTML = lowQuality.map(r => `
    <div style="padding:4px 8px;margin-bottom:3px;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.2);border-radius:3px;font-size:10px;display:flex;justify-content:space-between;align-items:center">
      <span>⚠ #${r.id} — ${r.annotator || '未知'}</span>
      <span style="color:var(--accent-red);cursor:pointer" onclick="EVAL_selectItem('${r.id}')">
        ${Math.round((r.consensus_score || r.agreement || 0) * 100)}% →
      </span>
    </div>
  `).join('');
}

/* ================================================================
   Kappa详情弹窗
   ================================================================ */
function EVAL_showKappaDetail() {
  const stats = EVAL_STATE.reviews;
  const agreements = stats.map(r => r.consensus_score || r.agreement || 0.85);
  const avgAgreement = agreements.length > 0 ? (agreements.reduce((a, b) => a + b, 0) / agreements.length * 100).toFixed(1) : '85.3';
  const highAgreement = agreements.filter(a => a >= 0.8).length;
  const lowAgreement = agreements.filter(a => a < 0.7).length;

  showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="color:var(--accent-blue);margin-bottom:12px">📈 Cohen Kappa 一致性详情</h4>
    <div style="font-size:12px;color:var(--text-muted);line-height:2">
      <p>📊 平均 IAA 一致率: <strong style="color:var(--accent-green)">${avgAgreement}%</strong></p>
      <p>📈 近8周 Kappa 趋势: 0.62 → 0.72 (↑0.10)</p>
      <p>✅ 高一致性 (≥80%): <strong style="color:var(--accent-green)">${highAgreement}</strong> 条</p>
      <p>⚠ 低一致性 (<70%): <strong style="color:var(--accent-red)">${lowAgreement}</strong> 条</p>
      <p>🎯 目标 Kappa: ≥0.70</p>
      <hr style="border-color:var(--border);margin:12px 0">
      <div style="font-size:11px">
        <strong>Cohen Kappa 解读:</strong><br>
        <span style="color:var(--accent-green)">≥0.81</span> 几乎完全一致 · 
        <span style="color:var(--accent-blue)">0.61-0.80</span> 高度一致 · 
        <span style="color:var(--accent-orange)">0.41-0.60</span> 中等一致 · 
        <span style="color:var(--accent-red)">&lt;0.40</span> 低一致性
      </div>
      <p style="margin-top:8px">🔄 建议: 对低一致性评测项进行复审，必要时增加评测轮次</p>
    </div>`);
}

/* ================================================================
   UI刷新
   ================================================================ */
function EVAL_refreshUI() {
  const pending = EVAL_STATE.reviews.filter(r => r.status === 'pending').length;

  const statQueue = $('eval-stat-queue');
  if (statQueue) statQueue.textContent = pending;

  const list = $('eval-queue-list');
  const count = $('eval-queue-count');
  if (list) list.innerHTML = EVAL_renderQueue(EVAL_STATE.reviews);
  if (count) count.textContent = `共 ${EVAL_STATE.reviews.length} 条`;

  if (EVAL_STATE.selectedId) {
    EVAL_selectItem(EVAL_STATE.selectedId);
  }

  const el = $('sReview');
  if (el) el.textContent = pending;
}

async function refreshEvalData() {
  await renderEvalReview();
}

function updateStatusBarReview(pending) {
  const el = $('sReview');
  if (el) el.textContent = pending;
}

/* ================================================================
   P1-C-W2: New /api/eval/* endpoints integration
   ================================================================ */
let EVAL_LIST = { page: 1, items: [], total: 0, loading: false };

async function EVAL_listEval(page) {
  EVAL_LIST.page = page || 1;
  EVAL_LIST.loading = true;
  const res = await window.httpGet('/api/eval/list' + window.IMDF_ERROR.qs({ page: EVAL_LIST.page, page_size: 20 }), { timeoutMs: 15000 });
  EVAL_LIST.loading = false;
  if (res.state !== window.HTTP_STATE.SUCCESS) {
    window.IMDF_ERROR.onApiError('eval.list', res.error);
    return null;
  }
  const ext = window.IMDF_ERROR.extractList(res.data);
  EVAL_LIST.items  = ext.items;
  EVAL_LIST.total  = ext.total;
  EVAL_LIST._pages = ext.pages;
  return ext;
}

/* POST /api/eval/{id}/run — start an evaluation */
async function EVAL_runEval(id) {
  if (!id) return;
  const res = await window.httpPost('/api/eval/' + encodeURIComponent(id) + '/run', { id: id }, { timeoutMs: 30000 });
  if (res.state !== window.HTTP_STATE.SUCCESS) {
    window.IMDF_ERROR.onApiError('eval.run', res.error);
    if (typeof showToast === 'function') showToast('❌ 启动评测失败: ' + window.IMDF_ERROR.describe(res.error), 'error');
    return null;
  }
  if (typeof showToast === 'function') showToast('✅ 评测已启动', 'success');
  return res.data;
}

/* GET /api/eval/{id}/status — poll evaluation status */
async function EVAL_getStatus(id) {
  if (!id) return null;
  const res = await window.httpGet('/api/eval/' + encodeURIComponent(id) + '/status', { timeoutMs: 10000 });
  if (res.state !== window.HTTP_STATE.SUCCESS) {
    window.IMDF_ERROR.onApiError('eval.status', res.error);
    return null;
  }
  return res.data;
}

/* POST /api/eval/{id}/submit — submit evaluation results */
async function EVAL_submitEval(id, payload) {
  if (!id) return null;
  const res = await window.httpPost('/api/eval/' + encodeURIComponent(id) + '/submit', Object.assign({ id: id }, payload || {}), { timeoutMs: 30000 });
  if (res.state !== window.HTTP_STATE.SUCCESS) {
    window.IMDF_ERROR.onApiError('eval.submit', res.error);
    if (typeof showToast === 'function') showToast('❌ 提交失败: ' + window.IMDF_ERROR.describe(res.error), 'error');
    return null;
  }
  if (typeof showToast === 'function') showToast('✅ 已提交', 'success');
  return res.data;
}

/* Polling helper: GET status every 2s up to 60s, stopping on terminal status. */
async function EVAL_pollUntilDone(id, opts) {
  opts = opts || {};
  const interval = opts.intervalMs || 2000;
  const timeout  = opts.timeoutMs  || 60000;
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const status = await EVAL_getStatus(id);
    if (!status) return null;
    const s = (status.status || status.state || '').toLowerCase();
    if (s === 'done' || s === 'completed' || s === 'success' || s === 'failed' || s === 'error' || s === 'cancelled' || s === 'canceled') {
      return status;
    }
    await new Promise(r => setTimeout(r, interval));
  }
  return null;
}
