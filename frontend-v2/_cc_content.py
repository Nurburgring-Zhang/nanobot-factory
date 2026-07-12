"""CommandCenter.vue content. Plain triple-quoted strings only."""
CC_TEMPLATE = """<!--
  V5 Chapter 1.3 - Conversation Command Center
  Chat-style panel: user types natural language, system parses intent
  (locally for now), emits a structured execution plan, and animates
  per-task progress via the Pinia command store.
-->
<template>
  <div class="command-center" data-testid="command-center">
    <header class="cc-header">
      <span class="cc-title">Conversation Command Center</span>
      <button type="button" class="cc-clear-btn" data-testid="clear-btn" :disabled="!store.hasMessages" @click="store.clear">Clear</button>
    </header>
    <div ref="messageListRef" class="cc-messages" data-testid="message-list">
      <div v-if="!store.hasMessages" class="cc-empty" data-testid="empty-chat">Describe what you want done. e.g. "annotate 100 images, then score them"</div>
      <div v-for="msg in store.messages" :key="msg.id" class="cc-msg" :class="'role-' + msg.role" :data-testid="'msg-' + msg.role">
        <div class="cc-msg-meta"><span class="cc-msg-role">{{ msg.role }}</span><span class="cc-msg-time">{{ formatTime(msg.timestamp) }}</span></div>
        <div class="cc-msg-content">{{ msg.content }}</div>
        <div v-if="msg.plan" class="cc-plan" data-testid="plan-card">
          <div class="cc-plan-summary">{{ msg.plan.summary }}</div>
          <ul class="cc-plan-tasks">
            <li v-for="task in msg.plan.tasks" :key="task.id" class="cc-plan-task" :data-task-id="task.id" :data-task-status="task.status">
              <div class="cc-plan-task-label">{{ task.label }} <span class="cc-plan-task-agent">({{ task.agent }})</span></div>
              <div class="cc-plan-task-bar"><div class="cc-plan-task-fill" :class="'status-' + task.status" :style="{ width: (task.progress * 100) + '%' }"></div></div>
              <div class="cc-plan-task-status">{{ task.status }}</div>
            </li>
          </ul>
        </div>
      </div>
    </div>
    <form class="cc-input-row" @submit.prevent="onSubmit">
      <input v-model="draft" type="text" class="cc-input" data-testid="cc-input" placeholder="Describe what you want done..." />
      <button type="submit" class="cc-submit" data-testid="cc-submit" :disabled="!draft.trim()">Send</button>
    </form>
  </div>
</template>
"""

CC_SCRIPT = """<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useCommandStore } from '@/stores/command'

const store = useCommandStore()
const draft = ref<string>('')
const messageListRef = ref<HTMLDivElement | null>(null)

watch(() => store.messages.length, async () => {
  await nextTick()
  const el = messageListRef.value
  if (el) el.scrollTop = el.scrollHeight
})

function formatTime(ts: number): string {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds())
}

function onSubmit(): void {
  const text = draft.value.trim()
  if (!text) return
  store.submitRequest(text)
  draft.value = ''
}

defineExpose({
  store,
  submit: (text: string) => store.submitRequest(text),
  messages: () => store.messages,
  hasMessages: () => store.hasMessages,
  isExecuting: () => store.isExecuting
})
</script>
"""

CC_STYLE = """<style scoped>
.command-center { display: flex; flex-direction: column; height: 100%; min-height: 480px; background: var(--app-surface, #fff); border: 1px solid var(--app-border, #e0e0e6); border-radius: 6px; overflow: hidden; }
.cc-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; border-bottom: 1px solid var(--app-border, #e0e0e6); background: var(--app-surface, #fafafa); }
.cc-title { font-weight: 600; font-size: 14px; color: var(--app-fg, #333); }
.cc-clear-btn { padding: 2px 8px; font-size: 12px; border: 1px solid var(--app-border, #ccc); background: var(--app-surface, #fff); border-radius: 4px; cursor: pointer; }
.cc-clear-btn:disabled { cursor: not-allowed; opacity: 0.5; }
.cc-messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.cc-empty { margin: auto; color: var(--app-muted, #888); font-size: 13px; text-align: center; }
.cc-msg { border: 1px solid var(--app-border, #e0e0e6); border-radius: 4px; padding: 6px 10px; background: var(--app-surface, #fcfcfc); }
.cc-msg-meta { display: flex; gap: 8px; font-size: 11px; color: var(--app-muted, #888); margin-bottom: 4px; }
.cc-msg-role { font-weight: 600; text-transform: uppercase; }
.cc-msg-content { font-size: 13px; color: var(--app-fg, #333); white-space: pre-wrap; word-break: break-word; }
.role-user { border-left: 3px solid var(--app-primary, #0a5dc2); }
.role-agent { border-left: 3px solid var(--app-success, #157a3e); background: #f0fff6; }
.role-system { border-left: 3px solid var(--app-muted, #888); background: #f5f5f7; font-style: italic; }
.role-plan { border-left: 3px solid var(--app-warning, #c87f0d); background: #fff7e6; }
.cc-plan { margin-top: 6px; padding-top: 6px; border-top: 1px dashed var(--app-border, #ccc); }
.cc-plan-summary { font-size: 12px; font-weight: 600; margin-bottom: 6px; color: var(--app-fg, #555); }
.cc-plan-tasks { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 4px; }
.cc-plan-task { display: grid; grid-template-columns: 1fr auto; grid-template-rows: auto auto; gap: 2px 8px; font-size: 11px; align-items: center; }
.cc-plan-task-label { grid-column: 1 / 2; grid-row: 1 / 2; color: var(--app-fg, #333); }
.cc-plan-task-agent { color: var(--app-muted, #888); margin-left: 4px; }
.cc-plan-task-bar { grid-column: 1 / 2; grid-row: 2 / 3; height: 4px; background: var(--app-border, #e0e0e6); border-radius: 2px; overflow: hidden; }
.cc-plan-task-fill { height: 100%; transition: width 0.2s ease; background: var(--app-muted, #aaa); }
.cc-plan-task-fill.status-running { background: var(--app-primary, #0a5dc2); }
.cc-plan-task-fill.status-done { background: var(--app-success, #157a3e); }
.cc-plan-task-fill.status-error { background: var(--app-error, #d03050); }
.cc-plan-task-status { grid-column: 2 / 3; grid-row: 1 / 3; font-size: 10px; color: var(--app-muted, #888); text-transform: uppercase; }
.cc-input-row { display: flex; gap: 6px; padding: 8px; border-top: 1px solid var(--app-border, #e0e0e6); background: var(--app-surface, #fafafa); }
.cc-input { flex: 1; padding: 6px 10px; border: 1px solid var(--app-border, #ccc); border-radius: 4px; font-size: 13px; background: var(--app-surface, #fff); color: var(--app-fg, #333); }
.cc-input:focus { outline: none; border-color: var(--app-primary, #0a5dc2); }
.cc-submit { padding: 6px 14px; background: var(--app-primary, #0a5dc2); color: #fff; border: 0; border-radius: 4px; font-size: 13px; cursor: pointer; }
.cc-submit:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
"""

COMMAND_CENTER_VUE = CC_TEMPLATE + CC_SCRIPT + CC_STYLE