"""RSS / news crawler channels (P20-F RSS)

5 个公开 RSS / news 搜索渠道适配器:
    - rsshub     : RSSHub (rsshub.app)   — 路由式 RSS 聚合
    - feedly     : Feedly (cloud.feedly.com) — RSS 阅读器公开搜索
    - newsapi    : NewsAPI (newsapi.org) — 新闻聚合 (公开网页搜索)
    - reddit     : Reddit (old.reddit.com) — 公开 .json 搜索端点
    - digg       : Digg (digg.com)        — 新闻聚合

P20-F 规范要点:
    - 类名后缀 Channel (例如 RsshubChannel) — 与既有 ChannelCrawler 系列保持一致
    - 基类 BaseCrawlerChannel 提供统一 httpx async 客户端 + 1 RPS 限速
    - 实现 async search(query, max_results) -> list[CrawledItemModel]
    - 实现 staticmethod parse(html/feed) -> list[CrawledItemModel]
    - 公开接口无 API key (走公开搜索端点 / HTML 抓取)
    - 网络错误一律返回空 list + log.warning, 不抛

Registry 用法:
    from imdf.crawler.channels.rss import REGISTRY
    RsshubChannel = REGISTRY["rsshub"]
    cw = RsshubChannel()
    items = await cw.search("machine learning", max_results=10)
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional, Type

import httpx

from .._schemas import CrawledItemModel
from ...config import USER_AGENT_POOL, CrawlerConfig, RobotsPolicy

logger = logging.getLogger(__name__)


# 内置 UA 池 — 与 config.USER_AGENT_POOL 一致, 子类随机取
_DEFAULT_UA_POOL: List[str] = list(USER_AGENT_POOL)


class BaseCrawlerChannel(ABC):
    """RSS 渠道适配器基类.

    与父级 ChannelCrawler 共享设计原则 (统一的 10 字段 CrawledItemModel 输出),
    但 RSS 渠道:
        - 公开搜索为主, 不需要 API key
        - 网络限速默认 1.0 RPS (与 task spec 对齐)
        - 走 httpx.AsyncClient (而不是默认 urllib)
        - 提供 staticmethod parse() 给纯解析路径 (无网络)
    """

    channel: ClassVar[str] = "rss_base"

    # 子类可重写 — 公开搜索端点模板
    api_endpoint: ClassVar[str] = ""

    # 每个渠道独立 1 RPS 限速 (task spec 要求)
    rate_limit_seconds: ClassVar[float] = 1.0

    # 默认超时
    timeout_seconds: ClassVar[float] = 15.0

    def __init__(self,
                 config: Optional[CrawlerConfig] = None,
                 ua_pool: Optional[List[str]] = None,
                 rate_limit_seconds: Optional[float] = None,
                 client: Optional[httpx.AsyncClient] = None) -> None:
        self.config = config or CrawlerConfig(
            name=self.channel, channel=self.channel,
            rate_limit=self._rate_limit_cfg(),
        )
        self.config.robots_policy = RobotsPolicy.WARN  # 公开 RSS 默认 warn
        self._ua_pool = ua_pool or list(_DEFAULT_UA_POOL)
        self.rate_limit_seconds = (
            rate_limit_seconds if rate_limit_seconds is not None
            else self.rate_limit_seconds
        )
        self._client = client
        self._owns_client = client is None
        # 限速用 — 单 channel 实例内部按 wall-clock 间隔调用
        self._lock = asyncio.Lock()
        self._last_call_ts: float = 0.0

    @staticmethod
    def _rate_limit_cfg():  # 工厂方法 — 避免 mutable default
        from ...config import RateLimitConfig
        return RateLimitConfig(rps=1.0, jitter_seconds=0.1)

    def _pick_ua(self) -> str:
        import random
        return random.choice(self._ua_pool) if self._ua_pool else (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": self._pick_ua()},
            )
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "BaseCrawlerChannel":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def _throttle(self) -> None:
        """1 RPS 限速 — 内部调用间隔 ≥ rate_limit_seconds."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait = self.rate_limit_seconds - (now - self._last_call_ts)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call_ts = asyncio.get_event_loop().time()

    async def _fetch(self, url: str, headers: Optional[Dict[str, str]] = None) -> str:
        """统一 fetch — 应用限速 + UA + 错误返回空串."""
        await self._throttle()
        merged_headers = {"User-Agent": self._pick_ua(), "Accept": "*/*"}
        if headers:
            merged_headers.update(headers)
        try:
            client = await self._get_client()
            resp = await client.get(url, headers=merged_headers)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPStatusError as e:
            logger.warning("%s HTTP %d for %s",
                           self.channel, e.response.status_code, url)
            return ""
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s network error for %s: %s",
                           self.channel, url, e)
            return ""
        except Exception as e:
            logger.warning("%s unexpected error for %s: %s",
                           self.channel, url, e)
            return ""

    # ----- 子类实现 -----

    @abstractmethod
    async def search(self, query: str,
                     max_results: int = 20) -> List[CrawledItemModel]:
        """异步搜索 — 调 _fetch + parse, 返回统一 10 字段 Pydantic v2 模型."""
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def parse(raw: str) -> List[CrawledItemModel]:
        """纯解析 — 给静态 HTML/JSON/RSS payload → list[CrawledItemModel]."""
        raise NotImplementedError

    # ----- 工具 -----

    def _build_item(self, *,
                    id: str,
                    url: str,
                    title: str,
                    description: str,
                    source: str,
                    author: str = "",
                    keywords: Optional[List[str]] = None,
                    thumbnail_url: str = "",
                    created_at: Optional[datetime] = None,
                    extra: Optional[Dict[str, Any]] = None) -> CrawledItemModel:
        return CrawledItemModel(
            id=id,
            url=url,
            title=title[:500],
            description=description[:2000],
            source=source,
            author=author[:200],
            keywords=keywords or [],
            created_at=created_at or datetime.utcnow(),
            thumbnail_url=thumbnail_url[:2000],
            extra=extra or {},
        )


# ============================================================
# Registry — P20-F RSS channels (rsshub + newsapi + reddit)
# ============================================================
REGISTRY: Dict[str, Type[BaseCrawlerChannel]] = {}

# 延迟 import — 避免循环依赖
def _register_all() -> None:
    from .rsshub import RsshubChannel
    from .newsapi import NewsApiChannel
    from .reddit import RedditChannel

    for cls in (RsshubChannel, NewsApiChannel, RedditChannel):
        REGISTRY[cls.channel] = cls
    # 同时把 channel classes 暴露到模块命名空间, 允许
    # `from imdf.crawler.channels.rss import RsshubChannel` 直接导入
    globals()["RsshubChannel"] = RsshubChannel
    globals()["NewsApiChannel"] = NewsApiChannel
    globals()["RedditChannel"] = RedditChannel


_register_all()


__all__ = [
    "BaseCrawlerChannel",
    "REGISTRY",
]