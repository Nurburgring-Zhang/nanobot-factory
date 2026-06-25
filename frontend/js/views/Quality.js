// views/Quality.js — 质量中心 (核心页 5)
import { http } from '../api/client.js';

const { defineComponent, ref, reactive, onMounted } = Vue;

export const Quality = defineComponent({
  name: 'Quality',
  setup() {
    const stats = reactive({ totalEvals: 0, badCases: 0, passRate: 0 });
    const badCases = ref([]);
    const error = ref(null);
    const loading = ref(false);

    async function load() {
      loading.value = true;
      error.value = null;
      try {
        const r = await http.get('/eval/bad-cases');
        badCases.value = Array.isArray(r) ? r : [];
        stats.badCases = badCases.value.length;
      } catch (e) {
        error.value = e;
      } finally {
        loading.value = false;
      }
    }

    function severityTagType(s) {
      if (s === 'high' || s === 'p0') return 'danger';
      if (s === 'medium' || s === 'p1') return 'warning';
      return 'info';
    }

    onMounted(load);

    return { stats, badCases, error, loading, load, severityTagType };
  },
  template: `
    <div class="page-quality">
      <div class="stats-grid">
        <div class="stat-card"><div class="num">{{ stats.totalEvals }}</div><div class="label">评测总数</div></div>
        <div class="stat-card"><div class="num">{{ stats.badCases }}</div><div class="label">Bad Case</div></div>
        <div class="stat-card"><div class="num">{{ stats.passRate }}%</div><div class="label">通过率</div></div>
      </div>

      <div class="card">
        <div class="card-title">⚠️ Bad Case 列表</div>

        <error-banner v-if="error" :error="error" :on-retry="load"></error-banner>
        <loading-spinner v-else-if="loading" text="加载 Bad Case 中..." size="default"></loading-spinner>
        <el-table v-else-if="badCases.length" :data="badCases" size="small" style="width:100%">
          <el-table-column prop="type" label="类型" width="120">
            <template #default="{ row }"><el-tag size="small">{{ row.type }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="severity" label="严重度" width="100">
            <template #default="{ row }">
              <el-tag :type="severityTagType(row.severity)" size="small">{{ row.severity }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="120"/>
          <el-table-column prop="created_at" label="时间" width="180"/>
          <el-table-column label="操作" width="160">
            <template #default>
              <el-button type="primary" link size="small">查看详情</el-button>
              <el-button type="success" link size="small">分配修正</el-button>
            </template>
          </el-table-column>
        </el-table>
        <empty-state v-else icon="✨" title="暂无 Bad Case" description="目前还没有质量问题"></empty-state>
      </div>
    </div>
  `,
});

export default Quality;