// components/AsyncBoundary.js — 三态: 自动切换 loading/error/data/empty
// 接收 asyncFn prop, 自动切换 loading/error/data/empty 四态
// slots: 'default' (data 态时显示, 接收 scoped { data })
// props: {
//   asyncFn: Function — 返回 Promise, 接受 (params) 入参
//   params: Any — 传给 asyncFn 的参数 (reactive)
//   empty: Boolean | Function(data) => Boolean — 判定 data 是否为空 (默认数组 length === 0)
// }

const { defineComponent, ref, watch, onMounted, computed, h } = Vue;
import { LoadingSpinner } from './LoadingSpinner.js';
import { EmptyState } from './EmptyState.js';
import { ErrorBanner } from './ErrorBanner.js';
import { userMessage } from '../utils/error.js';

export const AsyncBoundary = defineComponent({
  name: 'AsyncBoundary',
  props: {
    asyncFn: { type: Function, required: true },
    params: { type: null, default: undefined },
    empty: { type: [Boolean, Function], default: null },
  },
  setup(props, { slots }) {
    const state = ref('loading'); // 'loading' | 'error' | 'success' | 'empty'
    const data = ref(null);
    const error = ref(null);

    function isEmpty(d) {
      if (typeof props.empty === 'function') return props.empty(d);
      if (typeof props.empty === 'boolean') return props.empty;
      if (d == null) return true;
      if (Array.isArray(d)) return d.length === 0;
      if (typeof d === 'object' && 'items' in d && Array.isArray(d.items)) return d.items.length === 0;
      return false;
    }

    async function run() {
      state.value = 'loading';
      error.value = null;
      try {
        const r = await props.asyncFn(props.params);
        data.value = r;
        state.value = isEmpty(r) ? 'empty' : 'success';
      } catch (e) {
        error.value = e;
        state.value = 'error';
      }
    }

    function retry() {
      run();
    }

    onMounted(run);
    watch(() => props.params, run, { deep: true });

    return () => {
      if (state.value === 'loading') return h(LoadingSpinner, { text: '加载中...' });
      if (state.value === 'error') return h(ErrorBanner, { error: error.value, onRetry: retry });
      if (state.value === 'empty') return h(EmptyState, { icon: '📭', title: '暂无数据', description: '当前列表为空' });
      // success
      if (slots.default) return slots.default({ data: data.value, retry });
      return null;
    };
  },
});

export default AsyncBoundary;