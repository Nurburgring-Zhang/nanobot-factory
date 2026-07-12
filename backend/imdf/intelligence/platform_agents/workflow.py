"""智影 V4 — WorkflowAgent: 接管工作流 (start / stop / design / 模板)"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..agent_commands.parser import ParsedCommand
from .base import AgentCapability, PlatformAgent

logger = logging.getLogger(__name__)


class WorkflowAgent(PlatformAgent):
    """工作流 Agent — start / stop / design / 模板 / 监控"""

    def __init__(self):
        super().__init__(
            name="WorkflowAgent",
            description="工作流 Agent: 启动 / 停止 / 设计 / 监控 — 47 节点模板",
            capabilities=[AgentCapability.WORKFLOW],
        )
        self._running: Dict[str, Dict[str, Any]] = {}

    def handle(self, cmd: ParsedCommand) -> Any:
        action = cmd.action
        if action == "start_workflow":
            return self.start(cmd)
        if action == "stop_workflow":
            return self.stop(cmd)
        if action == "design_workflow":
            return self.design(cmd)
        if action == "list_workflows":
            return self.list_workflows()
        if action == "workflow_status":
            return self.workflow_status(cmd)
        return {"error": f"unknown action: {action}"}

    def start(self, cmd: ParsedCommand) -> Dict[str, Any]:
        workflow_id = cmd.get("workflow_id", "")
        if not workflow_id:
            self._record("start", False)
            return {"error": "missing workflow_id", "action": "start"}
        # 真实环境: workflow_builder.engine.WorkflowEngine.run_workflow
        self._running[workflow_id] = {
            "workflow_id": workflow_id,
            "status": "running",
            "started_at": __import__("time").time(),
            "input": cmd.get("input", {}),
        }
        self._record("start")
        return {
            "success": True,
            "action": "start",
            "workflow_id": workflow_id,
            "status": "running",
            "message": "已启动 — 真实环境调 workflow_builder.engine.WorkflowEngine.run_workflow",
        }

    def stop(self, cmd: ParsedCommand) -> Dict[str, Any]:
        workflow_id = cmd.get("workflow_id", "")
        if not workflow_id:
            self._record("stop", False)
            return {"error": "missing workflow_id", "action": "stop"}
        if workflow_id in self._running:
            self._running[workflow_id]["status"] = "stopped"
        self._record("stop")
        return {
            "success": True,
            "action": "stop",
            "workflow_id": workflow_id,
            "status": "stopped",
        }

    def design(self, cmd: ParsedCommand) -> Dict[str, Any]:
        """工作流设计 — 描述 → 节点链"""
        description = cmd.get("description", "")
        if not description:
            self._record("design", False)
            return {"error": "missing description", "action": "design"}
        # 真实环境: workflow_builder.template
        self._record("design")
        return {
            "success": True,
            "action": "design",
            "description": description,
            "suggested_nodes": _suggest_nodes_from_description(description),
            "message": "建议节点 — 可调 workflow_builder.template 生成",
        }

    def list_workflows(self) -> Dict[str, Any]:
        return {
            "success": True,
            "action": "list_workflows",
            "running": list(self._running.keys()),
            "count": len(self._running),
        }

    def workflow_status(self, cmd: ParsedCommand) -> Dict[str, Any]:
        workflow_id = cmd.get("workflow_id", "")
        if workflow_id and workflow_id in self._running:
            return {"success": True, "status": self._running[workflow_id]}
        return {"success": False, "error": f"workflow not found: {workflow_id}"}


def _suggest_nodes_from_description(desc: str) -> List[str]:
    """根据描述建议节点 — 简单关键词匹配"""
    desc_l = desc.lower()
    nodes = []
    if "爬" in desc or "抓" in desc or "crawl" in desc_l:
        nodes.append("crawler_node")
    if "搜索" in desc or "search" in desc_l:
        nodes.append("search_node")
    if "去重" in desc or "dedupe" in desc_l:
        nodes.append("dedupe_node")
    if "清" in desc or "clean" in desc_l:
        nodes.append("clean_node")
    if "标" in desc or "label" in desc_l:
        nodes.append("label_node")
    if "评" in desc or "score" in desc_l:
        nodes.append("score_node")
    if "分类" in desc or "classify" in desc_l:
        nodes.append("classify_node")
    if "存" in desc or "store" in desc_l:
        nodes.append("store_node")
    if not nodes:
        nodes = ["crawler_node", "dedupe_node", "clean_node", "label_node", "score_node", "store_node"]
    return nodes
