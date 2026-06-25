// views/Forbidden.js — 403 无权限页
// R6.5-W2: 由 RBAC 路由守卫跳转到此页 (当角色无权访问目标路径时)

const { defineComponent } = Vue;

export const Forbidden = defineComponent({
  name: 'Forbidden',
  setup() {
    function goHome() {
      if (window.VueRouter) {
        const router = window.app && window.app.config && window.app.config.globalProperties && window.app.config.globalProperties.$router;
        if (router) router.push('/dashboard');
        else window.location.hash = '#/dashboard';
      } else {
        window.location.hash = '#/dashboard';
      }
    }
    return { goHome };
  },
  template: `
    <div class="page-403" style="display:flex;align-items:center;justify-content:center;height:60vh;">
      <div style="text-align:center;max-width:480px;">
        <h1 style="font-size:96px;margin:0;color:#b3261e;">{{ $t('403.title') }}</h1>
        <p style="font-size:16px;color:#5b6066;margin:16px 0;">{{ $t('403.message') }}</p>
        <el-button type="primary" @click="goHome" v-label="'403.back'">{{ $t('403.back') }}</el-button>
      </div>
    </div>
  `,
});

export default Forbidden;
