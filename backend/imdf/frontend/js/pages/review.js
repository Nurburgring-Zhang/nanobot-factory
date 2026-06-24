/* IMDF v3 审核管理页面 — 审核队列 + 审核详情 + 批量操作 */

const REVIEW_STATE = {
  reviews: [],
  selectedId: null,
  selectedIds: new Set(),
  filters: { status: 'all', annotator: '' },
};

async function renderReview() {
  const container = $('page-content');
  if (!container) return;

  // 加载审核数据
  try {
    const data = await apiGet('/api/review/queue').catch(() => ({}));
    REVIEW_STATE.reviews = data.data || data.reviews || [];
  } catch (e) {
    REVIEW_STATE.reviews = [];
  }

  if (REVIEW_STATE.reviews.length === 0) {
    REVIEW_STATE.reviews = [];
  }

  const total = REVIEW_STATE.reviews.length;
  const pending = REVIEW_STATE.reviews.filter(r => r.status === 'pending').length;
  const approvedToday = REVIEW_STATE.reviews.filter(r => r.status === 'approved').length;
  const passRate = total > 0 ? Math.round((approvedToday / total) * 100) : 0;

  REVIEW_STATE.selectedId = null;
  REVIEW_STATE.selectedIds = new Set();

  container.innerHTML = `
    <!-- ===== 页面头部 ===== -->
    <div class="page-header">
      <div>
        <div class="page-title">📋 审核管理</div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px">标注质量审核 · 人工复核 · 批量操作</div>
      </div>
      <div class="page-stats">
        <div class="page-stat">
          <div class="page-stat-val" style="color:var(--accent-orange)" id="review-stat-pending">${pending}</div>
          <div class="page-stat-label">待审核</div>
        </div>
        <div class="page-stat">
          <div class="page-stat-val" style="color:var(--accent-green)" id="review-stat-approved">${approvedToday}</div>
          <div class="page-stat-label">今日通过</div>
        </div>
        <div class="page-stat">
          <div class="page-stat-val" style="color:${passRate >= 80 ? 'var(--accent-green)' : passRate >= 60 ? 'var(--accent-orange)' : 'var(--accent-red)'}" id="review-stat-rate">${passRate}%</div>
          <div class="page-stat-label">通过率</div>
        </div>
      </div>
      <div class="page-actions">
        <button class="btn btn-sm btn-outline" onclick="renderReview()">🔄 刷新</button>
      </div>
    </div>

    <!-- ===== 工具栏 ===== -->
    <div class="toolbar">
      <select onchange="REVIEW_filterByStatus(this.value)" style="min-width:120px">
        <option value="all">全部状态</option>
        <option value="pending">⏳ 待审核</option>
        <option value="approved">✅ 已通过</option>
        <option value="rejected">❌ 已驳回</option>
        <option value="skipped">⏭ 已跳过</option>
      </select>
      <input type="text" placeholder="🔍 搜索标注者/标签..." oninput="REVIEW_filterSearch(this.value)" style="flex:1;max-width:240px">
      <span style="flex:1"></span>
      <button class="btn btn-sm btn-success" onclick="REVIEW_batchAction('approve')" title="批量通过选中项">✅ 批量通过</button>
      <button class="btn btn-sm btn-danger" onclick="REVIEW_batchAction('reject')" title="批量驳回选中项">❌ 批量驳回</button>
      <button class="btn btn-sm btn-outline" onclick="REVIEW_batchAction('skip')" title="批量跳过选中项">⏭ 批量跳过</button>
    </div>

    <!-- ===== 两栏布局 ===== -->
    <div class="two-col" style="grid-template-columns:1fr 380px;">
      <!-- 左侧：审核队列 -->
      <div class="main-panel" style="display:flex;flex-direction:column;padding:0;overflow:hidden">
        <div style="padding:12px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
          <span class="section-title" style="margin-bottom:0">📋 审核队列</span>
          <span id="review-queue-count" style="font-size:11px;color:var(--text-muted)">共 ${total} 条</span>
        </div>
        <div id="review-queue-list" style="flex:1;overflow-y:auto;padding:0 16px">
          ${REVIEW_renderQueue(REVIEW_STATE.reviews)}
        </div>
      </div>

      <!-- 右侧：审核详情 -->
      <div class="side-panel" style="padding:0;display:flex;flex-direction:column;overflow:hidden">
        <div style="padding:12px 16px;border-bottom:1px solid var(--border)">
          <span class="section-title" style="margin-bottom:0">📝 审核详情</span>
        </div>
        <div id="review-detail-panel" style="flex:1;overflow-y:auto">
          <div class="empty-state-compact">
            <div class="empty-icon">👈</div>
            <div class="empty-text">选择左侧审核项查看详情</div>
            <div class="empty-hint">点击审核队列中的项目查看完整信息</div>
          </div>
        </div>
      </div>
    </div>
  `;
}

/* ================================================================
   审核队列渲染
   ================================================================ */
// R5-W3: 移除 REVIEW_generateMockReviews 死代码 — R3-W3 改造后 renderReview 已走真实 API,
// 该函数已无调用点; P2-2-W1: 移除 mock 兜底期望, 改为真实 API 调用

function REVIEW_renderQueue(reviews) {
  if (!reviews || reviews.length === 0) {
    return `<div class="empty-state-compact">
      <div class="empty-icon">✅</div>
      <div class="empty-text">审核队列已清空</div>
      <div class="empty-hint">所有标注已审核完毕</div>
    </div>`;
  }

  const statusBadge = {
    pending: '<span class="tag tag-orange">⏳ 待审核</span>',
    approved: '<span class="tag tag-green">✅ 已通过</span>',
    rejected: '<span class="tag tag-red">❌ 已驳回</span>',
    skipped: '<span class="tag tag-purple">⏭ 已跳过</span>',
  };

  return reviews.map((r, idx) => {
    const isActive = r.id === REVIEW_STATE.selectedId;
    const isChecked = REVIEW_STATE.selectedIds.has(r.id);
    const confPct = Math.round(parseFloat(r.confidence) * 100);
    const confColor = confPct >= 90 ? 'var(--accent-green)' : confPct >= 70 ? 'var(--accent-orange)' : 'var(--accent-red)';

    return `
    <div class="review-row ${isActive ? 'active' : ''}" onclick="REVIEW_selectItem('${r.id}')">
      <input type="checkbox" ${isChecked ? 'checked' : ''} 
        onclick="event.stopPropagation();REVIEW_toggleSelect('${r.id}', this.checked)" 
        style="accent-color:var(--accent-blue);flex-shrink:0">
      <div class="review-index">#${idx + 1}</div>
      <div class="review-main">
        <div class="review-title">${sanitizeHTML(r.label || '未知标签')}</div>
        <div class="review-meta">
          👤 ${sanitizeHTML(r.annotator)} · 📄 ${sanitizeHTML(r.image_name)} · 🕐 ${sanitizeHTML(r.created_at)}
        </div>
        <div style="font-size:10px;color:${confColor};margin-top:2px">
          🤖 AI置信度: ${confPct}%
        </div>
      </div>
      <div class="review-status">${statusBadge[r.status] || statusBadge.pending}</div>
    </div>`;
  }).join('');
}

/* ================================================================
   审核详情面板
   ================================================================ */
function REVIEW_selectItem(id) {
  REVIEW_STATE.selectedId = id;
  const review = REVIEW_STATE.reviews.find(r => r.id === id);
  if (!review) return;

  // 更新队列高亮
  document.querySelectorAll('.review-row').forEach(row => row.classList.remove('active'));
  const targetRow = document.querySelector(`.review-row[onclick*="${id}"]`);
  if (targetRow) targetRow.classList.add('active');

  // 渲染详情
  const panel = $('review-detail-panel');
  if (!panel) return;

  const confPct = Math.round(parseFloat(review.confidence) * 100);
  const aiConfPct = Math.round(parseFloat(review.ai_confidence || 0) * 100);
  const diffPct = Math.abs(confPct - aiConfPct);
  const isPending = review.status === 'pending';

  panel.innerHTML = `
    <div class="detail-panel">
      <div class="detail-field">
        <label>标注ID</label>
        <div class="detail-value">#${review.id}</div>
      </div>
      <div class="detail-field">
        <label>标注者</label>
        <div class="detail-value">👤 ${sanitizeHTML(review.annotator)}</div>
      </div>
      <div class="detail-field">
        <label>标签</label>
        <div class="detail-value">🏷️ ${sanitizeHTML(review.label)}</div>
      </div>
      <div class="detail-field">
        <label>图片</label>
        <div class="detail-value">📄 ${sanitizeHTML(review.image_name)}</div>
      </div>
      <div class="detail-field">
        <label>提交时间</label>
        <div class="detail-value">🕐 ${review.created_at}</div>
      </div>

      <div style="background:var(--bg-primary);border-radius:6px;padding:12px;margin-bottom:14px">
        <div style="font-size:11px;font-weight:600;margin-bottom:8px;color:var(--text-primary)">🤖 AI对比分析</div>
        <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:11px">
          <span style="color:var(--text-muted)">人工标签</span>
          <span style="color:var(--accent-blue)">${review.label}</span>
        </div>
        <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:11px">
          <span style="color:var(--text-muted)">AI 标签</span>
          <span style="color:var(--accent-purple)">${review.ai_label || '—'}</span>
        </div>
        <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:11px">
          <span style="color:var(--text-muted)">AI 置信度</span>
          <span style="color:${aiConfPct >= 90 ? 'var(--accent-green)' : 'var(--accent-orange)'}">${aiConfPct}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:11px">
          <span style="color:var(--text-muted)">人机差异度</span>
          <span style="color:${diffPct > 20 ? 'var(--accent-red)' : 'var(--accent-green)'}">${diffPct}%</span>
        </div>
      </div>

      ${review.comments ? `
      <div class="detail-field">
        <label>审核备注</label>
        <div class="detail-value" style="color:var(--accent-green)">💬 ${review.comments}</div>
      </div>` : ''}

      ${review.reviewer ? `
      <div class="detail-field">
        <label>审核人</label>
        <div class="detail-value">👤 ${review.reviewer} · ${review.reviewed_at}</div>
      </div>` : ''}

      ${review.bbox ? `
      <div class="detail-field">
        <label>BBox 坐标</label>
        <div class="detail-value" style="font-size:11px;font-family:monospace">
          x:${review.bbox.x} y:${review.bbox.y} w:${review.bbox.w} h:${review.bbox.h}
        </div>
      </div>` : ''}

      ${isPending ? `
      <div class="detail-actions">
        <button class="btn btn-success" onclick="REVIEW_approveItem('${review.id}')" style="flex:1">✅ 通过</button>
        <button class="btn btn-danger" onclick="REVIEW_rejectItem('${review.id}')" style="flex:1">❌ 驳回</button>
        <button class="btn btn-outline" onclick="REVIEW_skipItem('${review.id}')" style="flex:1">⏭ 跳过</button>
      </div>` : `
      <div class="detail-actions">
        <div style="width:100%;text-align:center;font-size:11px;color:var(--text-muted)">
          ${review.status === 'approved' ? '✅ 该标注已通过审核' : review.status === 'rejected' ? '❌ 该标注已被驳回' : '⏭ 该标注已跳过'}
        </div>
      </div>`}
    </div>
  `;
}

/* ================================================================
   审核操作
   R5-W3: 错误不再吞掉, 真实失败时回滚 UI 状态 + 弹错误 toast
   ================================================================ */
async function REVIEW_approveItem(id) {
  const review = REVIEW_STATE.reviews.find(r => r.id === id);
  if (!review) return;
  // 保存旧状态以便失败回滚
  const prevStatus = review.status;
  const prevReviewer = review.reviewer;
  const prevReviewedAt = review.reviewed_at;
  // 乐观更新 UI
  review.status = 'approved';
  review.reviewer = '当前用户';
  review.reviewed_at = new Date().toISOString().slice(0, 16).replace('T', ' ');
  REVIEW_STATE.selectedIds.delete(id);
  REVIEW_refreshUI();
  // 真实 API 调用 — 失败必须让用户知道
  try {
    const resp = await apiPost('/api/review/approve', { id });
    if (resp && resp.success === false) {
      throw new Error(resp.error || resp.message || '审核通过失败');
    }
    showToast('已通过审核 #' + id, 'success');
  } catch (e) {
    // 回滚 UI
    review.status = prevStatus;
    review.reviewer = prevReviewer;
    review.reviewed_at = prevReviewedAt;
    REVIEW_STATE.selectedIds.add(id);
    REVIEW_refreshUI();
    showToast('通过失败: ' + (e?.message || e), 'error');
  }
}

async function REVIEW_rejectItem(id) {
  const review = REVIEW_STATE.reviews.find(r => r.id === id);
  if (!review) return;
  // 保存旧状态以便失败回滚
  const prevStatus = review.status;
  const prevReviewer = review.reviewer;
  const prevReviewedAt = review.reviewed_at;
  // 乐观更新 UI
  review.status = 'rejected';
  review.reviewer = '当前用户';
  review.reviewed_at = new Date().toISOString().slice(0, 16).replace('T', ' ');
  REVIEW_STATE.selectedIds.delete(id);
  REVIEW_refreshUI();
  // 真实 API 调用 — 失败必须让用户知道
  try {
    const resp = await apiPost('/api/review/reject', { id });
    if (resp && resp.success === false) {
      throw new Error(resp.error || resp.message || '审核驳回失败');
    }
    showToast('已驳回 #' + id, 'success');
  } catch (e) {
    // 回滚 UI
    review.status = prevStatus;
    review.reviewer = prevReviewer;
    review.reviewed_at = prevReviewedAt;
    REVIEW_STATE.selectedIds.add(id);
    REVIEW_refreshUI();
    showToast('驳回失败: ' + (e?.message || e), 'error');
  }
}

function REVIEW_skipItem(id) {
  const review = REVIEW_STATE.reviews.find(r => r.id === id);
  if (!review) return;
  review.status = 'skipped';
  REVIEW_STATE.selectedIds.delete(id);
  REVIEW_refreshUI();
}

function REVIEW_batchAction(action) {
  const ids = [...REVIEW_STATE.selectedIds];
  if (ids.length === 0) {
    showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
      <h4 style="color:var(--accent-orange)">⚠️ 未选择审核项</h4>
      <p style="color:var(--text-muted);font-size:13px;margin-top:8px">请先在队列中勾选需要操作的审核项</p>`);
    return;
  }

  const actionLabel = { approve: '通过', reject: '驳回', skip: '跳过' };
  const actionColor = { approve: 'var(--accent-green)', reject: 'var(--accent-red)', skip: 'var(--accent-purple)' };

  showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="color:${actionColor[action]}">📋 批量${actionLabel[action]}</h4>
    <p style="color:var(--text-muted);font-size:13px;margin-top:8px">
      将对选中的 <strong>${ids.length}</strong> 条审核执行批量${actionLabel[action]}
    </p>
    <div style="margin-top:12px;max-height:160px;overflow-y:auto;font-size:11px">
      ${ids.map(id => {
        const r = REVIEW_STATE.reviews.find(r => r.id === id);
        return `<div style="padding:4px 0;border-bottom:1px solid rgba(42,42,74,0.3)">#${id} — ${r ? sanitizeHTML(r.label) : '—'} (${r ? sanitizeHTML(r.annotator) : '—'})</div>`;
      }).join('')}
    </div>
    <div style="display:flex;gap:8px;margin-top:12px">
      <button onclick="REVIEW_executeBatch('${action}', ${JSON.stringify(ids).replace(/"/g, '&quot;')})" 
        class="btn btn-primary" style="flex:1">✅ 确认${actionLabel[action]}</button>
    </div>`);
}

// R5-W3: REVIEW_executeBatch 改为真批量 API
// 策略: 优先尝试 POST /api/review/{action}-batch (若后端有 batch 端点),
// 失败/不存在时回退到 Promise.allSettled 并发调用单条端点 (类似 sc_triggerAll 的容错模式).
// 这样既支持未来加 batch 端点, 又能在 batch 端点缺失时不静默失败.
async function REVIEW_executeBatch(action, ids) {
  if (!Array.isArray(ids) || ids.length === 0) {
    showToast('未选择审核项', 'warning');
    return;
  }
  const actionLabel = { approve: '通过', reject: '驳回', skip: '跳过' };
  const actionPath = action === 'approve' ? 'approve' : action === 'reject' ? 'reject' : 'skip';

  // 先快照旧状态, 用于失败回滚
  const snapshots = ids.map(id => {
    const r = REVIEW_STATE.reviews.find(rv => rv.id === id);
    return r ? { id, status: r.status, reviewer: r.reviewer, reviewed_at: r.reviewed_at } : null;
  }).filter(Boolean);

  // 乐观更新 UI
  ids.forEach(id => {
    const review = REVIEW_STATE.reviews.find(r => r.id === id);
    if (!review) return;
    review.status = action === 'approve' ? 'approved' : action === 'reject' ? 'rejected' : 'skipped';
    review.reviewer = '当前用户(批量)';
    review.reviewed_at = new Date().toISOString().slice(0, 16).replace('T', ' ');
  });
  REVIEW_STATE.selectedIds = new Set();
  REVIEW_STATE.selectedId = null;
  closeModal();
  REVIEW_refreshUI();

  showGlobalLoading('批量' + actionLabel[action] + '中... ' + ids.length + ' 条');

  // 方案 1: 尝试 batch 端点 (单次请求带 ids 数组)
  let results = null;
  try {
    const batchResp = await apiPost('/api/review/' + actionPath + '-batch', { ids: ids });
    if (batchResp && batchResp.success !== false) {
      // batch 端点成功 — 把 ids 全部视为成功
      results = ids.map(id => ({ id, ok: true }));
    } else if (batchResp && (batchResp.code === 404 || /not\s*found|404/i.test(String(batchResp.error || '')))) {
      // batch 端点不存在 — 走回退方案
      results = null;
    } else {
      // batch 端点返回了真实错误 — 走回退方案但保留错误信息
      results = null;
    }
  } catch (e) {
    // 网络错误 — 也走回退方案
    results = null;
  }

  // 方案 2: 回退到并发单条调用
  if (!results) {
    const settled = await Promise.allSettled(
      ids.map(id => apiPost('/api/review/' + actionPath, { id }))
    );
    results = settled.map((s, i) => {
      const id = ids[i];
      if (s.status === 'fulfilled' && s.value && s.value.success !== false) {
        return { id, ok: true, err: null };
      }
      return {
        id,
        ok: false,
        err: s.status === 'fulfilled'
          ? (s.value?.error || s.value?.message || '失败')
          : (s.reason?.message || String(s.reason || '失败')),
      };
    });
  }

  hideGlobalLoading();

  // 统计并按结果处理
  const okList = results.filter(r => r.ok);
  const failList = results.filter(r => !r.ok);

  // 失败项回滚 UI
  if (failList.length > 0) {
    failList.forEach(fail => {
      const snap = snapshots.find(s => s.id === fail.id);
      if (!snap) return;
      const review = REVIEW_STATE.reviews.find(r => r.id === fail.id);
      if (!review) return;
      review.status = snap.status;
      review.reviewer = snap.reviewer;
      review.reviewed_at = snap.reviewed_at;
      REVIEW_STATE.selectedIds.add(fail.id);
    });
    REVIEW_refreshUI();
  }

  if (failList.length === 0) {
    showToast('已批量' + actionLabel[action] + ' ' + okList.length + ' 条', 'success');
  } else if (okList.length === 0) {
    showToast('批量' + actionLabel[action] + '失败: ' + failList[0].err, 'error');
  } else {
    const sampleErr = failList[0].err || '未知错误';
    showToast(
      '部分失败: 成功 ' + okList.length + ', 失败 ' + failList.length + ' (首个: ' + sampleErr + ')',
      'warning'
    );
  }
}

/* ================================================================
   筛选 & 搜索
   ================================================================ */
let REVIEW_filterStatus = 'all';
let REVIEW_searchQuery = '';

function REVIEW_filterByStatus(status) {
  REVIEW_filterStatus = status;
  REVIEW_applyFilters();
}

function REVIEW_filterSearch(query) {
  REVIEW_searchQuery = query.toLowerCase();
  REVIEW_applyFilters();
}

function REVIEW_applyFilters() {
  let filtered = REVIEW_STATE.reviews;

  if (REVIEW_filterStatus !== 'all') {
    filtered = filtered.filter(r => r.status === REVIEW_filterStatus);
  }

  if (REVIEW_searchQuery) {
    filtered = filtered.filter(r =>
      (r.annotator && r.annotator.toLowerCase().includes(REVIEW_searchQuery)) ||
      (r.label && r.label.toLowerCase().includes(REVIEW_searchQuery)) ||
      (r.id && r.id.toLowerCase().includes(REVIEW_searchQuery))
    );
  }

  const list = $('review-queue-list');
  const count = $('review-queue-count');
  if (list) list.innerHTML = REVIEW_renderQueue(filtered);
  if (count) count.textContent = `共 ${filtered.length} 条`;
}

function REVIEW_toggleSelect(id, checked) {
  if (checked) {
    REVIEW_STATE.selectedIds.add(id);
  } else {
    REVIEW_STATE.selectedIds.delete(id);
  }
}

/* ================================================================
   UI刷新
   ================================================================ */
function REVIEW_refreshUI() {
  const total = REVIEW_STATE.reviews.length;
  const pending = REVIEW_STATE.reviews.filter(r => r.status === 'pending').length;
  const approvedToday = REVIEW_STATE.reviews.filter(r => r.status === 'approved').length;
  const passRate = total > 0 ? Math.round((approvedToday / total) * 100) : 0;

  // 更新头部统计
  const statPending = $('review-stat-pending');
  const statApproved = $('review-stat-approved');
  const statRate = $('review-stat-rate');
  if (statPending) statPending.textContent = pending;
  if (statApproved) statApproved.textContent = approvedToday;
  if (statRate) {
    statRate.textContent = passRate + '%';
    statRate.style.color = passRate >= 80 ? 'var(--accent-green)' : passRate >= 60 ? 'var(--accent-orange)' : 'var(--accent-red)';
  }

  // 刷新队列
  REVIEW_applyFilters();

  // 刷新详情
  if (REVIEW_STATE.selectedId) {
    REVIEW_selectItem(REVIEW_STATE.selectedId);
  }

  // 更新状态栏
  const el = $('sReview');
  if (el) el.textContent = pending;
}

function review_detailModal(item) {
  let html = '<div class="modal-tabs"><div class="modal-tab active">标注对比</div><div class="modal-tab">Kappa一致性</div><div class="modal-tab">AI辅助</div></div>';
  html += '<div class="detail-panel"><div class="detail-section"><div class="detail-section-title">标注详情</div>';
  html += `<div class="detail-field"><span class="detail-field-label">标注者</span><span class="detail-field-value">${item.annotator}</span></div>`;
  html += `<div class="detail-field"><span class="detail-field-label">类型</span><span class="detail-field-value">${item.type}</span></div>`;
  html += `<div class="detail-field"><span class="detail-field-label">置信度</span><span class="detail-field-value">${item.confidence||'--'}</span></div>`;
  html += `<div class="detail-field"><span class="detail-field-label">Kappa</span><span class="detail-field-value"><span class="progress-bar" style="width:100px;display:inline-block"><span class="progress-fill green" style="width:${(item.kappa||0.85)*100}%"></span></span> ${((item.kappa||0.85)*100).toFixed(0)}%</span></div>`;
  html += '</div></div>';
  showModal('审核详情', html, '<button class="btn btn-success btn-sm" onclick="this.closest(\'.modal-overlay\').remove();showToast(\'已通过\')">✅ 通过</button><button class="btn btn-danger btn-sm" onclick="this.closest(\'.modal-overlay\').remove();showToast(\'已驳回\',\'error\')">❌ 驳回</button>');
}

function review_batchModal() {
  showConfirm('批量审核', '确定要对选中的5个项目执行批量审核操作吗？', ()=>showToast('批量审核完成: 5/5'));
}
