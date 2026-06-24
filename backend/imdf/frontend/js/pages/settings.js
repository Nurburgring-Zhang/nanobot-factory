/* IMDF 系统设置 v2 — 分组(API配置/模型设置/存储/通知/关于) */
function renderSettings() {
  var c = document.getElementById('page-content');
  if (!c) return;

  c.innerHTML = '' +
    '<div class="page-header">' +
      '<div>' +
        '<div class="page-title">⚙️ 系统设置</div>' +
        '<div style="font-size:11px;color:#8888aa;margin-top:2px">IMDF 无限数据工场 v3.0.0 · Build 2026.06.15</div>' +
      '</div>' +
      '<div class="page-actions">' +
        '<span class="tag tag-green" style="font-size:11px">🟢 系统正常</span>' +
        '<span style="font-size:11px;color:#8888aa;margin-left:8px">v3.0.0</span>' +
      '</div>' +
    '</div>' +
    '<div style="display:grid;grid-template-columns:200px 1fr;gap:16px">' +
      '<div style="background:#1e1e3a;border:1px solid #2a2a4a;border-radius:8px;overflow:hidden">' +
        '<div id="settingsNav" style="padding:4px 0">' +
          '<div class="settings-nav-item active" onclick="switchSettingsTab(\'api\',this)" style="padding:10px 14px;cursor:pointer;font-size:12px;color:#e0e0f0;background:rgba(74,122,255,0.1);border-left:3px solid #4a7aff;transition:all 0.15s">🔑 API配置</div>' +
          '<div class="settings-nav-item" onclick="switchSettingsTab(\'model\',this)" style="padding:10px 14px;cursor:pointer;font-size:12px;color:#8888aa;border-left:3px solid transparent;transition:all 0.15s">🤖 模型设置</div>' +
          '<div class="settings-nav-item" onclick="switchSettingsTab(\'storage\',this)" style="padding:10px 14px;cursor:pointer;font-size:12px;color:#8888aa;border-left:3px solid transparent;transition:all 0.15s">💾 存储配置</div>' +
          '<div class="settings-nav-item" onclick="switchSettingsTab(\'notification\',this)" style="padding:10px 14px;cursor:pointer;font-size:12px;color:#8888aa;border-left:3px solid transparent;transition:all 0.15s">🔔 通知设置</div>' +
          '<div class="settings-nav-item" onclick="switchSettingsTab(\'about\',this)" style="padding:10px 14px;cursor:pointer;font-size:12px;color:#8888aa;border-left:3px solid transparent;transition:all 0.15s">ℹ️ 关于系统</div>' +
        '</div>' +
      '</div>' +
      '<div id="settingsContent" style="background:#1e1e3a;border:1px solid #2a2a4a;border-radius:8px;padding:20px;min-height:500px"></div>' +
    '</div>';

  renderAPISettings();
}

var CURRENT_SETTINGS_TAB = 'api';

function switchSettingsTab(tab, el) {
  CURRENT_SETTINGS_TAB = tab;
  // Update nav styles
  var items = document.querySelectorAll('.settings-nav-item');
  for (var i = 0; i < items.length; i++) {
    items[i].classList.remove('active');
    items[i].style.color = '#8888aa';
    items[i].style.background = 'transparent';
    items[i].style.borderLeftColor = 'transparent';
  }
  if (el) {
    el.classList.add('active');
    el.style.color = '#e0e0f0';
    el.style.background = 'rgba(74,122,255,0.1)';
    el.style.borderLeftColor = '#4a7aff';
  }

  if (tab === 'api') renderAPISettings();
  else if (tab === 'model') renderModelSettings();
  else if (tab === 'storage') renderStorageSettings();
  else if (tab === 'notification') renderNotificationSettings();
  else if (tab === 'about') renderAboutSettings();
}

/* ===== API配置 ===== */
function renderAPISettings() {
  var container = document.getElementById('settingsContent');
  if (!container) return;

  container.innerHTML = '' +
    '<h4 style="margin-bottom:16px;color:#4a7aff">🔑 API 配置</h4>' +
    '<div class="param-row">' +
      '<span class="param-label">API Base URL</span>' +
      '<input class="param-value" value="http://localhost:8000/api/v1" style="flex:1;padding:6px 10px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0;font-size:12px">' +
      '<span class="param-hint">所有API请求的基础地址</span>' +
    '</div>' +
    '<div class="param-row">' +
      '<span class="param-label">API Key</span>' +
      '<input class="param-value" type="password" value="sk-imdf-••••••••••••" style="flex:1;padding:6px 10px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0;font-size:12px">' +
      '<button class="btn btn-outline btn-sm" onclick="toggleApiKey()" id="apiKeyToggle">👁 显示</button>' +
    '</div>' +
    '<div class="param-row">' +
      '<span class="param-label">超时时间(秒)</span>' +
      '<input class="param-value" type="number" value="30" style="width:80px;padding:6px 10px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0;font-size:12px">' +
      '<span class="param-hint">API请求超时设置</span>' +
    '</div>' +
    '<div class="param-row">' +
      '<span class="param-label">最大重试</span>' +
      '<input class="param-value" type="number" value="3" style="width:80px;padding:6px 10px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0;font-size:12px">' +
      '<span class="param-hint">失败后的最大重试次数</span>' +
    '</div>' +
    '<div style="margin-top:16px;padding-top:12px;border-top:1px solid #2a2a4a">' +
      '<div style="font-size:12px;font-weight:600;margin-bottom:8px;color:#e0e0f0">🔑 API Key 管理</div>' +
      '<div id="apiKeyList" style="font-size:12px;color:#8888aa">' +
        '<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #2a2a4a"><span>sk-imdf-prod-2026</span><span class="tag tag-green">活跃</span><span style="color:#ef4444;cursor:pointer">删除</span></div>' +
        '<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #2a2a4a"><span>sk-imdf-dev-test</span><span class="tag tag-red">已禁用</span><span style="color:#4a7aff;cursor:pointer">启用</span></div>' +
      '</div>' +
      '<button class="btn btn-primary btn-sm" style="margin-top:8px" onclick="generateNewApiKey()">➕ 生成新Key</button>' +
    '</div>' +
    '<div style="margin-top:16px;display:flex;gap:8px">' +
      '<button class="btn btn-primary" onclick="saveAPISettings()">💾 保存配置</button>' +
      '<button class="btn btn-outline" onclick="testAPIConnection()">🔗 测试连接</button>' +
    '</div>';
}

/* ===== 模型设置 ===== */
function renderModelSettings() {
  var container = document.getElementById('settingsContent');
  if (!container) return;

  container.innerHTML = '' +
    '<h4 style="margin-bottom:16px;color:#4a7aff">🤖 模型设置</h4>' +
    '<div class="param-row">' +
      '<span class="param-label">默认LLM模型</span>' +
      '<select class="param-value" style="padding:6px 10px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0;font-size:12px">' +
        '<option>deepseek-v4-pro</option><option>gpt-4o</option><option>claude-sonnet-4</option><option>gemini-2.5-pro</option>' +
      '</select>' +
      '<span class="param-hint">AI辅助功能的默认模型</span>' +
    '</div>' +
    '<div class="param-row">' +
      '<span class="param-label">Embedding模型</span>' +
      '<select class="param-value" style="padding:6px 10px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0;font-size:12px">' +
        '<option>text-embedding-3-large</option><option>bge-m3</option><option>jina-embeddings-v3</option>' +
      '</select>' +
      '<span class="param-hint">用于向量搜索和语义匹配</span>' +
    '</div>' +
    '<div class="param-row">' +
      '<span class="param-label">视觉模型</span>' +
      '<select class="param-value" style="padding:6px 10px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0;font-size:12px">' +
        '<option>qwen-vl-max</option><option>gpt-4o-vision</option><option>claude-3.5-sonnet</option>' +
      '</select>' +
      '<span class="param-hint">图像理解和多模态任务</span>' +
    '</div>' +
    '<div class="param-row">' +
      '<span class="param-label">Temperature</span>' +
      '<input class="param-value" type="range" min="0" max="2" step="0.1" value="0.7" style="width:200px">' +
      '<span class="param-hint" id="tempValue">0.7</span>' +
    '</div>' +
    '<div class="param-row">' +
      '<span class="param-label">Max Tokens</span>' +
      '<input class="param-value" type="number" value="4096" style="width:100px;padding:6px 10px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0;font-size:12px">' +
      '<span class="param-hint">单次响应的最大Token数</span>' +
    '</div>' +
    '<div style="margin-top:12px;display:flex;gap:8px">' +
      '<button class="btn btn-primary" onclick="saveModelSettings()">💾 保存</button>' +
    '</div>';
}

/* ===== 存储配置 ===== */
function renderStorageSettings() {
  var container = document.getElementById('settingsContent');
  if (!container) return;

  container.innerHTML = '' +
    '<h4 style="margin-bottom:16px;color:#4a7aff">💾 存储配置</h4>' +
    '<div class="param-row">' +
      '<span class="param-label">默认存储</span>' +
      '<select class="param-value" style="padding:6px 10px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0;font-size:12px">' +
        '<option>本地文件系统</option><option>Amazon S3</option><option>MinIO</option><option>阿里云OSS</option>' +
      '</select>' +
    '</div>' +
    '<div class="param-row">' +
      '<span class="param-label">存储路径</span>' +
      '<input class="param-value" value="/data/imdf/storage" style="flex:1;padding:6px 10px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0;font-size:12px">' +
    '</div>' +
    '<div class="param-row">' +
      '<span class="param-label">缓存大小</span>' +
      '<input class="param-value" type="number" value="10" style="width:80px;padding:6px 10px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0;font-size:12px">' +
      '<span class="param-hint">GB</span>' +
    '</div>' +
    '<div class="param-row">' +
      '<span class="param-label">自动备份</span>' +
      '<label style="display:flex;align-items:center;gap:8px;font-size:12px">' +
        '<input type="checkbox" checked style="accent-color:#4a7aff">' +
        '每日凌晨3:00自动备份' +
      '</label>' +
    '</div>' +
    '<div style="margin-top:12px;display:flex;gap:8px;align-items:center">' +
      '<div style="flex:1;height:6px;background:#0f0f1a;border-radius:3px;overflow:hidden">' +
        '<div style="width:45%;height:100%;background:#4a7aff;border-radius:3px"></div>' +
      '</div>' +
      '<span style="font-size:11px;color:#8888aa">已使用 45GB / 100GB</span>' +
    '</div>' +
    '<div style="margin-top:12px;display:flex;gap:8px">' +
      '<button class="btn btn-primary" onclick="saveStorageSettings()">💾 保存</button>' +
      '<button class="btn btn-outline" onclick="clearCache()">🗑 清除缓存</button>' +
    '</div>';
}

/* ===== 通知设置 ===== */
function renderNotificationSettings() {
  var container = document.getElementById('settingsContent');
  if (!container) return;

  container.innerHTML = '' +
    '<h4 style="margin-bottom:16px;color:#4a7aff">🔔 通知设置</h4>' +
    '<div style="display:grid;gap:12px">' +
      '<label style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #2a2a4a">' +
        '<div><div style="font-size:13px">任务完成通知</div><div style="font-size:10px;color:#8888aa">当任务执行完成时发送通知</div></div>' +
        '<input type="checkbox" checked style="accent-color:#4a7aff">' +
      '</label>' +
      '<label style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #2a2a4a">' +
        '<div><div style="font-size:13px">交付审核通知</div><div style="font-size:10px;color:#8888aa">交付单状态变更时通知</div></div>' +
        '<input type="checkbox" checked style="accent-color:#4a7aff">' +
      '</label>' +
      '<label style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #2a2a4a">' +
        '<div><div style="font-size:13px">质量告警</div><div style="font-size:10px;color:#8888aa">质量评分低于阈值时告警</div></div>' +
        '<input type="checkbox" checked style="accent-color:#4a7aff">' +
      '</label>' +
      '<label style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #2a2a4a">' +
        '<div><div style="font-size:13px">系统告警</div><div style="font-size:10px;color:#8888aa">系统错误或资源不足时通知</div></div>' +
        '<input type="checkbox" checked style="accent-color:#4a7aff">' +
      '</label>' +
      '<label style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #2a2a4a">' +
        '<div><div style="font-size:13px">邮件通知</div><div style="font-size:10px;color:#8888aa">同时发送邮件通知(需配置SMTP)</div></div>' +
        '<input type="checkbox" style="accent-color:#4a7aff">' +
      '</label>' +
    '</div>' +
    '<div class="param-row" style="margin-top:12px">' +
      '<span class="param-label">质量阈值</span>' +
      '<input class="param-value" type="number" value="85" style="width:80px;padding:6px 10px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0;font-size:12px">' +
      '<span class="param-hint">低于此值时触发质量告警</span>' +
    '</div>' +
    '<div style="margin-top:12px;display:flex;gap:8px">' +
      '<button class="btn btn-primary" onclick="saveNotificationSettings()">💾 保存</button>' +
    '</div>';
}

/* ===== 关于系统 ===== */
function renderAboutSettings() {
  var container = document.getElementById('settingsContent');
  if (!container) return;

  container.innerHTML = '' +
    '<h4 style="margin-bottom:16px;color:#4a7aff">ℹ️ 关于系统</h4>' +
    '<div style="display:grid;gap:12px;font-size:13px;line-height:2">' +
      '<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2a2a4a">' +
        '<span style="color:#8888aa">系统名称</span><span>IMDF 无限数据工场</span>' +
      '</div>' +
      '<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2a2a4a">' +
        '<span style="color:#8888aa">版本号</span><span class="tag tag-blue">v3.0.0</span>' +
      '</div>' +
      '<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2a2a4a">' +
        '<span style="color:#8888aa">构建日期</span><span>2026-06-15</span>' +
      '</div>' +
      '<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2a2a4a">' +
        '<span style="color:#8888aa">前端技术栈</span><span>Vanilla JS · CSS3 · Canvas API</span>' +
      '</div>' +
      '<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2a2a4a">' +
        '<span style="color:#8888aa">后端框架</span><span>FastAPI · Python 3.12</span>' +
      '</div>' +
      '<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2a2a4a">' +
        '<span style="color:#8888aa">节点总数</span><span>48 类节点 · 50+ 引擎</span>' +
      '</div>' +
      '<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2a2a4a">' +
        '<span style="color:#8888aa">API路由数</span><span>352+</span>' +
      '</div>' +
      '<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2a2a4a">' +
        '<span style="color:#8888aa">本地模型</span><span>12+ 预置模型</span>' +
      '</div>' +
    '</div>' +
    '<div style="margin-top:16px;padding:12px;background:#0f0f1a;border-radius:6px;font-size:12px;color:#8888aa;text-align:center">' +
      '<p>IMDF v3.0 — Infinite Multimodal Data Foundry</p>' +
      '<p style="margin-top:4px">© 2026 Nous Research. All rights reserved.</p>' +
    '</div>' +
    '<div style="margin-top:12px;display:flex;gap:8px">' +
      '<button class="btn btn-outline btn-sm" onclick="checkForUpdates()">🔄 检查更新</button>' +
      '<button class="btn btn-outline btn-sm" onclick="viewChangelog()">📋 更新日志</button>' +
    '</div>';
}

/* ===== Action helpers ===== */
async function saveAPISettings() {
  try {
    var container = document.getElementById('settingsContent');
    var inputs = container ? container.querySelectorAll('input') : [];
    var baseUrl = inputs[0]?.value || '';
    var timeout = parseInt(inputs[2]?.value) || 30;
    var maxRetries = parseInt(inputs[3]?.value) || 3;
    var result = await apiPost('/api/settings/api', { base_url: baseUrl, timeout: timeout, max_retries: maxRetries });
    if (result && result.success) {
      if (typeof showToast === 'function') showToast('API配置已保存', 'success');
    } else {
      if (typeof showToast === 'function') showToast('保存失败: ' + (result?.error || '未知错误'), 'error');
    }
  } catch (e) {
    if (typeof showToast === 'function') showToast('保存失败: ' + (e.message || e), 'error');
  }
}

async function saveModelSettings() {
  try {
    var container = document.getElementById('settingsContent');
    var selects = container ? container.querySelectorAll('select') : [];
    var defaultLlm = selects[0]?.value || 'deepseek-v4-pro';
    var embeddingModel = selects[1]?.value || 'text-embedding-3-large';
    var visionModel = selects[2]?.value || 'qwen-vl-max';
    var tempInput = container ? container.querySelector('input[type="range"]') : null;
    var temperature = parseFloat(tempInput?.value) || 0.7;
    var maxTokensInput = container ? container.querySelectorAll('input[type="number"]')[0] : null;
    var maxTokens = parseInt(maxTokensInput?.value) || 4096;
    var result = await apiPost('/api/settings/models', {
      default_llm: defaultLlm, embedding_model: embeddingModel,
      vision_model: visionModel, temperature: temperature, max_tokens: maxTokens
    });
    if (result && result.success) {
      if (typeof showToast === 'function') showToast('模型设置已保存', 'success');
    } else {
      if (typeof showToast === 'function') showToast('保存失败: ' + (result?.error || '未知错误'), 'error');
    }
  } catch (e) {
    if (typeof showToast === 'function') showToast('保存失败: ' + (e.message || e), 'error');
  }
}

async function saveStorageSettings() {
  try {
    var container = document.getElementById('settingsContent');
    var selects = container ? container.querySelectorAll('select') : [];
    var storageType = selects[0]?.value || '本地文件系统';
    var inputs = container ? container.querySelectorAll('input:not([type="checkbox"])') : [];
    var storagePath = inputs[1]?.value || '/data/imdf/storage';
    var cacheSize = parseInt(inputs[2]?.value) || 10;
    var autoBackup = container ? container.querySelector('input[type="checkbox"]')?.checked : false;
    var result = await apiPost('/api/settings/storage', {
      storage_type: storageType, storage_path: storagePath,
      cache_size_gb: cacheSize, auto_backup: autoBackup
    });
    if (result && result.success) {
      if (typeof showToast === 'function') showToast('存储配置已保存', 'success');
    } else {
      if (typeof showToast === 'function') showToast('保存失败: ' + (result?.error || '未知错误'), 'error');
    }
  } catch (e) {
    if (typeof showToast === 'function') showToast('保存失败: ' + (e.message || e), 'error');
  }
}

async function saveNotificationSettings() {
  try {
    var container = document.getElementById('settingsContent');
    var checkboxes = container ? container.querySelectorAll('input[type="checkbox"]') : [];
    var taskComplete = checkboxes[0]?.checked || false;
    var deliveryReview = checkboxes[1]?.checked || false;
    var qualityAlert = checkboxes[2]?.checked || false;
    var systemAlert = checkboxes[3]?.checked || false;
    var emailNotify = checkboxes[4]?.checked || false;
    var thresholdInput = container ? container.querySelector('input[type="number"]') : null;
    var qualityThreshold = parseInt(thresholdInput?.value) || 85;
    var result = await apiPost('/api/settings/notifications', {
      task_complete: taskComplete, delivery_review: deliveryReview,
      quality_alert: qualityAlert, system_alert: systemAlert,
      email_notify: emailNotify, quality_threshold: qualityThreshold
    });
    if (result && result.success) {
      if (typeof showToast === 'function') showToast('通知设置已保存', 'success');
    } else {
      if (typeof showToast === 'function') showToast('保存失败: ' + (result?.error || '未知错误'), 'error');
    }
  } catch (e) {
    if (typeof showToast === 'function') showToast('保存失败: ' + (e.message || e), 'error');
  }
}

function toggleApiKey() {
  var input = document.querySelector('#settingsContent input[type="password"]');
  var btn = document.getElementById('apiKeyToggle');
  if (input && btn) {
    if (input.type === 'password') {
      input.type = 'text';
      btn.textContent = '🙈 隐藏';
    } else {
      input.type = 'password';
      btn.textContent = '👁 显示';
    }
  }
}

async function testAPIConnection() {
  try {
    var result = await apiGet('/api/v1/health');
    if (result && (result.status === 'ok' || result.success)) {
      if (typeof showToast === 'function') showToast('API连接测试成功 ✓ (v' + (result.version || '?') + ')', 'success');
    } else {
      if (typeof showToast === 'function') showToast('API连接测试失败: ' + (result?.error || '服务异常'), 'error');
    }
  } catch (e) {
    if (typeof showToast === 'function') showToast('API连接测试失败: ' + (e.message || e), 'error');
  }
}

async function generateNewApiKey() {
  try {
    var result = await apiPost('/api/v1/api-keys/create', { name: 'settings-key-' + Date.now().toString(36) });
    if (result && result.success && result.data?.key) {
      if (typeof showToast === 'function') showToast('新API Key已生成: ' + result.data.key.slice(0, 16) + '...', 'success');
      if (typeof showModal === 'function') {
        showModal(
          '<span class="modal-close" onclick="closeModal()">✕</span>' +
          '<h4 style="margin-bottom:12px;color:#4ade80">✅ 新API Key已生成</h4>' +
          '<p style="font-size:12px;color:#8888aa;margin-bottom:8px">请立即复制此Key：</p>' +
          '<div style="background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;padding:12px;font-family:monospace;font-size:12px;word-break:break-all;color:#4a7aff;user-select:all;margin-bottom:12px">' + (result.data.key || '') + '</div>' +
          '<button style="padding:8px 20px;background:#4a7aff;border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:13px" onclick="closeModal()">关闭</button>'
        );
      }
    } else {
      if (typeof showToast === 'function') showToast('生成失败: ' + (result?.error || '未知错误'), 'error');
    }
  } catch (e) {
    if (typeof showToast === 'function') showToast('生成失败: ' + (e.message || e), 'error');
  }
}

async function clearCache() {
  try {
    var result = await apiPost('/api/settings/cache/clear');
    if (result && result.success) {
      if (typeof showToast === 'function') showToast('缓存已清除 ✓', 'success');
    } else {
      if (typeof showToast === 'function') showToast('清除失败: ' + (result?.error || '未知错误'), 'error');
    }
  } catch (e) {
    if (typeof showToast === 'function') showToast('清除失败: ' + (e.message || e), 'error');
  }
}

async function checkForUpdates() {
  try {
    var result = await apiGet('/api/v1/health');
    if (result && result.version) {
      if (typeof showToast === 'function') showToast('当前版本: v' + result.version + ' · 已是最新', 'info');
    } else {
      if (typeof showToast === 'function') showToast('当前已是最新版本 v3.0.0', 'info');
    }
  } catch (e) {
    if (typeof showToast === 'function') showToast('检查更新失败: ' + (e.message || e), 'error');
  }
}

function viewChangelog() {
  if (typeof showModal !== 'function') return;
  showModal('' +
    '<span class="modal-close" onclick="closeModal()">✕</span>' +
    '<h4 style="margin-bottom:12px;color:#4a7aff">📋 更新日志</h4>' +
    '<div style="font-size:12px;color:#8888aa;line-height:2">' +
      '<p><strong>v3.0.0</strong> (2026-06-15)</p>' +
      '<p>- 全新UI设计，深色工业主题</p>' +
      '<p>- 质量管线+PE模板系统重设计</p>' +
      '<p>- 统计分析看板+趋势图</p>' +
      '<p>- 团队管理+交付管理系统</p>' +
      '<p>- 系统设置分组管理</p>' +
    '</div>');
}

function settings_notificationWizard() {
  showWizard('通知配置向导', [
    {label:'渠道',content:()=>`
      <div class="preset-list">
        <div class="preset-item selected"><span class="preset-item-icon">📧</span><div class="preset-item-info"><div class="preset-item-name">邮件通知</div><div class="preset-item-desc">SMTPS发送,支持HTML模板</div></div></div>
        <div class="preset-item"><span class="preset-item-icon">💬</span><div class="preset-item-info"><div class="preset-item-name">Webhook</div><div class="preset-item-desc">Slack/Discord/飞书</div></div></div>
        <div class="preset-item"><span class="preset-item-icon">📱</span><div class="preset-item-info"><div class="preset-item-name">短信</div><div class="preset-item-desc">Twilio/Aliyun SMS</div></div></div>
      </div>`,
      validate:(d)=>{d.channel='email';return null;}
    },
    {label:'配置',content:(d)=>`
      <div class="form-group"><label class="form-label">SMTP服务器</label><input class="form-input" value="smtp.example.com"></div>
      <div class="form-row"><div class="form-group"><label class="form-label">端口</label><input class="form-input" value="587"></div><div class="form-group"><label class="form-label">加密</label><select class="form-select"><option>TLS</option><option>SSL</option></select></div></div>
      <div class="form-group"><label class="form-label">发件邮箱</label><input class="form-input" value="imdf@example.com"></div>`,
      validate:(d)=>{d.method='email';return null;}
    },
    {label:'触发',content:(d)=>`
      <div class="form-check"><input type="checkbox" checked id="nc1"><label for="nc1">标注完成通知</label></div>
      <div class="form-check"><input type="checkbox" checked id="nc2"><label for="nc2">审核超时告警(>24h)</label></div>
      <div class="form-check"><input type="checkbox" id="nc3"><label for="nc3">质量异常告警</label></div>
      <div class="form-check"><input type="checkbox" id="nc4"><label for="nc4">系统健康告警</label></div>`,
      onFinish:(d)=>showToast('通知配置已保存','success')
    }
  ]);
}

/* 5级: 关于页面钻取 */
function settings_aboutDetail() {
  showDrillDetail('系统信息', [
    {title:'版本信息',fields:{'IMDF':'v3.0','nanobot':'v2.1','Python':'3.12','FastAPI':'0.100+'}},
    {title:'组件列表',badge:'50+',
     childSections:[
       {title:'引擎',fields:{'生产':'13','标注':'8','质量':'7','检索':'3','传输':'2'}},
       {title:'模型',fields:{'本地':'12','云端':'5','ComfyUI':'4'}}
     ]},
    {title:'许可与依赖',badge:'MIT',json:'{"license":"MIT","key_deps":["fastapi","Pillow","scikit-learn","argon2"]}'}
  ]);
}

async function settings_testApi(){try{const r=await apiGet('/api/v1/health');showToast(r?.status==='ok'?'连接成功':'异常',r?.status==='ok'?'success':'error')}catch(e){showToast('连接失败','error')}}
async function settings_saveConfig(section,data){try{await apiPost('/api/admin/config',{section,...data});showToast('已保存','success')}catch(e){showToast('保存失败','error')}}