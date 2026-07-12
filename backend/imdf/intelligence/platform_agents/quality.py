"""智影 V4 — QualityAgent: 接管所有评分 (quality / aesthetic / custom)"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..agent_commands.parser import ParsedCommand
from ..processing.scoring import ScoreDimension, ScoringEngine
from .base import AgentCapability, PlatformAgent

logger = logging.getLogger(__name__)


class QualityAgent(PlatformAgent):
    """质量 Agent — 多维度评分 + 过滤"""

    def __init__(self):
        super().__init__(
            name="QualityAgent",
            description="质量 Agent: 质量分/美学分/自定义维度/阈值过滤",
            capabilities=[AgentCapability.SCORE],
        )
        self.engine = ScoringEngine()

    def handle(self, cmd: ParsedCommand) -> Any:
        action = cmd.action
        if action == "score_quality":
            return self.score_quality(cmd)
        if action == "score_aesthetic":
            return self.score_aesthetic(cmd)
        if action == "filter_by_score":
            return self.filter_by_score(cmd)
        if action == "multi_score":
            return self.multi_score(cmd)
        return {"error": f"unknown action: {action}"}

    def score_quality(self, cmd: ParsedCommand) -> Dict[str, Any]:
        model = cmd.get("model", "rule")
        self._record("score_quality")
        return {
            "success": True,
            "action": "score_quality",
            "model": model,
            "dimension": ScoreDimension.QUALITY.value,
            "engine": "ScoringEngine._score_quality",
        }

    def score_aesthetic(self, cmd: ParsedCommand) -> Dict[str, Any]:
        model = cmd.get("model", "musiq")
        self._record("score_aesthetic")
        return {
            "success": True,
            "action": "score_aesthetic",
            "model": model,
            "dimension": ScoreDimension.AESTHETIC.value,
            "engine": "ScoringEngine._score_aesthetic",
        }

    def filter_by_score(self, cmd: ParsedCommand) -> Dict[str, Any]:
        min_score = cmd.get("min_score", 0.7)
        dimension = cmd.get("dimension", "quality")
        self._record("filter_by_score")
        return {
            "success": True,
            "action": "filter_by_score",
            "min_score": min_score,
            "dimension": dimension,
            "message": f"按 {dimension} >= {min_score} 过滤",
        }

    def multi_score(self, cmd: ParsedCommand) -> Dict[str, Any]:
        """多维度同时评分"""
        dimensions = list(ScoreDimension)
        self._record("multi_score")
        return {
            "success": True,
            "action": "multi_score",
            "dimensions": [d.value for d in dimensions],
            "engine": "ScoringEngine.process",
        }
