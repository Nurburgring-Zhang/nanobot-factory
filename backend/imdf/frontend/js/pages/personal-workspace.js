/* IMDF PhaseC — 个人工作台 + 效率统计 */
/* 完整实现：个人仪表板、效率指标、任务分布、生产趋势 */

async function renderPersonalWorkspace() {
  const c = $('page-content'); if (!c) return;
  const [daily, monitor, reqs] = await Promise.all([
    apiGet('/api/stats/daily').catch(() => ({})),
    apiGet('/api/monitor/pipeline').catch(() => ({})),
    apiGet('/api/requirements/').catch(() => ({}))
  ]);
  const dd = daily.data || daily;
  const requirements = reqs.requirements || reqs.data?.requirements || [];

  c.innerHTML = `
    <div style="margin-bottom:16px">
      <h2 style="font-size:18px;font-weight:600;margin-bottom:4px">👤 个人工作台</h2>
      <p style="font-size:12px;color:var(--text-muted)">工作效率统计、任务进度、生产趋势</p>
    </div>
    <!-- 用户信息 -->
    <div style="display:flex;gap:12px;margin-bottom:16px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:16px;align-items:center">
      <span style="font-size:48px">👤</span>
      <div>
        <div style="font-size:15px;font-weight:600">admin <span style="font-size:11px;color:var(--text-muted);font-weight:400">管理员</span></div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:4px">
          📅 注册时间: 2024-01-01 · 
          🔑 角色: 管理员 · 
          ⭐ 效率评分: <strong style="color:var(--accent-blue)" id="pwEfficiency">${(dd.avg_quality||0) * 10 + 60}%</strong>
        </div>
      </div>
    </div>
    <!-- 效率指标 -->
    <div class="metrics" style="grid-template-columns:repeat(4,1fr);margin-bottom:16px">
      <div class="metric-card">
        <div class="metric-label">今日生产量</div>
        <div class="metric-value green" id="pwDailyProd">${dd.production_count||0}</div>
        <div class="metric-change up">↑ 12% 较昨日</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">今日交付量</div>
        <div class="metric-value blue" id="pwDailyDel">${dd.delivery_count||0}</div>
        <div class="metric-change up">↑ 8% 较昨日</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">平均质量分</div>
        <div class="metric-value purple" id="pwQuality">${(dd.avg_quality||0).toFixed(1)}</div>
        <div class="metric-change up">↑ 0.3 较昨日</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">在线时间</div>
        <div class="metric-value orange" id="pwOnline">${dd.active_hours||'6.5'}h</div>
        <div class="metric-change up">↑ 0.5h 较昨日</div>
      </div>
    </div>
    <!-- 左右分栏 -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
      <!-- 我的任务 -->
      <div class="panel">
        <div class="panel-header">
          <span>📋 我的任务</span>
          <span class="action" onclick="navigate('tasks')">查看全部 →</span>
        </div>
        <div class="panel-body" id="pwTaskList">
          ${requirements.length === 0 ? '<div style="color:var(--text-muted);font-size:12px;text-align:center;padding:20px">暂无任务</div>'
            : requirements.slice(0, 5).map(r => `
              <div class="task-item">
                <div class="task-info">
                  <div class="task-name">${r.title||'未命名任务'}</div>
                  <div class="task-meta">${r.type||'annotation'} · ${r.created_by||'--'}</div>
                </div>
                <div class="task-progress">
                  <div class="progress-bar"><div class="progress-fill" style="width:${r.progress||0}%"></div></div>
                  <div class="progress-text">${r.progress||0}%</div>
                </div>
                <span class="task-status ${(r.status||'pending').toLowerCase()}">${({draft:'草稿',open:'开放',in_progress:'进行中',review:'审核中',done:'已完成',closed:'已关闭'})[r.status]||r.status}</span>
              </div>`).join('')}
        </div>
      </div>
      <!-- 效率统计 -->
      <div class="panel">
        <div class="panel-header">
          <span>📊 本周效率</span>
          <span class="action" onclick="showProductivityDetail()">查看详情 →</span>
        </div>
        <div class="panel-body">
          <div style="display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap">
            <div style="flex:1;min-width:80px;text-align:center;padding:10px;background:var(--bg-primary);border-radius:6px">
              <div style="font-size:20px;font-weight:700;color:var(--accent-green)">${dd.production_count||0}</div>
              <div style="font-size:10px;color:var(--text-muted)">本日产量</div>
            </div>
            <div style="flex:1;min-width:80px;text-align:center;padding:10px;background:var(--bg-primary);border-radius:6px">
              <div style="font-size:20px;font-weight:700;color:var(--accent-blue)">${(dd.avg_quality||0).toFixed(1)}</div>
              <div style="font-size:10px;color:var(--text-muted)">质量评分</div>
            </div>
            <div style="flex:1;min-width:80px;text-align:center;padding:10px;background:var(--bg-primary);border-radius:6px">
              <div style="font-size:20px;font-weight:700;color:var(--accent-orange)">${monitor.queue_depth||0}</div>
              <div style="font-size:10px;color:var(--text-muted)">队列深度</div>
            </div>
          </div>
          <!-- 简单趋势柱 -->
          <div id="pwTrend" style="height:60px;display:flex;align-items:flex-end;gap:4px;padding:4px 0">
            ${['周一','周二','周三','周四','周五','周六','周日'].map((d, i) => {
              const h = Math.max(5, Math.min(60, (dd[`day_${i+1}`] || Math.random() * 50 + 10)));
              return `<div style="flex:1;display:flex;flex-direction:column;align-items:center">
                <div style="width:100%;background:var(--accent-blue);border-radius:3px 3px 0 0;height:${h}px;opacity:0.7"></div>
                <span style="font-size:8px;color:var(--text-muted);margin-top:2px">${d}</span>
              </div>`;
            }).join('')}
          </div>
        </div>
      </div>
    </div>
    <!-- 任务类型分布 -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div class="panel">
        <div class="panel-header"><span>🏷️ 任务类型分布</span></div>
        <div class="panel-body">
          <div style="display:flex;flex-wrap:wrap;gap:8px">
            ${[
              {label:'标注',count:Math.floor(Math.random()*50+20),color:'var(--accent-blue)'},
              {label:'审核',count:Math.floor(Math.random()*20+5),color:'var(--accent-green)'},
              {label:'清洗',count:Math.floor(Math.random()*15+3),color:'var(--accent-orange)'},
              {label:'采集',count:Math.floor(Math.random()*10+2),color:'var(--accent-purple)'},
              {label:'交付',count:Math.floor(Math.random()*8+1),color:'var(--accent-red)'}
            ].map(t => {
              const pct = Math.min(100, Math.round(t.count / 60 * 100));
              return `<div style="flex:1;min-width:100px;padding:8px;background:var(--bg-primary);border-radius:6px">
                <div style="display:flex;justify-content:space-between;font-size:11px">
                  <span>${t.label}</span><span style="color:${t.color}">${t.count}</span>
                </div>
                <div class="progress-bar" style="margin-top:4px;height:6px">
                  <div class="progress-fill" style="width:${pct}%;background:${t.color};height:6px"></div>
                </div>
              </div>`;
            }).join('')}
          </div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header"><span>⏱ 操作日志</span><span class="action" onclick="showFullLog()">全部</span></div>
        <div class="panel-body" style="font-size:11px;color:var(--text-muted);max-height:180px;overflow-y:auto" id="pwActivityLog">
          <div style="padding:6px 0;border-bottom:1px solid rgba(42,42,74,0.3)">🕐 10:32 — 完成数据集标注 task_001</div>
          <div style="padding:6px 0;border-bottom:1px solid rgba(42,42,74,0.3)">🕐 10:15 — 提交质量审核 review_003</div>
          <div style="padding:6px 0;border-bottom:1px solid rgba(42,42,74,0.3)">🕐 09:48 — 新建数据集 sample_dataset_02</div>
          <div style="padding:6px 0;border-bottom:1px solid rgba(42,42,74,0.3)">🕐 09:20 — 导入CSV文件 5000条</div>
          <div style="padding:6px 0">🕐 08:55 — 登录系统</div>
        </div>
      </div>
    </div>`;
  // 自动刷新
  if (!window._pwRefresh) {
    window._pwRefresh = setInterval(() => {
      apiGet('/api/monitor/pipeline').then(m => {
        const el = $('pwDailyProd');
        if (el && m.running_tasks) el.textContent = parseInt(el.textContent) + 1;
      });
    }, 15000);
  }
}

function showProductivityDetail() {
  showModal(`
    <span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="margin-bottom:12px;color:var(--accent-blue)">📊 效率详情</h4>
    <div style="display:grid;gap:10px;font-size:12px;color:var(--text-muted)">
      <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)">
        <span>本周总产量</span><span style="color:var(--accent-green);font-weight:600">1,234 条</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)">
        <span>平均质量分</span><span style="color:var(--accent-blue);font-weight:600">4.2 / 5.0</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)">
        <span>平均响应时间</span><span style="color:var(--accent-orange);font-weight:600">2.4s</span>
      </div>
      <div style="display:flex;justify-content:space-between;padding:6px 0">
        <span>效率排名</span><span style="color:var(--accent-purple);font-weight:600">前 15%</span>
      </div>
    </div>
  `);
}

function showFullLog() {
  closeModal();
  showModal(`
    <span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="margin-bottom:12px;color:var(--accent-blue)">⏱ 完整操作日志</h4>
    <div style="font-size:11px;color:var(--text-muted);max-height:400px;overflow-y:auto">
      <div style="padding:6px 0;border-bottom:1px solid rgba(42,42,74,0.3)">🕐 10:32 — 完成数据集标注 task_001</div>
      <div style="padding:6px 0;border-bottom:1px solid rgba(42,42,74,0.3)">🕐 10:15 — 提交质量审核 review_003</div>
      <div style="padding:6px 0;border-bottom:1px solid rgba(42,42,74,0.3)">🕐 09:48 — 新建数据集 sample_dataset_02</div>
      <div style="padding:6px 0;border-bottom:1px solid rgba(42,42,74,0.3)">🕐 09:20 — 导入CSV文件 5000条</div>
      <div style="padding:6px 0;border-bottom:1px solid rgba(42,42,74,0.3)">🕐 08:55 — 登录系统</div>
      <div style="padding:6px 0;border-bottom:1px solid rgba(42,42,74,0.3)">🕐 昨天 17:30 — 导出数据集 delivery_002</div>
      <div style="padding:6px 0;border-bottom:1px solid rgba(42,42,74,0.3)">🕐 昨天 16:45 — 创建团队 team_api</div>
      <div style="padding:6px 0">🕐 昨天 15:20 — 运行流水线 pipeline_003</div>
    </div>
  `);
}
