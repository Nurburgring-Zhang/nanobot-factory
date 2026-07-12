"""P19-V53: Vida intelligence package — 屏幕感知型主控 Agent 子包.

V5 第 26 章 — Vida 完整实现.

模块结构:
  * schemas         — Pydantic v2 数据模型 (ScreenData / Context / Intent / Action / ActionResult / Report)
  * screen_capture  — 多平台屏幕抓拍 (win32gui / pyautogui+AppKit / scrot / mock)
  * context_analyzer — 上下文分析 (6 大场景识别 + key_info 提取)
  * intent_predictor — LLM-based 意图预测 (6 种 intent_type + 7 种 suggested_action)
  * action_executor  — 7 种主动行动执行 (summarize/reply/organize/search/remind/draft/analyze)
  * memory_store    — 用户级 JSON memory (load/save/get_today_actions)

顶层入口:
  * VidaEngine (engines/vida_engine.py) — 协调 5 个组件完成 perceive-and-act 循环
"""
from __future__ import annotations

from .action_executor import ActionExecutor
from .context_analyzer import ContextAnalyzer, SCENARIO_KEYWORDS
from .intent_predictor import IntentPredictor, MockLLM
from .memory_store import AgentMemoryStore
from .schemas import (
    Action,
    ActionResult,
    ActionStatus,
    ActionType,
    Context,
    Intent,
    IntentType,
    Report,
    Scenario,
    ScreenData,
)
from .screen_capture import ScreenCapture

__version__ = "5.3.0"

__all__ = [
    "Action",
    "ActionExecutor",
    "ActionResult",
    "ActionStatus",
    "ActionType",
    "Context",
    "ContextAnalyzer",
    "Intent",
    "IntentPredictor",
    "IntentType",
    "MockLLM",
    "Report",
    "Scenario",
    "SCENARIO_KEYWORDS",
    "ScreenCapture",
    "ScreenData",
    "AgentMemoryStore",
]