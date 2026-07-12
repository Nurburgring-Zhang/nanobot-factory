"""智影 V4 — SystemAgent: 系统命令 (help / status / config / greeting)"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..agent_commands.parser import ParsedCommand
from .base import AgentCapability, PlatformAgent

logger = logging.getLogger(__name__)


HELP_TEXT = """智影 V4 — 智能数据采集 & 全 Agent 驱动平台

🕷️ **数据采集**
  "爬取 https://example.com" — 抓取网页
  "深度爬 https://example.com" — BFS/DFS 全站遍历
  "搜索 transformer 论文" — 学术搜索
  "爬 arxiv 关于 diffusion 的最新论文"
  "爬 reddit r/MachineLearning"
  "订阅 https://example.com/feed"

🧹 **数据处理**
  "去重" — 6 级去重 (URL/SHA/SimHash/...)
  "清洗" — 内容清洗
  "脱敏" — 去除 PII
  "分类" — 8 业务模态分类

🏷️ **打标/评分**
  "自动打标" — 多模型投票
  "评质量分" — 质量评分
  "评美学分" — MUSIQ/LAION 美学

📊 **项目管理**
  "创建项目 名称 xxx"
  "创建需求 标题 xxx"
  "分配任务 task-1 给 alice"
  "查询统计 按模态"
  "生成报告 上周"

⚙️ **系统**
  "帮助" / "help" — 本帮助
  "状态" / "status" — 系统状态
  "配置 key value" — 设置配置

💡 **示例对话**
  我: 爬取 https://arxiv.org/list/cs.AI/recent
  智影: 已通过 academic_arxiv 渠道采集 50 条数据...
  我: 对结果自动打标
  智影: 已打标,共识阈值 2,共生成 12 个标签...
  我: 按 quality > 0.7 过滤
  智影: 过滤完成,保留 23 条...
"""


class SystemAgent(PlatformAgent):
    """系统 Agent — help / status / config / greeting"""

    def __init__(self, orchestrator_status_fn=None):
        super().__init__(
            name="SystemAgent",
            description="系统 Agent: 帮助 / 状态 / 配置 / 闲聊",
            capabilities=[AgentCapability.SYSTEM],
        )
        # 可选回调 — 让 SystemAgent 调 orchestrator.get_status
        self._status_fn = orchestrator_status_fn

    def set_status_fn(self, fn):
        self._status_fn = fn

    def handle(self, cmd: ParsedCommand) -> Any:
        action = cmd.action
        if action == "help":
            return self.help(cmd)
        if action == "status":
            return self.status(cmd)
        if action == "config":
            return self.config(cmd)
        if action == "greeting":
            return self.greeting(cmd)
        if action == "thanks":
            return self.thanks(cmd)
        if action == "unknown":
            return self.unknown(cmd)
        return {"error": f"unknown action: {action}"}

    def help(self, cmd: ParsedCommand) -> Dict[str, Any]:
        topic = cmd.get("topic", "general")
        self._record("help")
        return {
            "success": True,
            "action": "help",
            "topic": topic,
            "text": HELP_TEXT,
        }

    def status(self, cmd: ParsedCommand) -> Dict[str, Any]:
        component = cmd.get("component", "all")
        self._record("status")
        if self._status_fn:
            full = self._status_fn()
        else:
            full = {"note": "no status fn registered"}
        return {
            "success": True,
            "action": "status",
            "component": component,
            "status": full,
        }

    def config(self, cmd: ParsedCommand) -> Dict[str, Any]:
        key = cmd.get("key", "")
        value = cmd.get("value", "")
        if not key:
            self._record("config", False)
            return {"error": "missing key", "action": "config"}
        self._record("config")
        return {
            "success": True,
            "action": "config",
            "key": key,
            "value": value,
            "message": f"已设置 {key} = {value}",
        }

    def greeting(self, cmd: ParsedCommand) -> Dict[str, Any]:
        self._record("greeting")
        return {
            "success": True,
            "action": "greeting",
            "message": "你好!我是智影 V4 智能数据助手。可以帮你爬取数据、自动打标、评分、分类、存储,以及管理项目和任务。\n试试说: '爬取 https://arxiv.org/list/cs.AI/recent' 或 '帮帮我'。",
            "suggestions": [
                "爬取 arxiv 关于 diffusion 的最新论文",
                "搜索 reddit r/MachineLearning 热门",
                "创建项目 名称 ai_research",
                "查看帮助",
            ],
        }

    def thanks(self, cmd: ParsedCommand) -> Dict[str, Any]:
        self._record("thanks")
        return {
            "success": True,
            "action": "thanks",
            "message": "不客气!有需要随时叫我。",
        }

    def unknown(self, cmd: ParsedCommand) -> Dict[str, Any]:
        self._record("unknown")
        return {
            "success": True,
            "action": "unknown",
            "message": f"我不太理解 '{cmd.raw_text}'。试试说 '帮帮我' 查看我能做什么。",
            "suggestions": ["查看帮助", "爬取 arxiv 论文", "创建项目"],
        }
