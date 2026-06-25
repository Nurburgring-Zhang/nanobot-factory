// components/ErrorBanner.js — 三态: error + 重试
// props: { error: Object|String, onRetry: Function }
// 用法: <error-banner :error="err" :on-retry="reload"></error-banner>

const { defineComponent, computed } = Vue;
import { userMessage } from '../utils/error.js';

export const ErrorBanner = defineComponent({
  name: 'ErrorBanner',
  props: {
    error: { type: [Object, String, Error], default: null },
    onRetry: { type: Function, default: null },
  },
  setup(props) {
    const message = computed(() => {
      if (!props.error) return '';
      return userMessage(props.error);
    });
    const retryable = computed(() => {
      if (!props.error) return false;
      if (props.error && typeof props.error === 'object' && 'retryable' in props.error) {
        return !!props.error.retryable;
      }
      return true;
    });
    const hasRetry = computed(() => typeof props.onRetry === 'function' && retryable.value);

    function onRetryClick() {
      if (typeof props.onRetry === 'function') props.onRetry();
    }

    return { message, hasRetry, onRetryClick };
  },
  template: `
    <div class="ls-error" role="alert">
      <div class="ls-error-icon">⚠️</div>
      <div class="ls-error-body">
        <div class="ls-error-title">出错了</div>
        <div class="ls-error-msg">{{ message }}</div>
      </div>
      <el-button v-if="hasRetry" type="primary" plain size="small" @click="onRetryClick">重试</el-button>
    </div>
  `,
});

export default ErrorBanner;