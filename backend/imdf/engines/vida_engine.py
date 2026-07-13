"""P19-V53: VidaEngine — 屏幕感知 + 上下文分析 + 意图预测 + 主动行动 主循环.

V5 第 26 章 — 屏幕感知型主控 Agent (Vida完整实现).

架构 (依赖注入):

    ┌────────────────────────────────────────────────────────────────────┐
    │                          VidaEngine                                │
    │                                                                    │
    │   screen_capture ─→ context_analyzer ─→ intent_predictor            │
    │          ▲                                  │                       │
    │          │                                  ▼                       │
    │      memory_store                      _decide_action               │
    │          ▲                                  │                       │
    │          │                                  ▼                       │
    │      save()                           action_executor               │
    │                                                                     │
    │   perceive_and_act(user_id)  ─→ 主循环: capture→analyze→load→      │
    │                                   predict→decide→execute→save→     │
    │                                   generate_daily_report            │
    │                                                                     │
    │   generate_daily_report(user_id) ─→ 聚合今日所有 actions             │
    └────────────────────────────────────────────────────────────────────┘

关键设计:
  * 完全 async (asyncio), 平台抓拍用 asyncio.to_thread 包装
  * confidence > 0.7 才执行 action (避免误判)
  * 所有依赖可注入 (DI) — 测试时 mock 每个组件
  * EventBus 记录所有感知-行动事件 (审计 + lineage)
"""
from __future__ import annotations

import logging
import re
import threading
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from imdf.orchestration.bus import EventBus

from imdf.intelligence.vida.action_executor import ActionExecutor
from imdf.intelligence.vida.context_analyzer import ContextAnalyzer
from imdf.intelligence.vida.intent_predictor import IntentPredictor
from imdf.intelligence.vida.memory_store import AgentMemoryStore
from imdf.intelligence.vida.schemas import (
    Action,
    ActionResult,
    ActionStatus,
    ActionType,
    Context,
    Intent,
    Report,
    Scenario,
    ScreenData,
)
from imdf.intelligence.vida.screen_capture import ScreenCapture

logger = logging.getLogger(__name__)


# Confidence threshold — 低于此值不执行 action
CONFIDENCE_THRESHOLD = 0.7

# IntentType → 默认 ActionType (当 intent.suggested_action 未指定时)
INTENT_TO_ACTION: Dict[str, ActionType] = {
    "write_code": ActionType.SUMMARIZE,
    "reply_message": ActionType.REPLY,
    "research": ActionType.SEARCH,
    "read_document": ActionType.SUMMARIZE,
    "email": ActionType.DRAFT,
    "other": ActionType.SUMMARIZE,
}


class VidaEngine:
    """Vida 主控 Agent — orchestrates 5 components."""

    def __init__(
        self,
        screen_capture: ScreenCapture,
        context_analyzer: ContextAnalyzer,
        intent_predictor: IntentPredictor,
        action_executor: ActionExecutor,
        memory_store: AgentMemoryStore,
        bus: EventBus,
        *,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
    ) -> None:
        self.screen_capture = screen_capture
        self.context_analyzer = context_analyzer
        self.intent_predictor = intent_predictor
        self.action_executor = action_executor
        self.memory_store = memory_store
        self.bus = bus
        self.confidence_threshold = confidence_threshold
        self._lock = threading.RLock()
        self._stats = {
            "perceive_runs": 0,
            "actions_executed": 0,
            "actions_skipped_low_confidence": 0,
            "reports_generated": 0,
        }

    # ── Status / Stats ─────────────────────────────────────────────
    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "stats": dict(self._stats),
                "components": {
                    "screen_capture": type(self.screen_capture).__name__,
                    "context_analyzer": type(self.context_analyzer).__name__,
                    "intent_predictor": type(self.intent_predictor).__name__,
                    "action_executor": type(self.action_executor).__name__,
                    "memory_store": type(self.memory_store).__name__,
                    "bus": type(self.bus).__name__,
                },
                "confidence_threshold": self.confidence_threshold,
            }

    # ── Main loop ──────────────────────────────────────────────────
    async def perceive_and_act(self, user_id: str) -> Dict[str, Any]:
        """完整感知-理解-预测-行动循环.

        步骤:
          1. screen_capture.capture()              — 抓拍屏幕
          2. context_analyzer.analyze(screen, user)  — 上下文分析
          3. memory_store.load(user_id)             — 加载历史
          4. intent_predictor.predict(context, mem)  — 意图预测
          5. if confidence > threshold:             — 决定是否行动
               decide action → execute → save → generate_daily_report
        """
        with self._lock:
            self._stats["perceive_runs"] += 1

        # 1. 抓拍屏幕
        screen: ScreenData = await self.screen_capture.capture()
        self._bus_event("vida.screen_captured", entity_id=screen.screen_id,
                        payload={"app": screen.active_app, "platform": screen.platform})

        # 2. 上下文分析
        context: Context = await self.context_analyzer.analyze(screen, user_id)
        self._bus_event("vida.context_analyzed", entity_id=context.context_id,
                        payload={"scenario": context.scenario.value, "app": context.app})

        # 3. 加载 memory
        memory = await self.memory_store.load(user_id)

        # 4. 意图预测
        intent: Intent = await self.intent_predictor.predict(context, memory)
        self._bus_event("vida.intent_predicted", entity_id=intent.intent_id,
                        payload={"intent_type": intent.intent_type.value,
                                 "confidence": intent.confidence,
                                 "suggested_action": intent.suggested_action.value})

        # 5. 决定 + 行动
        result: Dict[str, Any] = {
            "context": context,
            "intent": intent,
            "screen": screen,
            "action": None,
            "result": None,
        }

        if intent.confidence > self.confidence_threshold:
            action = await self._decide_action(intent, context)
            if action is not None:
                exec_result = await self.action_executor.execute(action)
                await self.memory_store.save(user_id, action, exec_result)
                with self._lock:
                    self._stats["actions_executed"] += 1
                self._bus_event("vida.action_executed", entity_id=exec_result.result_id,
                                payload={"action_type": action.action_type.value,
                                         "success": exec_result.success})

                result["action"] = action
                result["result"] = exec_result

                # 生成日报
                await self.generate_daily_report(user_id)
        else:
            with self._lock:
                self._stats["actions_skipped_low_confidence"] += 1
            self._bus_event("vida.action_skipped", entity_id=intent.intent_id,
                            payload={"confidence": intent.confidence,
                                     "threshold": self.confidence_threshold})

        return result

    # ── Action decision ────────────────────────────────────────────
    async def _decide_action(self, intent: Intent, context: Context) -> Optional[Action]:
        """根据 intent 决定具体 action + parameters."""
        intent_value = intent.intent_type.value
        action_type = intent.suggested_action
        if action_type is None or action_type == "":
            action_type = INTENT_TO_ACTION.get(intent_value, ActionType.SUMMARIZE)

        # 构造参数 (基于 context)
        parameters: Dict[str, Any] = {
            "intent_id": intent.intent_id,
            "scenario": context.scenario.value,
            "app": context.app,
        }
        # 场景专属参数
        if action_type == ActionType.SUMMARIZE:
            files = context.key_info.get("files") or [""]
            parameters["content"] = context.text or files[0]
            parameters["length"] = "short"
        elif action_type == ActionType.REPLY:
            parameters["message"] = context.text[:200]
            parameters["context"] = context.key_info.get("participants", [])
            parameters["n"] = 3
        elif action_type == ActionType.ORGANIZE:
            parameters["files"] = context.key_info.get("files", [])
        elif action_type == ActionType.SEARCH:
            parameters["query"] = context.key_info.get("page_url") or context.app or "recent"
        elif action_type == ActionType.DRAFT:
            parameters["subject"] = context.key_info.get("subject", "Auto-draft")
            parameters["template"] = "professional"
        elif action_type == ActionType.ANALYZE:
            parameters["data"] = context.key_info.get("code_symbols", [])

        return Action(
            action_id=f"act_{uuid.uuid4().hex[:8]}",
            intent_id=intent.intent_id,
            action_type=action_type,
            parameters=parameters,
            timestamp=datetime.now(timezone.utc),
        )

    # ── Daily report ───────────────────────────────────────────────
    async def generate_daily_report(self, user_id: str) -> Report:
        """聚合今日所有 action → daily report."""
        today_entries = await self.memory_store.get_today_actions(user_id)

        completed = [e for e in today_entries
                     if e.get("result", {}).get("status") == ActionStatus.COMPLETED.value]
        in_progress = [e for e in today_entries
                       if e.get("result", {}).get("status") == ActionStatus.IN_PROGRESS.value]
        failed = [e for e in today_entries
                  if e.get("result", {}).get("status") == ActionStatus.FAILED.value]

        # key_words: 从 action_type + rationale 提取
        key_words = self._extract_key_words(today_entries)
        # time_distribution: hour → count
        time_dist = self._calculate_time_distribution(today_entries)
        # tomorrow_plan: 简单建议
        tomorrow_plan = self._suggest_tomorrow_plan(today_entries, key_words)
        # completed_items: 取前 5 条
        completed_items = [
            {
                "title": (e.get("action", {}).get("action_type") or "action"),
                "result": (e.get("result", {}).get("result") or {}),
            }
            for e in completed[:5]
        ]

        report = Report(
            report_id=f"rep_{uuid.uuid4().hex[:8]}",
            user_id=user_id,
            date=datetime.now(timezone.utc).date().isoformat(),
            completed_count=len(completed),
            in_progress_count=len(in_progress),
            failed_count=len(failed),
            completed_items=completed_items,
            key_words=key_words,
            tomorrow_plan=tomorrow_plan,
            time_distribution=time_dist,
        )

        with self._lock:
            self._stats["reports_generated"] += 1
        self._bus_event("vida.daily_report_generated", entity_id=report.report_id,
                        payload={"date": report.date,
                                 "completed": report.completed_count,
                                 "in_progress": report.in_progress_count})
        return report

    # ── Helpers ────────────────────────────────────────────────────
    def _extract_key_words(self, entries: List[Dict[str, Any]]) -> List[str]:
        """从 entries 提取关键词 — 频次最高的 action_type + rationale 关键字."""
        counter: Counter[str] = Counter()
        for e in entries:
            action = e.get("action", {})
            if isinstance(action, dict):
                counter[action.get("action_type", "")] += 1
            result = e.get("result", {})
            rationale = ""
            if isinstance(result, dict):
                rationale = str(result.get("error", "")) + str(result.get("result", {}).get("summary", ""))
            for word in re.findall(r"\b[a-zA-Z_]{4,}\b", rationale):
                counter[word.lower()] += 1
        # 返回 top 10
        return [w for w, _ in counter.most_common(10) if w]

    def _calculate_time_distribution(self, entries: List[Dict[str, Any]]) -> Dict[str, int]:
        """按小时分桶."""
        dist: Counter[str] = Counter()
        for e in entries:
            ts = str(e.get("timestamp", ""))
            if len(ts) >= 13:
                hour = ts[11:13]
                dist[hour] += 1
        return dict(sorted(dist.items()))

    def _suggest_tomorrow_plan(self, entries: List[Dict[str, Any]],
                                key_words: List[str]) -> List[str]:
        """简单建议 — 基于今日 failed + 重复 action."""
        failed_count = sum(
            1 for e in entries
            if e.get("result", {}).get("status") == ActionStatus.FAILED.value
        )
        plan: List[str] = []
        if failed_count > 0:
            plan.append(f"Re-try {failed_count} failed action(s) from today")
        if "summarize" in key_words:
            plan.append("Continue summarizing recent context")
        if "search" in key_words:
            plan.append("Schedule research tasks for top queries")
        if not plan:
            plan.append("Continue current workflow patterns")
        return plan[:5]

    def _bus_event(self, topic: str, *, entity_id: str,
                   payload: Optional[Dict[str, Any]] = None) -> None:
        """Bus publish wrapper — 失败不抛 (audit 是 best-effort)."""
        try:
            self.bus.record(topic=topic, entity_type="vida_event", entity_id=entity_id,
                            payload=payload or {}, actor="vida_engine",
                            source_module="engines.vida_engine")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Vida bus event %s failed: %s", topic, exc)


__all__ = ["VidaEngine", "VidaEngineState", "CONFIDENCE_THRESHOLD", "INTENT_TO_ACTION"]


@dataclass
class VidaEngineState:
    """State snapshot of a ``VidaEngine`` instance.

    P22-P2-real-fix-3-Engines: previously the ``engine_router`` imported
    ``VidaEngineState`` (forward-compatible export) but the class did
    not exist on the module, breaking the import. This dataclass
    captures the structured state that callers (engine_router,
    monitoring, tests) can read.

    Fields:
      * ``perceive_runs`` / ``actions_executed`` / ``actions_skipped_low_confidence``
        / ``reports_generated`` — counters from VidaEngine._stats
      * ``confidence_threshold`` — current threshold
      * ``components`` — names of the 6 injected components
    """

    perceive_runs: int = 0
    actions_executed: int = 0
    actions_skipped_low_confidence: int = 0
    reports_generated: int = 0
    confidence_threshold: float = CONFIDENCE_THRESHOLD
    components: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_engine(cls, engine: "VidaEngine") -> "VidaEngineState":
        """Snapshot the state of a live ``VidaEngine``."""
        with engine._lock:
            return cls(
                perceive_runs=engine._stats["perceive_runs"],
                actions_executed=engine._stats["actions_executed"],
                actions_skipped_low_confidence=engine._stats["actions_skipped_low_confidence"],
                reports_generated=engine._stats["reports_generated"],
                confidence_threshold=engine.confidence_threshold,
                components={
                    "screen_capture": type(engine.screen_capture).__name__,
                    "context_analyzer": type(engine.context_analyzer).__name__,
                    "intent_predictor": type(engine.intent_predictor).__name__,
                    "action_executor": type(engine.action_executor).__name__,
                    "memory_store": type(engine.memory_store).__name__,
                    "bus": type(engine.bus).__name__,
                },
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "perceive_runs": self.perceive_runs,
            "actions_executed": self.actions_executed,
            "actions_skipped_low_confidence": self.actions_skipped_low_confidence,
            "reports_generated": self.reports_generated,
            "confidence_threshold": self.confidence_threshold,
            "components": dict(self.components),
        }