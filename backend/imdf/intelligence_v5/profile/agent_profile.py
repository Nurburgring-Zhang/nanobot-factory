"""智影 V5 — Agent Profile 模板 (Hermes setup --portal)"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class AgentProfileTemplate:
    """Agent 启动配置模板 — Hermes 风格"""

    name: str
    description: str = ""
    role: str = "default"  # planner / executor / critic / etc.
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: str = ""
    tools: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    mcp_servers: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    rate_limit: int = 100  # per hour
    budget_per_day_usd: float = 10.0


# 预置模板 — Hermes setup --portal 默认 + 智影 V5 扩展
AGENT_PROFILE_TEMPLATES: Dict[str, AgentProfileTemplate] = {
    "default": AgentProfileTemplate(
        name="default",
        description="Hermes 默认 Agent profile",
        role="executor",
        model="gpt-4",
        temperature=0.7,
    ),
    "planner": AgentProfileTemplate(
        name="planner",
        description="Full Harness Planner — 拆解需求为 Sprint 计划",
        role="planner",
        model="claude-opus-4",
        temperature=0.3,
        max_tokens=8192,
        skills=["planner"],
    ),
    "generator": AgentProfileTemplate(
        name="generator",
        description="Full Harness Generator — 按计划实现",
        role="generator",
        model="gpt-4",
        temperature=0.5,
        max_tokens=8192,
        skills=["code", "writing"],
    ),
    "evaluator": AgentProfileTemplate(
        name="evaluator",
        description="Full Harness Evaluator — 真实评估产出",
        role="evaluator",
        model="claude-opus-4",
        temperature=0.2,
        skills=["code-review", "qa"],
    ),
    "researcher": AgentProfileTemplate(
        name="researcher",
        description="研究员 — 广度调研 + 深度分析",
        role="researcher",
        model="claude-opus-4",
        temperature=0.5,
        skills=["web-search", "web-crawl", "academic-crawl"],
    ),
    "data_analyst": AgentProfileTemplate(
        name="data_analyst",
        description="数据分析师 — SQL + Python + 可视化",
        role="executor",
        model="gpt-4",
        temperature=0.3,
        skills=["sql", "python", "visualization"],
    ),
    "creative_director": AgentProfileTemplate(
        name="creative_director",
        description="创意总监 — 短剧/广告/视频脚本",
        role="creative",
        model="claude-opus-4",
        temperature=0.9,
        skills=["video-harness", "brand-research"],
    ),
    "moderator": AgentProfileTemplate(
        name="moderator",
        description="圆桌会议 Moderator — 主持多 Agent 讨论",
        role="moderator",
        model="claude-opus-4",
        temperature=0.4,
        skills=["roundtable", "decision"],
    ),
}
