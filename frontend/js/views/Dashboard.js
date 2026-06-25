// views/Dashboard.js — 仪表盘 (核心页 1) — P1-C-W1 spec 集成
// 调用 5 个 API: /api/stats/overview, /api/tasks/recent, /api/notifications, /api/audit/stats, /api/users/me
// 三态: loading / empty / error  (使用 AsyncBoundary + ErrorBanner + EmptyState + LoadingSpinner)
// i18n: zh-CN/en-US (通过 $t)
// RBAC: v-permission 保护敏感操作

import { defineComponent, ref, reactive, computed, onMounted } from 'vue';
import { httpGet } from '../api/client.js';
import { userMessage, NormalizedError } from '../utils/error.js';
import {
  getStatsOverview, getRecentTasks, getNotifications,
  getAuditStats, getMe,
} from '../api/dashboard.js';

export const Dashboard = defineComponent({
  name: 'Dashboard',
  setup() {
    const period = ref('today'); // today / week / month
    const stats = reactive({
      production_count: 0, delivery_count: 0, daily_active_users: 0,
      avg_quality_score: 0, tasks_total: 0, tasks_done: 0, tasks_pending: 0,
      assets_total: 0, projects_total: 0, members_online: 0,
    });
    const recent = ref([]);
    const notifs = ref([]);
    const audit = reactive({ total_actions: 0, anomalies: 0 });
    const me = ref(null);
    const error = ref(null);
    const loading = ref(false);

    async function load() {
      loading.value = true;
      error.value = null;
      try {
        // 5 个 API 并发拉取 (P1-C-W1 spec)
        const [ov, t, n, a, m] = await Promise.allSettled([
          getStatsOverview(period.value),
          getRecentTasks(5),
          getNotifications(5, true),
          getAuditStats(period.value),
          getMe().catch(() => null), // 401 不算错
        ]);
        // stats/overview
        if (ov.status === 'fulfilled' && ov.value && ov.value.success) {
          const d = ov.value.data || {};
          Object.assign(stats, {
            production_count: d.production_count || 0,
            delivery_count: d.delivery_count || 0,
            daily_active_users: d.daily_active_users || 0,
            avg_quality_score: d.avg_quality_score || 0,
            tasks_total: d.tasks_total || 0,
            tasks_done: d.tasks_done || 0,
            tasks_pending: d.tasks_pending || 0,
            assets_total: d.assets_total || 0,
            projects_total: d.projects_total || 0,
            members_online: d.members_online || 0,
          });
        } else if (ov.status === 'rejected') {
          // 累积错误, 但不立即 throw — 让其它 4 个仍能渲染
          if (!error.value) error.value = ov.reason;
        }
        // tasks/recent
        if (t.status === 'fulfilled' && t.value && t.value.success) {
          const list = (t.value.data && t.value.data.tasks) || [];
          recent.value = Array.isArray(list) ? list : [];
        }
        // notifications
        if (n.status === 'fulfilled' && n.value && n.value.success) {
          const list = (n.value.data && n.value.data.notifications) || [];
          notifs.value = Array.isArray(list) ? list : [];
        }
        // audit/stats
        if (a.status === 'fulfilled' && a.value && a.value.success) {
          const d = a.value.data || {};
          audit.total_actions = d.total_actions || 0;
          audit.anomalies = d.anomalies || 0;
        }
        // users/me
        if (m.status === 'fulfilled' && m.value && m.value.success) {
          me.value = m.value.data || null;
        } else {
          me.value = null; // 401 → 未登录
        }
      } catch (e) {
        error.value = e;
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

    function onPeriodChange(p) {
      period.value = p;
      load();
    }

    return {
      period, stats, recent, notifs, audit, me, error, loading, meLabel, meRole,
      userMessage, load, onPeriodChange,
    };
  },
  template: `
    <div class="page-dashboard">
      <error-banner v-if="error && !loading" :error="error" :on-retry="load"></error-banner>

      <!-- 周期切换 (RBAC: view:dashboard) -->
      <div class="card" v-permission="'view:dashboard'">
        <div class="card-title">
          📊 {{ $t('nav.dashboard') }}
          <span style="float:right;font-size:12px;color:#909399">
            <el-radio-group v-model="period" size="small" @change="onPeriodChange">
              <el-radio-button label="today">{{ $t('period.today') }}</el-radio-button>
              <el-radio-button label="week">{{ $t('period.week') }}</el-radio-button>
              <el-radio-button label="month">{{ $t('period.month') }}</el-radio-button>
            </el-radio-group>
          </span>
        </div>

        <loading-spinner v-if="loading" :text="$t('common.loading')"></loading-spinner>

        <div v-else class="stats-grid">
          <div class="stat-card">
            <div class="num">{{ stats.production_count }}</div>
            <div class="label">{{ $t('stats.production_count') }}</div>
          </div>
          <div class="stat-card">
            <div class="num">{{ stats.avg_quality_score }}</div>
            <div class="label">{{ $t('stats.avg_quality_score') }}</div>
          </div>
          <div class="stat-card">
            <div class="num">{{ stats.tasks_pending }}</div>
            <div class="label">{{ $t('stats.tasks_pending') }}</div>
          </div>
          <div class="stat-card">
            <div class="num">{{ stats.daily_active_users }}</div>
            <div class="label">{{ $t('stats.daily_active_users') }}</div>
          </div>
        </div>
      </div>

      <!-- 最近任务 (RBAC: view:task) -->
      <div class="flex">
        <div class="card flex-1" v-permission="'view:task'">
          <div class="card-title">⏱ {{ $t('dashboard.recent_tasks') }} <span style="float:right;font-size:11px;color:#909399">GET /api/tasks/recent</span></div>
          <el-table v-if="recent.length" :data="recent" size="small" style="width:100%">
            <el-table-column prop="id" :label="$t('col.id')" width="120"/>
            <el-table-column prop="name" :label="$t('col.name')" min-width="160"/>
            <el-table-column prop="status" :label="$t('col.status')" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === 'done' ? 'success' : row.status === 'error' ? 'danger' : row.status === 'running' ? 'warning' : 'info'" size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="owner" :label="$t('col.assignee')" width="120"/>
          </el-table>
          <empty-state v-else icon="📭" :title="$t('common.empty')" :description="$t('dashboard.recent_tasks_empty')"></empty-state>
        </div>

        <!-- 通知 (无需权限) -->
        <div class="card" style="width:340px">
          <div class="card-title">🔔 {{ $t('dashboard.notifications') }} <span style="float:right;font-size:11px;color:#909399">GET /api/notifications</span></div>
          <div v-if="notifs.length" style="max-height:240px;overflow-y:auto">
            <div v-for="n in notifs" :key="n.id" class="rank-row">
              <span style="font-size:18px;margin-right:8px">{{ n.level === 'error' ? '❌' : n.level === 'warn' ? '⚠️' : n.level === 'success' ? '✅' : 'ℹ️' }}</span>
              <span class="rank-name" style="font-size:13px">{{ n.title }}</span>
            </div>
          </div>
          <empty-state v-else icon="🔕" :title="$t('common.empty')" :description="$t('dashboard.notifications_empty')"></empty-state>
        </div>
      </div>

      <!-- 底部: 审计 + 当前用户 + 统计 -->
      <div class="flex">
        <div class="stat-card flex-1" v-permission="'view:audit'">
          <div class="num">{{ audit.total_actions }}</div>
          <div class="label">{{ $t('stats.audit_actions') }} (异常: {{ audit.anomalies }})</div>
        </div>
        <div class="stat-card flex-1">
          <div class="num" style="font-size:18px">{{ meLabel }}</div>
          <div class="label">{{ $t('stats.current_user') }} ({{ meRole }})</div>
        </div>
        <div class="stat-card flex-1">
          <div class="num">{{ stats.assets_total }} / {{ stats.projects_total }}</div>
          <div class="label">{{ $t('stats.assets_projects') }}</div>
        </div>
      </div>
    </div>
  `,
});

export default Dashboard;
