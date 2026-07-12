"""智影 V4 — Agent 命令子包: 自然语言 → 平台操作"""
from .intent import IntentClassifier, Intent, IntentCategory
from .parser import CommandParser, ParsedCommand, CommandParameter
from .router import CommandRouter, RouterResult
from .session import SessionManager, AgentSession, SessionContext

__all__ = [
    "IntentClassifier",
    "Intent",
    "IntentCategory",
    "CommandParser",
    "ParsedCommand",
    "CommandParameter",
    "CommandRouter",
    "RouterResult",
    "SessionManager",
    "AgentSession",
    "SessionContext",
]
