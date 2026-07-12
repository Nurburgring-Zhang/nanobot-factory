/**
 * Pinia store: command (Conversation Command Center)
 *
 * Drives the right-side chat panel where users describe tasks in natural
 * language and the system parses intent, shows a structured execution
 * plan, and reports progress as each task runs.
 *
 * State machine:
 *   messages         — chronological chat (user / agent / system / plan)
 *   currentPlan      — the most-recently-emitted plan, if any
 *   executingTaskIds — task ids currently in 'running' state
 *
 * Actions:
 *   submitRequest(text)    — parse intent (mock API), append user msg,
 *                            call executePlan() to drive progress
 *   appendMessage(msg)     — push a chat message (any role)
 *   updatePlanProgress     — bump a task step's progress
 *   markTaskRunning/Done   — bookkeeping for the executing set
 *   clear()                — wipe messages + plan + executing set
 *
 * Persistence:
 *   Only `messages` is persisted to localStorage (key 'vdp-command.messages.v1').
 *   Plans and executing-task state are intentionally NOT persisted — they
 *   are transient runtime artefacts that should not survive reloads.
 *
 * Why a dedicated store instead of a composable?
 *   The Command Center talks to the Agent service via Pinia getters, and
 *   the Canvas tab may subscribe to plan events later. Centralising the
 *   state here makes both single-source-of-truth and testable.
 */
import { defineStore } from 'pinia'

export type MessageRole = 'user' | 'agent' | 'system' | 'plan'

export interface ChatMessage {
  id: string
  role: MessageRole
  /** Plain text for user/agent/system; structured payload for 'plan'. */
  content: string
  /** Optional structured plan payload (only present when role === 'plan'). */
  plan?: ExecutionPlan
  /** Wall-clock ms timestamp. */
  timestamp: number
}

export interface ExecutionTask {
  id: string
  /** Human-readable step label, e.g. "加载数据集". */
  label: string
  /** Which agent / capability runs this step. */
  agent: string
  /** 0–1, drives the per-task progress bar. */
  progress: number
  status: 'pending' | 'running' | 'done' | 'error'
}

export interface ExecutionPlan {
  id: string
  /** Original user request. */
  request: string
  /** Top-level interpretation, e.g. "数据采集 → 标注 → 评分". */
  summary: string
  /** Ordered task list. */
  tasks: ExecutionTask[]
  /** Wall-clock ms when the plan was emitted. */
  createdAt: number
}

interface CommandState {
  messages: ChatMessage[]
  currentPlan: ExecutionPlan | null
  executingTaskIds: string[]
}

const STORAGE_KEY = 'vdp-command.messages.v1'

function makeId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

/** Pull persisted messages out of localStorage, falling back to []. */
function loadMessages(): ChatMessage[] {
  if (typeof localStorage === 'undefined') return []
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    // Best-effort shape check — drop anything that doesn't look right.
    return parsed.filter((m): m is ChatMessage =>
      !!m && typeof m === 'object' &&
      typeof (m as ChatMessage).id === 'string' &&
      typeof (m as ChatMessage).role === 'string' &&
      typeof (m as ChatMessage).content === 'string' &&
      typeof (m as ChatMessage).timestamp === 'number'
    )
  } catch {
    return []
  }
}

function persistMessages(messages: ChatMessage[]): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages))
  } catch {
    /* quota / private mode — silent fallback; in-memory still works */
  }
}

/** Local intent parser — turns a Chinese / English user request into a
 *  trivial execution plan. The real backend will do this via LLM; for
 *  the frontend demo we synthesise a plan based on keyword matching so
 *  tests and the demo flow are deterministic. */
function parseIntentLocally(text: string): { summary: string; tasks: ExecutionTask[] } {
  const lower = text.toLowerCase()
  const tasks: ExecutionTask[] = []
  let stepIdx = 1

  // Asset / 资产
  if (/(asset|资源|资产|素材|图片|视频)/.test(lower)) {
    tasks.push({ id: `t${stepIdx}`, label: '加载数据资产', agent: 'asset-loader', progress: 0, status: 'pending' })
    stepIdx++
  }
  // Capability / 能力
  if (/(capability|能力|模块|处理|transform|clean)/.test(lower)) {
    tasks.push({ id: `t${stepIdx}`, label: '激活能力模块', agent: 'capability-runner', progress: 0, status: 'pending' })
    stepIdx++
  }
  // Annotation / 标注
  if (/(annotat|标注|label)/.test(lower)) {
    tasks.push({ id: `t${stepIdx}`, label: '启动标注流水线', agent: 'annotation-agent', progress: 0, status: 'pending' })
    stepIdx++
  }
  // Scoring / 评分
  if (/(scor|评分|打分|rank)/.test(lower)) {
    tasks.push({ id: `t${stepIdx}`, label: '运行评分模型', agent: 'scoring-agent', progress: 0, status: 'pending' })
    stepIdx++
  }
  // Workflow / 工作流
  if (/(workflow|工作流|编排|orchestrat)/.test(lower)) {
    tasks.push({ id: `t${stepIdx}`, label: '执行编排工作流', agent: 'workflow-runner', progress: 0, status: 'pending' })
    stepIdx++
  }
  // Fallback — always emit at least one task so the UI shows something
  if (tasks.length === 0) {
    tasks.push({ id: 't1', label: '解析用户请求', agent: 'intent-parser', progress: 0, status: 'pending' })
    tasks.push({ id: 't2', label: '调用默认 Agent', agent: 'default-agent', progress: 0, status: 'pending' })
  } else {
    // Always append a finalisation step
    tasks.push({ id: `t${stepIdx}`, label: '汇总结果并返回', agent: 'aggregator', progress: 0, status: 'pending' })
  }

  const summary = tasks.map(t => t.label).join(' → ')
  return { summary, tasks }
}

export const useCommandStore = defineStore('command', {
  state: (): CommandState => ({
    messages: loadMessages(),
    currentPlan: null,
    executingTaskIds: []
  }),

  getters: {
    hasMessages: (state): boolean => state.messages.length > 0,
    lastMessage: (state): ChatMessage | null =>
      state.messages.length > 0 ? state.messages[state.messages.length - 1] : null,
    isExecuting: (state): boolean => state.executingTaskIds.length > 0
  },

  actions: {
    appendMessage(input: { role: MessageRole; content: string; plan?: ExecutionPlan }): ChatMessage {
      const msg: ChatMessage = {
        id: makeId('msg'),
        role: input.role,
        content: input.content,
        plan: input.plan,
        timestamp: Date.now()
      }
      this.messages.push(msg)
      persistMessages(this.messages)
      return msg
    },

    submitRequest(text: string): ChatMessage | null {
      const trimmed = (text || '').trim()
      if (!trimmed) return null
      // 1. Record the user's request
      this.appendMessage({ role: 'user', content: trimmed })

      // 2. Parse intent (locally — the real /api/v1/agent/parse_intent is
      //    not yet implemented; we keep the same surface so swapping in
      //    the real call later is a one-line change).
      const parsed = parseIntentLocally(trimmed)
      const plan: ExecutionPlan = {
        id: makeId('plan'),
        request: trimmed,
        summary: parsed.summary,
        tasks: parsed.tasks,
        createdAt: Date.now()
      }
      this.currentPlan = plan
      const planMsg = this.appendMessage({ role: 'plan', content: parsed.summary, plan })

      // 3. Kick off execution (asynchronously, non-blocking). Tests can
      //    call executePlan() directly to drive deterministically.
      void this.executePlan(plan.id)
      return planMsg
    },

    /** Drive a plan's tasks forward, animating progress. Each task
     *  transitions: pending → running → done, one at a time. */
    async executePlan(planId: string): Promise<void> {
      const plan = this.currentPlan
      if (!plan || plan.id !== planId) return
      for (const task of plan.tasks) {
        this.executingTaskIds.push(task.id)
        task.status = 'running'
        this.appendMessage({ role: 'agent', content: `▶ ${task.label} (${task.agent})` })
        // Animate progress 0 → 1 in 5 steps of 80ms each
        for (let p = 1; p <= 5; p++) {
          task.progress = p / 5
          await new Promise(r => setTimeout(r, 80))
        }
        task.status = 'done'
        task.progress = 1
        this.appendMessage({ role: 'agent', content: `✓ ${task.label}` })
        this.executingTaskIds = this.executingTaskIds.filter(id => id !== task.id)
      }
      this.appendMessage({ role: 'system', content: '任务完成 · All tasks completed' })
    },

    updatePlanProgress(taskId: string, progress: number): void {
      if (!this.currentPlan) return
      const task = this.currentPlan.tasks.find(t => t.id === taskId)
      if (!task) return
      task.progress = Math.min(1, Math.max(0, progress))
    },

    markTaskRunning(taskId: string): void {
      if (!this.currentPlan) return
      const task = this.currentPlan.tasks.find(t => t.id === taskId)
      if (!task) return
      task.status = 'running'
      if (!this.executingTaskIds.includes(taskId)) {
        this.executingTaskIds.push(taskId)
      }
    },

    markTaskDone(taskId: string): void {
      if (!this.currentPlan) return
      const task = this.currentPlan.tasks.find(t => t.id === taskId)
      if (!task) return
      task.status = 'done'
      task.progress = 1
      this.executingTaskIds = this.executingTaskIds.filter(id => id !== taskId)
    },

    clear(): void {
      this.messages = []
      this.currentPlan = null
      this.executingTaskIds = []
      persistMessages(this.messages)
    }
  }
})