"""智影 V5 — Proactive Engine (Vida 模式)

Proactive Agent 核心:
- 持续理解用户上下文
- 主动预判 + 主动建议
- 屏幕/活动感知
- 今日战报卡
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ActivityType(str, Enum):
    """活动类型"""
    CODING = "coding"               # 写代码
    WRITING = "writing"             # 写文档
    MEETING = "meeting"             # 会议
    BROWSING = "browsing"           # 浏览
    EDITING = "editing"             # 编辑
    DEBUGGING = "debugging"         # 调试
    TESTING = "testing"             # 测试
    REVIEWING = "reviewing"         # 审查
    PLANNING = "planning"           # 规划
    RESEARCH = "researching"         # 调研
    COMMUNICATING = "communicating"  # 沟通
    IDLE = "idle"                   # 空闲


class IntentPrediction(str, Enum):
    """预判意图"""
    NEEDS_HELP = "needs_help"            # 需要帮助
    NEEDS_INFO = "needs_info"            # 需要信息
    NEEDS_TOOL = "needs_tool"            # 需要工具
    NEEDS_BREAK = "needs_break"          # 需要休息
    NEEDS_REVIEW = "needs_review"        # 需要审查
    NEEDS_DEPLOY = "needs_deploy"        # 需要部署
    PROCEED = "proceed"                  # 继续
    PAUSE = "pause"                      # 暂停
    UNKNOWN = "unknown"


@dataclass
class ContextSnapshot:
    """当前上下文快照"""

    snapshot_id: str = field(default_factory=lambda: f"cs-{uuid.uuid4().hex[:8]}")
    user_id: str = ""
    activity: ActivityType = ActivityType.IDLE
    current_app: str = ""           # 当前应用
    current_file: str = ""          # 当前文件
    current_url: str = ""           # 当前 URL
    recent_files: List[str] = field(default_factory=list)  # 最近文件
    recent_actions: List[Dict[str, Any]] = field(default_factory=list)  # 最近操作
    focus_duration_sec: float = 0.0  # 专注时长
    intent_signal: str = ""         # 意图信号 (from current text/action)
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "user_id": self.user_id,
            "activity": self.activity.value,
            "current_app": self.current_app,
            "current_file": self.current_file,
            "current_url": self.current_url,
            "recent_files_count": len(self.recent_files),
            "recent_actions_count": len(self.recent_actions),
            "focus_duration_sec": self.focus_duration_sec,
            "intent_signal": self.intent_signal,
            "timestamp": self.timestamp,
        }


@dataclass
class ProactiveAction:
    """主动行动建议"""

    action_id: str = field(default_factory=lambda: f"pa-{uuid.uuid4().hex[:8]}")
    title: str = ""
    description: str = ""
    intent: IntentPrediction = IntentPrediction.UNKNOWN
    trigger_snapshot_id: str = ""
    suggested_command: str = ""  # 用户可一键执行的命令
    suggested_skill: str = ""   # 推荐 skill
    urgency: str = "low"          # low/medium/high
    estimated_impact: str = ""   # 估计影响
    auto_executable: bool = False  # 是否可自动执行
    created_at: float = 0.0
    accepted: Optional[bool] = None  # None = 未决策, True/False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "title": self.title,
            "description": self.description,
            "intent": self.intent.value,
            "suggested_command": self.suggested_command,
            "suggested_skill": self.suggested_skill,
            "urgency": self.urgency,
            "estimated_impact": self.estimated_impact,
            "auto_executable": self.auto_executable,
            "accepted": self.accepted,
            "created_at": self.created_at,
        }


@dataclass
class DailyReport:
    """今日战报卡"""

    report_id: str = field(default_factory=lambda: f"dr-{uuid.uuid4().hex[:8]}")
    user_id: str = ""
    date: str = ""
    completed_items: List[str] = field(default_factory=list)
    key_outputs: List[str] = field(default_factory=list)
    time_distribution: Dict[str, float] = field(default_factory=dict)  # activity → minutes
    keywords: List[str] = field(default_factory=list)
    tomorrow_todo: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "user_id": self.user_id,
            "date": self.date,
            "completed_count": len(self.completed_items),
            "key_output_count": len(self.key_outputs),
            "time_distribution": self.time_distribution,
            "keywords": self.keywords[:10],
            "tomorrow_todo_count": len(self.tomorrow_todo),
            "metrics": self.metrics,
            "created_at": self.created_at,
        }


@dataclass
class ProactiveContext:
    """Proactive 上下文 — 长期记忆 + 当前状态"""

    user_id: str = ""
    snapshots: List[ContextSnapshot] = field(default_factory=list)
    actions: List[ProactiveAction] = field(default_factory=list)
    long_term_memory: Dict[str, Any] = field(default_factory=dict)
    preferences: Dict[str, Any] = field(default_factory=dict)
    work_patterns: Dict[str, Any] = field(default_factory=dict)
    last_report_date: str = ""
    last_report: Optional[DailyReport] = None

    def add_snapshot(self, snapshot: ContextSnapshot):
        self.snapshots.append(snapshot)
        # 限制 100
        if len(self.snapshots) > 100:
            self.snapshots = self.snapshots[-100:]

    def add_action(self, action: ProactiveAction):
        self.actions.append(action)
        if len(self.actions) > 200:
            self.actions = self.actions[-200:]

    def accept_action(self, action_id: str) -> bool:
        for a in self.actions:
            if a.action_id == action_id:
                a.accepted = True
                return True
        return False

    def reject_action(self, action_id: str) -> bool:
        for a in self.actions:
            if a.action_id == action_id:
                a.accepted = False
                return True
        return False

    def update_long_term(self, key: str, value: Any):
        self.long_term_memory[key] = value

    def get_long_term(self, key: str, default: Any = None) -> Any:
        return self.long_term_memory.get(key, default)

    def learn_work_pattern(self, pattern_key: str, pattern: Dict[str, Any]):
        self.work_patterns[pattern_key] = pattern

    def get_work_pattern(self, pattern_key: str) -> Optional[Dict[str, Any]]:
        return self.work_patterns.get(pattern_key)


class ProactiveEngine:
    """Proactive Agent 主引擎"""

    def __init__(self):
        self.contexts: Dict[str, ProactiveContext] = {}
        self.action_handlers: Dict[str, Callable] = {}
        self.metrics: Dict[str, int] = {"snapshots": 0, "actions": 0, "reports": 0}

    def get_or_create_context(self, user_id: str) -> ProactiveContext:
        if user_id not in self.contexts:
            self.contexts[user_id] = ProactiveContext(user_id=user_id)
        return self.contexts[user_id]

    async def observe(self, user_id: str, snapshot: ContextSnapshot) -> List[ProactiveAction]:
        """观察 — 接收新快照, 生成主动建议"""
        ctx = self.get_or_create_context(user_id)
        ctx.add_snapshot(snapshot)
        self.metrics["snapshots"] += 1
        # 推断意图 + 生成建议
        actions = await self._analyze_and_suggest(ctx, snapshot)
        for a in actions:
            ctx.add_action(a)
        self.metrics["actions"] += len(actions)
        return actions

    async def _analyze_and_suggest(
        self,
        ctx: ProactiveContext,
        snapshot: ContextSnapshot,
    ) -> List[ProactiveAction]:
        """分析 + 建议"""
        actions: List[ProactiveAction] = []
        # 1. 长时间编码 → 提醒休息
        if snapshot.activity == ActivityType.CODING and snapshot.focus_duration_sec > 7200:  # 2h
            actions.append(
                ProactiveAction(
                    title="你已经连续编码 2 小时, 该休息了",
                    description="持续高强度编码会降低效率, 建议 5-10 分钟休息",
                    intent=IntentPrediction.NEEDS_BREAK,
                    suggested_command="启动 5 分钟番茄钟",
                    urgency="medium",
                    estimated_impact="提升后续 30% 效率",
                    auto_executable=True,
                    created_at=time.time(),
                )
            )
        # 2. 调试中 → 建议生成测试
        if snapshot.activity == ActivityType.DEBUGGING and snapshot.focus_duration_sec > 1800:
            actions.append(
                ProactiveAction(
                    title="调试超过 30 分钟, 建议写测试用例",
                    description="相同 bug 可能复发, 写测试能防止回归",
                    intent=IntentPrediction.NEEDS_TOOL,
                    suggested_skill="obsidian-create-skill",
                    suggested_command="为这个 bug 写一个测试用例",
                    urgency="medium",
                    estimated_impact="防止 80% 回归",
                    created_at=time.time(),
                )
            )
        # 3. 文档撰写 → 建议自动归档
        if snapshot.activity == ActivityType.WRITING and snapshot.current_file.endswith(".md"):
            actions.append(
                ProactiveAction(
                    title="文档已撰写, 是否归档到长期记忆?",
                    description="把这份文档归档到 profile/style, Agent 越用越懂你",
                    intent=IntentPrediction.PROCEED,
                    suggested_skill="obsidian-apply-memory",
                    suggested_command="把这篇文档归档到长期记忆",
                    urgency="low",
                    estimated_impact="Agent 后续可参考",
                    created_at=time.time(),
                )
            )
        # 4. 会议结束 → 总结
        if snapshot.activity == ActivityType.MEETING and snapshot.metadata.get("just_ended"):
            actions.append(
                ProactiveAction(
                    title="会议刚结束, 总结要点?",
                    description="自动总结会议要点并归档到 inbox",
                    intent=IntentPrediction.PROCEED,
                    suggested_skill="obsidian-digest-note",
                    suggested_command="消化并归档这次会议纪要",
                    urgency="high",
                    estimated_impact="沉淀会议决策",
                    created_at=time.time(),
                )
            )
        # 5. 浏览中 → 安全检查
        if snapshot.activity == ActivityType.BROWSING:
            if "login" in snapshot.current_url.lower() or "auth" in snapshot.current_url.lower():
                actions.append(
                    ProactiveAction(
                        title="检测到登录页 — 安全检查",
                        description="确认网站是官方域名, 不要输入密码到钓鱼页",
                        intent=IntentPrediction.NEEDS_HELP,
                        urgency="high",
                        estimated_impact="防止账号泄露",
                        created_at=time.time(),
                    )
                )
        return actions

    def accept_action(self, user_id: str, action_id: str) -> bool:
        ctx = self.get_or_create_context(user_id)
        return ctx.accept_action(action_id)

    def reject_action(self, user_id: str, action_id: str) -> bool:
        ctx = self.get_or_create_context(user_id)
        return ctx.reject_action(action_id)

    async def generate_daily_report(self, user_id: str) -> DailyReport:
        """生成今日战报卡"""
        ctx = self.get_or_create_context(user_id)
        # 聚合今日 snapshots
        today = time.strftime("%Y-%m-%d", time.localtime())
        today_snapshots = [s for s in ctx.snapshots if time.strftime("%Y-%m-%d", time.localtime(s.timestamp)) == today]
        if not today_snapshots:
            today_snapshots = ctx.snapshots[-20:]  # fallback
        # 活动分布
        activities = Counter(s.activity.value for s in today_snapshots)
        time_dist = {act: float(activities[act]) * 10 for act in activities}  # 简化: 每快照 10 min
        # 关键词
        keywords: List[str] = []
        for s in today_snapshots:
            if s.intent_signal:
                keywords.extend(s.intent_signal.split()[:5])
        kw_counter = Counter(keywords)
        # 完成项 (从 actions 取已接受的)
        completed = [
            a.title for a in ctx.actions
            if a.accepted is True
            and time.strftime("%Y-%m-%d", time.localtime(a.created_at)) == today
        ]
        # 关键产出
        key_outputs = [s.current_file for s in today_snapshots if s.current_file][:10]
        # 明日 Todo (从 pending actions)
        tomorrow = [
            a.suggested_command for a in ctx.actions
            if a.accepted is None
            and time.strftime("%Y-%m-%d", time.localtime(a.created_at)) == today
        ][:5]
        report = DailyReport(
            user_id=user_id,
            date=today,
            completed_items=completed,
            key_outputs=key_outputs,
            time_distribution=time_dist,
            keywords=[k for k, _ in kw_counter.most_common(10)],
            tomorrow_todo=tomorrow,
            metrics={
                "snapshot_count": len(today_snapshots),
                "action_count": sum(1 for a in ctx.actions if time.strftime("%Y-%m-%d", time.localtime(a.created_at)) == today),
                "accept_rate": sum(1 for a in ctx.actions if a.accepted is True) / max(sum(1 for a in ctx.actions if a.accepted is not None), 1),
            },
            created_at=time.time(),
        )
        ctx.last_report = report
        ctx.last_report_date = today
        self.metrics["reports"] += 1
        return report

    def get_stats(self) -> Dict[str, Any]:
        return {
            "users": len(self.contexts),
            "total_snapshots": self.metrics["snapshots"],
            "total_actions": self.metrics["actions"],
            "total_reports": self.metrics["reports"],
        }


proactive_engine = ProactiveEngine()
