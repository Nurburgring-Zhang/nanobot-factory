// components/EmptyState.js — 三态: empty
// props: { icon: String, title: String, description: String, action: String }
// emits: 'action'
// 用法: <empty-state icon="📭" title="暂无数据" description="还没有项目" action="新建项目" @action="onNew"></empty-state>

const { defineComponent, computed } = Vue;

export const EmptyState = defineComponent({
  name: 'EmptyState',
  props: {
    icon: { type: String, default: '📭' },
    title: { type: String, default: '暂无数据' },
    description: { type: String, default: '' },
    action: { type: String, default: '' },
  },
  emits: ['action'],
  setup(props, { emit }) {
    const hasAction = computed(() => !!props.action);
    function onClick() {
      emit('action');
    }
    return { hasAction, onClick };
  },
  template: `
    <div class="ls-empty" role="status">
      <div class="ls-empty-icon">{{ icon }}</div>
      <div class="ls-empty-title">{{ title }}</div>
      <div v-if="description" class="ls-empty-desc">{{ description }}</div>
      <el-button v-if="hasAction" type="primary" class="ls-empty-action" @click="onClick">{{ action }}</el-button>
    </div>
  `,
});

export default EmptyState;