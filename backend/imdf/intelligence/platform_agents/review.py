"""智影 V4 — ReviewAgent: 接管所有审核 (accept / reject / 质检)"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..agent_commands.parser import ParsedCommand
from .base import AgentCapability, PlatformAgent

logger = logging.getLogger(__name__)


class ReviewAgent(PlatformAgent):
    """审核 Agent — 接受/拒绝/质检/多级审核"""

    def __init__(self):
        super().__init__(
            name="ReviewAgent",
            description="审核 Agent: 接受 / 拒绝 / 质检 / 多级审核 / 仲裁",
            capabilities=[AgentCapability.REVIEW],
        )
        # 审核规则
        self.quality_threshold = 0.6
        self.safety_threshold = 0.8

    def handle(self, cmd: ParsedCommand) -> Any:
        action = cmd.action
        if action == "approve":
            return self.approve(cmd)
        if action == "reject":
            return self.reject(cmd)
        if action == "quality_check":
            return self.quality_check(cmd)
        if action == "arbitration":
            return self.arbitration(cmd)
        return {"error": f"unknown action: {action}"}

    def approve(self, cmd: ParsedCommand) -> Dict[str, Any]:
        item_id = cmd.get("item_id", "")
        if not item_id:
            self._record("approve", False)
            return {"error": "missing item_id", "action": "approve"}
        # 真实环境: review_engine.approve / acceptance_engine.submit_acceptance
        self._record("approve")
        return {
            "success": True,
            "action": "approve",
            "item_id": item_id,
            "message": "已通过 — 真实环境调用 review/acceptance engine",
        }

    def reject(self, cmd: ParsedCommand) -> Dict[str, Any]:
        item_id = cmd.get("item_id", "")
        reason = cmd.get("reason", "")
        if not item_id:
            self._record("reject", False)
            return {"error": "missing item_id", "action": "reject"}
        self._record("reject")
        return {
            "success": True,
            "action": "reject",
            "item_id": item_id,
            "reason": reason or "未通过质检",
            "message": "已拒绝 — 真实环境调用 review engine",
        }

    def quality_check(self, cmd: ParsedCommand) -> Dict[str, Any]:
        """批量质检 — 基于 quality_score + safety"""
        threshold = cmd.get("min_score", self.quality_threshold)
        self._record("quality_check")
        return {
            "success": True,
            "action": "quality_check",
            "threshold": threshold,
            "message": f"对 working set 应用 quality_score >= {threshold} 过滤",
        }

    def arbitration(self, cmd: ParsedCommand) -> Dict[str, Any]:
        """争议仲裁 — 多人标注不一致时"""
        item_id = cmd.get("item_id", "")
        if not item_id:
            self._record("arbitration", False)
            return {"error": "missing item_id", "action": "arbitration"}
        self._record("arbitration")
        return {
            "success": True,
            "action": "arbitration",
            "item_id": item_id,
            "message": "已提交仲裁 — 真实环境调多标注员投票",
        }
