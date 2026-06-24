/* IMDF v4 众包平台 — 完整实现
 * API: GET stats/teams | POST workers/assign/golden-check/majority-vote/quality-coefficient
 *       GET quality-report/{worker_id} | POST teams
 */

const CROWD_STATE = {
  workers: [],
  teams: [],
  stats: {},
  tasks: [],
  selectedWorkerId: null,
  selectedTeamId: null,
  view: 'workers',
  loading: false,
};

async function renderCrowdPlatform() {
  const c = $('page-content');
  if (!c) return;

  CROWD_STATE.loading = true;
  c.innerHTML = '<div class="loading-state"><div class="spinner"></div><p>加载众包数据...</p></div>';

  try {
    const [statsRes, workersRes, teamsRes] = await Promise.all([
      apiGet('/api/crowd/stats'),
      apiPost('/api/crowd/workers', {}),
      apiGet('/api/crowd/teams'),
    ]);
    CROWD_STATE.stats = statsRes?.data || statsRes || {};
    CROWD_STATE.workers = workersRes?.workers || workersRes?.data || [];
    CROWD_STATE.teams = teamsRes?.teams || teamsRes?.data || [];
  } catch (e) { /* API不可用时用空数据 */ }

  CROWD_STATE.loading = false;
  cp_render();
}

function cp_render() {
  const c = $('page-content');
  if (!c) return;
  const { workers, teams, stats, view, selectedWorkerId } = CROWD_STATE;

  c.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">👥 众包平台</div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px">工人管理 · 任务分配 · 质量监控 · 多数投票</div>
      </div>
      <div class="page-stats">
        <div class="page-stat">
          <div class="page-stat-val" style="color:var(--accent-blue)">${stats.active_workers || 0}</div>
          <div class="page-stat-label">活跃工人</div>
        </div>
        <div class="page-stat">
          <div class="page-stat-val" style="color:var(--accent-orange)">${stats.pending_tasks || 0}</div>
          <div class="page-stat-label">待处理任务</div>
        </div>
        <div class="page-stat">
          <div class="page-stat-val" style="color:var(--accent-green)">${stats.completed_tasks || 0}</div>
          <div class="page-stat-label">已完成</div>
        </div>
        <div class="page-stat">
          <div class="page-stat-val">${((stats.completion_rate || 0) * 100).toFixed(0)}%</div>
          <div class="page-stat-label">完成率</div>
        </div>
      </div>
      <div class="page-actions">
        <div class="view-toggle">
          <button class="${view==='workers'?'active':''}" onclick="cp_switchView('workers')">工人</button>
          <button class="${view==='teams'?'active':''}" onclick="cp_switchView('teams')">团队</button>
          <button class="${view==='tasks'?'active':''}" onclick="cp_switchView('tasks')">任务</button>
        </div>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <button class="btn btn-primary btn-sm" onclick="cp_addWorker()">+ 添加工人</button>
        <button class="btn btn-outline btn-sm" onclick="cp_createTeam()">+ 创建团队</button>
        <button class="btn btn-outline btn-sm" onclick="cp_createTask()">+ 创建任务</button>
      </div>
      <div class="toolbar-right">
        <button class="btn btn-sm" onclick="cp_refresh()">🔄 刷新</button>
      </div>
    </div>

    ${view === 'workers' ? cp_renderWorkers(workers) : ''}
    ${view === 'teams' ? cp_renderTeams(teams) : ''}
    ${view === 'tasks' ? cp_renderTasks() : ''}

    ${selectedWorkerId ? cp_renderWorkerDetail() : ''}
  `;
}

function cp_renderWorkers(workers) {
  if (!workers.length) {
    return `<div class="empty-state">
      <div class="empty-state-icon">👤</div>
      <div class="empty-state-text">暂无工人</div>
      <div class="empty-state-hint">点击"添加工人"招募众包标注人员</div>
    </div>`;
  }
  return `<div class="data-table-wrapper">
    <table class="data-table">
      <thead><tr>
        <th>工人</th><th>技能等级</th><th>评分</th><th>完成任务</th><th>状态</th><th>操作</th>
      </tr></thead>
      <tbody>${workers.map(w => `
        <tr>
          <td><strong>${w.name || '匿名'}</strong></td>
          <td>${'⭐'.repeat(w.skill_level || 1)}</td>
          <td>${(w.rating || 0).toFixed(1)}</td>
          <td>${w.tasks_completed || 0}</td>
          <td><span class="status-badge status-${w.available ? 'active' : 'offline'}">${w.available ? '在线' : '离线'}</span></td>
          <td>
            <button class="btn btn-sm" onclick="cp_selectWorker('${w.id || w.worker_id}')">详情</button>
            <button class="btn btn-sm btn-outline" onclick="cp_assignTask('${w.id || w.worker_id}')">分配</button>
          </td>
        </tr>`).join('')}</tbody>
    </table>
  </div>`;
}

function cp_renderTeams(teams) {
  if (!teams.length) {
    return `<div class="empty-state">
      <div class="empty-state-icon">👥</div>
      <div class="empty-state-text">暂无团队</div>
      <div class="empty-state-hint">点击"创建团队"组建标注团队</div>
    </div>`;
  }
  return `<div class="data-table-wrapper">
    <table class="data-table">
      <thead><tr><th>团队</th><th>成员数</th><th>任务数</th><th>平均质量</th><th>操作</th></tr></thead>
      <tbody>${teams.map(t => `
        <tr>
          <td><strong>${t.name}</strong></td>
          <td>${t.member_count || 0}</td>
          <td>${t.task_count || 0}</td>
          <td>${((t.avg_quality || 0) * 100).toFixed(0)}%</td>
          <td>
            <button class="btn btn-sm" onclick="cp_selectTeam('${t.id}')">查看</button>
          </td>
        </tr>`).join('')}</tbody>
    </table>
  </div>`;
}

function cp_renderTasks() {
  return `<div class="two-col">
    <div class="side-panel">
      <div class="section-title">任务列表</div>
      <div class="empty-state">
        <div class="empty-state-icon">📋</div>
        <div class="empty-state-text">活跃任务将显示在此处</div>
        <div class="empty-state-hint">点击"创建任务"发布众包标注任务</div>
      </div>
    </div>
    <div class="main-panel">
      <div class="section-title">任务详情</div>
      <div class="info-cards">
        <div class="info-card">
          <div class="info-card-label">批量操作</div>
          <div class="info-card-actions">
            <button class="btn btn-outline btn-sm" onclick="cp_majorityVote()">🗳 多数投票</button>
            <button class="btn btn-outline btn-sm" onclick="cp_goldenCheck()">✅ 金标准校验</button>
          </div>
        </div>
      </div>
    </div>
  </div>`;
}

function cp_renderWorkerDetail() {
  const w = CROWD_STATE.workers.find(w => (w.id || w.worker_id) === CROWD_STATE.selectedWorkerId);
  if (!w) return '';
  return `<div class="modal-overlay" onclick="if(event.target===this)CROWD_STATE.selectedWorkerId=null;cp_render()">
    <div class="modal-content" style="max-width:500px">
      <div class="modal-header">
        <h3>工人详情: ${w.name}</h3>
        <button class="modal-close" onclick="CROWD_STATE.selectedWorkerId=null;cp_render()">✕</button>
      </div>
      <div class="modal-body">
        <p><strong>技能等级:</strong> ${'⭐'.repeat(w.skill_level || 1)}</p>
        <p><strong>评分:</strong> ${(w.rating || 0).toFixed(1)}</p>
        <p><strong>完成任务:</strong> ${w.tasks_completed || 0}</p>
        <p><strong>状态:</strong> ${w.available ? '在线' : '离线'}</p>
        <hr>
        <button class="btn btn-primary btn-sm" onclick="cp_qualityReport('${w.id || w.worker_id}')">📊 质量报告</button>
        <button class="btn btn-outline btn-sm" onclick="cp_qualityCoefficient('${w.id || w.worker_id}')">📐 质量系数</button>
      </div>
    </div>
  </div>`;
}

/* ---------- 交互操作 ---------- */

async function cp_refresh() { renderCrowdPlatform(); }
function cp_switchView(v) { CROWD_STATE.view = v; CROWD_STATE.selectedWorkerId = null; cp_render(); }
function cp_selectWorker(id) { CROWD_STATE.selectedWorkerId = id; cp_render(); }
function cp_selectTeam(id) { CROWD_STATE.selectedTeamId = id; cp_render(); }

function cp_addWorker() {
  showFormModal('添加众包工人', [
    { id: 'name', label: '姓名', required: true },
    { id: 'skill_level', label: '技能等级', type: 'select', options: ['1','2','3','4','5'], value: '3' },
    { id: 'email', label: '邮箱' },
  ], {
    label: '添加',
    callback: async (d) => {
      try {
        const res = await apiPost('/api/crowd/workers', { name: d.name, skill_level: parseInt(d.skill_level), email: d.email });
        if (res?.success) { showToast('工人已添加'); cp_refresh(); }
        else showToast('添加失败: ' + (res?.error || '未知错误'), 'error');
      } catch (e) { showToast('添加失败', 'error'); }
    }
  });
}

function cp_createTeam() {
  showFormModal('创建团队', [
    { id: 'name', label: '团队名称', required: true },
    { id: 'description', label: '描述' },
  ], {
    label: '创建',
    callback: async (d) => {
      try {
        const res = await apiPost('/api/crowd/teams', { name: d.name, description: d.description });
        if (res?.success) { showToast('团队已创建'); cp_refresh(); }
        else showToast('创建失败: ' + (res?.error || '未知错误'), 'error');
      } catch (e) { showToast('创建失败', 'error'); }
    }
  });
}

function cp_createTask() {
  showFormModal('创建众包任务', [
    { id: 'name', label: '任务名称', required: true },
    { id: 'type', label: '类型', type: 'select', options: ['标注', '审核', '分类'] },
    { id: 'count', label: '数量', value: '100' },
    { id: 'description', label: '说明' },
  ], {
    label: '发布',
    callback: async (d) => {
      try {
        const res = await apiPost('/api/crowd/assign', {
          task_name: d.name, task_type: d.type, item_count: parseInt(d.count), description: d.description
        });
        if (res?.success) { showToast('任务已发布'); cp_refresh(); }
        else showToast('发布失败', 'error');
      } catch (e) { showToast('发布失败', 'error'); }
    }
  });
}

function cp_assignTask(workerId) {
  showFormModal('分配任务', [
    { id: 'task_name', label: '任务名称', required: true },
    { id: 'item_count', label: '项目数量', value: '50' },
  ], {
    label: '分配',
    callback: async (d) => {
      try {
        const res = await apiPost('/api/crowd/assign', {
          worker_id: workerId, task_name: d.task_name, item_count: parseInt(d.item_count)
        });
        if (res?.success) showToast('任务已分配');
        else showToast('分配失败', 'error');
      } catch (e) { showToast('分配失败', 'error'); }
    }
  });
}

async function cp_majorityVote() {
  showFormModal('多数投票', [
    { id: 'item_id', label: '项目ID', required: true },
    { id: 'annotations', label: '标注结果(JSON)', type: 'textarea', value: '[{"label":"A"},{"label":"A"},{"label":"B"}]' },
  ], {
    label: '投票',
    callback: async (d) => {
      try {
        const annotations = JSON.parse(d.annotations);
        const res = await apiPost('/api/crowd/majority-vote', { item_id: d.item_id, annotations });
        showToast('投票结果: ' + JSON.stringify(res?.result || res));
      } catch (e) { showToast('投票失败: ' + e.message, 'error'); }
    }
  });
}

async function cp_goldenCheck() {
  showFormModal('金标准校验', [
    { id: 'item_id', label: '项目ID', required: true },
    { id: 'annotation_label', label: '标注标签', required: true },
    { id: 'golden_label', label: '金标准标签', required: true },
  ], {
    label: '校验',
    callback: async (d) => {
      try {
        const res = await apiPost('/api/crowd/golden-check', {
          item_id: d.item_id, annotation_label: d.annotation_label, golden_label: d.golden_label
        });
        showToast(res?.match ? '✅ 与金标准一致' : '❌ 与金标准不一致');
      } catch (e) { showToast('校验失败', 'error'); }
    }
  });
}

async function cp_qualityReport(workerId) {
  showToast('正在加载质量报告...');
  try {
    const res = await apiGet('/api/crowd/quality-report/' + workerId);
    const data = res?.data || res;
    const msg = `工人质量报告: 准确率${((data.accuracy||0)*100).toFixed(0)}% | 一致性${((data.consistency||0)*100).toFixed(0)}%`;
    showToast(msg);
  } catch (e) { showToast('加载失败', 'error'); }
}

async function cp_qualityCoefficient(workerId) {
  showFormModal('计算质量系数', [
    { id: 'accuracy', label: '准确率(0-1)', value: '0.85' },
    { id: 'consistency', label: '一致性(0-1)', value: '0.90' },
    { id: 'speed', label: '速度(0-1)', value: '0.75' },
  ], {
    label: '计算',
    callback: async (d) => {
      try {
        const res = await apiPost('/api/crowd/quality-coefficient', {
          worker_id: workerId, accuracy: parseFloat(d.accuracy),
          consistency: parseFloat(d.consistency), speed: parseFloat(d.speed)
        });
        showToast('质量系数: ' + (res?.coefficient || res?.data?.coefficient || '计算完成'));
      } catch (e) { showToast('计算失败', 'error'); }
    }
  });
}
