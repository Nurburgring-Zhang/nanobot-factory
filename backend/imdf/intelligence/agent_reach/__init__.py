"""V5 第32章 — Agent Reach 互联网能力.

Unified internet access layer covering 14 channels so any Agent can fetch/search
web sources through a single ``AgentReachIntegration`` entry point.

Channels:
    web, twitter, youtube, bilibili, reddit, xiaohongshu, github,
    rss, exa_search, linkedin, instagram, wechat, douyin, zhihu
"""
from __future__ import annotations

from imdf.intelligence.agent_reach.schemas import (
    FetchResult,
    MultiChannelResult,
    HealthStatus,
)
from imdf.intelligence.agent_reach.integration import AgentReachIntegration

__all__ = [
    "FetchResult",
    "MultiChannelResult",
    "HealthStatus",
    "AgentReachIntegration",
]