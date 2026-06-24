/* IMDF 团队管理 v2 — 成员表格 + 添加/编辑/角色管理
   P1-C-W1: 优先调用 /api/users (task spec), 兜底 /api/team/members (已有)
*/
async function renderTeam() {
  var c = document.getElementById('page-content');
  if (!c) return;

  // P1-C-W1: 主路径 — GET /api/users (task spec'd endpoint)
  // 兜底: /api/team/members (R4-Worker-3 已有)
  var members = [];
  var apiError = null;
  var apiUsed = '/api/users';
  try {
    var resp = await apiGet('/api/users?page=1&page_size=100');
    if (resp && resp.success && resp.data) {
      var rawUsers = resp.data.users || resp.data;
      // 兼容 shape: 后端 /api/users 返回 {users: [...]}, 老 /api/team/members 返回 {members: [...]}
      members = Array.isArray(rawUsers) ? rawUsers : (rawUsers.members || []);
    } else if (resp && resp.code === 404) {
      // 后端 /api/users 不可用 → 兜底
      apiUsed = '/api/team/members (fallback)';
      var fb = await apiGet('/api/team/members');
      if (fb && fb.success) {
        members = (fb.data && fb.data.members) || fb.members || [];
      } else {
        apiError = (fb && (fb.error || fb.message)) || '后端 /api/team/members 返回非 success';
      }
    } else {
      apiError = (resp && (resp.error || resp.message)) || '后端返回非 success';
    }
  } catch (e) {
    apiError = e.message || String(e);
  }

  // 后端无数据或异常 → 显示空状态 (不注入假数据)
  var isEmpty = (members.length === 0);

  var totalMembers = members.length;
  var online = 0;
  var roleDist = {};
  for (var i = 0; i < members.length; i++) {
    if (members[i].status === 'online') online++;
    var r = members[i].role;
    roleDist[r] = (roleDist[r] || 0) + 1;
  }

  var roleLabel = { admin:'管理员', annotator:'标注员', reviewer:'质检员', viewer:'观察者' };
  var roleDistStr = '';
  var roleKeys = Object.keys(roleDist);
  for (var ri = 0; ri < roleKeys.length; ri++) {
    if (ri > 0) roleDistStr += ' · ';
    roleDistStr += (roleLabel[roleKeys[ri]] || roleKeys[ri]) + ' ' + roleDist[roleKeys[ri]];
  }

  c.innerHTML = '' +
    '<div class="page-header">' +
      '<div>' +
        '<div class="page-title">👥 团队管理</div>' +
        '<div style="font-size:11px;color:#8888aa;margin-top:2px">管理标注人员、质检人员、团队角色和权限</div>' +
      '</div>' +
      '<div class="page-stats">' +
        '<div class="page-stat"><div class="page-stat-val" style="color:#4a7aff">' + totalMembers + '</div><div class="page-stat-label">成员数</div></div>' +
        '<div class="page-stat"><div class="page-stat-val" style="color:#4ade80">' + online + '</div><div class="page-stat-label">在线</div></div>' +
        '<div class="page-stat"><div class="page-stat-val" style="color:#a78bfa;font-size:11px">' + (roleDistStr || '无数据') + '</div><div class="page-stat-label">角色分布</div></div>' +
      '</div>' +
    '</div>' +
    '<div class="toolbar">' +
      '<button class="btn btn-primary btn-sm" onclick="showAddMember()">➕ 添加成员</button>' +
      '<span style="flex:1"></span>' +
      '<input id="teamSearch" placeholder="🔍 搜索成员..." onkeyup="filterTeamMembers()" style="max-width:200px">' +
      '<select id="teamRoleFilter" onchange="filterTeamMembers()" style="min-width:100px">' +
        '<option value="">全部角色</option>' +
        '<option value="admin">管理员</option><option value="annotator">标注员</option><option value="reviewer">质检员</option><option value="viewer">观察者</option>' +
      '</select>' +
      '<select id="teamStatusFilter" onchange="filterTeamMembers()" style="min-width:100px">' +
        '<option value="">全部状态</option>' +
        '<option value="online">在线</option><option value="offline">离线</option>' +
      '</select>' +
    '</div>' +
    '<div style="background:#1e1e3a;border:1px solid #2a2a4a;border-radius:8px;overflow:hidden">' +
      '<table class="data-table" id="teamTable">' +
        '<thead><tr>' +
          '<th style="width:40px">#</th>' +
          '<th>用户名</th>' +
          '<th style="width:80px">角色</th>' +
          '<th style="width:70px">状态</th>' +
          '<th style="width:110px">最后活跃</th>' +
          '<th style="width:80px">任务量</th>' +
          '<th style="width:80px">质量分</th>' +
          '<th style="width:160px">操作</th>' +
        '</tr></thead>' +
        '<tbody id="teamTableBody"></tbody>' +
      '</table>' +
    '</div>';

  renderTeamTable(members);
}

function renderTeamTable(members) {
  var tbody = document.getElementById('teamTableBody');
  if (!tbody) return;

  var roleLabel = { admin:'管理员', annotator:'标注员', reviewer:'质检员', viewer:'观察者' };
  var roleColor = { admin:'#a78bfa', annotator:'#4a7aff', reviewer:'#4ade80', viewer:'#8888aa' };
  var roleBg = { admin:'rgba(167,139,250,0.15)', annotator:'rgba(74,122,255,0.15)', reviewer:'rgba(74,222,128,0.15)', viewer:'rgba(136,136,170,0.15)' };

  var html = '';
  for (var i = 0; i < members.length; i++) {
    var m = members[i];
    var statusColor = m.status === 'online' ? '#4ade80' : '#666688';
    var statusBg = m.status === 'online' ? 'rgba(74,222,128,0.15)' : 'rgba(102,102,136,0.15)';

    html += '<tr class="team-row" data-role="' + (m.role || '') + '" data-status="' + (m.status || '') + '">' +
      '<td style="color:#8888aa;font-size:11px">' + (i + 1) + '</td>' +
      '<td style="font-weight:600">' +
        '<div style="display:flex;align-items:center;gap:8px">' +
          '<span style="width:28px;height:28px;border-radius:50%;background:' + (roleBg[m.role] || '#2a2a4a') + ';display:flex;align-items:center;justify-content:center;font-size:14px;color:' + (roleColor[m.role] || '#8888aa') + '">' + (m.username || '?').charAt(0) + '</span>' +
          '<span>' + (m.username || m.name || '未命名') + '</span>' +
        '</div>' +
      '</td>' +
      '<td><span style="font-size:11px;padding:3px 8px;border-radius:10px;color:' + (roleColor[m.role] || '#8888aa') + ';background:' + (roleBg[m.role] || '#1e1e3a') + '">' + (roleLabel[m.role] || m.role || '成员') + '</span></td>' +
      '<td><span style="display:inline-flex;align-items:center;gap:4px;font-size:11px">' +
        '<span style="width:6px;height:6px;border-radius:50%;background:' + statusColor + '"></span>' +
        (m.status === 'online' ? '在线' : '离线') +
      '</span></td>' +
      '<td style="font-size:11px;color:#8888aa">' + (m.last_active || '--') + '</td>' +
      '<td>' + (m.tasks || 0).toLocaleString() + '</td>' +
      '<td style="font-weight:600;color:' + (typeof m.quality === 'number' && m.quality >= 90 ? '#4ade80' : m.quality >= 80 ? '#fbbf24' : '#ef4444') + '">' + (m.quality === '--' ? '--' : (typeof m.quality === 'number' ? m.quality.toFixed(1) : m.quality)) + '</td>' +
      '<td>' +
        '<button class="btn btn-outline btn-sm" onclick="editMemberRole(\'' + (m.id || m.username) + '\')" style="margin-right:4px">✏️ 编辑角色</button>' +
        (m.status === 'online' ?
          '<button class="btn btn-danger btn-sm" onclick="disableMember(\'' + (m.id || m.username) + '\')" style="margin-right:4px">⏸ 禁用</button>' :
          '<button class="btn btn-success btn-sm" onclick="enableMember(\'' + (m.id || m.username) + '\')" style="margin-right:4px">▶ 启用</button>') +
        '<button class="btn btn-outline btn-sm" onclick="viewMemberDetail(\'' + (m.id || m.username) + '\')">📋</button>' +
      '</td>' +
      '</tr>';
  }

  if (members.length === 0) {
    var emptyMsg = apiError
      ? '⚠️ 数据加载失败: ' + apiError + '<br/><span style="color:#666;font-size:11px">点击重试或检查后端 /api/team/members</span>'
      : '📭 暂无成员数据，点击上方"添加成员"创建';
    html = '<tr><td colspan="8" style="text-align:center;padding:40px;color:#8888aa">' + emptyMsg + '</td></tr>';
  }

  tbody.innerHTML = html;
}

function filterTeamMembers() {
  var search = ((document.getElementById('teamSearch') || {}).value || '').toLowerCase();
  var role = (document.getElementById('teamRoleFilter') || {}).value || '';
  var status = (document.getElementById('teamStatusFilter') || {}).value || '';

  var rows = document.querySelectorAll('.team-row');
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    var text = row.textContent.toLowerCase();
    var rowRole = row.getAttribute('data-role') || '';
    var rowStatus = row.getAttribute('data-status') || '';
    var matchSearch = !search || text.indexOf(search) >= 0;
    var matchRole = !role || rowRole === role;
    var matchStatus = !status || rowStatus === status;
    row.style.display = matchSearch && matchRole && matchStatus ? '' : 'none';
  }
}

/* ===== 成员操作 ===== */
function showAddMember() {
  if (typeof showModal !== 'function') return;
  showModal('' +
    '<span class="modal-close" onclick="closeModal()">✕</span>' +
    '<h4 style="margin-bottom:16px;color:#4a7aff">👤 添加成员</h4>' +
    '<div style="display:grid;gap:10px">' +
      '<input id="newMemberName" placeholder="用户名" style="padding:8px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0">' +
      '<input id="newMemberEmail" placeholder="邮箱(可选)" style="padding:8px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0">' +
      '<select id="newMemberRole" style="padding:8px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0">' +
        '<option value="annotator">标注员</option><option value="reviewer">质检员</option><option value="admin">管理员</option><option value="viewer">观察者</option>' +
      '</select>' +
      '<input id="newMemberSkills" placeholder="技能标签(逗号分隔)" style="padding:8px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0">' +
      '<button onclick="addMember()" class="btn btn-primary" style="width:100%;padding:10px">➕ 添加</button>' +
    '</div>');
}

async function addMember() {
  // P1-C-W1: 主路径 POST /api/users (task spec), 兜底 /api/team/members, /api/crowd/workers
  var name = (document.getElementById('newMemberName') || {}).value || '新成员';
  var role = (document.getElementById('newMemberRole') || {}).value || 'annotator';
  var skills = ((document.getElementById('newMemberSkills') || {}).value || '标注').split(',').map(function(s) { return s.trim(); });
  var email = (document.getElementById('newMemberEmail') || {}).value || '';
  var ok = false;
  try {
    var r = await apiPost('/api/users', { username: name, role: role, skills: skills, email: email });
    if (r && r.success) ok = true;
  } catch (e) { /* fall through */ }
  if (!ok) {
    try {
      var r2 = await apiPost('/api/team/members', { username: name, role: role, skills: skills, email: email });
      if (r2 && r2.success) ok = true;
    } catch (e2) { /* fall through */ }
  }
  if (!ok) {
    try { await apiPost('/api/crowd/workers', { name: name, role: role, skills: skills }); ok = true; } catch(e3) {}
  }
  if (typeof closeModal === 'function') closeModal();
  if (typeof showToast === 'function') showToast(ok ? '成员已添加: ' + name : '添加失败, 请重试', ok ? 'success' : 'error');
  renderTeam();
}

function editMemberRole(id) {
  if (typeof showModal !== 'function') return;
  showModal('' +
    '<span class="modal-close" onclick="closeModal()">✕</span>' +
    '<h4 style="margin-bottom:16px;color:#4a7aff">✏️ 编辑成员角色</h4>' +
    '<p style="font-size:12px;color:#8888aa;margin-bottom:12px">成员: ' + id + '</p>' +
    '<div style="display:grid;gap:10px">' +
      '<select id="editMemberRole" style="padding:8px;background:#0f0f1a;border:1px solid #2a2a4a;border-radius:4px;color:#e0e0f0">' +
        '<option value="admin">管理员</option><option value="annotator">标注员</option><option value="reviewer">质检员</option><option value="viewer">观察者</option>' +
      '</select>' +
      '<button onclick="saveMemberRole(\'' + id + '\')" class="btn btn-primary" style="width:100%;padding:10px">💾 保存</button>' +
    '</div>');
}

// R4-Worker-3: 死按钮接 API
async function saveMemberRole(id) {
  var role = (document.getElementById('editMemberRole') || {}).value || 'annotator';
  // P1-C-W1: 主路径 PUT /api/users/{id} (含 role), 兜底 /api/team/members/{id}/role
  var ok = false;
  try {
    var r = await apiPut('/api/users/' + encodeURIComponent(id), { role: role });
    if (r && r.success) {
      ok = true;
      if (typeof showToast === 'function') showToast('角色已更新: ' + id + ' → ' + role, 'success');
    }
  } catch (e) { /* fall through */ }
  if (!ok) {
    try {
      var r2 = await apiPut('/api/team/members/' + encodeURIComponent(id) + '/role', { role: role });
      if (r2 && r2.success) {
        ok = true;
        if (typeof showToast === 'function') showToast('角色已更新: ' + id + ' → ' + role, 'success');
      } else {
        if (typeof showToast === 'function') showToast('更新失败: ' + (r2?.error || '未知'), 'error');
      }
    } catch (e2) {
      if (typeof showToast === 'function') showToast('网络错误: ' + e2.message, 'error');
    }
  }
  if (typeof closeModal === 'function') closeModal();
  renderTeam();
}

async function disableMember(id) {
  // P1-C-W1: PUT /api/users/{id} (status=disabled), 兜底 /api/team/members/{id}/disable
  var ok = false;
  try {
    var r = await apiPut('/api/users/' + encodeURIComponent(id), { status: 'disabled' });
    if (r && r.success) {
      ok = true;
      if (typeof showToast === 'function') showToast('成员已禁用: ' + id, 'warning');
    }
  } catch (e) { /* fall through */ }
  if (!ok) {
    try {
      var r2 = await apiPost('/api/team/members/' + encodeURIComponent(id) + '/disable', {});
      if (r2 && r2.success) {
        ok = true;
        if (typeof showToast === 'function') showToast('成员已禁用: ' + id, 'warning');
      } else {
        if (typeof showToast === 'function') showToast('操作失败: ' + (r2?.error || r2?.message || '未知'), 'error');
      }
    } catch (e2) {
      if (typeof showToast === 'function') showToast('网络错误: ' + e2.message, 'error');
    }
  }
  renderTeam();
}

async function enableMember(id) {
  // P1-C-W1: PUT /api/users/{id} (status=online), 兜底 /api/team/members/{id}/enable
  var ok = false;
  try {
    var r = await apiPut('/api/users/' + encodeURIComponent(id), { status: 'online' });
    if (r && r.success) {
      ok = true;
      if (typeof showToast === 'function') showToast('成员已启用: ' + id, 'success');
    }
  } catch (e) { /* fall through */ }
  if (!ok) {
    try {
      var r2 = await apiPost('/api/team/members/' + encodeURIComponent(id) + '/enable', {});
      if (r2 && r2.success) {
        ok = true;
        if (typeof showToast === 'function') showToast('成员已启用: ' + id, 'success');
      } else {
        if (typeof showToast === 'function') showToast('操作失败: ' + (r2?.error || r2?.message || '未知'), 'error');
      }
    } catch (e2) {
      if (typeof showToast === 'function') showToast('网络错误: ' + e2.message, 'error');
    }
  }
  renderTeam();
}

function viewMemberDetail(id) {
  // R5-Worker-2: 改用 GET /api/team/members/{id} (按 id 精确取详情)
  // 显示加载态
  if (typeof showModal === 'function') {
    showModal('' +
      '<span class="modal-close" onclick="closeModal()">✕</span>' +
      '<h4 style="margin-bottom:12px;color:#4a7aff">👤 成员详情</h4>' +
      '<div style="color:#8888aa;font-size:12px;text-align:center;padding:40px 0">加载中...</div>');
  }
  apiGet('/api/team/members/' + encodeURIComponent(id)).then(function(resp){
    // 兼容 404 情况: resp 可能没有 success 字段
    var m = null;
    if (resp && resp.success && resp.data) {
      m = resp.data;
    } else if (resp && resp.data && resp.data.id) {
      // 404 fallback: 后端可能直接返回 data 不带 success
      m = resp.data;
    }
    if (!m) {
      if (typeof showModal !== 'function') return;
      showModal('' +
        '<span class="modal-close" onclick="closeModal()">✕</span>' +
        '<h4 style="margin-bottom:12px;color:#4a7aff">👤 成员: ' + id + '</h4>' +
        '<div style="font-size:12px;color:#8888aa;line-height:2">' +
          '<p>暂无详细信息</p>' +
        '</div>');
      return;
    }
    if (typeof showModal !== 'function') return;
    var statusText = m.status === 'online' ? '在线' : (m.status === 'disabled' || m.status === 'offline' ? '禁用/离线' : (m.status || '--'));
    var qualityText = (m.quality === '--' || m.quality == null) ? '--' : (typeof m.quality === 'number' ? m.quality.toFixed(1) : m.quality);
    showModal('' +
      '<span class="modal-close" onclick="closeModal()">✕</span>' +
      '<h4 style="margin-bottom:12px;color:#4a7aff">👤 成员详情: ' + (m.username || m.name || id) + '</h4>' +
      '<div style="font-size:12px;color:#8888aa;line-height:2">' +
        '<p><strong>ID:</strong> ' + (m.id || '--') + '</p>' +
        '<p><strong>用户名:</strong> ' + (m.username || m.name || '--') + '</p>' +
        '<p><strong>角色:</strong> ' + (m.role || '--') + '</p>' +
        '<p><strong>状态:</strong> ' + statusText + '</p>' +
        '<p><strong>最后活跃:</strong> ' + (m.last_active || '--') + '</p>' +
        '<p><strong>任务完成:</strong> ' + ((m.tasks || 0).toLocaleString()) + ' 条</p>' +
        '<p><strong>质量评分:</strong> ' + qualityText + '</p>' +
        '<p><strong>加入时间:</strong> ' + (m.created_at || '--') + '</p>' +
        (m.email ? '<p><strong>邮箱:</strong> ' + m.email + '</p>' : '') +
      '</div>' +
      '<hr style="margin:12px 0;border:0;border-top:1px solid #2a2a4a">' +
      '<div id="wf-audit-log" style="font-size:11px;color:#8888aa;line-height:1.6">' +
        '<strong style="color:#a78bfa">📋 审计日志 (GET /api/users/' + id + '/audit)</strong><br>加载中...' +
      '</div>');
    // P1-C-W1: 拉取审计日志
    apiGet('/api/users/' + encodeURIComponent(id) + '/audit?limit=10').then(function(ar){
      var logEl = document.getElementById('wf-audit-log');
      if (!logEl) return;
      if (!ar || !ar.success || !ar.data || !ar.data.entries) {
        logEl.innerHTML += '<br>⚠️ 审计日志加载失败';
        return;
      }
      var entries = ar.data.entries;
      var html = '<strong style="color:#a78bfa">📋 审计日志 (最近 ' + entries.length + ' 条)</strong>';
      for (var i = 0; i < entries.length; i++) {
        var e = entries[i];
        html += '<div style="padding:4px 0;border-bottom:1px solid #1a1a2a">' +
          '<span style="color:#4a7aff">' + (e.action || '--') + '</span> · ' +
          (e.resource ? '<span style="color:#4ade80">' + e.resource + '</span> · ' : '') +
          '<span style="color:#666;font-size:10px">' + (e.ts || '') + '</span><br>' +
          '<span style="color:#8888aa">' + (e.detail || '') + (e.ip ? ' (IP: ' + e.ip + ')' : '') + '</span>' +
          '</div>';
      }
      logEl.innerHTML = html;
    }).catch(function(){ /* 静默失败 */ });
  }).catch(function(e) {
    if (typeof showModal === 'function') {
      showModal('' +
        '<span class="modal-close" onclick="closeModal()">✕</span>' +
        '<h4 style="margin-bottom:12px;color:#4a7aff">👤 成员: ' + id + '</h4>' +
        '<div style="font-size:12px;color:#ef4444;line-height:2">' +
          '<p>加载失败: ' + (e?.message || '网络错误') + '</p>' +
        '</div>');
    }
  });
}
