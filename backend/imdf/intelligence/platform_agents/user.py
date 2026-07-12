"""智影 V4 — UserAgent: 接管用户/团队/分配"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..agent_commands.parser import ParsedCommand
from .base import AgentCapability, PlatformAgent

logger = logging.getLogger(__name__)


class UserAgent(PlatformAgent):
    """用户 Agent — 用户管理/任务分配/团队/角色"""

    def __init__(self):
        super().__init__(
            name="UserAgent",
            description="用户 Agent: 用户/团队/角色/任务分配",
            capabilities=[AgentCapability.MANAGE_USER],
        )

    def handle(self, cmd: ParsedCommand) -> Any:
        action = cmd.action
        if action == "assign_task":
            return self.assign_task(cmd)
        if action == "create_user":
            return self.create_user(cmd)
        if action == "list_team":
            return self.list_team(cmd)
        if action == "user_stats":
            return self.user_stats(cmd)
        return {"error": f"unknown action: {action}"}

    def assign_task(self, cmd: ParsedCommand) -> Dict[str, Any]:
        task_id = cmd.get("task_id", "")
        assignee = cmd.get("assignee", "")
        if not task_id or not assignee:
            self._record("assign_task", False)
            return {"error": "missing task_id or assignee", "action": "assign_task"}
        # 真实环境: workbench_engine.assign_task / user_engine.assign
        self._record("assign_task")
        return {
            "success": True,
            "action": "assign_task",
            "task_id": task_id,
            "assignee": assignee,
            "message": "已分配 — 真实环境调 workbench/user engine",
        }

    def create_user(self, cmd: ParsedCommand) -> Dict[str, Any]:
        self._record("create_user")
        return {"success": True, "action": "create_user", "message": "已创建 — 真实环境调 user_engine"}

    def list_team(self, cmd: ParsedCommand) -> Dict[str, Any]:
        self._record("list_team")
        return {
            "success": True,
            "action": "list_team",
            "members": [],
            "message": "已查 — 真实环境调 user_engine.list",
        }

    def user_stats(self, cmd: ParsedCommand) -> Dict[str, Any]:
        self._record("user_stats")
        return {
            "success": True,
            "action": "user_stats",
            "stats": {
                "total_users": 0,
                "active": 0,
                "tasks_completed": 0,
            },
            "message": "统计已生成 — 真实环境调 DB aggregate",
        }
