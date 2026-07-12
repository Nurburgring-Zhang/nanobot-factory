"""智影 V4 — DataAcquisitionOrchestrator: 主控 Agent"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..agent_commands.intent import Intent, IntentClassifier
from ..agent_commands.parser import CommandParser, ParsedCommand
from ..agent_commands.router import CommandRouter, RouterResult
from ..agent_commands.session import SessionManager
from ..crawler.dispatcher import CrawlerDispatcher
from ..platform_agents.annotation import AnnotationAgent
from ..platform_agents.data_acquisition import DataAcquisitionAgent
from ..platform_agents.pipeline import PipelineAgent
from ..platform_agents.project import ProjectAgent
from ..platform_agents.quality import QualityAgent
from ..platform_agents.review import ReviewAgent
from ..platform_agents.user import UserAgent
from ..platform_agents.workflow import WorkflowAgent
from ..platform_agents.system import SystemAgent

logger = logging.getLogger(__name__)


@dataclass
class TurnResult:
    """单轮对话结果"""

    session_id: str
    user_text: str
    parsed_command: ParsedCommand
    router_result: RouterResult
    response_text: str = ""
    suggestions: List[str] = field(default_factory=list)
    ts: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_text": self.user_text,
            "parsed": self.parsed_command.to_dict(),
            "router": self.router_result.to_dict(),
            "response": self.response_text,
            "suggestions": self.suggestions,
            "ts": self.ts,
        }


class DataAcquisitionOrchestrator:
    """主控 Agent — 接收 NL → 解析 → 路由 → 调用 → 反馈"""

    def __init__(self):
        # 1. 注册所有平台 Agent
        self.dispatcher = CrawlerDispatcher()
        self.data_acq = DataAcquisitionAgent(self.dispatcher)
        self.pipeline = PipelineAgent()
        self.annotation = AnnotationAgent()
        self.review = ReviewAgent()
        self.workflow = WorkflowAgent()
        self.project = ProjectAgent()
        self.user = UserAgent()
        self.quality = QualityAgent()
        self.system = SystemAgent(orchestrator_status_fn=self.get_status)

        # 2. router 注册
        self.router = CommandRouter(
            {
                "DataAcquisitionAgent": self.data_acq,
                "PipelineAgent": self.pipeline,
                "AnnotationAgent": self.annotation,
                "ReviewAgent": self.review,
                "WorkflowAgent": self.workflow,
                "ProjectAgent": self.project,
                "UserAgent": self.user,
                "QualityAgent": self.quality,
                "SystemAgent": self.system,
            }
        )

        # 3. NL 处理
        self.intent_classifier = IntentClassifier()
        self.parser = CommandParser(self.intent_classifier)

        # 4. 会话
        self.session_manager = SessionManager()

    def chat(self, text: str, session_id: Optional[str] = None, user_id: str = "default") -> TurnResult:
        """同步 chat"""
        session = self.session_manager.get_or_create(session_id, user_id)
        context = {
            "last_intent": session.context.last_intent,
            "history": session.context.history[-5:],
            "working_set_size": len(session.context.working_set),
        }
        parsed = self.parser.parse(text, context)
        router_result = self.router.route_sync(parsed)
        response = self._build_response(parsed, router_result)
        session.context.add_turn("user", text, {"intent": parsed.intent.category.value, "action": parsed.action})
        session.context.add_turn("assistant", response, {"success": router_result.success})
        self.session_manager.update_context(session.session_id, intent=parsed.intent, last_result=router_result.output)
        return TurnResult(
            session_id=session.session_id,
            user_text=text,
            parsed_command=parsed,
            router_result=router_result,
            response_text=response,
            suggestions=self._build_suggestions(parsed, router_result),
            ts=time.time(),
        )

    async def chat_async(self, text: str, session_id: Optional[str] = None, user_id: str = "default") -> TurnResult:
        """异步 chat"""
        session = self.session_manager.get_or_create(session_id, user_id)
        context = {
            "last_intent": session.context.last_intent,
            "history": session.context.history[-5:],
        }
        parsed = self.parser.parse(text, context)
        router_result = await self.router.route(parsed)
        response = self._build_response(parsed, router_result)
        session.context.add_turn("user", text)
        session.context.add_turn("assistant", response)
        self.session_manager.update_context(session.session_id, intent=parsed.intent)
        return TurnResult(
            session_id=session.session_id,
            user_text=text,
            parsed_command=parsed,
            router_result=router_result,
            response_text=response,
            suggestions=self._build_suggestions(parsed, router_result),
            ts=time.time(),
        )

    def _build_response(self, parsed: ParsedCommand, result: RouterResult) -> str:
        """构造自然语言响应"""
        if not result.success:
            err = result.error or "未知错误"
            if "missing" in err:
                return f"参数缺失: {err.split(':')[-1].strip()}。请补充后再试。"
            return f"操作失败: {err}"
        action = result.action
        output = result.output
        if isinstance(output, dict):
            if "items" in output and isinstance(output["items"], list):
                count = len(output["items"])
                if "channel" in output:
                    return f"已通过 {output['channel']} 渠道采集 {count} 条数据。耗时 {result.duration_ms:.0f}ms。"
                if "provider" in output:
                    return f"已通过 {output['provider']} 搜索 {count} 条结果。耗时 {result.duration_ms:.0f}ms。"
                if "query" in output:
                    return f"搜索 '{output['query']}' 完成,共 {count} 条结果。"
                return f"操作成功,共 {count} 条数据。"
            if "data" in output:
                return f"统计数据已生成,维度: {output.get('group_by', '?')}。"
            if "url" in output and output.get("url", "").startswith("/api"):
                return f"报告已生成: {output['url']}"
            if "message" in output:
                return output["message"]
        return f"{action} 已完成,耗时 {result.duration_ms:.0f}ms"

    def _build_suggestions(self, parsed: ParsedCommand, result: RouterResult) -> List[str]:
        """构造后续建议"""
        suggestions: List[str] = []
        action = parsed.intent.action
        if action in ("crawl_url", "crawl_website", "academic_crawl", "social_crawl"):
            suggestions = [
                "对采集的数据自动打标",
                "对采集的数据做质量评分",
                "过滤 quality < 0.6 的数据",
                "导出到 MinIO 存储",
            ]
        elif action in ("web_search", "image_search", "academic_search"):
            suggestions = [
                "对搜索结果自动打标",
                "按模态分类",
                "生成摘要报告",
            ]
        elif action == "auto_label":
            suggestions = [
                "查看所有候选标签",
                "调整共识阈值",
                "对低置信度结果人工审核",
            ]
        elif action == "create_project":
            suggestions = [
                "为项目创建初始需求",
                "分配团队成员",
                "配置项目工作流",
            ]
        else:
            suggestions = [
                "查看帮助",
                "查询统计",
                "生成报告",
            ]
        return suggestions

    def get_status(self) -> Dict[str, Any]:
        return {
            "router": self.router.get_metrics(),
            "sessions": self.session_manager.get_metrics(),
            "data_acq": self.data_acq.get_metrics(),
            "pipeline": self.pipeline.get_metrics(),
            "annotation": self.annotation.get_metrics(),
            "review": self.review.get_metrics(),
            "workflow": self.workflow.get_metrics(),
            "project": self.project.get_metrics(),
            "user": self.user.get_metrics(),
            "quality": self.quality.get_metrics(),
            "system": self.system.get_metrics(),
        }
