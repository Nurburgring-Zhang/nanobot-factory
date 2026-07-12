"""智影 V5 — Proactive 子包: 主动型 Agent (Vida 模式)

迁移自 Vida (Proactive Agent):
- 持续理解上下文 + 长期记忆
- 预判用户意图 + 主动协助
- 屏幕感知 + 主动建议
- 今日战报卡
"""
from .proactive_engine import (
    ProactiveEngine,
    ProactiveContext,
    ProactiveAction,
    ContextSnapshot,
    DailyReport,
    proactive_engine,
)

__all__ = [
    "ProactiveEngine",
    "ProactiveContext",
    "ProactiveAction",
    "ContextSnapshot",
    "DailyReport",
    "proactive_engine",
]
