"""P19-V53: Vida intent_predictor — LLM-based intent prediction.

V5 第 26 章 § 26.3:
  * LLM prompt 模板 — 6 选 1 (write_code|reply_message|research|read_document|email|other)
  * 解析 JSON 返回 Intent
  * 提供 mock LLM (测试用) — 根据 scenario 给出固定 confidence
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol

from .schemas import ActionType, Context, Intent, IntentType, Scenario

logger = logging.getLogger(__name__)


class LLMRunnable(Protocol):
    """LLM provider 接口 — 任何有 .complete() 的对象都可注入."""

    async def complete(self, prompt: str, *, response_format: str = "text") -> str: ...


# Prompt 模板 — 6 个 intent_type 选项 + JSON 输出格式
INTENT_PROMPT = """\
You are a screen-aware intent predictor. Based on the user's current context, \
predict what they are most likely to do NEXT.

Current Application: {app}
Scenario: {scenario}
Screen Text (first 200 chars): {text}
Key Information: {key_info}
User Memory Summary: {memory}

Return a JSON object with EXACTLY these fields:
{{
    "intent_type": "write_code" | "reply_message" | "research" | "read_document" | "email" | "other",
    "confidence": <float 0.0-1.0>,
    "suggested_action": "summarize" | "reply" | "organize" | "search" | "remind" | "draft" | "analyze",
    "rationale": "<one-sentence explanation>"
}}

Pick the single most likely intent. confidence should reflect how strong the signal is.
"""


# Scenario → 启发式 (intent, action, confidence) — 用于 mock LLM
SCENARIO_HEURISTIC: Dict[Scenario, Tuple[IntentType, ActionType, float]] = {
    Scenario.CODE: (IntentType.WRITE_CODE, ActionType.SUMMARIZE, 0.85),
    Scenario.CHAT: (IntentType.REPLY_MESSAGE, ActionType.REPLY, 0.82),
    Scenario.DOCUMENT: (IntentType.READ_DOCUMENT, ActionType.SUMMARIZE, 0.78),
    Scenario.RESEARCH: (IntentType.RESEARCH, ActionType.SEARCH, 0.80),
    Scenario.EMAIL: (IntentType.EMAIL, ActionType.DRAFT, 0.83),
    Scenario.TERMINAL: (IntentType.WRITE_CODE, ActionType.ANALYZE, 0.65),
}


def _extract_json(raw: str) -> Dict[str, Any]:
    """从 LLM 输出中提取 JSON — 处理 markdown code fence."""
    text = (raw or "").strip()
    # 去掉 ```json ... ``` 包装
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    # 找第一个 { 和最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


class IntentPredictor:
    """意图预测 — LLM-based (可注入 LLM provider)."""

    def __init__(self, llm: Optional[LLMRunnable] = None,
                 *,
                 heuristic_only: bool = False) -> None:
        """heuristic_only=True 跳过 LLM 直接用 SCENARIO_HEURISTIC (测试加速)."""
        self.llm = llm
        self.heuristic_only = heuristic_only or (llm is None)

    async def predict(self, context: Context, memory: Dict[str, Any]) -> Intent:
        """预测用户意图 — 返回 Intent."""
        import uuid

        intent_id = f"int_{uuid.uuid4().hex[:8]}"

        if self.heuristic_only:
            return self._heuristic_intent(intent_id, context)

        assert self.llm is not None, "llm is required when heuristic_only=False"
        prompt = INTENT_PROMPT.format(
            app=context.app,
            scenario=context.scenario.value,
            text=context.text[:200],
            key_info=json.dumps(context.key_info, ensure_ascii=False)[:300],
            memory=json.dumps(memory or {}, ensure_ascii=False)[:300],
        )
        try:
            raw = await self.llm.complete(prompt, response_format="json")
            data = _extract_json(raw)
            return Intent(
                intent_id=intent_id,
                context_id=context.context_id,
                intent_type=IntentType(data["intent_type"]),
                confidence=float(data["confidence"]),
                suggested_action=ActionType(data["suggested_action"]),
                rationale=str(data.get("rationale", "")),
                parameters=data.get("parameters", {}),
                timestamp=context.timestamp,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vida intent LLM failed (%s); fallback heuristic", exc)
            return self._heuristic_intent(intent_id, context)

    def _heuristic_intent(self, intent_id: str, context: Context) -> Intent:
        """无 LLM 时用场景启发式生成 Intent."""
        intent_type, action_type, confidence = SCENARIO_HEURISTIC.get(
            context.scenario, (IntentType.OTHER, ActionType.SUMMARIZE, 0.5)
        )
        rationale = (
            f"heuristic: scenario={context.scenario.value} → "
            f"intent={intent_type.value} action={action_type.value}"
        )
        return Intent(
            intent_id=intent_id,
            context_id=context.context_id,
            intent_type=intent_type,
            confidence=confidence,
            suggested_action=action_type,
            rationale=rationale,
            parameters={},
            timestamp=context.timestamp,
        )


# ── Mock LLM for tests ─────────────────────────────────────────────
class MockLLM:
    """Mock LLM — 返回 deterministic JSON, 用于 unit test."""

    def __init__(self, *, confidence: float = 0.85,
                 intent_type: IntentType = IntentType.WRITE_CODE,
                 action_type: ActionType = ActionType.SUMMARIZE) -> None:
        self.confidence = confidence
        self.intent_type = intent_type
        self.action_type = action_type
        self.call_count = 0

    async def complete(self, prompt: str, *, response_format: str = "text") -> str:
        self.call_count += 1
        return json.dumps({
            "intent_type": self.intent_type.value,
            "confidence": self.confidence,
            "suggested_action": self.action_type.value,
            "rationale": f"mock-LLM after {self.call_count} calls",
        })


__all__ = ["IntentPredictor", "LLMRunnable", "MockLLM", "INTENT_PROMPT", "SCENARIO_HEURISTIC"]