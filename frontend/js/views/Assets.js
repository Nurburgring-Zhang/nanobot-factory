// views/Assets.js — 资产管理 (核心页 4) — P1-C-W1 spec 集成
// 调用 5 个 API: /api/assets (list), /api/assets/upload, /api/assets/{id} (delete),
//                /api/assets/{id}/download, /api/assets/{id}/tag
// 三态: loading / empty / error
// i18n: zh-CN/en-US ($t)
// RBAC: v-permission (create:asset / delete:asset)

import { defineComponent, ref, reactive, computed, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { userMessage, NormalizedError } from '../utils/error.js';
import {
  listAssets, uploadAsset, deleteAsset, tagAsset, buildDownloadUrl,
} from '../api/assets.js';

export const Assets = defineComponent({
  name: 'Assets',
  setup() {
    const query = ref('');
    const typeFilter = ref('');
    const list = ref([]);
    const error = ref(null);
    const loading = ref(false);
    const uploadDialog = ref(false);
    const tagDialog = ref(false);
    const tagTarget = ref(null);
    const newTags = ref('');
    const uploadFile = ref(null);
    const uploadType = ref('image');
    const uploadTags = ref('');

    async function load() {
      loading.value = true;
      error.value = null;
      try {
        const r = await listAssets({ q: query.value, type: typeFilter.value, page: 1, pageSize: 50 });
        if (r && r.success && r.data) {
          list.value = r.data.assets || [];
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

    function openUpload() {
      uploadFile.value = null;
      uploadType.value = 'image';
      uploadTags.value = '';
      uploadDialog.value = true;
    }

    async function doUpload() {
      if (!uploadFile.value) {
        ElMessage.warning('请选择文件');
        return;
      }
      try {
        const r = await uploadAsset(uploadFile.value, { type: uploadType.value, tags: uploadTags.value });
        if (r && r.success) {
          ElMessage.success('上传成功: ' + (r.data && r.data.name || ''));
          uploadDialog.value = false;
          load();
        } else {
          ElMessage.error('上传失败: ' + (r && r.error || '未知'));
        }
      } catch (e) {
        ElMessage.error('网络错误: ' + userMessage(e));
      }
    }

    function onFileChange(e) {
      const f = (e.target && e.target.files && e.target.files[0]) || null;
      uploadFile.value = f;
    }

    function onDownload(a) {
      // 跳转到原生下载 URL (浏览器处理, 不用 fetch)
      const url = buildDownloadUrl(a.id);
      window.open(url, '_blank', 'noopener');
    }

    function openTagDialog(a) {
      tagTarget.value = a;
      newTags.value = '';
      tagDialog.value = true;
    }

    async function doTag() {
      if (!tagTarget.value) return;
      const tags = newTags.value.split(',').map((s) => s.trim()).filter(Boolean);
      if (tags.length === 0) { ElMessage.warning('请输入至少一个标签'); return; }
      try {
        const r = await tagAsset(tagTarget.value.id, tags);
        if (r && r.success) {
          ElMessage.success('标签已更新: ' + (r.data && r.data.tags || []).join(', '));
          tagDialog.value = false;
          load();
        } else {
          ElMessage.error('失败: ' + (r && r.error || '未知'));
        }
      } catch (e) {
        ElMessage.error('网络错误: ' + userMessage(e));
      }
    }

    async function onDelete(a) {
      try {
        await ElMessageBox.confirm(`确定删除资产 ${a.name} ?`, '确认', { type: 'warning' });
      } catch (_) { return; }
      try {
        const r = await deleteAsset(a.id);
        if (r && r.success) {
          ElMessage.success('已删除: ' + a.name);
          load();
        } else {
          ElMessage.error('删除失败: ' + (r && r.error || '未知'));
        }
      } catch (e) {
        ElMessage.error('网络错误: ' + userMessage(e));
      }
    }

    return {
      query, typeFilter, list, error, loading,
      uploadDialog, uploadFile, uploadType, uploadTags,
      tagDialog, tagTarget, newTags,
      userMessage,
      load, openUpload, doUpload, onFileChange,
      onDownload, openTagDialog, doTag, onDelete,
    };
  },
  template: `
    <div class="page-assets">
      <div class="card">
        <div class="card-title">🖼️ {{ $t('nav.assets') }} <span style="float:right;font-size:11px;color:#909399">P1-C-W1: 5 asset APIs</span></div>

        <error-banner v-if="error && !loading" :error="error" :on-retry="load"></error-banner>

        <div class="table-actions">
          <el-input v-model="query" :placeholder="$t('common.search')" style="width:240px" clearable @change="load" @keyup.enter="load"/>
          <el-select v-model="typeFilter" :placeholder="$t('col.type')" style="width:140px" clearable @change="load">
            <el-option label="🖼️ image" value="image"/>
            <el-option label="🎬 video" value="video"/>
            <el-option label="📝 text" value="text"/>
            <el-option label="🎵 audio" value="audio"/>
            <el-option label="🎯 3d" value="model3d"/>
          </el-select>
          <el-button type="primary" @click="load" :loading="loading">🔄 {{ $t('common.refresh') }}</el-button>
          <el-button type="success" v-permission="'create:asset'" @click="openUpload">📤 {{ $t('btn.upload') }}</el-button>
        </div>

        <loading-spinner v-if="loading" :text="$t('common.loading')"></loading-spinner>

        <el-table v-else-if="list.length" :data="list" size="small" style="width:100%">
          <el-table-column prop="id" :label="$t('col.id')" width="160"/>
          <el-table-column prop="name" :label="$t('col.name')" min-width="160"/>
          <el-table-column prop="type" :label="$t('col.type')" width="100">
            <template #default="{ row }">
              <el-tag size="small">{{ row.type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('col.size')" width="100">
            <template #default="{ row }">{{ row.size ? (row.size / 1024).toFixed(1) + ' KB' : '--' }}</template>
          </el-table-column>
          <el-table-column :label="$t('col.tags')" min-width="200">
            <template #default="{ row }">
              <el-tag v-for="t in (row.tags || [])" :key="t" size="small" type="info" style="margin-right:2px">{{ t }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('col.action')" width="280" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="onDownload(row)">⬇️ {{ $t('btn.download') }}</el-button>
              <el-button type="warning" link size="small" @click="openTagDialog(row)" v-permission="'edit:asset'">🏷️ {{ $t('btn.tag') }}</el-button>
              <el-button type="danger" link size="small" @click="onDelete(row)" v-permission="'delete:asset'">🗑</el-button>
            </template>
          </el-table-column>
        </el-table>

        <empty-state v-else icon="🖼️" :title="$t('common.empty')" :description="$t('assets.empty_desc')"></empty-state>
      </div>

      <!-- 上传 dialog -->
      <el-dialog v-model="uploadDialog" :title="$t('btn.upload')" width="480px">
        <div style="display:grid;gap:12px">
          <input type="file" @change="onFileChange"/>
          <el-select v-model="uploadType" :placeholder="$t('col.type')">
            <el-option label="image" value="image"/>
            <el-option label="video" value="video"/>
            <el-option label="text" value="text"/>
            <el-option label="audio" value="audio"/>
            <el-option label="model3d" value="model3d"/>
          </el-select>
          <el-input v-model="uploadTags" placeholder="tags (comma-separated)"/>
        </div>
        <template #footer>
          <el-button @click="uploadDialog = false">{{ $t('common.cancel') }}</el-button>
          <el-button type="primary" @click="doUpload">📤 {{ $t('btn.upload') }}</el-button>
        </template>
      </el-dialog>

      <!-- 打标签 dialog -->
      <el-dialog v-model="tagDialog" :title="$t('btn.tag')" width="420px">
        <p v-if="tagTarget" style="font-size:12px;color:#909399">asset: {{ tagTarget.name }} (current: {{ (tagTarget.tags || []).join(', ') || 'none' }})</p>
        <el-input v-model="newTags" placeholder="new tags (comma-separated, will be merged)" style="margin-top:8px"/>
        <template #footer>
          <el-button @click="tagDialog = false">{{ $t('common.cancel') }}</el-button>
          <el-button type="primary" @click="doTag">🏷️ {{ $t('btn.save') }}</el-button>
        </template>
      </el-dialog>
    </div>
  `,
});

export default Assets;
