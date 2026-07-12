"""智影 V4 — CommandRouter: 命令路由到具体平台 Agent"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .parser import ParsedCommand

logger = logging.getLogger(__name__)


@dataclass
class RouterResult:
    """路由结果"""

    success: bool
    action: str
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    agent_used: str = ""
    steps: List[str] = field(default_factory=list)
    partial: bool = False
    audit: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "output": self.output if not isinstance(self.output, (bytes, bytearray)) else f"<{len(self.output)} bytes>",
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
            "agent_used": self.agent_used,
            "steps": self.steps,
            "partial": self.partial,
            "audit_count": len(self.audit),
        }


# 路由表: action → (agent_name, method_name)
ACTION_ROUTES: Dict[str, tuple] = {
    # Crawl
    "crawl_url": ("DataAcquisitionAgent", "crawl_url"),
    "crawl_website": ("DataAcquisitionAgent", "crawl_website"),
    "crawl_search": ("DataAcquisitionAgent", "crawl_search"),
    "deep_crawl": ("DataAcquisitionAgent", "deep_crawl"),
    "batch_crawl": ("DataAcquisitionAgent", "batch_crawl"),
    "academic_crawl": ("DataAcquisitionAgent", "academic_crawl"),
    "social_crawl": ("DataAcquisitionAgent", "social_crawl"),
    "rss_subscribe": ("DataAcquisitionAgent", "rss_subscribe"),
    "file_download": ("DataAcquisitionAgent", "file_download"),
    # Search
    "web_search": ("DataAcquisitionAgent", "web_search"),
    "image_search": ("DataAcquisitionAgent", "image_search"),
    "video_search": ("DataAcquisitionAgent", "video_search"),
    "academic_search": ("DataAcquisitionAgent", "academic_search"),
    "code_search": ("DataAcquisitionAgent", "code_search"),
    # Process
    "dedupe": ("PipelineAgent", "dedupe"),
    "clean": ("PipelineAgent", "clean"),
    "remove_pii": ("PipelineAgent", "remove_pii"),
    "extract_content": ("PipelineAgent", "extract_content"),
    # Label
    "auto_label": ("AnnotationAgent", "auto_label"),
    "manual_label": ("AnnotationAgent", "manual_label"),
    "label_review": ("AnnotationAgent", "label_review"),
    # Score
    "score_quality": ("QualityAgent", "score_quality"),
    "score_aesthetic": ("QualityAgent", "score_aesthetic"),
    "filter_by_score": ("QualityAgent", "filter_by_score"),
    # Classify
    "classify_modality": ("PipelineAgent", "classify"),
    "filter_by_class": ("PipelineAgent", "filter_by_class"),
    # Store
    "upload": ("DataAcquisitionAgent", "upload"),
    "export": ("DataAcquisitionAgent", "export"),
    # Analyze
    "stats": ("ProjectAgent", "stats"),
    "report": ("ProjectAgent", "report"),
    "query_data": ("ProjectAgent", "query_data"),
    "compare": ("ProjectAgent", "compare"),
    # Manage
    "create_project": ("ProjectAgent", "create_project"),
    "create_requirement": ("ProjectAgent", "create_requirement"),
    "assign_task": ("UserAgent", "assign_task"),
    "approve": ("ReviewAgent", "approve"),
    "reject": ("ReviewAgent", "reject"),
    # Workflow
    "start_workflow": ("WorkflowAgent", "start"),
    "stop_workflow": ("WorkflowAgent", "stop"),
    "design_workflow": ("WorkflowAgent", "design"),
    # System
    "help": ("SystemAgent", "help"),
    "status": ("SystemAgent", "status"),
    "config": ("SystemAgent", "config"),
    "greeting": ("SystemAgent", "greeting"),
    "thanks": ("SystemAgent", "thanks"),
    "unknown": ("SystemAgent", "unknown"),
}


class CommandRouter:
    """命令路由 — ParsedCommand → 平台 Agent 调用"""

    def __init__(self, agents: Optional[Dict[str, Any]] = None):
        # agents: name → instance
        self.agents: Dict[str, Any] = agents or {}
        self.metrics = {"total": 0, "success": 0, "failed": 0, "by_action": {}}

    def register_agent(self, name: str, agent: Any):
        self.agents[name] = agent

    async def route(self, cmd: ParsedCommand) -> RouterResult:
        """异步路由"""
        start = time.time()
        self.metrics["total"] += 1
        self.metrics["by_action"].setdefault(cmd.action, 0)
        self.metrics["by_action"][cmd.action] += 1
        route = ACTION_ROUTES.get(cmd.action)
        if route is None:
            self.metrics["failed"] += 1
            return RouterResult(
                success=False,
                action=cmd.action,
                error=f"unknown action: {cmd.action}",
                duration_ms=(time.time() - start) * 1000,
            )
        agent_name, method_name = route
        agent = self.agents.get(agent_name)
        if agent is None:
            self.metrics["failed"] += 1
            return RouterResult(
                success=False,
                action=cmd.action,
                error=f"agent not available: {agent_name}",
                duration_ms=(time.time() - start) * 1000,
            )
        method = getattr(agent, method_name, None)
        if method is None:
            self.metrics["failed"] += 1
            return RouterResult(
                success=False,
                action=cmd.action,
                error=f"agent {agent_name} has no method {method_name}",
                duration_ms=(time.time() - start) * 1000,
                agent_used=agent_name,
            )
        try:
            # 异步调用
            params = {p.name: p.value for p in cmd.parameters}
            result = method(cmd) if asyncio.iscoroutinefunction(method) else method(cmd)
            if asyncio.iscoroutine(result):
                result = await result
            self.metrics["success"] += 1
            return RouterResult(
                success=True,
                action=cmd.action,
                output=result,
                duration_ms=(time.time() - start) * 1000,
                agent_used=agent_name,
                steps=[agent_name, method_name],
            )
        except Exception as e:
            self.metrics["failed"] += 1
            logger.exception(f"route {cmd.action} failed")
            return RouterResult(
                success=False,
                action=cmd.action,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
                agent_used=agent_name,
            )

    def route_sync(self, cmd: ParsedCommand) -> RouterResult:
        """同步路由 (非异步 agent 用)"""
        start = time.time()
        self.metrics["total"] += 1
        route = ACTION_ROUTES.get(cmd.action)
        if route is None:
            return RouterResult(success=False, action=cmd.action, error="unknown_action", duration_ms=(time.time() - start) * 1000)
        agent_name, method_name = route
        agent = self.agents.get(agent_name)
        if agent is None:
            return RouterResult(success=False, action=cmd.action, error=f"agent_not_available:{agent_name}", duration_ms=(time.time() - start) * 1000)
        method = getattr(agent, method_name, None)
        if method is None:
            return RouterResult(success=False, action=cmd.action, error=f"method_missing:{method_name}", duration_ms=(time.time() - start) * 1000, agent_used=agent_name)
        try:
            result = method(cmd)
            self.metrics["success"] += 1
            return RouterResult(success=True, action=cmd.action, output=result, duration_ms=(time.time() - start) * 1000, agent_used=agent_name, steps=[agent_name, method_name])
        except Exception as e:
            self.metrics["failed"] += 1
            return RouterResult(success=False, action=cmd.action, error=str(e), duration_ms=(time.time() - start) * 1000, agent_used=agent_name)

    def get_metrics(self) -> Dict[str, Any]:
        return self.metrics

    def list_routes(self) -> List[str]:
        return list(ACTION_ROUTES.keys())
