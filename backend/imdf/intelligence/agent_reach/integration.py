"""V5 第32章 — Agent Reach unified internet access layer.

``AgentReachIntegration`` is the single entry point that exposes 14
channels (web/twitter/youtube/bilibili/reddit/xiaohongshu/github/rss/
exa_search/linkedin/instagram/wechat/douyin/zhihu) behind three
operations: ``fetch``, ``search``, ``health_check``.

Features:
    * TTLCache (max_size=5000, default_ttl=300s) — shared across channels.
    * Concurrent fan-out via ``asyncio.gather(return_exceptions=True)``.
    * Channel handler registry — handler class lazy-imported.
    * Pydantic v2 schemas (FetchResult, MultiChannelResult, HealthStatus).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cachetools import TTLCache

from imdf.intelligence.agent_reach.schemas import (
    FetchResult,
    HealthStatus,
    MultiChannelResult,
)

logger = logging.getLogger(__name__)


# ── Channel registry — single source of truth for 14 channels ──────────────
# Each entry: handler_class_path (lazy import), handler_name (display), free (bool)
CHANNELS: Dict[str, Dict[str, Any]] = {
    "web": {
        "handler": "JinaReader",
        "module": "imdf.intelligence.agent_reach.channels.web",
        "free": True,
        "description": "Web page reading via Jina Reader (r.jina.ai)",
    },
    "twitter": {
        "handler": "TwitterAPI",
        "module": "imdf.intelligence.agent_reach.channels.twitter",
        "free": False,
        "description": "Twitter / X API (mock implementation)",
    },
    "youtube": {
        "handler": "YouTubeDL",
        "module": "imdf.intelligence.agent_reach.channels.youtube",
        "free": True,
        "description": "YouTube video + subtitle downloader (mock)",
    },
    "bilibili": {
        "handler": "BilibiliDL",
        "module": "imdf.intelligence.agent_reach.channels.bilibili",
        "free": True,
        "description": "Bilibili B站 video downloader (mock)",
    },
    "reddit": {
        "handler": "RedditAPI",
        "module": "imdf.intelligence.agent_reach.channels.reddit",
        "free": True,
        "description": "Reddit thread fetcher (mock)",
    },
    "xiaohongshu": {
        "handler": "RedFox",
        "module": "imdf.intelligence.agent_reach.channels.xiaohongshu",
        "free": False,
        "description": "小红书 RedFox note fetcher (mock)",
    },
    "github": {
        "handler": "GitHubAPI",
        "module": "imdf.intelligence.agent_reach.channels.github",
        "free": True,
        "description": "GitHub REST API search (real + mock fallback)",
    },
    "rss": {
        "handler": "FeedParser",
        "module": "imdf.intelligence.agent_reach.channels.rss",
        "free": True,
        "description": "RSS / Atom feed parser (mock)",
    },
    "exa_search": {
        "handler": "ExaSearch",
        "module": "imdf.intelligence.agent_reach.channels.exa_search",
        "free": False,
        "description": "Exa semantic search (mock)",
    },
    "linkedin": {
        "handler": "LinkedInMCP",
        "module": "imdf.intelligence.agent_reach.channels.linkedin",
        "free": False,
        "description": "LinkedIn profile MCP (mock)",
    },
    "instagram": {
        "handler": "Instaloader",
        "module": "imdf.intelligence.agent_reach.channels.instagram",
        "free": True,
        "description": "Instagram post loader (mock)",
    },
    "wechat": {
        "handler": "WeChatMCP",
        "module": "imdf.intelligence.agent_reach.channels.wechat",
        "free": False,
        "description": "WeChat 公众号 MCP (mock)",
    },
    "douyin": {
        "handler": "DouyinAPI",
        "module": "imdf.intelligence.agent_reach.channels.douyin",
        "free": False,
        "description": "Douyin 抖音 API (mock)",
    },
    "zhihu": {
        "handler": "ZhihuAPI",
        "module": "imdf.intelligence.agent_reach.channels.zhihu",
        "free": False,
        "description": "Zhihu 知乎 API (mock)",
    },
}

DEFAULT_SEARCH_CHANNELS: List[str] = ["exa_search", "web", "reddit", "twitter"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentReachIntegration:
    """Unified internet access — 14 channels, single API.

    Methods:
        fetch(channel, query, **kwargs)        — single channel fetch
        search(query, channels=None)           — fan-out across channels
        health_check()                         — ping every channel

    Cache:
        TTLCache(max_size=5000, default_ttl=300). Keyed by
        ``(channel, query, frozenset(kwargs.items()))``.
    """

    def __init__(self, *, cache_size: int = 5000, cache_ttl: int = 300):
        self.cache: TTLCache = TTLCache(maxsize=cache_size, ttl=cache_ttl)
        self.health_status: Dict[str, HealthStatus] = {}
        self._handler_cache: Dict[str, Any] = {}

    # ── Public API ───────────────────────────────────────────────────────
    async def fetch(self, channel: str, query: str, **kwargs: Any) -> FetchResult:
        """Fetch ``query`` via the specified ``channel``.

        Steps:
            1. Validate channel → KeyError if unknown
            2. Check cache → return cached FetchResult if hit
            3. Get handler by name → import lazily
            4. Call handler.fetch(query, **kwargs)
            5. Cache result → FetchResult on success
            6. Return; on exception → FetchResult(success=False, error=str(e))
        """
        if channel not in CHANNELS:
            raise KeyError(f"unknown channel: {channel!r}; valid: {sorted(CHANNELS.keys())}")

        cache_key = (channel, query, tuple(sorted(kwargs.items())))
        cached = self.cache.get(cache_key)
        if cached is not None:
            # Return a copy so mutating ``cached`` flag does not corrupt the
            # stored entry or prior references returned to the caller.
            return cached.model_copy(update={"cached": True})

        handler = self._get_handler(channel)
        try:
            result = await handler.fetch(query, **kwargs)
        except Exception as e:  # noqa: BLE001
            logger.exception("fetch(%s, %s) raised", channel, query)
            return FetchResult(
                success=False,
                channel=channel,
                query=query,
                error=f"{type(e).__name__}: {e}",
                metadata={"handler": CHANNELS[channel]["handler"]},
            )

        # Cache only successful results to avoid pinning transient errors
        if result.success:
            self.cache[cache_key] = result
        return result

    async def search(
        self,
        query: str,
        channels: Optional[List[str]] = None,
    ) -> MultiChannelResult:
        """Fan-out ``query`` across multiple channels concurrently.

        Default channels: ``["exa_search", "web", "reddit", "twitter"]``.
        """
        if channels is None:
            channels = list(DEFAULT_SEARCH_CHANNELS)
        else:
            # validate
            for ch in channels:
                if ch not in CHANNELS:
                    raise KeyError(f"unknown channel in search: {ch!r}")
        start = time.time()
        results: Dict[str, FetchResult] = {}

        # fan out — gather with return_exceptions to isolate failures
        tasks = [self.fetch(ch, query) for ch in channels]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        for ch, item in zip(channels, gathered):
            if isinstance(item, Exception):
                results[ch] = FetchResult(
                    success=False,
                    channel=ch,
                    query=query,
                    error=f"{type(item).__name__}: {item}",
                )
            else:
                results[ch] = item

        elapsed_ms = (time.time() - start) * 1000.0
        success_count = sum(1 for r in results.values() if r.success)
        return MultiChannelResult(
            query=query,
            channels=list(channels),
            results=results,
            total=len(channels),
            success_count=success_count,
            error_count=len(channels) - success_count,
            elapsed_ms=elapsed_ms,
        )

    async def health_check(self) -> Dict[str, HealthStatus]:
        """Ping every channel — record healthy/unhealthy/error status."""
        tasks: List[asyncio.Task] = []
        channel_names: List[str] = []
        for ch_name in CHANNELS:
            handler = self._get_handler(ch_name)
            channel_names.append(ch_name)
            tasks.append(asyncio.create_task(self._ping_channel(ch_name, handler)))

        statuses: List[HealthStatus] = await asyncio.gather(*tasks)
        self.health_status = {name: st for name, st in zip(channel_names, statuses)}
        return self.health_status

    # ── Internals ────────────────────────────────────────────────────────
    def _get_handler(self, channel: str):
        """Lazy import + instance-cache the handler class for ``channel``."""
        if channel in self._handler_cache:
            return self._handler_cache[channel]
        cfg = CHANNELS[channel]
        import importlib
        mod = importlib.import_module(cfg["module"])
        cls = getattr(mod, cfg["handler"])
        instance = cls()
        self._handler_cache[channel] = instance
        return instance

    async def _ping_channel(self, channel: str, handler: Any) -> HealthStatus:
        start = time.time()
        try:
            ok = await asyncio.wait_for(handler.ping(), timeout=10.0)
            latency = (time.time() - start) * 1000.0
            return HealthStatus(
                channel=channel,
                healthy=bool(ok),
                status="healthy" if ok else "unhealthy",
                latency_ms=latency,
                checked_at=_now_iso(),
            )
        except Exception as e:  # noqa: BLE001
            latency = (time.time() - start) * 1000.0
            return HealthStatus(
                channel=channel,
                healthy=False,
                status="error",
                latency_ms=latency,
                error=f"{type(e).__name__}: {e}",
                checked_at=_now_iso(),
            )

    # ── Inspection helpers ───────────────────────────────────────────────
    def list_channels(self) -> List[str]:
        return sorted(CHANNELS.keys())

    def is_free(self, channel: str) -> bool:
        return bool(CHANNELS.get(channel, {}).get("free", False))

    def cache_info(self) -> Dict[str, Any]:
        return {
            "size": len(self.cache),
            "max_size": self.cache.maxsize,
            "ttl": self.cache.ttl,
        }


__all__ = [
    "AgentReachIntegration",
    "CHANNELS",
    "DEFAULT_SEARCH_CHANNELS",
]