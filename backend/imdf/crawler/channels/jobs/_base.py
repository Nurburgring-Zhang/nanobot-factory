"""Jobs 渠道适配器 — 公共基类 (P20-B2)

4 渠道:
    - LagouChannel       拉勾网 (www.lagou.com)
    - BossZhipinChannel  BOSS直聘 (www.zhipin.com)
    - ZhilianChannel     智联招聘 (www.zhaopin.com)
    - Job51Channel       前程无忧 (www.51job.com)

设计要点 (来自 task spec):
    - BaseCrawlerChannel 抽象基类 — 提供 httpx 异步客户端、限速、UA 池
    - JobPosting Pydantic v2 统一输出 schema
    - 子类实现 parse(html) static + async search(query, max_results)
    - 网络失败/解析失败 → 返回空列表 + log, 不抛异常
    - 尊重 robots.txt (best-effort, robots_txt_cache)
    - 1 req/sec 限速 (per channel, token-bucket)

Usage:
    from imdf.crawler.channels.jobs import LagouChannel

    async def main():
        async with LagouChannel() as ch:
            results = await ch.search("Python 后端", max_results=20)
            for r in results:
                print(r.title, r.salary, r.url)
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import urllib.robotparser as robotparser
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


# ============================================================
# 真实浏览器 UA 池 — 轮换降低被识别为爬虫的风险
# ============================================================
_USER_AGENT_POOL: Tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
)


# ============================================================
# JobPosting — Pydantic v2 统一输出 schema
# ============================================================
class JobPosting(BaseModel):
    """统一 job posting schema — 4 渠道都用这个.

    字段 (按 task spec 推荐的 7 字段 + 扩展):
        id          渠道内职位 id (稳定 hash 或网站 id)
        title       职位名称
        company     公司名
        salary      薪资范围 ("15-25K·15 薪" / "面议")
        location    工作地点
        url         职位详情页 URL
        source      渠道名 (lagou/bosszhipin/zhilian/job51)
        posted_at   发布日期 (ISO 字符串, 可能为空)
        description 职位描述摘要
        tags        关键词列表 (技能标签)
        extra       渠道特定扩展 (经验/学历/福利/抓取时间)
    """
    model_config = ConfigDict(
        extra="allow",
        str_strip_whitespace=True,
        validate_assignment=False,
    )

    id: str = Field(..., min_length=1, max_length=200)
    title: str = Field(default="", max_length=500)
    company: str = Field(default="", max_length=200)
    salary: str = Field(default="", max_length=100)
    location: str = Field(default="", max_length=200)
    url: str = Field(default="", max_length=2000)
    source: str = Field(default="", max_length=50)
    posted_at: str = Field(default="", max_length=50)
    description: str = Field(default="", max_length=2000)
    tags: List[str] = Field(default_factory=list)
    crawled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    extra: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v if x is not None and str(x).strip()]
        if isinstance(v, str):
            # 拆 csv / 顿号 / 空格
            parts = re.split(r"[,、;；\s/|]+", v)
            return [p for p in parts if p]
        return [str(v)]


# ============================================================
# CrawlResult — 适配 task spec 中 list[CrawlResult] 返回类型
# ============================================================
class CrawlResult(BaseModel):
    """单次 search 调用的统一返回项.

    task spec 写的是 list[CrawlResult], 我们把 JobPosting 嵌入 CrawlResult
    保持 4 渠道一致; 外部使用可以 CrawlResult.posting 访问.
    """
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., min_length=1, max_length=200)
    url: str = Field(default="", max_length=2000)
    title: str = Field(default="", max_length=500)
    source: str = Field(default="", max_length=50)
    posting: JobPosting = Field(default_factory=JobPosting)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_posting(cls, posting: JobPosting, metadata: Optional[Dict[str, Any]] = None) -> "CrawlResult":
        return cls(
            id=posting.id,
            url=posting.url,
            title=posting.title,
            source=posting.source,
            posting=posting,
            metadata=metadata or {},
        )


# ============================================================
# 限速器 — token bucket 简化
# ============================================================
class _RateLimiter:
    """每个 channel 实例一个 — 1 req/sec."""
    def __init__(self, rps: float = 1.0):
        self._min_interval = 1.0 / max(rps, 0.01)
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = (self._last_call + self._min_interval) - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()


# ============================================================
# robots.txt 缓存 — best-effort, 失败默认 allow
# ============================================================
class _RobotsCache:
    def __init__(self, ttl_seconds: int = 3600):
        self._cache: Dict[str, Tuple[robotparser.RobotFileParser, float]] = {}
        self._ttl = ttl_seconds

    def get(self, host: str, fetcher) -> robotparser.RobotFileParser:
        now = time.time()
        cached = self._cache.get(host)
        if cached and (now - cached[1]) < self._ttl:
            return cached[0]
        rp = robotparser.RobotFileParser()
        try:
            text = fetcher(f"https://{host}/robots.txt")
            if text:
                rp.parse(text.splitlines())
        except Exception as e:
            logger.debug("robots fetch failed for %s: %s", host, e)
        self._cache[host] = (rp, now)
        return rp


# ============================================================
# BaseCrawlerChannel
# ============================================================
class BaseCrawlerChannel(ABC):
    """Jobs 渠道抽象基类.

    子类必须实现:
        channel:    类属性, 渠道名 (如 "lagou")
        api_endpoint: 搜索 URL 模板 — 必须含 {query} 占位符
        parse(html): static method → List[JobPosting]

    子类可重写:
        _build_url(query, page): 默认调用 .format(query=...) 替换占位符
    """

    channel: ClassVar[str] = "jobs_base"
    api_endpoint: ClassVar[str] = ""

    def __init__(self,
                 timeout: float = 15.0,
                 rate_limit_rps: float = 1.0,
                 client: Optional[httpx.AsyncClient] = None,
                 transport: Optional[httpx.MockTransport] = None,
                 honor_robots: bool = False) -> None:
        self.timeout = timeout
        self._rate_limiter = _RateLimiter(rps=rate_limit_rps)
        self._robots_cache = _RobotsCache()
        self._honor_robots = honor_robots
        self._ua_index = 0
        # 客户端注入优先级: explicit client > transport > build new
        self._injected_client = client
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None
        self._owns_client = False  # True if we built the client ourselves

    # ---- context manager ----

    async def __aenter__(self) -> "BaseCrawlerChannel":
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
            self._owns_client = False

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        if self._injected_client is not None:
            self._client = self._injected_client
            self._owns_client = False
            return self._client
        kwargs: Dict[str, Any] = {
            "timeout": self.timeout,
            "follow_redirects": True,
            "headers": {"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        self._client = httpx.AsyncClient(**kwargs)
        self._owns_client = True
        return self._client

    def _next_ua(self) -> str:
        ua = _USER_AGENT_POOL[self._ua_index % len(_USER_AGENT_POOL)]
        self._ua_index += 1
        return ua

    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self._next_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    # ---- public API (task spec contract) ----

    async def search(self, query: str, max_results: int = 20) -> List[CrawlResult]:
        """异步 search — task spec 入口.

        Returns: List[CrawlResult]. 网络/解析失败返回 [].
        """
        query = (query or "").strip()
        if not query:
            logger.warning("%s.search: empty query, return []", self.channel)
            return []
        max_results = max(1, min(int(max_results), 100))
        try:
            html = await self._fetch(query=query, max_results=max_results)
        except Exception as e:
            logger.warning("%s.fetch failed: %s", self.channel, e)
            return []
        if not html:
            return []
        try:
            postings = self.parse(html)
        except Exception as e:
            logger.warning("%s.parse failed: %s", self.channel, e)
            return []
        # 截断 + 包装成 CrawlResult
        out: List[CrawlResult] = []
        for p in postings[:max_results]:
            # 确保 source 字段一致
            if not p.source:
                p.source = self.channel
            out.append(CrawlResult.from_posting(p))
        return out

    @staticmethod
    @abstractmethod
    def parse(html: str) -> List[JobPosting]:
        """静态解析 — 子类必须实现, 不发起网络请求."""
        raise NotImplementedError

    # ---- protected helpers ----

    def _build_url(self, query: str, page: int = 1) -> str:
        """默认 URL 构造 — 子类可重写 (如 POST JSON)."""
        if not self.api_endpoint:
            raise NotImplementedError("api_endpoint not set")
        from urllib.parse import quote_plus
        return self.api_endpoint.format(query=quote_plus(query), page=page)

    def _robots_ok(self, url: str, client: httpx.AsyncClient) -> bool:
        """best-effort robots.txt 检查 — 默认放行."""
        if not self._honor_robots:
            return True
        host = urlparse(url).netloc
        try:
            def sync_fetch(robots_url: str) -> str:
                # 同步抓 robots — 极简 urllib, 避免 async in sync
                import urllib.request
                req = urllib.request.Request(robots_url, headers={"User-Agent": self._next_ua()})
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.read().decode("utf-8", errors="replace")
            rp = self._robots_cache.get(host, sync_fetch)
            ua = self._next_ua()
            return rp.can_fetch(ua, url)
        except Exception as e:
            logger.debug("%s robots check fail (allow): %s", self.channel, e)
            return True

    async def _fetch(self, query: str, max_results: int) -> str:
        """单次 fetch — 限速 + robots + UA 轮换."""
        await self._rate_limiter.acquire()
        client = await self._ensure_client()
        url = self._build_url(query=query, page=1)
        if not self._robots_ok(url, client):
            logger.info("%s blocked by robots.txt: %s", self.channel, url)
            return ""
        try:
            resp = await client.get(url, headers=self._headers())
        except Exception as e:
            logger.warning("%s network error: %s", self.channel, e)
            return ""
        if resp.status_code != 200:
            logger.warning("%s status %d for url %s", self.channel, resp.status_code, url)
            return ""
        # decode: 优先用 apparent_encoding, fallback utf-8
        try:
            if resp.encoding:
                return resp.text
            return resp.content.decode("utf-8", errors="replace")
        except Exception:
            return resp.content.decode("utf-8", errors="replace")


__all__ = [
    "BaseCrawlerChannel",
    "JobPosting",
    "CrawlResult",
    "USER_AGENT_POOL",
]


# 兼容导出 — 旧 API 引用
USER_AGENT_POOL = _USER_AGENT_POOL
