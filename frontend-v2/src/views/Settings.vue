<template>
  <div class="settings-view">
    <NCard :bordered="false" class="header-card">
      <NSpace align="center" justify="space-between" :wrap-item="false">
        <div>
          <NText strong style="font-size: 20px">系统设置</NText>
          <NText depth="3" style="margin-left: 8px">
            偏好 · JWT · API · 系统信息
          </NText>
        </div>
        <NSpace>
          <NTag :type="themeTagType" :bordered="false" size="large">
            {{ prefs.theme }} 主题
          </NTag>
          <ActionButton type="primary" :loading="saving" @click="onSave">
            <template #icon><NIcon><SaveOutline /></NIcon></template>
            保存
          </ActionButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NAlert v-if="error" type="error" :show-icon="true" closable style="margin-bottom: 12px" @close="error = null">
      {{ error }}
    </NAlert>
    <NAlert v-if="savedHint" type="success" :show-icon="true" closable style="margin-bottom: 12px" @close="savedHint = ''">
      {{ savedHint }}
    </NAlert>

    <NTabs v-model:value="activeTab" type="line" animated>
      <!-- ── User preferences ── -->
      <NTabPane name="prefs" tab="用户偏好">
        <NCard :bordered="false">
          <NForm label-placement="top" :model="prefs">
            <NGrid :cols="2" :x-gap="12" :y-gap="12">
              <NGi>
                <NFormItem label="主题">
                  <NRadioGroup v-model:value="prefs.theme">
                    <NSpace>
                      <NRadio value="light">浅色</NRadio>
                      <NRadio value="dark">深色</NRadio>
                      <NRadio value="auto">跟随系统</NRadio>
                    </NSpace>
                  </NRadioGroup>
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem label="语言">
                  <NSelect
                    v-model:value="prefs.locale"
                    :options="[
                      { label: '简体中文', value: 'zh-CN' },
                      { label: 'English', value: 'en-US' },
                    ]"
                  />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem label="主色">
                  <NColorPicker v-model:value="prefs.primaryColor" :show-alpha="false" />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem label="默认每页条数">
                  <NInputNumber v-model:value="prefs.pageSize" :min="10" :max="100" :step="10" />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem label="自动刷新间隔 (秒)">
                  <NInputNumber v-model:value="prefs.refreshSeconds" :min="5" :max="600" :step="5" />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem label="默认登陆页">
                  <NInput v-model:value="prefs.defaultLanding" placeholder="例如 / 或 /datasets" />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem label="显示 Tooltips">
                  <NSwitch v-model:value="prefs.showTooltips" />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem label="紧凑表格">
                  <NSwitch v-model:value="prefs.compactTables" />
                </NFormItem>
              </NGi>
            </NGrid>
          </NForm>
        </NCard>
      </NTabPane>

      <!-- ── JWT inspection ── -->
      <NTabPane name="jwt" tab="JWT 切换">
        <div class="jwt-grid">
          <NCard title="当前 Token" :bordered="false">
            <NSpin :show="loadingToken">
              <NEmpty v-if="!tokenInfo" description="尚未登录或 Token 不可用" />
              <div v-else>
                <NDescriptions :column="1" bordered size="small">
                  <NDescriptionsItem label="过期时间">
                    <NTag :type="tokenInfo.isExpired ? 'error' : 'success'" size="small">
                      {{ tokenInfo.expiresAt || '—' }}
                    </NTag>
                  </NDescriptionsItem>
                  <NDescriptionsItem label="状态">
                    <NTag :type="tokenInfo.isExpired ? 'error' : 'success'" size="small">
                      {{ tokenInfo.isExpired ? '已过期' : '有效' }}
                    </NTag>
                  </NDescriptionsItem>
                  <NDescriptionsItem label="Header">{{ tokenInfo.header }}</NDescriptionsItem>
                  <NDescriptionsItem label="Payload">{{ tokenInfo.payload }}</NDescriptionsItem>
                </NDescriptions>
                <NSpace style="margin-top: 8px">
                  <NButton size="small" @click="onCopyToken">复制 Token</NButton>
                  <NButton size="small" type="warning" @click="onRefreshToken">手动刷新</NButton>
                  <NButton size="small" type="error" @click="onLogout">登出</NButton>
                </NSpace>
              </div>
            </NSpin>
          </NCard>

          <NCard title="JWT 配置" :bordered="false">
            <NForm label-placement="top" :model="jwt">
              <NGrid :cols="2" :x-gap="12" :y-gap="12">
                <NGi>
                  <NFormItem label="Access TTL (分钟)">
                    <NInputNumber v-model:value="jwt.accessTtlMinutes" :min="5" :max="1440" />
                  </NFormItem>
                </NGi>
                <NGi>
                  <NFormItem label="Refresh TTL (天)">
                    <NInputNumber v-model:value="jwt.refreshTtlDays" :min="1" :max="90" />
                  </NFormItem>
                </NGi>
                <NGi>
                  <NFormItem label="算法">
                    <NSelect
                      v-model:value="jwt.algorithm"
                      :options="[
                        { label: 'HS256', value: 'HS256' },
                        { label: 'HS384', value: 'HS384' },
                        { label: 'HS512', value: 'HS512' },
                      ]"
                    />
                  </NFormItem>
                </NGi>
                <NGi>
                  <NFormItem label="自动刷新缓冲 (秒)">
                    <NInputNumber v-model:value="jwt.autoRefreshBuffer" :min="0" :max="600" />
                  </NFormItem>
                </NGi>
                <NGi :span="2">
                  <NFormItem label="启用轮转">
                    <NSwitch v-model:value="jwt.rotateEnabled" />
                  </NFormItem>
                </NGi>
              </NGrid>
            </NForm>
          </NCard>
        </div>
      </NTabPane>

      <!-- ── API endpoint ── -->
      <NTabPane name="api" tab="API 端点">
        <NCard :bordered="false">
          <NForm label-placement="top" :model="api">
            <NGrid :cols="2" :x-gap="12" :y-gap="12">
              <NGi :span="2">
                <NFormItem label="API Base URL">
                  <NInput v-model:value="api.apiBase" placeholder="例如 /api 或 https://api.example.com" />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem label="Gateway Base URL">
                  <NInput v-model:value="api.gatewayBase" placeholder="完整 URL，含协议" />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem label="请求超时 (毫秒)">
                  <NInputNumber v-model:value="api.timeoutMs" :min="1000" :max="120000" :step="1000" />
                </NFormItem>
              </NGi>
            </NGrid>
            <NSpace>
              <NButton type="primary" @click="onTestApi">测试连接</NButton>
              <NButton @click="onResetApi">重置默认</NButton>
            </NSpace>
            <div v-if="apiTestResult" class="api-test">
              <NAlert :type="apiTestResult.ok ? 'success' : 'error'" :show-icon="true">
                {{ apiTestResult.message }}
              </NAlert>
            </div>
          </NForm>
        </NCard>
      </NTabPane>

      <!-- ── System info ── -->
      <NTabPane name="system" tab="系统信息">
        <NCard :bordered="false">
          <NSpin :show="sysLoading">
            <NDescriptions :column="2" bordered size="small">
              <NDescriptionsItem label="版本">{{ systemInfo?.version || '—' }}</NDescriptionsItem>
              <NDescriptionsItem label="构建">{{ systemInfo?.build || '—' }}</NDescriptionsItem>
              <NDescriptionsItem label="环境">{{ systemInfo?.env || '—' }}</NDescriptionsItem>
              <NDescriptionsItem label="启动时间">{{ systemInfo?.startedAt || '—' }}</NDescriptionsItem>
              <NDescriptionsItem label="前端 Vite">{{ viteVersion }}</NDescriptionsItem>
              <NDescriptionsItem label="User Agent">{{ ua }}</NDescriptionsItem>
            </NDescriptions>
          </NSpin>
        </NCard>
      </NTabPane>
    </NTabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NCard, NSpace, NText, NTag, NIcon, NTabs, NTabPane, NForm, NFormItem, NGrid, NGi, NInput, NInputNumber,
  NSwitch, NSelect, NRadioGroup, NRadio, NColorPicker, NDescriptions, NDescriptionsItem, NSpin, NEmpty,
  NAlert, NButton, useMessage,
} from 'naive-ui'
import { SaveOutline } from '@vicons/ionicons5'
import ActionButton from '@/components/ActionButton.vue'
import {
  loadPreferences, savePreferences, loadJwtConfig, saveJwtConfig, inspectToken,
  fetchSystemInfo, type UserPreferences, type JwtConfig, type SystemInfo,
} from '@/api/settings'
import { http } from '@/api/http'

const router = useRouter()
const message = useMessage()

const activeTab = ref('prefs')

const prefs = reactive<UserPreferences>(loadPreferences())
const jwt = reactive<JwtConfig>(loadJwtConfig())
const api = reactive({ apiBase: '/api', gatewayBase: '', timeoutMs: 30_000 })

const saving = ref(false)
const savedHint = ref('')
const error = ref<string | null>(null)

const loadingToken = ref(false)
const tokenInfo = ref<{ raw: string; header: any; payload: any; expiresAt?: string; isExpired: boolean } | null>(null)

const sysLoading = ref(false)
const systemInfo = ref<SystemInfo | null>(null)

const ua = typeof navigator !== 'undefined' ? navigator.userAgent : '—'
const viteVersion = ((import.meta as any).env?.VITE_VERSION as string) || 'dev'
const themeTagType = computed<'info' | 'warning' | 'success'>(() => {
  if (prefs.theme === 'dark') return 'warning'
  if (prefs.theme === 'auto') return 'info'
  return 'success'
})

async function onSave() {
  saving.value = true
  try {
    savePreferences({ ...prefs })
    saveJwtConfig({ ...jwt })
    localStorage.setItem('imdf.api.config', JSON.stringify(api))
    savedHint.value = '偏好已保存 — 部分改动将在下次刷新后生效'
    message.success('已保存')
  } catch (e) {
    error.value = (e as Error).message || '保存失败'
  } finally {
    saving.value = false
    setTimeout(() => { savedHint.value = '' }, 3500)
  }
}

function loadToken() {
  loadingToken.value = true
  try {
    tokenInfo.value = inspectToken()
  } catch (e) {
    tokenInfo.value = null
  } finally { loadingToken.value = false }
}

function onCopyToken() {
  if (!tokenInfo.value) return
  navigator.clipboard.writeText(tokenInfo.value.raw)
    .then(() => message.success('Token 已复制'))
    .catch(() => message.warning('复制失败 — 请手动复制'))
}

async function onRefreshToken() {
  try {
    const refresh = localStorage.getItem('imdf.auth.refresh_token')
    if (!refresh) { message.warning('无 refresh token'); return }
    const res = await http.post<{ access_token: string }>('/api/auth/refresh', { refresh_token: refresh })
    if (res.data?.access_token) {
      localStorage.setItem('imdf.auth.access_token', res.data.access_token)
      message.success('已刷新')
      loadToken()
    }
  } catch (e) {
    message.error((e as Error).message || '刷新失败')
  }
}

function onLogout() {
  localStorage.removeItem('imdf.auth.access_token')
  localStorage.removeItem('imdf.auth.refresh_token')
  localStorage.removeItem('imdf.auth.user')
  message.success('已登出')
  router.push('/login')
}

const apiTestResult = ref<{ ok: boolean; message: string } | null>(null)

async function onTestApi() {
  try {
    const base = api.gatewayBase || api.apiBase || ''
    const url = base.startsWith('http') ? `${base.replace(/\/$/, '')}/` : '/'
    const res = await http.get(url, { timeout: api.timeoutMs })
    apiTestResult.value = { ok: true, message: `连接成功 (${res.status})` }
    message.success(`连接成功 (${res.status})`)
  } catch (e) {
    apiTestResult.value = { ok: false, message: `连接失败: ${(e as Error).message}` }
    message.warning(`连接失败: ${(e as Error).message}`)
  }
}

function onResetApi() {
  api.apiBase = '/api'
  api.gatewayBase = ''
  api.timeoutMs = 30_000
  message.info('已重置为默认')
}

async function loadSystemInfo() {
  sysLoading.value = true
  try {
    systemInfo.value = await fetchSystemInfo()
  } catch {
    systemInfo.value = {
      version: '0.0.0', build: 'dev', env: import.meta.env.MODE,
      startedAt: new Date().toISOString(), services: [],
    }
  } finally { sysLoading.value = false }
}

onMounted(() => {
  loadToken()
  loadSystemInfo()
  try {
    const raw = localStorage.getItem('imdf.api.config')
    if (raw) Object.assign(api, JSON.parse(raw))
  } catch { /* ignore */ }
})
</script>

<style scoped>
.settings-view { padding: 16px; }
.header-card { margin-bottom: 12px; }
.jwt-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.api-test { margin-top: 12px; }
</style>