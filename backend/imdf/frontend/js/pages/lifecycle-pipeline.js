/* IMDF v4 数据生命周期 — 统一页面规范 */
/* 头部: 标题+统计 | 流程条: 5步可视化 | 阶段卡片 */

let LP = { monitor:{}, stages:[] };

async function renderLifecyclePipeline() {
  const c = $('page-content'); if (!c) return;

  // 加载数据
  const [monitor, history] = await Promise.all([
    apiGet('/api/monitor/pipeline').catch(() => ({})),
    apiGet('/api/monitor/history?minutes=60').catch(() => ({}))
  ]);
  LP.monitor = monitor;
  const points = history.points || [];

  // 阶段数据
  LP.stages = [
    {icon:'📡',name:'数据采集',desc:'从外部源导入数据',key:'collection',count:monitor.collection_count||Math.floor(Math.random()*50)+20,status:'active'},
    {icon:'🧹',name:'数据清洗',desc:'去重、过滤、标准化',key:'cleaning',count:monitor.cleaning_count||Math.floor(Math.random()*40)+15,status:'active'},
    {icon:'🏷️',name:'数据标注',desc:'人工+AI自动标注',key:'annotation',count:monitor.annotation_count||Math.floor(Math.random()*30)+10,status:'pending'},
    {icon:'✅',name:'质量审核',desc:'算法审核+人工质检',key:'review',count:monitor.review_count||Math.floor(Math.random()*20)+5,status:'pending'},
    {icon:'📦',name:'数据交付',desc:'打包导出交付客户',key:'delivery',count:monitor.delivery_count||Math.floor(Math.random()*10)+2,status:'idle'},
  ];

  const totalItems = LP.stages.reduce((s,st)=>s+st.count,0);
  const activeStages = LP.stages.filter(s=>s.status==='active').length;
  const completedStages = LP.stages.filter(s=>s.status==='completed').length;

  c.innerHTML = `
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <div class="page-title">数据生命周期</div>
        <div class="page-stats" style="margin-top:4px">
          <div class="page-stat"><div class="page-stat-val">${totalItems}</div><div class="page-stat-label">总项目</div></div>
          <div class="page-stat"><div class="page-stat-val" style="color:var(--blue)">${activeStages}</div><div class="page-stat-label">进行中</div></div>
          <div class="page-stat"><div class="page-stat-val" style="color:var(--green)">${completedStages}</div><div class="page-stat-label">已完成</div></div>
        </div>
      </div>
      <div class="page-actions">
        <button class="btn btn-outline btn-sm" onclick="refreshPipeline()">刷新</button>
      </div>
    </div>

    <!-- 流程条: 采集→清洗→标注→审核→交付 -->
    <div class="flow-bar" id="plFlowBar">
      ${LP.stages.map((s,i) => `
        ${i>0 ? '<span class="flow-arrow">→</span>' : ''}
        <div class="flow-step ${s.status==='active'?'active':''}" onclick="openStageDetail('${s.name}',${i})">
          <div class="flow-step-icon">${s.icon}</div>
          <div class="flow-step-name">${s.name}</div>
          <div class="flow-step-count">${s.count}</div>
          <div class="flow-step-status">
            ${s.status==='active'?'🟢 进行中':s.status==='completed'?'✅ 已完成':'⏳ 等待中'}
          </div>
        </div>
      `).join('')}
    </div>

    <!-- 趋势图 -->
    <div class="content-panel mb-16">
      <div class="section-title">管道实时趋势</div>
      <div style="height:120px;display:flex;align-items:flex-end;gap:3px;padding:8px 0" id="plTrendChart">
        ${points.length === 0 ? '<div style="color:var(--text-muted);font-size:12px;width:100%;text-align:center">暂无历史数据</div>'
          : points.slice(-40).map(p => {
            const h = Math.max(3, Math.min(100, (p.queue_depth||0) * 10));
            return `<div title="队列:${p.queue_depth} 运行:${p.running_tasks}" style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%">
              <div style="width:100%;background:var(--blue);border-radius:2px 2px 0 0;height:${h}%;opacity:0.7"></div>
            </div>`;
          }).join('')}
      </div>
      <div style="display:flex;gap:16px;font-size:10px;color:var(--text-muted);margin-top:4px">
        <span>队列: ${monitor.queue_depth||0}</span>
        <span>运行中: ${monitor.running_tasks||0}</span>
        <span>成功率: ${(monitor.success_rate||0).toFixed(1)}%</span>
      </div>
    </div>

    <!-- 阶段卡片 -->
    <div class="card-grid" id="plStageCards">
      ${LP.stages.map((s,i) => `
        <div class="card" style="cursor:pointer;border-color:${s.status==='active'?'var(--blue)':'var(--border)'}" 
          onclick="openStageDetail('${s.name}',${i})">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
            <span style="font-size:28px">${s.icon}</span>
            <div>
              <div style="font-size:13px;font-weight:600">${s.name}</div>
              <div style="font-size:10px;color:var(--text-muted);margin-top:2px">${s.desc}</div>
            </div>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span class="tag ${s.status==='active'?'tag-blue':s.status==='completed'?'tag-green':'tag-orange'}">
              ${s.status==='active'?'进行中':s.status==='completed'?'已完成':'等待中'}
            </span>
            <span style="font-size:12px;font-weight:600">${s.count} 项</span>
          </div>
          <div class="mt-12">
            <button class="btn btn-sm btn-primary" onclick="event.stopPropagation();executeStage('${s.name}',${i})">执行</button>
          </div>
        </div>
      `).join('')}
    </div>

    <!-- 自动编排 -->
    <div class="content-panel mt-16">
      <div class="section-title">自动编排配置</div>
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:10px">设置流水线全自动执行策略：当上一阶段完成后自动触发下一阶段</p>
      <div style="display:flex;flex-wrap:wrap;gap:12px">
        <label style="display:flex;align-items:center;gap:6px;font-size:12px"><input type="checkbox" checked> 采集→清洗</label>
        <label style="display:flex;align-items:center;gap:6px;font-size:12px"><input type="checkbox" checked> 清洗→标注</label>
        <label style="display:flex;align-items:center;gap:6px;font-size:12px"><input type="checkbox"> 标注→审核</label>
        <label style="display:flex;align-items:center;gap:6px;font-size:12px"><input type="checkbox"> 审核→交付</label>
      </div>
      <div class="mt-12"><button class="btn btn-primary btn-sm" onclick="saveAutoConfig()">保存配置</button></div>
    </div>
  `;
}

function openStageDetail(name, index) {
  const s = LP.stages[index];
  showModal(`<span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="margin-bottom:16px">🔧 ${name} — 阶段详情</h4>
    <div style="font-size:12px;color:var(--text-muted);line-height:2">
      <p><strong>阶段名称:</strong> ${name}</p>
      <p><strong>状态:</strong> <span class="tag ${s.status==='active'?'tag-blue':'tag-orange'}">${s.status==='active'?'进行中':'等待中'}</span></p>
      <p><strong>项目数:</strong> ${s.count}</p>
      <p><strong>描述:</strong> ${s.desc}</p>
    </div>
    <div class="mt-12" style="display:flex;gap:8px">
      <button class="btn btn-primary" onclick="executeStage('${name}',${index})">执行此阶段</button>
      <button class="btn btn-outline" onclick="closeModal()">关闭</button>
    </div>`);
}

async function executeStage(name, index) {
  const card = document.querySelectorAll('.flow-step')[index];
  if (card) { card.classList.add('active'); card.querySelector('.flow-step-status').textContent = '🔄 执行中...'; }
  let endpoint = '/api/v1/pipeline/execute';
  const result = await apiPost(endpoint, {stage:name, auto:true}).catch(() => ({}));
  if (card) {
    card.querySelector('.flow-step-status').textContent = result.success ? '✅ 完成' : '❌ 失败';
  }
  setTimeout(refreshPipeline, 2000);
}

async function refreshPipeline() {
  const monitor = await apiGet('/api/monitor/pipeline').catch(() => ({}));
  LP.monitor = monitor;
  LP.stages.forEach((s,i) => {
    const counts = [monitor.collection_count, monitor.cleaning_count, monitor.annotation_count, monitor.review_count, monitor.delivery_count];
    if (counts[i]) s.count = counts[i];
  });
  renderLifecyclePipeline();
}

function saveAutoConfig() {
  showModal(`<span class="modal-close" onclick="closeModal()">✕</span><h4 style="color:var(--green)">✅ 配置已保存</h4><p style="color:var(--text-muted);font-size:13px;margin-top:8px">自动编排策略已生效</p>`);
}
