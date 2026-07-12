"""P19-V53: Vida schemas (Pydantic v2).

V5 第 26 章 — Vida 屏幕感知主控 Agent 的数据模型.

Models:
  * ScreenData     — 屏幕抓拍结果
  * Context        — 上下文分析输出 (含 6 种 scenario)
  * Intent         — 意图预测 (6 种 intent_type)
  * Action         — 主动行动 (7 种 action_type)
  * ActionResult   — 行动执行结果
  * Report         — 每日战报
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Scenario(str, Enum):
    """6 大用户工作场景."""

    CODE = "code"
    CHAT = "chat"
    DOCUMENT = "document"
    RESEARCH = "research"
    EMAIL = "email"
    TERMINAL = "terminal"


class IntentType(str, Enum):
    """意图类型 (与 LLM prompt 中的 6 个候选对应)."""

    WRITE_CODE = "write_code"
    REPLY_MESSAGE = "reply_message"
    RESEARCH = "research"
    READ_DOCUMENT = "read_document"
    EMAIL = "email"
    OTHER = "other"


class ActionType(str, Enum):
    """7 种主动行动类型."""

    SUMMARIZE = "summarize"
    REPLY = "reply"
    ORGANIZE = "organize"
    SEARCH = "search"
    REMIND = "remind"
    DRAFT = "draft"
    ANALYZE = "analyze"


class ActionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# --------------------------------------------------------------------------- #
#  Core models
# --------------------------------------------------------------------------- #
class ScreenData(BaseModel):
    """一次屏幕抓拍 — image 可以是 bytes (PNG/JPEG) 或 base64."""

    model_config = ConfigDict(extra="allow")

    screen_id: str = Field(default_factory=lambda: "")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    image: bytes = b""
    image_b64: str = ""
    width: int = 1920
    height: int = 1080
    active_app: str = ""
    active_window_title: str = ""
    platform: str = "mock"
    extra: Dict[str, Any] = Field(default_factory=dict)


class Context(BaseModel):
    """结构化上下文 — 屏幕抓拍 + 文本 + 场景."""

    model_config = ConfigDict(extra="allow")

    context_id: str = ""
    screen_id: str = ""
    user_id: str = ""
    app: str = ""
    scenario: Scenario = Scenario.CODE
    text: str = ""
    key_info: Dict[str, Any] = Field(default_factory=dict)
    language: str = "en"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Intent(BaseModel):
    """意图预测."""

    model_config = ConfigDict(extra="allow")

    intent_id: str = ""
    context_id: str = ""
    intent_type: IntentType = IntentType.OTHER
    confidence: float = 0.0
    suggested_action: ActionType = ActionType.SUMMARIZE
    rationale: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Action(BaseModel):
    """主动行动 — ActionType + 参数."""

    model_config = ConfigDict(extra="allow")

    action_id: str = ""
    intent_id: str = ""
    action_type: ActionType = ActionType.SUMMARIZE
    parameters: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 5
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ActionResult(BaseModel):
    """行动执行结果."""

    model_config = ConfigDict(extra="allow")

    result_id: str = ""
    action_id: str = ""
    action_type: ActionType = ActionType.SUMMARIZE
    success: bool = True
    status: ActionStatus = ActionStatus.COMPLETED
    result: Dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    duration_ms: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Report(BaseModel):
    """每日战报."""

    model_config = ConfigDict(extra="allow")

    report_id: str = ""
    user_id: str = ""
    date: str = ""  # YYYY-MM-DD
    completed_count: int = 0
    in_progress_count: int = 0
    failed_count: int = 0
    completed_items: List[Dict[str, Any]] = Field(default_factory=list)
    key_words: List[str] = Field(default_factory=list)
    tomorrow_plan: List[str] = Field(default_factory=list)
    time_distribution: Dict[str, int] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = [
    "Action",
    "ActionResult",
    "ActionStatus",
    "ActionType",
    "Context",
    "Intent",
    "IntentType",
    "Report",
    "Scenario",
    "ScreenData",
]