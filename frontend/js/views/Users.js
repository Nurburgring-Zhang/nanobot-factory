// views/Users.js — 用户管理 (核心页 5) — P1-C-W1 spec 集成
// 调用 6 个 API: /api/users (list), /api/users (create), /api/users/{id} (update),
//                /api/users/{id} (delete), /api/users/{id}/audit, /api/users/me
// 三态: loading / empty / error
// i18n: zh-CN/en-US ($t)
// RBAC: v-permission (view:user / manage:user)

import { defineComponent, ref, reactive, computed, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { userMessage, NormalizedError } from '../utils/error.js';
import {
  listUsers, createUser, updateUser, deleteUser, getUserAudit, getMe,
} from '../api/users.js';

export const Users = defineComponent({
  name: 'Users',
  setup() {
    const roleFilter = ref('');
    const query = ref('');
    const list = ref([]);
    const me = ref(null);
    const error = ref(null);
    const loading = ref(false);
    const editDialog = ref(false);
    const editTarget = ref(null);
    const editForm = reactive({ username: '', role: 'annotator', email: '', status: 'offline' });
    const auditDialog = ref(false);
    const auditList = ref([]);
    const auditTarget = ref(null);

    async function load() {
      loading.value = true;
      error.value = null;
      try {
        const [r, m] = await Promise.allSettled([
          listUsers({ role: roleFilter.value, page: 1, pageSize: 50 }),
          getMe().catch(() => null),
        ]);
        if (r.status === 'fulfilled' && r.value && r.value.success) {
          list.value = (r.value.data && r.value.data.users) || [];
        } else {
          list.value = [];
          if (r.status === 'rejected') error.value = r.reason;
          else error.value = new NormalizedError({ type: 'client', message: (r.value && r.value.error) || '后端返回非 success', retryable: true });
        }
        if (m.status === 'fulfilled' && m.value && m.value.success) {
          me.value = m.value.data || null;
        } else {
          me.value = null; // 401 → 未登录
        }
      } catch (e) {
        error.value = e;
        list.value = [];
      } finally {
        loading.value = false;
      }
    }

    onMounted(load);

    const meLabel = computed(() => {
      if (me.value) return me.value.username || me.value.name || '已登录';
      return '未登录';
    });
    const meRole = computed(() => (me.value && me.value.role) || 'guest');

    function openCreate() {
      editTarget.value = null;
      Object.assign(editForm, { username: '', role: 'annotator', email: '', status: 'offline' });
      editDialog.value = true;
    }

    function openEdit(u) {
      editTarget.value = u;
      Object.assign(editForm, {
        username: u.username || '',
        role: u.role || 'annotator',
        email: u.email || '',
        status: u.status || 'offline',
      });
      editDialog.value = true;
    }

    async function saveEdit() {
      if (!editTarget.value) {
        // create
        if (editForm.username.length < 2) { ElMessage.warning('用户名至少 2 字符'); return; }
        try {
          const r = await createUser({
            username: editForm.username,
            role: editForm.role,
            email: editForm.email,
            skills: [],
          });
          if (r && r.success) {
            ElMessage.success('用户已创建: ' + (r.data && r.data.username || ''));
            editDialog.value = false;
            load();
          } else {
            ElMessage.error('创建失败: ' + (r && r.error || '未知'));
          }
        } catch (e) {
          ElMessage.error('网络错误: ' + userMessage(e));
        }
      } else {
        // update (role / status / email)
        try {
          const r = await updateUser(editTarget.value.id, {
            role: editForm.role,
            email: editForm.email,
            status: editForm.status,
          });
          if (r && r.success) {
            ElMessage.success('用户已更新');
            editDialog.value = false;
            load();
          } else {
            ElMessage.error('更新失败: ' + (r && r.error || '未知'));
          }
        } catch (e) {
          ElMessage.error('网络错误: ' + userMessage(e));
        }
      }
    }

    async function onDelete(u) {
      try {
        await ElMessageBox.confirm(`确定删除用户 ${u.username}?`, '确认', { type: 'warning' });
      } catch (_) { return; }
      try {
        const r = await deleteUser(u.id);
        if (r && r.success) {
          ElMessage.success('已删除: ' + u.username);
          load();
        } else {
          ElMessage.error('删除失败: ' + (r && r.error || '未知'));
        }
      } catch (e) {
        ElMessage.error('网络错误: ' + userMessage(e));
      }
    }

    async function viewAudit(u) {
      auditTarget.value = u;
      auditList.value = [];
      auditDialog.value = true;
      try {
        const r = await getUserAudit(u.id, 20);
        if (r && r.success && r.data) {
          auditList.value = r.data.entries || [];
        } else {
          ElMessage.error('加载审计失败: ' + (r && r.error || '未知'));
        }
      } catch (e) {
        ElMessage.error('网络错误: ' + userMessage(e));
      }
    }

    function roleTagType(r) {
      if (r === 'admin') return 'danger';
      if (r === 'annotator') return 'primary';
      if (r === 'reviewer') return 'success';
      if (r === 'viewer') return 'info';
      return '';
    }

    return {
      roleFilter, query, list, me, error, loading,
      editDialog, editTarget, editForm,
      auditDialog, auditList, auditTarget,
      meLabel, meRole,
      userMessage, roleTagType,
      load, openCreate, openEdit, saveEdit, onDelete, viewAudit,
    };
  },
  template: `
    <div class="page-users">
      <div class="card">
        <div class="card-title">
          👤 {{ $t('nav.users') }}
          <span style="float:right;font-size:12px;color:#909399">P1-C-W1: 6 user APIs</span>
        </div>

        <div style="font-size:12px;color:#909399;margin-bottom:12px">
          {{ $t('stats.current_user') }}: <strong style="color:#409eff">{{ meLabel }}</strong> ({{ meRole }}) · <span style="font-family:monospace">GET /api/users/me</span>
        </div>

        <error-banner v-if="error && !loading" :error="error" :on-retry="load"></error-banner>

        <div class="table-actions">
          <el-input v-model="query" :placeholder="$t('common.search')" style="width:200px" clearable @change="load" @keyup.enter="load"/>
          <el-select v-model="roleFilter" :placeholder="$t('col.role')" style="width:140px" clearable @change="load">
            <el-option label="admin" value="admin"/>
            <el-option label="annotator" value="annotator"/>
            <el-option label="reviewer" value="reviewer"/>
            <el-option label="viewer" value="viewer"/>
          </el-select>
          <el-button type="primary" @click="load" :loading="loading">🔄 {{ $t('common.refresh') }}</el-button>
          <el-button type="success" v-permission="'manage:user'" @click="openCreate">➕ {{ $t('common.create') }}</el-button>
        </div>

        <loading-spinner v-if="loading" :text="$t('common.loading')"></loading-spinner>

        <el-table v-else-if="list.length" :data="list" size="small" style="width:100%">
          <el-table-column prop="id" :label="$t('col.id')" width="140"/>
          <el-table-column prop="username" :label="$t('col.name')" min-width="120"/>
          <el-table-column :label="$t('col.role')" width="120">
            <template #default="{ row }">
              <el-tag :type="roleTagType(row.role)" size="small">{{ row.role }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('col.status')" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'online' ? 'success' : row.status === 'disabled' ? 'danger' : 'info'" size="small">{{ row.status || '--' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="email" label="email" min-width="160"/>
          <el-table-column prop="created_at" :label="$t('col.created_at')" width="160">
            <template #default="{ row }">{{ (row.created_at || '').substring(0, 16) }}</template>
          </el-table-column>
          <el-table-column :label="$t('col.action')" width="280" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="viewAudit(row)" v-permission="'view:audit'">📋 {{ $t('btn.audit') }}</el-button>
              <el-button type="warning" link size="small" @click="openEdit(row)" v-permission="'manage:user'">✏️ {{ $t('common.edit') }}</el-button>
              <el-button type="danger" link size="small" @click="onDelete(row)" v-permission="'manage:user'">🗑</el-button>
            </template>
          </el-table-column>
        </el-table>

        <empty-state v-else icon="👤" :title="$t('common.empty')" :description="$t('users.empty_desc')"></empty-state>
      </div>

      <!-- 编辑/创建 dialog -->
      <el-dialog v-model="editDialog" :title="editTarget ? $t('common.edit') : $t('common.create')" width="480px">
        <div style="display:grid;gap:12px">
          <el-input v-model="editForm.username" placeholder="username (2-64 chars)" :disabled="!!editTarget"/>
          <el-select v-model="editForm.role" placeholder="role">
            <el-option label="admin" value="admin"/>
            <el-option label="annotator" value="annotator"/>
            <el-option label="reviewer" value="reviewer"/>
            <el-option label="viewer" value="viewer"/>
          </el-select>
          <el-input v-model="editForm.email" placeholder="email"/>
          <el-select v-if="editTarget" v-model="editForm.status" placeholder="status">
            <el-option label="online" value="online"/>
            <el-option label="offline" value="offline"/>
            <el-option label="disabled" value="disabled"/>
          </el-select>
        </div>
        <template #footer>
          <el-button @click="editDialog = false">{{ $t('common.cancel') }}</el-button>
          <el-button type="primary" @click="saveEdit">💾 {{ $t('common.save') }}</el-button>
        </template>
      </el-dialog>

      <!-- 审计 dialog -->
      <el-dialog v-model="auditDialog" :title="$t('btn.audit')" width="520px">
        <p v-if="auditTarget" style="font-size:12px;color:#909399;margin-bottom:12px">
          user: <strong>{{ auditTarget.username }}</strong> · {{ auditList.length }} entries
        </p>
        <div v-if="auditList.length" style="max-height:400px;overflow-y:auto">
          <div v-for="(e, i) in auditList" :key="i" style="padding:8px;border-bottom:1px solid #f0f0f0;font-size:12px">
            <div>
              <el-tag size="small" :type="e.action === 'delete' ? 'danger' : e.action === 'update' ? 'warning' : e.action === 'create' ? 'success' : 'info'">{{ e.action }}</el-tag>
              <span style="margin-left:6px" v-if="e.resource">{{ e.resource }}</span>
              <span style="color:#909399;float:right">{{ (e.ts || '').substring(0, 19) }}</span>
            </div>
            <div style="color:#606266;margin-top:2px">{{ e.detail }}{{ e.ip ? ' · IP: ' + e.ip : '' }}</div>
          </div>
        </div>
        <empty-state v-else icon="📋" :title="$t('common.empty')" :description="$t('users.no_audit')"></empty-state>
      </el-dialog>
    </div>
  `,
});

export default Users;
