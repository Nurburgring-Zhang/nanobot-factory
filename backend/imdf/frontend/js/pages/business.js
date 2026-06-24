/* IMDF v3 任务管理 + 工作流画布 + 团队 + 交付 + 审核 + 统计页面 */

/* ===== 任务管理 ===== */
async function renderTasks() {
  const c = $('page-content'); if (!c) return;
  c.innerHTML = `
    <div style="margin-bottom:16px">
      <h2 style="font-size:18px;font-weight:600;margin-bottom:4px">📋 任务管理</h2>
      <p style="font-size:12px;color:var(--text-muted)">管理所有数据生产任务，分配人员，追踪进度</p>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:12px">
      <button class="tb-pri" onclick="showCreateRequirement()" style="background:var(--accent-blue)">➕ 新建任务</button>
      <span style="flex:1"></span>
      <span style="font-size:12px;color:var(--text-muted)">📊 进行中: <strong id="taskRunning">0</strong></span>
      <span style="font-size:12px;color:var(--text-muted)">✅ 已完成: <strong id="taskDone">0</strong></span>
      <span style="font-size:12px;color:var(--text-muted)">⏳ 待审核: <strong id="taskReview">0</strong></span>
    </div>
    <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;overflow:hidden">
      <table class="data-table">
        <thead><tr>
          <th style="width:60px">ID</th><th>任务名称</th><th style="width:70px">类型</th><th style="width:60px">优先级</th>
          <th style="width:60px">进度</th><th style="width:70px">状态</th><th style="width:70px">负责人</th><th style="width:130px">操作</th>
        </tr></thead>
        <tbody id="taskTableBody">
          <tr><td colspan="8" style="text-align:center;padding:40px;color:var(--text-muted)">加载中...</td></tr>
        </tbody>
      </table>
    </div>`;
  loadTasks();
}

async function loadTasks() {
  const data = await apiGet('/api/requirements/').catch(() => ({}));
  const reqs = data.data?.requirements || data.requirements || [];
  const tb = $('taskTableBody'); if (!tb) return;
  if (reqs.length === 0) {
    tb.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:var(--text-muted)">📭 暂无任务，点击上方"新建任务"创建</td></tr>';
    return;
  }
  const priorities = ['P0','P1','P2','P3']; const priColor = {P0:'var(--accent-red)',P1:'var(--accent-orange)',P2:'var(--accent-blue)',P3:'var(--text-muted)'};
  tb.innerHTML = reqs.map(r => `
    <tr>
      <td style="color:var(--text-muted);font-size:11px">${(r.id||'').slice(0,8)}</td>
      <td><strong>${r.title||'未命名'}</strong></td>
      <td>${r.type||'annotation'}</td>
      <td style="color:${priColor[r.priority]||'var(--text-muted)'}">${r.priority||'P2'}</td>
      <td>${r.progress||0}%</td>
      <td><span class="task-status ${(r.status||'pending').toLowerCase()}">${({draft:'草稿',open:'开放',in_progress:'进行中',review:'审核中',done:'已完成',closed:'已关闭'})[r.status]||r.status}</span></td>
      <td style="color:var(--text-muted)">${r.created_by||'--'}</td>
      <td><button class="tb-btn" onclick="showTaskDetail('${r.id||''}')">详情</button></td>
    </tr>`).join('');
}

function showCreateRequirement() {
  showModal(`
    <span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="margin-bottom:16px;color:var(--accent-blue)">📋 新建任务</h4>
    <div style="display:grid;gap:10px">
      <input id="reqTitle" placeholder="任务名称" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
      <select id="reqType" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
        <option value="annotation">数据标注</option><option value="collection">数据采集</option><option value="cleaning">数据清洗</option><option value="review">质量审核</option>
      </select>
      <select id="reqPriority" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
        <option value="P0">P0 - 紧急</option><option value="P1">P1 - 高</option><option value="P2">P2 - 中</option><option value="P3">P3 - 低</option>
      </select>
      <button style="padding:10px;background:var(--accent-blue);border:none;border-radius:6px;color:#fff;cursor:pointer" onclick="createRequirement()">创建</button>
    </div>`);
}

async function createRequirement() {
  const title = $('reqTitle')?.value || '新任务';
  const type = $('reqType')?.value || 'annotation';
  const priority = $('reqPriority')?.value || 'P2';
  await apiPost('/api/requirements/create', {title, type, priority});
  closeModal(); loadTasks();
}

function showTaskDetail(id) {
  apiGet(`/api/requirements/`).then(data => {
    const reqs = data.data?.requirements || data.requirements || [];
    const r = reqs.find(x => x.id === id);
    showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
      <h4 style="margin-bottom:12px;color:var(--accent-blue)">📋 ${r?.title||id}</h4>
      <div style="color:var(--text-muted);font-size:12px;line-height:2">
        <p>ID: ${id}</p><p>类型: ${r?.type||'--'}</p><p>优先级: ${r?.priority||'--'}</p>
        <p>状态: ${r?.status||'--'}</p><p>创建人: ${r?.created_by||'--'}</p>
        <p>描述: ${r?.description||'暂无描述'}</p></div>`);
  });
}

/* ===== 工作流画布 ===== */
async function renderWorkflow() {
  const c = $('page-content'); if (!c) return;
  const nodes = await apiGet('/api/workflow/nodes').catch(() => ({}));
  const nodeList = nodes.data?.nodes || [];
  const templates = await apiGet('/api/workflow/templates').catch(() => ({}));
  const tmplList = templates.data?.templates || [];

  c.innerHTML = `
    <div style="margin-bottom:12px;display:flex;gap:6px;align-items:center">
      <h2 style="font-size:16px;font-weight:600">🚀 工作流画布</h2>
      <span style="flex:1"></span>
      <select id="wfTemplate" style="padding:4px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px">
        <option value="">📋 选择模板...</option>
        ${tmplList.map(t => `<option value="${t.id}">${t.name}</option>`).join('')}
      </select>
      <button class="tb-pri" onclick="runWorkflow()" style="background:var(--accent-green)">▶ 执行</button>
      <button class="tb-pri" onclick="validateWorkflow()" style="background:var(--accent-blue)">✓ 验证</button>
    </div>
    <div style="display:flex;gap:12px;height:calc(100vh - 220px)">
      <div style="width:180px;min-width:180px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;overflow:hidden;display:flex;flex-direction:column">
        <div style="padding:6px 10px;border-bottom:1px solid var(--border);font-size:11px;font-weight:600">节点库 <span style="color:var(--text-muted);font-weight:400">(${nodeList.length})</span></div>
        <div style="flex:1;overflow-y:auto;padding:4px">
          ${['dimension','capability','function'].map(cat => {
            const items = nodeList.filter(n => n.category === cat);
            if (items.length === 0) return '';
            return `<div style="font-size:10px;color:var(--text-muted);padding:4px 6px;margin-top:4px;text-transform:uppercase">${({dimension:'📐 维度',capability:'⚡ 能力',function:'🔧 功能'})[cat]||cat}</div>
              ${items.slice(0,10).map(n => `<div style="padding:4px 6px;margin:2px 0;border-radius:4px;font-size:11px;cursor:grab;background:var(--bg-primary);border:1px solid transparent" onmouseover="this.style.borderColor='var(--accent-blue)'" onmouseout="this.style.borderColor='transparent'">${n.label||n.type}</div>`).join('')}`;
          }).join('')}
        </div>
      </div>
      <div style="flex:1;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:13px;flex-direction:column;gap:8px">
        <div style="font-size:48px">🎨</div>
        <div>可视化工作流画布</div>
        <div style="font-size:11px">左侧节点库拖拽节点到此处 · 连线形成DAG</div>
        <div style="font-size:11px;color:var(--accent-blue);cursor:pointer" onclick="runWorkflow()">点击"执行"运行当前工作流 →</div>
        <div id="wfResult" style="margin-top:8px;font-size:11px;color:var(--text-muted)"></div>
      </div>
      <div style="width:200px;min-width:200px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;overflow:hidden;display:flex;flex-direction:column">
        <div style="padding:6px 10px;border-bottom:1px solid var(--border);font-size:11px;font-weight:600">属性</div>
        <div id="wfProps" style="flex:1;overflow-y:auto;padding:8px;font-size:11px;color:var(--text-muted);text-align:center;padding-top:40px">选择节点查看属性</div>
      </div>
    </div>`;
}

async function runWorkflow() {
  const r = $('wfResult'); if (r) r.textContent = '⏳ 执行中...';
  const result = await apiPost('/api/workflow/execute', {nodes:[{id:"n1",type:"text"}],connections:[]});
  if (r) r.textContent = result.success ? '✅ 执行完成' : '❌ 执行失败: ' + (result.error||'');
}

async function validateWorkflow() {
  const r = $('wfResult'); if (r) r.textContent = '⏳ 验证中...';
  const result = await apiPost('/api/workflow/validate', {nodes:[{id:"n1",type:"text"}],connections:[]});
  if (r) {
    const valid = result.data?.valid ?? result.valid;
    r.textContent = valid ? '✅ DAG验证通过' : '❌ DAG验证失败: ' + JSON.stringify(result.data?.errors||[]);
    r.style.color = valid ? 'var(--accent-green)' : 'var(--accent-red)';
  }
}

/* ===== 团队管理 ===== */
async function renderTeam() {
  const c = $('page-content'); if (!c) return;
  const [workers, stats] = await Promise.all([
    apiGet('/api/crowd/stats').catch(()=>({})),
    apiGet('/api/stats/daily').catch(()=>({}))
  ]);
  c.innerHTML = `
    <div style="margin-bottom:16px">
      <h2 style="font-size:18px;font-weight:600;margin-bottom:4px">👥 团队管理</h2>
      <p style="font-size:12px;color:var(--text-muted)">管理标注人员、团队、任务分配</p>
    </div>
    <div class="metrics" style="grid-template-columns:repeat(4,1fr);margin-bottom:16px">
      <div class="metric-card"><div class="metric-label">在线人数</div><div class="metric-value blue">12</div></div>
      <div class="metric-card"><div class="metric-label">标注人员</div><div class="metric-value green">8</div></div>
      <div class="metric-card"><div class="metric-label">质检人员</div><div class="metric-value orange">3</div></div>
      <div class="metric-card"><div class="metric-label">今日工作量</div><div class="metric-value purple">1,234 条</div></div>
    </div>
    <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;overflow:hidden">
      <div style="padding:10px 14px;border-bottom:1px solid var(--border);font-size:12px;font-weight:600">
        团队成员
        <button style="float:right;padding:4px 10px;background:var(--accent-blue);border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:11px" onclick="showAddWorker()">+ 添加</button>
      </div>
      <table class="data-table">
        <thead><tr><th>姓名</th><th>角色</th><th>技能</th><th>状态</th><th>工作量</th><th>质量分</th><th>操作</th></tr></thead>
        <tbody><tr><td colspan="7" style="text-align:center;padding:30px;color:var(--text-muted)">暂无成员数据，可点击"添加"创建</td></tr></tbody>
      </table>
    </div>`;
}

function showAddWorker() {
  showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="margin-bottom:12px;color:var(--accent-blue)">👤 添加成员</h4>
    <div style="display:grid;gap:10px">
      <input id="wName" placeholder="姓名" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
      <select id="wRole" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
        <option value="annotator">标注员</option><option value="reviewer">质检员</option><option value="admin">管理员</option>
      </select>
      <input id="wSkills" placeholder="技能标签(逗号分隔)" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
      <button style="padding:10px;background:var(--accent-blue);border:none;border-radius:6px;color:#fff;cursor:pointer" onclick="addWorker()">添加</button>
    </div>`);
}

async function addWorker() {
  const name = $('wName')?.value || '成员';
  const skills = ($('wSkills')?.value || '标注').split(',').map(s=>s.trim());
  await apiPost('/api/crowd/workers', {name, skills});
  closeModal(); renderTeam();
}

/* ===== 交付管理 ===== */
async function renderDelivery() {
  const c = $('page-content'); if (!c) return;
  const data = await apiGet('/api/delivery/').catch(()=>({}));
  const deliveries = data.data?.deliveries || data.deliveries || [];
  c.innerHTML = `
    <div style="margin-bottom:16px">
      <h2 style="font-size:18px;font-weight:600;margin-bottom:4px">📦 交付管理</h2>
      <p style="font-size:12px;color:var(--text-muted)">数据交付审核与追踪</p>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:12px">
      <button class="tb-pri" onclick="showCreateDelivery()" style="background:var(--accent-blue)">➕ 创建交付</button>
      <span style="flex:1"></span>
      <span style="font-size:12px;color:var(--text-muted)">📦 待交付: <strong>${deliveries.filter(d=>d.status==='pending').length}</strong></span>
      <span style="font-size:12px;color:var(--text-muted)">✅ 已交付: <strong>${deliveries.filter(d=>d.status==='approved').length}</strong></span>
    </div>
    <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;overflow:hidden">
      <table class="data-table"><thead><tr><th>数据集</th><th>目标</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead>
        <tbody>${deliveries.length === 0 ? '<tr><td colspan="5" style="text-align:center;padding:30px;color:var(--text-muted)">暂无交付记录</td></tr>'
          : deliveries.map(d => `<tr><td>${d.dataset||'--'}</td><td>${d.target||'--'}</td>
            <td><span class="task-status ${(d.status||'pending').toLowerCase()}">${d.status||'pending'}</span></td>
            <td style="color:var(--text-muted);font-size:11px">${(d.created_at||'').slice(0,10)||'--'}</td>
            <td><button class="tb-btn">详情</button></td></tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

function showCreateDelivery() {
  showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="margin-bottom:12px;color:var(--accent-blue)">📦 创建交付</h4>
    <div style="display:grid;gap:10px">
      <input id="delDs" placeholder="数据集名称" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
      <input id="delTarget" placeholder="交付目标" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
      <button style="padding:10px;background:var(--accent-blue);border:none;border-radius:6px;color:#fff;cursor:pointer" onclick="createDelivery()">创建</button>
    </div>`);
}

async function createDelivery() {
  const dataset = $('delDs')?.value || 'dataset';
  const target = $('delTarget')?.value || 'customer';
  await apiPost('/api/delivery/create', {dataset, target});
  closeModal(); renderDelivery();
}

/* ===== 审核管理 ===== */
async function renderReview() {
  const c = $('page-content'); if (!c) return;
  const data = await apiGet('/api/review/').catch(()=>({}));
  const reviews = data.data?.reviews || data.reviews || [];
  c.innerHTML = `
    <div style="margin-bottom:16px">
      <h2 style="font-size:18px;font-weight:600;margin-bottom:4px">📋 审核管理</h2>
      <p style="font-size:12px;color:var(--text-muted)">算法审核与质量审核</p>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:12px">
      <button class="tb-pri" onclick="showSubmitReview()" style="background:var(--accent-blue)">➕ 提交审核</button>
    </div>
    <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;overflow:hidden">
      <table class="data-table"><thead><tr><th>名称</th><th>版本</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>${reviews.length === 0 ? '<tr><td colspan="4" style="text-align:center;padding:30px;color:var(--text-muted)">暂无审核记录</td></tr>'
          : reviews.map(r => `<tr><td>${r.name||'--'}</td><td>${r.version||'--'}</td>
            <td><span class="task-status ${(r.status||'pending').toLowerCase()}">${r.status||'pending'}</span></td>
            <td><button class="tb-btn">详情</button></td></tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

function showSubmitReview() {
  showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="margin-bottom:12px;color:var(--accent-blue)">📋 提交审核</h4>
    <div style="display:grid;gap:10px">
      <input id="revName" placeholder="算法/数据集名称" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
      <input id="revVer" placeholder="版本号" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
      <button style="padding:10px;background:var(--accent-blue);border:none;border-radius:6px;color:#fff;cursor:pointer" onclick="submitReview()">提交</button>
    </div>`);
}

async function submitReview() {
  const name = $('revName')?.value || '模型';
  const version = $('revVer')?.value || '1.0';
  await apiPost('/api/review/submit', {name, version});
  closeModal(); renderReview();
}

/* ===== 统计分析 v3 — 运营看板+绩效排行+趋势图+质量分布 ===== */
async function renderStats() {
  const c = $('page-content'); if (!c) return;
  const [daily, weekly, monthly, ops] = await Promise.all([
    apiGet('/api/stats/daily').catch(()=>({})),
    apiGet('/api/stats/weekly').catch(()=>({})),
    apiGet('/api/stats/monthly').catch(()=>({})),
    apiGet('/api/ops/overview').catch(()=>({}))
  ]);
  c.innerHTML = `
    <div style="margin-bottom:16px">
      <h2 style="font-size:18px;font-weight:600;margin-bottom:4px">📈 统计分析</h2>
      <p style="font-size:12px;color:var(--text-muted)">运营看板、绩效排行、生产趋势、质量分布</p>
    </div>
    <!-- 指标卡 -->
    <div class="metrics" style="grid-template-columns:repeat(4,1fr);margin-bottom:16px">
      <div class="metric-card"><div class="metric-label">日生产量</div><div class="metric-value green">${daily.production_count||ops.production_count||0}</div></div>
      <div class="metric-card"><div class="metric-label">日交付量</div><div class="metric-value orange">${daily.delivery_count||ops.delivery_count||0}</div></div>
      <div class="metric-card"><div class="metric-label">平均质量</div><div class="metric-value purple">${(daily.avg_quality||ops.avg_quality_score||0).toFixed(1)}</div></div>
      <div class="metric-card"><div class="metric-label">日活跃用户</div><div class="metric-value blue">${ops.daily_active_users||0}</div></div>
    </div>

    <!-- 生产趋势 + 质量分布 并排 -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
      <!-- 生产趋势折线图 -->
      <div class="panel">
        <div class="panel-header"><span>📈 生产趋势 (近30天)</span></div>
        <div class="panel-body" style="padding:8px">
          <canvas id="trendChart" width="580" height="220" style="width:100%;height:220px"></canvas>
        </div>
      </div>
      <!-- 质量分布直方图 -->
      <div class="panel">
        <div class="panel-header"><span>📊 质量分布</span></div>
        <div class="panel-body" style="padding:8px">
          <canvas id="qualityChart" width="580" height="220" style="width:100%;height:220px"></canvas>
        </div>
      </div>
    </div>

    <!-- 人员绩效排行 -->
    <div class="panel" style="margin-bottom:12px">
      <div class="panel-header"><span>👥 人员绩效排行</span><span style="font-size:11px;color:var(--text-muted)">本月</span></div>
      <div class="panel-body" style="padding:0;max-height:240px;overflow-y:auto">
        <table class="data-table" id="perfTable">
          <thead><tr>
            <th style="width:40px">#</th><th>姓名</th><th style="width:80px">角色</th>
            <th style="width:80px">生产量</th><th style="width:80px">标注量</th>
            <th style="width:70px">质量分</th><th style="width:70px">效率</th><th style="width:80px">趋势</th>
          </tr></thead>
          <tbody id="perfTableBody">
            <tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text-muted)">加载中...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 周/月统计 -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
      <div class="panel"><div class="panel-header"><span>📅 周统计</span></div>
        <div class="panel-body" style="font-size:12px;color:var(--text-muted)">${weekly.production_count ? `本周生产: ${weekly.production_count} | 本周交付: ${weekly.delivery_count}` : '暂无周数据'}</div></div>
      <div class="panel"><div class="panel-header"><span>📆 月统计</span></div>
        <div class="panel-body" style="font-size:12px;color:var(--text-muted)">${monthly.production_count ? `本月生产: ${monthly.production_count} | 本月交付: ${monthly.delivery_count}` : '暂无月数据'}</div></div>
    </div>

    <!-- 管道监控 -->
    <div class="panel">
      <div class="panel-header"><span>🔧 管道监控</span></div>
      <div class="panel-body" id="monitorDisplay" style="font-size:12px;color:var(--text-muted)">加载中...</div>
    </div>`;

  // Draw charts
  setTimeout(() => {
    drawTrendChart();
    drawQualityChart();
    loadPerfRanking();
  }, 100);

  apiGet('/api/monitor/pipeline').then(m => {
    const el = $('monitorDisplay');
    if (el) el.innerHTML = `队列深度: ${m.queue_depth||0} | 运行中: ${m.running_tasks||0} | 成功率: ${(m.success_rate||0).toFixed(1)}%`;
  });
}

/* ===== 生产趋势折线图 (Canvas) ===== */
async function drawTrendChart() {
  const canvas = $('trendChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const pad = { top: 30, right: 30, bottom: 40, left: 50 };
  const pw = W - pad.left - pad.right;
  const ph = H - pad.top - pad.bottom;

  // Fetch real trend data from API; show empty state on failure (no mock fallback)
  var data = [];
  var labels = [];
  var days = 7;
  try {
    var trendResult = await apiGet('/api/ops/trend?period=7d');
    if (trendResult && trendResult.success && (trendResult.data?.points || trendResult.points)) {
      var points = trendResult.data?.points || trendResult.points || [];
      if (points.length > 0) {
        data = points.map(function(p) { return typeof p === 'object' ? (p.value || p.count || 0) : p; });
        labels = points.map(function(p, i) {
          if (typeof p === 'object' && p.date) return p.date;
          var d = new Date(Date.now() - (points.length - 1 - i) * 86400000);
          return (d.getMonth()+1) + '/' + d.getDate();
        });
        days = data.length;
      }
    }
  } catch(e) {
    // P2-2-W1: 不再 fallback 到 generated/random 数据, 失败时显示空状态
  }
  // P2-2-W1: 无数据时不再生成 random fake, 直接显示空
  if (data.length === 0) {
    if (window.toastInfo) window.toastInfo('趋势数据加载失败, 请稍后重试');
  }
  var maxVal = data.length ? Math.max.apply(null, data) : 100;

  // Clear
  ctx.clearRect(0, 0, W, H);

  // Background grid
  ctx.strokeStyle = 'rgba(42,42,74,0.5)';
  ctx.lineWidth = 0.5;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (ph / 4) * i;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(W - pad.right, y);
    ctx.stroke();
    // Y-axis labels
    ctx.fillStyle = '#666688';
    ctx.font = '9px sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(Math.round(maxVal * (1 - i/4)), pad.left - 6, y + 3);
  }

  // X-axis labels
  ctx.textAlign = 'center';
  const step = Math.floor(days / 6);
  for (let i = 0; i < days; i += step) {
    const x = pad.left + (pw / (days - 1)) * i;
    ctx.fillText(labels[i], x, H - pad.bottom + 14);
  }

  // Line
  ctx.strokeStyle = '#4a7aff';
  ctx.lineWidth = 2;
  ctx.beginPath();
  data.forEach((v, i) => {
    const x = pad.left + (pw / (days - 1)) * i;
    const y = pad.top + ph * (1 - v / maxVal);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Area fill
  ctx.lineTo(pad.left + pw, pad.top + ph);
  ctx.lineTo(pad.left, pad.top + ph);
  ctx.closePath();
  ctx.fillStyle = 'rgba(74,122,255,0.08)';
  ctx.fill();

  // Dots
  data.forEach((v, i) => {
    const x = pad.left + (pw / (days - 1)) * i;
    const y = pad.top + ph * (1 - v / maxVal);
    ctx.fillStyle = '#4a7aff';
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fill();
  });

  // Title
  ctx.fillStyle = '#8888aa';
  ctx.font = '10px sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText('生产量', pad.left, 16);
}

/* ===== 质量分布直方图 (Canvas) ===== */
async function drawQualityChart() {
  const canvas = $('qualityChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const pad = { top: 30, right: 20, bottom: 40, left: 50 };
  const pw = W - pad.left - pad.right;
  const ph = H - pad.top - pad.bottom;

  // Fetch real quality distribution from API; show empty state on failure (no mock fallback)
  var buckets = ['0-50', '50-60', '60-70', '70-80', '80-90', '90-100'];
  var counts = [0, 0, 0, 0, 0, 0];
  var qualityLoaded = false;
  try {
    var qualityResult = await apiGet('/api/quality/iaa/report');
    if (qualityResult && qualityResult.success && qualityResult.report) {
      var dist = qualityResult.report.score_distribution;
      if (dist && Array.isArray(dist) && dist.length >= 6) {
        counts = dist.slice(0, 6).map(function(v) { return typeof v === 'number' ? v : (v.count || 0); });
        qualityLoaded = true;
      }
    }
  } catch(e) {
    // P2-2-W1: 不再 fallback 到 mock, 失败时显示空状态
  }
  if (!qualityLoaded && window.toastInfo) {
    window.toastInfo('质量分布数据加载失败, 请稍后重试');
  }
  var maxCount = Math.max.apply(null, counts);
  const colors = ['#ef4444', '#f97316', '#fbbf24', '#4ade80', '#22c55e', '#16a34a'];

  ctx.clearRect(0, 0, W, H);

  // Grid
  ctx.strokeStyle = 'rgba(42,42,74,0.5)';
  ctx.lineWidth = 0.5;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (ph / 4) * i;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(W - pad.right, y);
    ctx.stroke();
    ctx.fillStyle = '#666688';
    ctx.font = '9px sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(Math.round(maxCount * (1 - i/4)), pad.left - 6, y + 3);
  }

  // Bars
  const barWidth = pw / buckets.length * 0.7;
  const gap = pw / buckets.length * 0.3;
  buckets.forEach((label, i) => {
    const barH = (counts[i] / maxCount) * ph;
    const x = pad.left + (pw / buckets.length) * i + gap / 2;
    const y = pad.top + ph - barH;

    // Bar with gradient
    const grad = ctx.createLinearGradient(x, y, x, pad.top + ph);
    grad.addColorStop(0, colors[i]);
    grad.addColorStop(1, colors[i] + '44');
    ctx.fillStyle = grad;
    ctx.fillRect(x, y, barWidth, barH);

    // Value on top
    ctx.fillStyle = '#e0e0f0';
    ctx.font = 'bold 10px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(counts[i], x + barWidth / 2, y - 6);

    // Label
    ctx.fillStyle = '#8888aa';
    ctx.font = '9px sans-serif';
    ctx.fillText(label, x + barWidth / 2, H - pad.bottom + 14);
  });

  // X-axis
  ctx.strokeStyle = '#2a2a4a';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top + ph);
  ctx.lineTo(W - pad.right, pad.top + ph);
  ctx.stroke();

  // Legend
  ctx.fillStyle = '#8888aa';
  ctx.font = '10px sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText('数据集数量', pad.left, 16);
}

/* ===== 人员绩效排行 ===== */
async function loadPerfRanking() {
  const tbody = $('perfTableBody');
  if (!tbody) return;

  // Fetch real personnel data from API; no mock fallback — empty state on failure
  var personnel = [];
  var personnelLoaded = false;
  try {
    var perfResult = await apiGet('/api/stats/personnel');
    if (perfResult && perfResult.success && (perfResult.data?.personnel || perfResult.personnel)) {
      var apiPersonnel = perfResult.data?.personnel || perfResult.personnel || [];
      if (apiPersonnel.length > 0) {
        personnel = apiPersonnel.map(function(p) {
          return {
            name: p.name || p.username || '--',
            role: p.role || '标注员',
            production: p.production || p.production_count || 0,
            annotation: p.annotation || p.annotation_count || 0,
            quality: p.quality || p.quality_score || 0,
            efficiency: p.efficiency || p.efficiency_score || 0,
            trend: p.trend
          };
        });
        personnelLoaded = true;
      }
    }
  } catch(e) {
    // P2-2-W1: 不再 fallback 到 mock, 失败时显示空状态
  }
  if (!personnelLoaded) {
    if (window.toastInfo) window.toastInfo('人员绩效数据加载失败');
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:30px;color:var(--text-muted)">暂无人员绩效数据</td></tr>';
    return;
  }

  const medals = ['🥇', '🥈', '🥉'];

  tbody.innerHTML = personnel.map((p, i) => {
    const trendIcon = p.trend > 0 ? '📈' : p.trend < 0 ? '📉' : '📊';
    const trendColor = p.trend > 0 ? 'var(--accent-green)' : p.trend < 0 ? 'var(--accent-red)' : 'var(--accent-orange)';
    return `<tr>
      <td style="text-align:center;font-weight:600">${i < 3 ? medals[i] : (i + 1)}</td>
      <td><strong>${p.name}</strong></td>
      <td style="color:var(--text-muted);font-size:11px">${p.role}</td>
      <td>${p.production}</td>
      <td>${p.annotation}</td>
      <td style="color:${p.quality >= 90 ? 'var(--accent-green)' : 'var(--accent-orange)'}">${p.quality}%</td>
      <td>
        <div style="display:flex;align-items:center;gap:6px">
          <div style="flex:1;height:4px;background:var(--bg-primary);border-radius:2px;overflow:hidden">
            <div style="height:100%;background:var(--accent-blue);border-radius:2px;width:${p.efficiency}%"></div>
          </div>
          <span style="font-size:10px;color:var(--text-muted)">${p.efficiency}%</span>
        </div>
      </td>
      <td style="text-align:center;color:${trendColor}">${trendIcon}</td>
    </tr>`;
  }).join('');
}

/* ===== 设置页面 ===== */
async function renderSettings() {
  const c = $('page-content'); if (!c) return;
  const user = getCurrentUser();
  const isAdmin = user?.role === 'admin';

  c.innerHTML = `
    <div style="margin-bottom:16px">
      <h2 style="font-size:18px;font-weight:600;margin-bottom:4px">⚙️ 系统设置</h2>
      <p style="font-size:12px;color:var(--text-muted)">用户设置 · API Key管理 · ${isAdmin ? '管理员面板' : '账户信息'}</p>
    </div>

    <!-- Settings Tabs -->
    <div id="settingsTabs" style="display:flex;gap:2px;margin-bottom:16px;border-bottom:1px solid var(--border)">
      <div class="settings-tab active" data-stab="user" onclick="switchSettingsTab('user')">👤 用户设置</div>
      ${isAdmin ? '<div class="settings-tab" data-stab="admin" onclick="switchSettingsTab(\'admin\')">🛡️ 管理员面板</div>' : ''}
    </div>

    <!-- User Settings Page -->
    <div id="settingsPageUser" style="display:grid;gap:12px">
      <!-- Profile Card -->
      <div class="panel">
        <div class="panel-header"><span>👤 个人信息</span></div>
        <div class="panel-body" id="settingsProfile" style="font-size:13px;line-height:2">
          <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">
            <div style="width:48px;height:48px;border-radius:50%;background:var(--accent-blue);display:flex;align-items:center;justify-content:center;font-size:22px;color:#fff">${(user?.username||'U')[0].toUpperCase()}</div>
            <div>
              <div style="font-weight:600;font-size:15px" id="spUsername">--</div>
              <div style="font-size:11px;color:var(--text-muted)" id="spRole">--</div>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px">
            <div><span style="color:var(--text-muted)">用户名:</span> <span id="spUsername2">--</span></div>
            <div><span style="color:var(--text-muted)">邮箱:</span> <span id="spEmail">--</span></div>
            <div><span style="color:var(--text-muted)">角色:</span> <span id="spRole2">--</span></div>
            <div><span style="color:var(--text-muted)">注册时间:</span> <span id="spCreated">--</span></div>
          </div>
        </div>
      </div>

      <!-- Quota Usage Card -->
      <div class="panel">
        <div class="panel-header"><span>📊 配额使用情况</span></div>
        <div class="panel-body" id="settingsQuota" style="font-size:12px">
          <div style="display:grid;gap:12px">
            <div>
              <div style="display:flex;justify-content:space-between;margin-bottom:4px">
                <span style="color:var(--text-muted)">API 调用</span>
                <span id="sqApi">0 / 10,000</span>
              </div>
              <div style="height:6px;background:var(--bg-primary);border-radius:3px;overflow:hidden">
                <div id="sqApiBar" style="height:100%;background:var(--accent-blue);border-radius:3px;width:0%;transition:width 0.5s"></div>
              </div>
            </div>
            <div>
              <div style="display:flex;justify-content:space-between;margin-bottom:4px">
                <span style="color:var(--text-muted)">存储</span>
                <span id="sqStorage">0 MB / 1,024 MB</span>
              </div>
              <div style="height:6px;background:var(--bg-primary);border-radius:3px;overflow:hidden">
                <div id="sqStorageBar" style="height:100%;background:var(--accent-green);border-radius:3px;width:0%;transition:width 0.5s"></div>
              </div>
            </div>
            <div>
              <div style="display:flex;justify-content:space-between;margin-bottom:4px">
                <span style="color:var(--text-muted)">数据集</span>
                <span id="sqDatasets">0 / 50</span>
              </div>
              <div style="height:6px;background:var(--bg-primary);border-radius:3px;overflow:hidden">
                <div id="sqDatasetsBar" style="height:100%;background:var(--accent-orange);border-radius:3px;width:0%;transition:width 0.5s"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Change Password Card -->
      <div class="panel">
        <div class="panel-header"><span>🔒 修改密码</span></div>
        <div class="panel-body" style="display:grid;gap:10px;max-width:360px">
          <div id="pwdMsg" style="display:none;padding:8px;border-radius:4px;font-size:12px"></div>
          <input id="pwdCurrent" type="password" placeholder="当前密码" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
          <input id="pwdNew" type="password" placeholder="新密码(至少6字符)" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
          <input id="pwdConfirm" type="password" placeholder="确认新密码" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
          <button onclick="changePassword()" style="padding:10px;background:var(--accent-blue);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:13px">更新密码</button>
        </div>
      </div>

      <!-- API Key Management Card -->
      <div class="panel">
        <div class="panel-header">
          <span>🔑 API Key 管理</span>
          <span class="action" onclick="generateApiKey()">+ 生成新Key</span>
        </div>
        <div class="panel-body">
          <div id="settingsApiKeyList" style="font-size:12px;color:var(--text-muted)">加载中...</div>
        </div>
      </div>
    </div>

    <!-- Admin Panel Page -->
    ${isAdmin ? `
    <div id="settingsPageAdmin" style="display:none;gap:12px">
      <div class="panel">
        <div class="panel-header">
          <span>👥 用户列表</span>
          <span style="font-size:11px;color:var(--text-muted)">共 <strong id="adminUserCount">0</strong> 人</span>
        </div>
        <div class="panel-body" style="padding:0">
          <div id="adminUserTableContainer" style="overflow-x:auto">
            <table class="data-table">
              <thead><tr>
                <th>ID</th><th>用户名</th><th>邮箱</th><th>角色</th><th>状态</th><th>配额(API)</th><th>配额(存储)</th><th>注册时间</th><th>操作</th>
              </tr></thead>
              <tbody id="adminUserTableBody">
                <tr><td colspan="9" style="text-align:center;padding:30px;color:var(--text-muted)">加载中...</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Quota Bulk Settings -->
      <div class="panel">
        <div class="panel-header"><span>📊 默认配额设置</span></div>
        <div class="panel-body" style="display:grid;gap:12px;max-width:480px">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            <div>
              <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px">默认API调用配额</label>
              <input id="adminDefaultApiQuota" type="number" value="10000" style="width:100%;padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
            </div>
            <div>
              <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px">默认存储配额(MB)</label>
              <input id="adminDefaultStorageQuota" type="number" value="1024" style="width:100%;padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
            </div>
            <div>
              <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px">默认数据集配额</label>
              <input id="adminDefaultDatasetQuota" type="number" value="50" style="width:100%;padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary)">
            </div>
          </div>
          <button onclick="saveDefaultQuotas()" style="padding:10px;background:var(--accent-blue);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:13px">保存默认配额</button>
        </div>
      </div>
    </div>
    ` : ''}

    <!-- System Health (always shown at bottom) -->
    <div class="panel" style="margin-top:${isAdmin ? '12px' : '12px'}">
      <div class="panel-header"><span>🟢 系统健康</span></div>
      <div class="panel-body" id="settingsHealth" style="font-size:12px;line-height:2">
        加载中...
      </div>
    </div>
  `;

  // Inject CSS for settings tabs
  if (!document.getElementById('settings-tab-style')) {
    const style = document.createElement('style');
    style.id = 'settings-tab-style';
    style.textContent = `
      .settings-tab {
        padding: 8px 20px;
        cursor: pointer;
        font-size: 13px;
        font-weight: 500;
        color: var(--text-muted);
        border-bottom: 2px solid transparent;
        transition: all 0.2s;
      }
      .settings-tab:hover { color: var(--text-primary); }
      .settings-tab.active {
        color: var(--accent-blue);
        border-bottom-color: var(--accent-blue);
      }
    `;
    document.head.appendChild(style);
  }

  // Load user profile
  loadUserProfile();
  // Load quota
  loadUserQuota();
  // Load API keys
  loadSettingsApiKeys();
  // Load system health
  loadSystemHealth();
  // Load admin panel if admin
  if (isAdmin) loadAdminUsers();
}

/* Settings tab switching */
function switchSettingsTab(tab) {
  document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
  const tabEl = document.querySelector(`.settings-tab[data-stab="${tab}"]`);
  if (tabEl) tabEl.classList.add('active');

  const userPage = document.getElementById('settingsPageUser');
  const adminPage = document.getElementById('settingsPageAdmin');
  if (userPage) userPage.style.display = tab === 'user' ? '' : 'none';
  if (adminPage) adminPage.style.display = tab === 'admin' ? '' : 'none';
}

/* Load user profile from API */
async function loadUserProfile() {
  const data = await apiGet('/auth/me').catch(() => ({}));
  const user = data.data?.user || data.user || getCurrentUser() || {};
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val || '--'; };
  set('spUsername', user.username);
  set('spUsername2', user.username);
  set('spRole', user.role || 'user');
  set('spRole2', user.role || 'user');
  set('spEmail', user.email || '--');
  set('spCreated', user.created_at ? new Date(user.created_at).toLocaleDateString('zh-CN') : '--');
}

/* Load user quota */
async function loadUserQuota() {
  const data = await apiGet('/api/v1/user/quota').catch(() => ({}));
  const q = data.data || data || {};
  const apiUsed = q.api_calls_used || 0;
  const apiLimit = q.api_calls_limit || 10000;
  const storageUsed = q.storage_used_mb || 0;
  const storageLimit = q.storage_limit_mb || 1024;
  const dsUsed = q.datasets_used || 0;
  const dsLimit = q.datasets_limit || 50;

  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  set('sqApi', `${apiUsed.toLocaleString()} / ${apiLimit.toLocaleString()}`);
  set('sqStorage', `${storageUsed.toLocaleString()} MB / ${storageLimit.toLocaleString()} MB`);
  set('sqDatasets', `${dsUsed} / ${dsLimit}`);

  const pct = (used, limit) => Math.min(100, Math.round((used / Math.max(limit, 1)) * 100));
  const bar = document.getElementById('sqApiBar'); if (bar) bar.style.width = pct(apiUsed, apiLimit) + '%';
  const bar2 = document.getElementById('sqStorageBar'); if (bar2) bar2.style.width = pct(storageUsed, storageLimit) + '%';
  const bar3 = document.getElementById('sqDatasetsBar'); if (bar3) bar3.style.width = pct(dsUsed, dsLimit) + '%';
}

/* Load API Keys for settings page */
async function loadSettingsApiKeys() {
  const data = await apiGet('/api/v1/api-keys').catch(() => ({}));
  const keys = data.data || data.keys || [];
  const el = document.getElementById('settingsApiKeyList');
  if (!el) return;
  if (keys.length === 0) {
    el.innerHTML = '<p style="padding:8px 0">暂无API Key，点击上方"生成新Key"创建</p>';
  } else {
    el.innerHTML = keys.map(k => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)">
        <div>
          <div style="font-weight:500">${k.name || '未命名Key'}</div>
          <code style="font-size:11px;color:var(--accent-blue);user-select:text">${(k.key || k.prefix || '').slice(0,24)}${(k.key||'').length > 24 ? '...' : ''}</code>
          <div style="font-size:10px;color:var(--text-muted);margin-top:2px">
            创建: ${k.created_at ? new Date(k.created_at).toLocaleDateString('zh-CN') : '--'} ·
            过期: ${k.expires_at ? new Date(k.expires_at).toLocaleDateString('zh-CN') : '永不过期'}
          </div>
        </div>
        <div style="display:flex;gap:6px;align-items:center">
          <span style="font-size:11px;color:${k.status==='active'?'var(--accent-green)':'var(--accent-red)'}">${k.status==='active'?'● 活跃':'○ 已吊销'}</span>
          <button style="padding:4px 8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);cursor:pointer;font-size:11px" onclick="copyApiKey('${(k.key||'').replace(/'/g,"\\'")}')">📋 复制</button>
          ${k.status === 'active' ? `<button style="padding:4px 8px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:4px;color:var(--accent-red);cursor:pointer;font-size:11px" onclick="revokeApiKey('${(k.id||'').replace(/'/g,"\\'")}')">吊销</button>` : ''}
        </div>
      </div>
    `).join('');
  }
}

/* Generate new API Key */
async function generateApiKey() {
  const name = prompt('请输入API Key名称（便于识别）：', 'key-' + Date.now().toString(36));
  if (!name) return;
  const result = await apiPost('/api/v1/api-keys/create', { name });
  if (result.success && result.data?.key) {
    // Show the full key once
    showModal(`
      <span class="modal-close" onclick="closeModal()">✕</span>
      <h4 style="margin-bottom:12px;color:var(--accent-green)">✅ API Key 已生成</h4>
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:8px">请立即复制此Key，关闭后将无法再次查看完整Key：</p>
      <div style="background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;padding:12px;font-family:monospace;font-size:12px;word-break:break-all;color:var(--accent-blue);user-select:all;margin-bottom:12px">${result.data.key}</div>
      <button style="padding:8px 20px;background:var(--accent-blue);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:13px" onclick="navigator.clipboard.writeText('${result.data.key.replace(/'/g,"\\'")}');closeModal();loadSettingsApiKeys()">📋 已复制，关闭</button>
    `);
  } else {
    (window.toastError || ((m) => alert(m)))('创建失败: ' + (result.error || '未知错误'));
  }
  loadSettingsApiKeys();
}

/* Copy API Key to clipboard */
function copyApiKey(key) {
  if (!key) return;
  navigator.clipboard.writeText(key).then(() => {
    // Brief visual feedback
    const btns = document.querySelectorAll('button');
    btns.forEach(b => { if (b.textContent.includes('复制') && b.onclick.toString().includes(key.slice(0,8))) { b.textContent = '✅ 已复制'; setTimeout(() => { b.textContent = '📋 复制'; }, 1500); } });
  }).catch(() => (window.toastError || ((m) => alert(m)))('复制失败,请手动选择Key文本'));
}

/* Revoke API Key */
async function revokeApiKey(id) {
  if (!id) return;
  if (!confirm('确定要吊销此API Key吗？吊销后使用此Key的请求将立即失效。')) return;
  await apiPost(`/api/v1/api-keys/${id}/revoke`);
  loadSettingsApiKeys();
}

/* Change password */
async function changePassword() {
  const current = document.getElementById('pwdCurrent')?.value || '';
  const newPwd = document.getElementById('pwdNew')?.value || '';
  const confirm = document.getElementById('pwdConfirm')?.value || '';
  const msg = document.getElementById('pwdMsg');

  if (!current) { showPwdMsg('请输入当前密码', 'error'); return; }
  if (!newPwd || newPwd.length < 6) { showPwdMsg('新密码至少需要6个字符', 'error'); return; }
  if (newPwd !== confirm) { showPwdMsg('两次输入的新密码不一致', 'error'); return; }

  const result = await apiPost('/auth/change-password', {
    current_password: current,
    new_password: newPwd
  });

  if (result.success) {
    showPwdMsg('✅ 密码修改成功', 'success');
    document.getElementById('pwdCurrent').value = '';
    document.getElementById('pwdNew').value = '';
    document.getElementById('pwdConfirm').value = '';
  } else {
    showPwdMsg('❌ ' + (result.error || '密码修改失败'), 'error');
  }
}

function showPwdMsg(text, type) {
  const msg = document.getElementById('pwdMsg');
  if (!msg) return;
  msg.textContent = text;
  msg.style.display = 'block';
  msg.style.background = type === 'success' ? 'rgba(74,222,128,0.1)' : 'rgba(239,68,68,0.1)';
  msg.style.color = type === 'success' ? 'var(--accent-green)' : 'var(--accent-red)';
  msg.style.border = '1px solid ' + (type === 'success' ? 'rgba(74,222,128,0.3)' : 'rgba(239,68,68,0.3)');
  setTimeout(() => { if (msg) msg.style.display = 'none'; }, 4000);
}

/* Load system health */
async function loadSystemHealth() {
  const health = await apiGet('/api/v1/health').catch(() => ({}));
  const el = document.getElementById('settingsHealth');
  if (!el) return;
  el.innerHTML = `
    <p>服务状态: <span style="color:${health.status==='ok'?'var(--accent-green)':'var(--accent-red)'}">${health.status||'unknown'}</span></p>
    <p>版本: ${health.version||'3.0.0'}</p>
    <p>数据库: ${health.database||'未知'}</p>
    <p>运行时间: ${health.uptime||'--'}</p>
  `;
}

/* ===== Admin Panel Functions ===== */

async function loadAdminUsers() {
  const data = await apiGet('/api/v1/admin/users').catch(() => ({}));
  const users = data.data?.users || data.users || [];
  const tbody = document.getElementById('adminUserTableBody');
  const countEl = document.getElementById('adminUserCount');
  if (countEl) countEl.textContent = users.length;

  if (!tbody) return;
  if (users.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:30px;color:var(--text-muted)">暂无用户数据</td></tr>';
    return;
  }

  tbody.innerHTML = users.map(u => `
    <tr id="adminUserRow-${u.id || ''}">
      <td style="font-size:11px;color:var(--text-muted)">${(u.id||'').slice(0,8)}</td>
      <td><strong>${u.username||'--'}</strong></td>
      <td style="font-size:11px">${u.email||'--'}</td>
      <td>
        <select onchange="updateUserRole('${u.id||''}', this.value)" style="padding:4px 6px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px">
          <option value="user" ${u.role==='user'?'selected':''}>用户</option>
          <option value="annotator" ${u.role==='annotator'?'selected':''}>标注员</option>
          <option value="reviewer" ${u.role==='reviewer'?'selected':''}>审核员</option>
          <option value="admin" ${u.role==='admin'?'selected':''}>管理员</option>
          <option value="viewer" ${u.role==='viewer'?'selected':''}>只读</option>
        </select>
      </td>
      <td>
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:11px">
          <input type="checkbox" ${u.disabled ? '' : 'checked'} onchange="toggleUserStatus('${u.id||''}', this.checked)" style="accent-color:var(--accent-blue)">
          <span style="color:${u.disabled ? 'var(--accent-red)' : 'var(--accent-green)'}">${u.disabled ? '已禁用' : '已启用'}</span>
        </label>
      </td>
      <td>
        <input type="number" value="${u.api_quota || 10000}" onchange="updateUserQuota('${u.id||''}', 'api', this.value)" style="width:80px;padding:4px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px">
      </td>
      <td>
        <input type="number" value="${u.storage_quota_mb || 1024}" onchange="updateUserQuota('${u.id||''}', 'storage', this.value)" style="width:80px;padding:4px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:11px">
      </td>
      <td style="font-size:11px;color:var(--text-muted)">${u.created_at ? new Date(u.created_at).toLocaleDateString('zh-CN') : '--'}</td>
      <td>
        <button style="padding:4px 8px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:4px;color:var(--accent-red);cursor:pointer;font-size:11px" onclick="deleteUser('${u.id||''}','${u.username||''}')">删除</button>
      </td>
    </tr>
  `).join('');
}

async function updateUserRole(userId, newRole) {
  if (!userId) return;
  const result = await apiPut('/api/v1/admin/users/' + userId + '/role', { role: newRole });
  if (!result.success) {
    (window.toastError || ((m) => alert(m)))('更新角色失败: ' + (result.error || '未知错误'));
    loadAdminUsers();
  }
}

async function toggleUserStatus(userId, enabled) {
  if (!userId) return;
  const result = await apiPost('/api/v1/admin/users/' + userId + '/toggle-status', { disabled: !enabled });
  if (!result.success) {
    (window.toastError || ((m) => alert(m)))('更新状态失败: ' + (result.error || '未知错误'));
    loadAdminUsers();
  }
}

function updateUserQuota(userId, quotaType, value) {
  if (!userId) return;
  // Debounce: use timeout to batch save
  if (updateUserQuota._timers && updateUserQuota._timers[userId + quotaType]) {
    clearTimeout(updateUserQuota._timers[userId + quotaType]);
  }
  if (!updateUserQuota._timers) updateUserQuota._timers = {};
  updateUserQuota._timers[userId + quotaType] = setTimeout(async () => {
    const num = parseInt(value, 10);
    if (isNaN(num) || num < 0) return;
    const body = quotaType === 'api' ? { api_quota: num } : { storage_quota_mb: num };
    const result = await apiPut('/api/v1/admin/users/' + userId + '/quota', body);
    if (!result.success) {
      (window.toastError || ((m) => alert(m)))('更新配额失败: ' + (result.error || '未知错误'));
      loadAdminUsers();
    }
  }, 600);
}

async function deleteUser(userId, username) {
  if (!userId) return;
  if (!confirm(`确定要永久删除用户 "${username}" 吗？此操作不可撤销！`)) return;
  const result = await apiDelete('/api/v1/admin/users/' + userId);
  if (result.success) {
    loadAdminUsers();
  } else {
    (window.toastError || ((m) => alert(m)))('删除失败: ' + (result.error || '未知错误'));
  }
}

async function saveDefaultQuotas() {
  const apiQuota = parseInt(document.getElementById('adminDefaultApiQuota')?.value, 10) || 10000;
  const storageQuota = parseInt(document.getElementById('adminDefaultStorageQuota')?.value, 10) || 1024;
  const datasetQuota = parseInt(document.getElementById('adminDefaultDatasetQuota')?.value, 10) || 50;

  const result = await apiPut('/api/v1/admin/defaults/quota', {
    api_calls_limit: apiQuota,
    storage_limit_mb: storageQuota,
    datasets_limit: datasetQuota
  });

  if (result.success) {
    (window.toastOk || ((m) => alert(m)))('默认配额已保存');
  } else {
    (window.toastError || ((m) => alert(m)))('保存失败: ' + (result.error || '未知错误'));
  }
}
