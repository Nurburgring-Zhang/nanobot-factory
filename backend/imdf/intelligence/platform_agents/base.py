"""智影 V4 — PlatformAgent 基类 + 能力定义"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ..agent_commands.parser import ParsedCommand

logger = logging.getLogger(__name__)


class AgentCapability(str, Enum):
    """Agent 能力声明"""

    CRAWL = "crawl"
    SEARCH = "search"
    DEDUPE = "dedupe"
    CLEAN = "clean"
    LABEL = "label"
    SCORE = "score"
    CLASSIFY = "classify"
    STORE = "store"
    MANAGE_PROJECT = "manage_project"
    MANAGE_USER = "manage_user"
    REVIEW = "review"
    WORKFLOW = "workflow"
    QUERY = "query"
    REPORT = "report"
    SYSTEM = "system"


@dataclass
class PlatformAgent(ABC):
    """所有平台 Agent 的基类"""

    name: str = "BaseAgent"
    description: str = ""
    capabilities: List[AgentCapability] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=lambda: {"calls": 0, "errors": 0, "by_action": {}})

    @abstractmethod
    def handle(self, cmd: ParsedCommand) -> Any:
        """处理命令"""
        pass

    def _record(self, action: str, success: bool = True):
        self.metrics["calls"] += 1
        if not success:
            self.metrics["errors"] += 1
        self.metrics["by_action"].setdefault(action, 0)
        self.metrics["by_action"][action] += 1

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "calls": self.metrics["calls"],
            "errors": self.metrics["errors"],
            "error_rate": round(self.metrics["errors"] / max(self.metrics["calls"], 1), 3),
            "actions": self.metrics["by_action"],
        }
