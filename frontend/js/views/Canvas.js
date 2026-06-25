// views/Canvas.js — 画布 (核心页 3) — P1-C-W1 spec 集成
// 调用 5 个 API: /api/canvas/{id}, /api/canvas/{id}/save, /api/canvas/templates,
//                /api/canvas/{id}/render, /api/canvas/{id}/export
// 三态: loading / empty / error
// i18n: zh-CN/en-US ($t)
// RBAC: v-permission (edit:asset 等)

import { defineComponent, ref, reactive, computed, onMounted } from 'vue';
import { userMessage, NormalizedError } from '../utils/error.js';
import {
  getCanvas, saveCanvas, listCanvasTemplates, renderCanvas, exportCanvas,
} from '../api/canvas.js';

export const Canvas = defineComponent({
  name: 'Canvas',
  setup() {
    const canvasId = ref('default');
    const canvas = reactive({ nodes: {}, connections: [] });
    const templates = ref([]);
    const status = ref('idle'); // idle | loading | saving | rendering | error
    const error = ref(null);
    const lastSaved = ref(null);
    const lastRenderTask = ref(null);
    const exportUrl = ref(null);

    async function loadFromBackend() {
      status.value = 'loading';
      error.value = null;
      try {
        const r = await getCanvas(canvasId.value);
        if (r && r.success && r.data) {
          canvas.nodes = r.data.nodes || {};
          canvas.connections = r.data.connections || [];
        } else if (r && r.code === 404) {
          canvas.nodes = {};
          canvas.connections = [];
        }
        status.value = 'idle';
      } catch (e) {
        error.value = e;
        status.value = 'error';
      }
    }

    async function loadTemplates() {
      try {
        const r = await listCanvasTemplates();
        if (r && r.success && r.data) {
          templates.value = r.data.templates || [];
        }
      } catch (e) {
        // 静默失败 — 模板列表是辅助功能
        console.warn('[canvas] templates load failed:', e);
      }
    }

    async function save() {
      status.value = 'saving';
      error.value = null;
      try {
        const r = await saveCanvas(canvasId.value, {
          nodes: canvas.nodes,
          connections: canvas.connections,
        });
        if (r && r.success) {
          lastSaved.value = (r.data && r.data.saved_at) || new Date().toISOString();
        } else {
          error.value = new NormalizedError({
            type: 'client',
            message: (r && r.error) || '保存失败',
            retryable: true,
          });
        }
        status.value = 'idle';
      } catch (e) {
        error.value = e;
        status.value = 'error';
      }
    }

    async function applyTemplate(tplId) {
      const tpl = templates.value.find((t) => t.id === tplId);
      if (!tpl) return;
      canvas.nodes = {};
      canvas.connections = [];
      const nodesArr = tpl.nodes || [];
      for (const nd of nodesArr) {
        canvas.nodes[nd.id] = { ...nd };
      }
      canvas.connections = (tpl.connections || []).slice();
      window.dispatchEvent(new CustomEvent('toast', { detail: { message: `已应用模板: ${tpl.name}`, type: 'success' } }));
    }

    async function render() {
      status.value = 'rendering';
      error.value = null;
      try {
        const r = await renderCanvas(canvasId.value, 'png');
        if (r && r.success && r.data) {
          lastRenderTask.value = r.data.task_id;
          window.dispatchEvent(new CustomEvent('toast', { detail: { message: `渲染已提交: ${r.data.task_id}`, type: 'info' } }));
        } else {
          error.value = new NormalizedError({ type: 'client', message: (r && r.error) || '渲染失败', retryable: true });
        }
        status.value = 'idle';
      } catch (e) {
        error.value = e;
        status.value = 'error';
      }
    }

    async function doExport() {
      error.value = null;
      try {
        const r = await exportCanvas(canvasId.value, 'json');
        if (r && r.success && r.data && r.data.download_url) {
          exportUrl.value = r.data.download_url;
          window.dispatchEvent(new CustomEvent('toast', { detail: { message: '导出 URL 已生成: ' + r.data.download_url, type: 'success' } }));
        } else {
          error.value = new NormalizedError({ type: 'client', message: (r && r.error) || '导出失败', retryable: true });
        }
      } catch (e) {
        error.value = e;
      }
    }

    onMounted(() => {
      loadFromBackend();
      loadTemplates();
    });

    const nodeCount = computed(() => Object.keys(canvas.nodes).length);
    const connCount = computed(() => canvas.connections.length);

    return {
      canvasId, canvas, templates, status, error,
      lastSaved, lastRenderTask, exportUrl,
      nodeCount, connCount,
      userMessage, loadFromBackend, save, applyTemplate, render, doExport,
    };
  },
  template: `
    <div class="page-canvas">
      <div class="card">
        <div class="card-title">🎨 {{ $t('nav.canvas') }} <span style="float:right;font-size:11px;color:#909399">P1-C-W1: 5 canvas APIs</span></div>

        <error-banner v-if="error" :error="error" :on-retry="loadFromBackend"></error-banner>

        <div class="canvas-toolbar">
          <el-input v-model="canvasId" placeholder="Canvas ID" style="width:200px" size="small"/>
          <el-button type="primary" plain size="small" @click="loadFromBackend" :loading="status === 'loading'">{{ $t('btn.load') }}</el-button>
          <el-button type="success" plain size="small" v-permission="'edit:asset'" @click="save" :loading="status === 'saving'">💾 {{ $t('btn.save') }}</el-button>
          <el-select :placeholder="$t('btn.load_template')" size="small" style="width:200px" @change="applyTemplate" v-permission="'edit:asset'">
            <el-option v-for="t in templates" :key="t.id" :label="t.name + ' (' + (t.nodes?.length || 0) + ' nodes)'" :value="t.id"/>
          </el-select>
          <el-button type="warning" plain size="small" @click="render" :loading="status === 'rendering'" v-permission="'view:asset'">🎨 {{ $t('btn.render') }}</el-button>
          <el-button size="small" @click="doExport" v-permission="'view:asset'">📤 {{ $t('btn.export') }}</el-button>
          <span style="flex:1"></span>
          <span v-if="lastSaved" style="font-size:11px;color:#67c23a">✓ {{ $t('canvas.saved_at') }}: {{ lastSaved.substring(0, 19) }}</span>
          <span v-if="lastRenderTask" style="font-size:11px;color:#409eff;margin-left:8px">🎨 {{ $t('canvas.render_task') }}: {{ lastRenderTask }}</span>
          <span v-if="exportUrl" style="font-size:11px;color:#909399;margin-left:8px"><a :href="exportUrl" target="_blank">⬇ {{ exportUrl }}</a></span>
        </div>

        <div class="canvas-host">
          <loading-spinner v-if="status === 'loading'" :text="$t('canvas.loading')"></loading-spinner>
          <empty-state v-else-if="nodeCount === 0" icon="🎨" :title="$t('canvas.empty_title')" :description="$t('canvas.empty_desc')"></empty-state>
          <div v-else style="width:100%;padding:20px;text-align:left;color:#303133">
            <div style="font-size:14px;margin-bottom:12px"><strong>{{ nodeCount }}</strong> nodes · <strong>{{ connCount }}</strong> connections</div>
            <div style="font-size:12px;color:#909399">{{ $t('canvas.full_editor') }}</div>
          </div>
        </div>
      </div>
    </div>
  `,
});

export default Canvas;
