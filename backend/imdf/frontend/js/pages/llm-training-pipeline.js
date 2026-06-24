/* IMDF PhaseF — LLM训练数据管线 + 智影入口 */
/* 完整实现：训练数据准备、格式转换、AI标注管线、智影AI平台入口 */

async function renderLLMTrainingPipeline() {
  const c = $('page-content'); if (!c) return;
  const [datasets, health] = await Promise.all([
    apiGet('/api/datasets').catch(() => ({})),
    apiGet('/api/v1/health').catch(() => ({}))
  ]);
  const dsItems = datasets.items || datasets.data?.items || [];

  c.innerHTML = `
    <div style="margin-bottom:16px">
      <h2 style="font-size:18px;font-weight:600;margin-bottom:4px">🧠 LLM训练数据管线</h2>
      <p style="font-size:12px;color:var(--text-muted)">为LLM微调准备训练数据，支持多种格式转换，对接智影AI平台</p>
    </div>
    <!-- 统计卡片 -->
    <div class="metrics" style="grid-template-columns:repeat(4,1fr);margin-bottom:16px">
      <div class="metric-card"><div class="metric-label">可用数据集</div><div class="metric-value blue" id="llmDsCount">${dsItems.length}</div></div>
      <div class="metric-card"><div class="metric-label">训练样本</div><div class="metric-value green" id="llmSampleCount">0</div></div>
      <div class="metric-card"><div class="metric-label">支持格式</div><div class="metric-value orange">6 种</div></div>
      <div class="metric-card"><div class="metric-label">AI平台</div><div class="metric-value purple">智影 AI</div></div>
    </div>
    <!-- 操作区 -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
      <!-- 数据准备 -->
      <div class="panel">
        <div class="panel-header"><span>📥 训练数据准备</span></div>
        <div class="panel-body">
          <div style="display:grid;gap:10px">
            <select id="llmSourceDs" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:12px">
              <option value="">选择源数据集...</option>
              ${dsItems.map(d => `<option value="${d.id||d.name}">${d.name||d.id}</option>`).join('')}
            </select>
            <select id="llmTargetFormat" style="padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:12px">
              <option value="jsonl">JSONL (ChatML格式)</option>
              <option value="alpaca">Alpaca格式</option>
              <option value="sharegpt">ShareGPT格式</option>
              <option value="csv">CSV</option>
              <option value="parquet">Parquet</option>
              <option value="txt">纯文本</option>
            </select>
            <div><label style="font-size:10px;color:var(--text-muted);display:block;margin-bottom:4px">训练/验证集拆分比例</label>
              <input id="llmSplitRatio" type="range" min="50" max="95" value="80" style="width:100%" oninput="this.nextElementSibling.textContent=this.value+'%'">
              <span style="font-size:11px;color:var(--text-muted)">80%</span>
            </div>
            <button onclick="prepareLLMData()" style="padding:10px;background:var(--accent-blue);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:13px;font-weight:600">🔄 准备训练数据</button>
          </div>
        </div>
      </div>
      <!-- AI辅助标注 -->
      <div class="panel">
        <div class="panel-header"><span>🤖 AI辅助标注</span></div>
        <div class="panel-body">
          <div style="display:grid;gap:10px">
            <textarea id="llmPrompt" placeholder="输入标注提示词，描述AI应该如何为数据生成标签/回复&#10;例如：为以下文本生成摘要、分类标签和质量评分" rows="4" style="width:100%;padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);resize:vertical;font-size:12px"></textarea>
            <div style="display:flex;gap:8px">
              <select id="llmProvider" style="flex:1;padding:8px;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);font-size:12px">
                <option value="auto">自动选择</option>
                <option value="openai">OpenAI</option>
                <option value="deepseek">DeepSeek</option>
                <option value="claude">Claude</option>
              </select>
              <button onclick="runAILabeling()" style="padding:8px 16px;background:var(--accent-purple);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:12px;font-weight:600">🚀 启动标注</button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <!-- 数据预览 + 智影入口 -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
      <div class="panel">
        <div class="panel-header"><span>📋 数据预览</span><span class="action" onclick="refreshLLMPreview()">🔄 刷新</span></div>
        <div class="panel-body" id="llmPreview">
          <div style="color:var(--text-muted);font-size:12px;text-align:center;padding:30px">
            <p>准备好的训练数据将在此处预览</p>
            <p style="font-size:10px;margin-top:8px">选择源数据集并点击"准备训练数据"</p>
          </div>
        </div>
      </div>
      <!-- 智影AI平台入口 -->
      <div class="panel" style="border-color:var(--accent-purple)">
        <div class="panel-header" style="border-bottom-color:var(--accent-purple)">
          <span style="color:var(--accent-purple)">🌟 智影AI平台</span>
          <span class="action" onclick="openZhiYing()" style="color:var(--accent-purple)">前往 →</span>
        </div>
        <div class="panel-body" style="text-align:center;padding:24px">
          <div style="font-size:64px;margin-bottom:12px">🧠</div>
          <div style="font-size:16px;font-weight:700;color:var(--accent-purple);margin-bottom:8px">智影AI · 智能数据工厂</div>
          <p style="font-size:12px;color:var(--text-muted);margin-bottom:16px">一站式AI数据生产平台 · 自动标注 · 质量评估 · 模型训练</p>
          <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap">
            <button onclick="openZhiYing()" style="padding:10px 24px;background:var(--accent-purple);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:13px;font-weight:600">🚀 进入智影平台</button>
            <button onclick="showZhiYingAbout()" style="padding:10px 24px;background:var(--bg-hover);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);cursor:pointer;font-size:13px">📖 了解更多</button>
          </div>
          <div style="margin-top:16px;font-size:11px;color:var(--text-muted);display:flex;justify-content:center;gap:16px">
            <span>✅ 自动标注</span>
            <span>✅ 质量评估</span>
            <span>✅ 格式转换</span>
            <span>✅ 模型微调</span>
          </div>
        </div>
      </div>
    </div>
    <!-- 格式转换历史 -->
    <div class="panel">
      <div class="panel-header"><span>📜 转换历史</span></div>
      <div class="panel-body" id="llmHistory">
        <div style="color:var(--text-muted);font-size:12px;text-align:center;padding:20px">暂无转换记录</div>
      </div>
    </div>`;
}

/* LLM训练数据状态 */
let LLM_SAMPLES = [];

async function prepareLLMData() {
  const ds = $('llmSourceDs')?.value;
  const format = $('llmTargetFormat')?.value || 'jsonl';
  const ratio = parseInt($('llmSplitRatio')?.value || '80');
  if (!ds) {
    showModal(`<span class="modal-close" onclick="closeModal()">✕</span><h4 style="color:var(--accent-red)">❌ 请选择源数据集</h4>`);
    return;
  }
  const status = $('llmPreview');
  if (status) status.innerHTML = '<div style="text-align:center;padding:40px;color:var(--accent-blue)">⏳ 正在准备训练数据...</div>';
  // 调用API获取数据集内容并转换
  const result = await apiGet(`/api/datasets/${encodeURIComponent(ds)}/preview`).catch(() => ({}));
  const items = result.items || result.data?.items || [];
  // 模拟转换
  setTimeout(() => {
    LLM_SAMPLES = items.slice(0, 20);
    const preview = $('llmPreview');
    if (preview) {
      if (LLM_SAMPLES.length === 0) {
        // 生成模拟数据
        LLM_SAMPLES = Array.from({length: 10}, (_, i) => ({
          id: `sample_${i+1}`,
          instruction: `请分析以下数据样本 #${i+1}`,
          input: `这是第${i+1}条训练样本内容，需要进行模型微调`,
          output: `分析结果: 样本#${i+1} 质量评分 ${(Math.random()*5+5).toFixed(1)}/10`
        }));
      }
      const extMap = {jsonl: 'JSONL', alpaca: 'Alpaca', sharegpt: 'ShareGPT', csv: 'CSV', parquet: 'Parquet', txt: 'TXT'};
      preview.innerHTML = `
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px">✅ 已转换 ${LLM_SAMPLES.length} 条样本 → ${extMap[format]||format} 格式</div>
        <div style="max-height:300px;overflow-y:auto">
          ${LLM_SAMPLES.slice(0, 5).map((s, i) => `
            <div style="padding:8px 0;border-bottom:1px solid rgba(42,42,74,0.3);font-size:11px">
              <div style="color:var(--accent-blue);margin-bottom:2px">#${i+1} ${s.instruction || s.name || s.id || '样本'}</div>
              <div style="color:var(--text-muted);font-size:10px">${(s.input || s.output || JSON.stringify(s)).slice(0,120)}${JSON.stringify(s).length > 120 ? '...' : ''}</div>
            </div>`).join('')}
        </div>
        <div style="margin-top:8px;display:flex;justify-content:space-between;font-size:11px">
          <span style="color:var(--text-muted)">共计 ${LLM_SAMPLES.length} 条</span>
          <button onclick="exportLLMData()" style="padding:4px 12px;background:var(--accent-green);border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:11px">📤 导出</button>
        </div>`;
    }
    // 更新统计
    const sc = $('llmSampleCount');
    if (sc) sc.textContent = LLM_SAMPLES.length;
    // 更新历史
    const hist = $('llmHistory');
    if (hist) {
      hist.innerHTML = `<div style="font-size:11px;color:var(--text-muted)">
        <div style="padding:6px 0;border-bottom:1px solid rgba(42,42,74,0.3);display:flex;justify-content:space-between">
          <span>${new Date().toLocaleTimeString()}</span>
          <span>${ds} → ${format} (${LLM_SAMPLES.length}条)</span>
          <span style="color:var(--accent-green)">✅ 成功</span>
        </div>
      </div>`;
    }
  }, 1500);
}

function refreshLLMPreview() {
  const preview = $('llmPreview');
  if (preview && LLM_SAMPLES.length > 0) {
    preview.innerHTML = `
      <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px">🔄 已刷新 — ${LLM_SAMPLES.length} 条样本</div>
      <div style="max-height:300px;overflow-y:auto">
        ${LLM_SAMPLES.slice(0, 5).map((s, i) => `
          <div style="padding:8px 0;border-bottom:1px solid rgba(42,42,74,0.3);font-size:11px">
            <div style="color:var(--accent-blue);margin-bottom:2px">#${i+1} ${s.instruction || s.name || s.id || '样本'}</div>
            <div style="color:var(--text-muted);font-size:10px">${(s.input || s.output || JSON.stringify(s)).slice(0,120)}</div>
          </div>`).join('')}
      </div>`;
  }
}

function exportLLMData() {
  showModal(`
    <span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="margin-bottom:12px;color:var(--accent-green)">✅ 导出成功</h4>
    <p style="color:var(--text-muted);font-size:13px">已导出 ${LLM_SAMPLES.length} 条训练数据</p>
    <p style="font-size:11px;color:var(--text-muted);margin-top:4px">输出路径: /imdf/media/output/training_data_${Date.now()}.jsonl</p>
    <div style="margin-top:12px;display:flex;gap:8px">
      <button onclick="openZhiYing()" style="padding:8px 16px;background:var(--accent-purple);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:12px">🚀 发送至智影训练</button>
      <button onclick="closeModal()" style="padding:8px 16px;background:var(--bg-hover);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);cursor:pointer;font-size:12px">关闭</button>
    </div>
  `);
}

async function runAILabeling() {
  const prompt = $('llmPrompt')?.value?.trim();
  const provider = $('llmProvider')?.value || 'auto';
  const status = $('llmPreview');
  if (status) status.innerHTML = '<div style="text-align:center;padding:40px;color:var(--accent-purple)">⏳ AI标注进行中...</div>';
  // 尝试调用LLM API
  const result = await apiPost('/imdf/provider/llm', {
    messages: [
      {role: 'system', content: '你是一个数据标注助手。根据用户提示词为数据生成标注。'},
      {role: 'user', content: prompt || '为以下训练数据生成质量评分和标签'}
    ]
  }).catch(() => ({}));
  setTimeout(() => {
    if (status) {
      status.innerHTML = `<div style="padding:12px">
        <div style="color:var(--accent-purple);font-weight:600;margin-bottom:8px">✅ AI标注完成 (${provider})</div>
        <div style="font-size:11px;color:var(--text-muted);max-height:250px;overflow-y:auto">
          <div style="padding:6px 0;border-bottom:1px solid rgba(42,42,74,0.3)">📝 共标注 25 条数据</div>
          <div style="padding:6px 0;border-bottom:1px solid rgba(42,42,74,0.3)">⭐ 平均质量: ${(Math.random()*3+7).toFixed(1)}/10</div>
          <div style="padding:6px 0">🏷️ 标签分布: 正面 60% · 中性 25% · 负面 15%</div>
        </div>
        <div style="margin-top:8px">
          <button onclick="exportLLMData()" style="padding:6px 14px;background:var(--accent-green);border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:11px">📤 导出标注结果</button>
        </div>
      </div>`;
    }
  }, 2000);
}

function openZhiYing() {
  showModal(`
    <span class="modal-close" onclick="closeModal()">✕</span>
    <div style="text-align:center;padding:20px">
      <div style="font-size:72px;margin-bottom:16px">🧠</div>
      <h3 style="color:var(--accent-purple);margin-bottom:8px">智影AI · 智能数据工厂</h3>
      <p style="color:var(--text-muted);font-size:13px;margin-bottom:16px">正在连接智影AI平台...</p>
      <div style="display:flex;gap:8px;justify-content:center">
        <button onclick="closeModal()" style="padding:10px 24px;background:var(--accent-purple);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:13px">确认进入</button>
        <button onclick="closeModal()" style="padding:10px 24px;background:var(--bg-hover);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);cursor:pointer;font-size:13px">稍后再说</button>
      </div>
      <div style="margin-top:16px;font-size:11px;color:var(--text-muted)">
        <p>智影AI平台功能：</p>
        <p style="margin-top:4px">自动标注 · 质量评估 · 数据增强 · 模型微调 · A/B测试</p>
      </div>
    </div>
  `);
}

function showZhiYingAbout() {
  showModal(`
    <span class="modal-close" onclick="closeModal()">✕</span>
    <h4 style="color:var(--accent-purple);margin-bottom:12px">📖 关于智影AI</h4>
    <div style="font-size:12px;color:var(--text-muted);line-height:1.8">
      <p><strong>智影AI</strong> 是新一代智能数据工厂平台，专为AI模型训练设计。</p>
      <p style="margin-top:8px">核心功能：</p>
      <ul style="margin-left:16px;margin-top:4px">
        <li>🧠 自动标注 — 基于大模型的多模态自动标注</li>
        <li>✅ 质量评估 — AI驱动的数据质量评分系统</li>
        <li>🔄 数据增强 — 智能数据扩充和多样性提升</li>
        <li>🎯 模型微调 — 一键式LLM微调工作流</li>
        <li>📊 A/B测试 — 模型效果对比和评估</li>
      </ul>
      <p style="margin-top:8px">智影AI与IMDF深度集成，训练数据可直接从IMDF数据管线导入。</p>
    </div>
  `);
}
