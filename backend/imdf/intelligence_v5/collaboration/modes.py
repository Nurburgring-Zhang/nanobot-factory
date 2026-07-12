"""智影 V5 — 6 种协作模式 (Solo / Roundtable / Critic / Pipeline / Split / Swarm)"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CollaborationMode(str, Enum):
    """6 种协作模式"""
    SOLO = "solo"                # 单 Bot 完成
    ROUNDTABLE = "roundtable"    # 圆桌讨论
    CRITIC = "critic"            # 独立审核
    PIPELINE = "pipeline"        # 流水线
    SPLIT = "split"              # 分头干
    SWARM = "swarm"              # 竞选择优


@dataclass
class CollaborationContext:
    """协作上下文"""
    task: str
    thread_id: str = ""
    matter_id: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    constraints: List[str] = field(default_factory=list)
    deadline: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CollaborationResult:
    """协作结果"""
    session_id: str
    mode: CollaborationMode
    success: bool
    output: Any = None
    final_bot_id: str = ""
    steps: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode.value,
            "success": self.success,
            "output": self.output if not isinstance(self.output, (bytes, bytearray)) else f"<{len(self.output)} bytes>",
            "final_bot_id": self.final_bot_id,
            "step_count": len(self.steps),
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class CollaborationSession:
    """协作会话基类"""
    session_id: str = field(default_factory=lambda: f"cs-{uuid.uuid4().hex[:12]}")
    mode: CollaborationMode = CollaborationMode.SOLO
    context: Optional[CollaborationContext] = None
    started_at: float = 0.0
    completed_at: float = 0.0
    steps: List[Dict[str, Any]] = field(default_factory=list)
    output: Any = None
    error: Optional[str] = None

    def add_step(self, bot_id: str, action: str, input: Any = None, output: Any = None, success: bool = True, error: str = ""):
        self.steps.append(
            {
                "step_id": f"st-{len(self.steps)}",
                "bot_id": bot_id,
                "action": action,
                "input": str(input)[:200] if input else None,
                "output": str(output)[:200] if output else None,
                "success": success,
                "error": error,
                "ts": time.time(),
            }
        )

    def to_result(self) -> CollaborationResult:
        duration = (self.completed_at - self.started_at) * 1000 if self.completed_at else 0
        return CollaborationResult(
            session_id=self.session_id,
            mode=self.mode,
            success=self.error is None,
            output=self.output,
            final_bot_id=self.steps[-1]["bot_id"] if self.steps else "",
            steps=self.steps,
            duration_ms=duration,
            error=self.error,
        )


# ===== Solo 模式 =====
@dataclass
class SoloSession(CollaborationSession):
    """单人完成 — 边界清楚、目标明确的小任务"""

    bot_id: str = ""

    def __init__(self, bot_id: str, **kwargs):
        super().__init__(mode=CollaborationMode.SOLO, **kwargs)
        self.bot_id = bot_id


# ===== Roundtable 模式 =====
@dataclass
class RoundtableSession(CollaborationSession):
    """圆桌讨论 — 多个 Bot 公开讨论, Leader 收束"""

    participant_ids: List[str] = field(default_factory=list)
    leader_id: str = ""
    rounds: int = 3
    discussion: List[Dict[str, Any]] = field(default_factory=list)

    def __init__(self, participant_ids: List[str], leader_id: str, rounds: int = 3, **kwargs):
        super().__init__(mode=CollaborationMode.ROUNDTABLE, **kwargs)
        self.participant_ids = participant_ids
        self.leader_id = leader_id
        self.rounds = rounds

    def add_opinion(self, bot_id: str, opinion: str, round_num: int):
        self.discussion.append(
            {
                "round": round_num,
                "bot_id": bot_id,
                "opinion": opinion,
                "ts": time.time(),
            }
        )


# ===== Critic 模式 =====
@dataclass
class CriticSession(CollaborationSession):
    """独立审核 — 一个做, 另一个审, 审核方可以打回重做"""

    maker_id: str = ""
    critic_id: str = ""
    max_iterations: int = 3
    iteration: int = 0
    feedback_history: List[Dict[str, Any]] = field(default_factory=list)

    def __init__(self, maker_id: str, critic_id: str, max_iterations: int = 3, **kwargs):
        super().__init__(mode=CollaborationMode.CRITIC, **kwargs)
        self.maker_id = maker_id
        self.critic_id = critic_id
        self.max_iterations = max_iterations

    def record_feedback(self, iteration: int, decision: str, feedback: str, score: float = 0.0):
        self.feedback_history.append(
            {
                "iteration": iteration,
                "critic_id": self.critic_id,
                "decision": decision,  # "accept" | "reject" | "revise"
                "feedback": feedback,
                "score": score,
                "ts": time.time(),
            }
        )


# ===== Pipeline 模式 =====
@dataclass
class PipelineSession(CollaborationSession):
    """流水线 — A → B → C, 每步产出是下一步输入"""

    stages: List[Dict[str, Any]] = field(default_factory=list)  # [{bot_id, action, output_key}]
    current_stage: int = 0
    stage_outputs: Dict[str, Any] = field(default_factory=dict)

    def __init__(self, stages: List[Dict[str, Any]], **kwargs):
        super().__init__(mode=CollaborationMode.PIPELINE, **kwargs)
        self.stages = stages

    def advance(self):
        self.current_stage += 1

    def is_complete(self) -> bool:
        return self.current_stage >= len(self.stages)


# ===== Split 模式 =====
@dataclass
class SplitSession(CollaborationSession):
    """分头干 — 大任务拆几块, 不同 Bot 并行, Leader 合并"""

    sub_tasks: List[Dict[str, Any]] = field(default_factory=list)  # [{bot_id, sub_task}]
    leader_id: str = ""
    sub_results: Dict[str, Any] = field(default_factory=dict)

    def __init__(self, sub_tasks: List[Dict[str, Any]], leader_id: str, **kwargs):
        super().__init__(mode=CollaborationMode.SPLIT, **kwargs)
        self.sub_tasks = sub_tasks
        self.leader_id = leader_id


# ===== Swarm 模式 =====
@dataclass
class SwarmSession(CollaborationSession):
    """竞选择优 — 同题目给多 Bot, 各自完成, 选最好的"""

    candidates: List[Dict[str, Any]] = field(default_factory=list)  # [{bot_id, output, score}]
    selection_criteria: str = ""
    judge_id: str = ""

    def __init__(self, candidates: List[Dict[str, Any]], judge_id: str, selection_criteria: str = "quality", **kwargs):
        super().__init__(mode=CollaborationMode.SWARM, **kwargs)
        self.candidates = candidates
        self.judge_id = judge_id
        self.selection_criteria = selection_criteria


class CollaborationEngine:
    """协作引擎 — 创建 + 执行 6 种模式会话"""

    def __init__(self):
        self.sessions: Dict[str, CollaborationSession] = {}
        self.metrics: Dict[str, int] = {"total": 0, "by_mode": {}}

    def create_solo(self, bot_id: str, context: CollaborationContext) -> SoloSession:
        s = SoloSession(bot_id=bot_id, context=context)
        self._register(s)
        return s

    def create_roundtable(
        self,
        participant_ids: List[str],
        leader_id: str,
        context: CollaborationContext,
        rounds: int = 3,
    ) -> RoundtableSession:
        s = RoundtableSession(
            participant_ids=participant_ids,
            leader_id=leader_id,
            rounds=rounds,
            context=context,
        )
        self._register(s)
        return s

    def create_critic(
        self,
        maker_id: str,
        critic_id: str,
        context: CollaborationContext,
        max_iterations: int = 3,
    ) -> CriticSession:
        s = CriticSession(
            maker_id=maker_id,
            critic_id=critic_id,
            max_iterations=max_iterations,
            context=context,
        )
        self._register(s)
        return s

    def create_pipeline(
        self,
        stages: List[Dict[str, Any]],
        context: CollaborationContext,
    ) -> PipelineSession:
        s = PipelineSession(stages=stages, context=context)
        self._register(s)
        return s

    def create_split(
        self,
        sub_tasks: List[Dict[str, Any]],
        leader_id: str,
        context: CollaborationContext,
    ) -> SplitSession:
        s = SplitSession(sub_tasks=sub_tasks, leader_id=leader_id, context=context)
        self._register(s)
        return s

    def create_swarm(
        self,
        candidates: List[Dict[str, Any]],
        judge_id: str,
        context: CollaborationContext,
        selection_criteria: str = "quality",
    ) -> SwarmSession:
        s = SwarmSession(
            candidates=candidates,
            judge_id=judge_id,
            selection_criteria=selection_criteria,
            context=context,
        )
        self._register(s)
        return s

    def get_session(self, session_id: str) -> Optional[CollaborationSession]:
        return self.sessions.get(session_id)

    def _register(self, s: CollaborationSession):
        self.sessions[s.session_id] = s
        self.metrics["total"] += 1
        self.metrics["by_mode"][s.mode.value] = self.metrics["by_mode"].get(s.mode.value, 0) + 1
        s.started_at = time.time()
        logger.info(f"Collaboration session created: {s.mode.value} [{s.session_id}]")

    def finish_session(self, session_id: str, output: Any = None, error: Optional[str] = None):
        s = self.sessions.get(session_id)
        if not s:
            return
        s.completed_at = time.time()
        s.output = output
        s.error = error
        duration = (s.completed_at - s.started_at) * 1000
        logger.info(f"Collaboration session finished: {s.mode.value} [{session_id}] {duration:.0f}ms")

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_sessions": self.metrics["total"],
            "by_mode": self.metrics["by_mode"],
            "active_sessions": sum(1 for s in self.sessions.values() if s.completed_at == 0),
            "completed_sessions": sum(1 for s in self.sessions.values() if s.completed_at > 0),
        }


collaboration_engine = CollaborationEngine()
