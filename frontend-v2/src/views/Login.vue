<template>
  <div class="login-page">
    <NCard class="login-card" :bordered="false">
      <div class="login-header">
        <h1 class="brand">智影</h1>
        <p class="brand-en">nanobot-factory</p>
      </div>
      <NForm
        ref="formRef"
        :model="form"
        :rules="rules"
        label-placement="left"
        label-width="auto"
        require-mark-placement="right-hanging"
        size="large"
        @submit.prevent="onSubmit"
      >
        <NFormItem path="username" label="账号">
          <NInput v-model:value="form.username" placeholder="username" clearable autofocus />
        </NFormItem>
        <NFormItem path="password" label="密码">
          <NInput
            v-model:value="form.password"
            type="password"
            show-password-on="click"
            placeholder="password"
            @keydown.enter="onSubmit"
          />
        </NFormItem>
        <div v-if="auth.lastError" class="login-error">
          {{ auth.lastError }}
        </div>
        <NButton
          type="primary"
          block
          size="large"
          :loading="auth.loading"
          attr-type="submit"
          @click="onSubmit"
        >
          登录
        </NButton>
      </NForm>
      <div class="login-footer">
        <span class="hint">默认账号可在后端 docs/ 中查阅</span>
      </div>
    </NCard>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  NCard,
  NForm,
  NFormItem,
  NInput,
  NButton,
  type FormInst,
  type FormRules
} from 'naive-ui'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const formRef = ref<FormInst | null>(null)

const form = reactive({
  username: '',
  password: ''
})

const rules: FormRules = {
  username: { required: true, message: '请输入账号', trigger: ['blur', 'input'] },
  password: { required: true, message: '请输入密码', trigger: ['blur', 'input'] }
}

async function onSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  const user = await auth.login({ username: form.username, password: form.password })
  if (user) {
    const redirect = (route.query.redirect as string) || '/'
    router.replace(redirect)
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1e3c72 0%, #2a5298 50%, #2080f0 100%);
}
.login-card {
  width: 380px;
  padding: 32px 28px 24px 28px;
  border-radius: 12px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.18);
}
.login-header {
  text-align: center;
  margin-bottom: 24px;
}
.brand {
  font-size: 36px;
  font-weight: 700;
  letter-spacing: 8px;
  color: #2080f0;
  margin: 0 0 4px 0;
}
.brand-en {
  font-size: 12px;
  color: #888;
  letter-spacing: 2px;
  margin: 0;
}
.login-error {
  color: #d03050;
  font-size: 13px;
  margin-bottom: 12px;
}
.login-footer {
  margin-top: 16px;
  text-align: center;
}
.hint {
  font-size: 11px;
  color: #aaa;
}
</style>