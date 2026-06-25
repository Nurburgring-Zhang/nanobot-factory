// components/LoadingSpinner.js — 三态: loading
// props: { text: String, size: String (small|default|large) }
// 用法: <loading-spinner text="加载中..." size="default"></loading-spinner>

const { defineComponent, computed } = Vue;

const sizeMap = {
  small: 18,
  default: 28,
  large: 40,
};

export const LoadingSpinner = defineComponent({
  name: 'LoadingSpinner',
  props: {
    text: { type: String, default: '加载中...' },
    size: { type: String, default: 'default' },
  },
  setup(props) {
    const px = computed(() => sizeMap[props.size] || sizeMap.default);
    return { px };
  },
  template: `
    <div class="ls-loading" role="status" aria-live="polite">
      <div class="ls-spinner" :style="{ width: px + 'px', height: px + 'px', borderWidth: Math.max(2, Math.floor(px / 14)) + 'px' }"></div>
      <div class="ls-text">{{ text }}</div>
    </div>
  `,
});

export default LoadingSpinner;