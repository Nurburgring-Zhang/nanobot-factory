// views/Projects.js — 项目管理 (核心页 2) — P1-C-W1 spec 集成
// 调用 5 个 API: /api/projects (list), /api/projects (create), /api/projects/{id} (update),
//                /api/projects/{id} (delete), /api/projects/{id}/members
// 三态: loading / empty / error
// i18n: zh-CN/en-US ($t)
// RBAC: v-permission (create:requirement / edit:requirement / delete:requirement)

import { defineComponent, ref, reactive, computed, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { userMessage, NormalizedError } from '../utils/error.js';
import {
  listProjects, createProject, updateProject, deleteProject, getProjectMembers,
} from '../api/projects.js';

export const Projects = defineComponent({
  name: 'Projects',
  setup() {
    const query = ref('');
    const statusFilter = ref('');
    const list = ref([]);
    const error = ref(null);
    const loading = ref(false);
    const editDialog = ref(false);
    const editTarget = ref(null);
    const editForm = reactive({ name: '', description: '', status: 'active', owner: '' });
    const membersDialog = ref(false);
    const membersList = ref([]);
    const membersTarget = ref(null);

    async function load() {
      loading.value = true;
      error.value = null;
      try {
        const r = await listProjects({ status: statusFilter.value, page: 1, pageSize: 50 });
        if (r && r.success && r.data) {
          list.value = r.data.projects || [];
        } else {
          list.value = [];
          error.value = new NormalizedError({ type: 'client', message: (r && r.error) || '后端返回非 success', retryable: true });
        }
      } catch (e) {
        error.value = e;
        list.value = [];
      } finally {
        loading.value = false;
      }
    }

    onMounted(load);

    function openCreate() {
      editTarget.value = null;
      Object.assign(editForm, { name: '', description: '', status: 'active', owner: '' });
      editDialog.value = true;
    }

    function openEdit(p) {
      editTarget.value = p;
      Object.assign(editForm, {
        name: p.name || '',
        description: p.description || '',
        status: p.status || 'active',
        owner: p.owner || '',
      });
      editDialog.value = true;
    }

    async function saveEdit() {
      if (!editForm.name.trim()) { ElMessage.warning('项目名不能为空'); return; }
      try {
        let r;
        if (editTarget.value) {
          r = await updateProject(editTarget.value.id, { ...editForm });
        } else {
          r = await createProject({ ...editForm });
        }
        if (r && r.success) {
          ElMessage.success(editTarget.value ? '项目已更新' : '项目已创建');
          editDialog.value = false;
          load();
        } else {
          ElMessage.error('失败: ' + (r && r.error || '未知'));
        }
      } catch (e) {
        ElMessage.error('网络错误: ' + userMessage(e));
      }
    }

    async function onDelete(p) {
      try {
        await ElMessageBox.confirm(`确定删除项目 ${p.name}?`, '确认', { type: 'warning' });
      } catch (_) { return; }
      try {
        const r = await deleteProject(p.id);
        if (r && r.success) {
          ElMessage.success('已删除: ' + p.name);
          load();
        } else {
          ElMessage.error('删除失败: ' + (r && r.error || '未知'));
        }
      } catch (e) {
        ElMessage.error('网络错误: ' + userMessage(e));
      }
    }

    async function viewMembers(p) {
      membersTarget.value = p;
      membersList.value = [];
      membersDialog.value = true;
      try {
        const r = await getProjectMembers(p.id);
        if (r && r.success && r.data) {
          membersList.value = r.data.members || [];
        } else {
          ElMessage.error('加载成员失败: ' + (r && r.error || '未知'));
        }
      } catch (e) {
        ElMessage.error('网络错误: ' + userMessage(e));
      }
    }

    function statusTagType(s) {
      if (s === 'active') return 'success';
      if (s === 'paused') return 'warning';
      if (s === 'archived') return 'info';
      if (s === 'done') return 'primary';
      return '';
    }

    return {
      query, statusFilter, list, error, loading,
      editDialog, editTarget, editForm,
      membersDialog, membersList, membersTarget,
      userMessage, statusTagType,
      load, openCreate, openEdit, saveEdit, onDelete, viewMembers,
    };
  },
  template: `
    <div class="page-projects">
      <div class="card">
        <div class="card-title">📁 {{ $t('nav.projects') }} <span style="float:right;font-size:11px;color:#909399">P1-C-W1: 5 project APIs</span></div>

        <error-banner v-if="error && !loading" :error="error" :on-retry="load"></error-banner>

        <div class="table-actions">
          <el-input v-model="query" :placeholder="$t('common.search')" style="width:240px" clearable @change="load" @keyup.enter="load"/>
          <el-select v-model="statusFilter" :placeholder="$t('col.status')" style="width:140px" clearable @change="load">
            <el-option label="🟢 active" value="active"/>
            <el-option label="🟡 paused" value="paused"/>
            <el-option label="📦 archived" value="archived"/>
            <el-option label="✅ done" value="done"/>
          </el-select>
          <el-button type="primary" @click="load" :loading="loading">🔄 {{ $t('common.refresh') }}</el-button>
          <el-button type="success" v-permission="'create:requirement'" @click="openCreate">➕ {{ $t('common.create') }}</el-button>
        </div>

        <loading-spinner v-if="loading" :text="$t('common.loading')"></loading-spinner>

        <el-table v-else-if="list.length" :data="list" size="small" style="width:100%">
          <el-table-column prop="id" :label="$t('col.id')" width="120"/>
          <el-table-column prop="name" :label="$t('col.name')" min-width="180"/>
          <el-table-column :label="$t('col.status')" width="120">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="owner" :label="$t('col.assignee')" width="120"/>
          <el-table-column prop="created_at" :label="$t('col.created_at')" width="180">
            <template #default="{ row }">{{ (row.created_at || '').substring(0, 16) }}</template>
          </el-table-column>
          <el-table-column :label="$t('col.action')" width="280" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="viewMembers(row)">👥 {{ $t('btn.members') }}</el-button>
              <el-button type="warning" link size="small" @click="openEdit(row)" v-permission="'edit:requirement'">✏️ {{ $t('common.edit') }}</el-button>
              <el-button type="danger" link size="small" @click="onDelete(row)" v-permission="'edit:requirement'">🗑</el-button>
            </template>
          </el-table-column>
        </el-table>

        <empty-state v-else icon="📁" :title="$t('common.empty')" :description="$t('projects.empty_desc')"></empty-state>
      </div>

      <!-- 编辑/创建 dialog -->
      <el-dialog v-model="editDialog" :title="editTarget ? $t('common.edit') : $t('common.create')" width="480px">
        <div style="display:grid;gap:12px">
          <el-input v-model="editForm.name" placeholder="项目名 (2-200 chars)"/>
          <el-input v-model="editForm.description" type="textarea" :rows="3" placeholder="描述"/>
          <el-select v-model="editForm.status" placeholder="状态">
            <el-option label="🟢 active" value="active"/>
            <el-option label="🟡 paused" value="paused"/>
            <el-option label="📦 archived" value="archived"/>
            <el-option label="✅ done" value="done"/>
          </el-select>
          <el-input v-model="editForm.owner" placeholder="owner (用户名)"/>
        </div>
        <template #footer>
          <el-button @click="editDialog = false">{{ $t('common.cancel') }}</el-button>
          <el-button type="primary" @click="saveEdit">💾 {{ $t('common.save') }}</el-button>
        </template>
      </el-dialog>

      <!-- 成员 dialog -->
      <el-dialog v-model="membersDialog" :title="$t('btn.members')" width="380px">
        <p v-if="membersTarget" style="font-size:12px;color:#909399;margin-bottom:12px">{{ membersTarget.name }} · owner: {{ membersTarget.owner }}</p>
        <div v-if="membersList.length" style="font-size:13px">
          <div v-for="m in membersList" :key="m" style="padding:6px 0;border-bottom:1px solid #f0f0f0">👤 {{ m }}</div>
        </div>
        <empty-state v-else icon="👤" :title="$t('common.empty')" :description="$t('projects.no_members')"></empty-state>
      </el-dialog>
    </div>
  `,
});

export default Projects;
