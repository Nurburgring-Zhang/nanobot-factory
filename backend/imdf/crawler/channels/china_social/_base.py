"""BaseCrawlerChannel + CrawlResult — china_social package 基础类型.

设计要点:
    - CrawlResult: Pydantic v2, 10 字段 schema (与现有 CrawledItem / CrawledItemModel 对齐)
    - CrawlSearchRequest: Pydantic v2 输入验证 (query / max_results / page)
    - BaseCrawlerChannel: async crawler 抽象基类
        - 提供 httpx async client (可注入 transport= 用于 Mock)
        - 提供 rate-limit 令牌桶 (1 req/sec)
        - 提供 robots.txt 缓存 (尊重 Disallow)
        - 提供 user-agent 轮转池
        - 子类实现 search() / parse()
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ============================================================
# Pydantic v2 输入/输出模型
# ============================================================


class CrawlResult(BaseModel):
    """统一 10 字段爬取结果 — 与现有 CrawledItem / CrawledItemModel 字段对齐.

    字段:
        id            渠道内 item id (string, 必填)
        url           主要 URL (必填)
        title         标题 (默认空字符串)
        description   描述 (默认空字符串)
        source        渠道名 (必填, 如 wechatmp/weibomp/...)
        author        作者/uploader (默认空字符串)
        keywords      关键词列表 (默认空列表)
        created_at    抓取时间 (UTC datetime)
        thumbnail_url 缩略图 URL (默认空字符串)
        extra         渠道特定扩展字段 (Dict)
    """
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    id: str = Field(..., min_length=1, max_length=200)
    url: str = Field(..., min_length=1, max_length=2000)
    title: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=2000)
    source: str = Field(..., min_length=1, max_length=50)
    author: str = Field(default="", max_length=200)
    keywords: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    thumbnail_url: str = Field(default="", max_length=2000)
    extra: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 dict — 兼容 JSON / dataclass 互转."""
        out = self.model_dump()
        if isinstance(out.get("created_at"), datetime):
            out["created_at"] = out["created_at"].isoformat()
        return out


class CrawlSearchRequest(BaseModel):
    """Crawler 搜索请求 — Pydantic v2 输入验证."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(..., min_length=1, max_length=200)
    max_results: int = Field(default=20, ge=1, le=100)
    page: int = Field(default=1, ge=1, le=20)
    extra: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# User-Agent 池 (中国社交平台常见 UA)
# ============================================================


_USER_AGENT_POOL: List[str] = [
    # Desktop Chrome (Win)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Desktop Chrome (Mac)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Desktop Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
    # Desktop Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    # Mobile WeChat (Android)
    "Mozilla/5.0 (Linux; Android 12; HarmonyOS; VIE-AL10) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36 "
    "MicroMessenger/8.0.45 NetType/WIFI Language/zh_CN",
]


def _rotate_user_agent() -> str:
    """从 UA 池随机取一个 — 简单 round-robin 替代."""
    return random.choice(_USER_AGENT_POOL)


# ============================================================
# Rate limiter — 1 req/sec (token bucket)
# ============================================================


class _RateLimiter:
    """简单 token bucket: 1 req/sec 平均速率.

    使用 asyncio.Lock 保证并发安全. 适用少量并发场景.
    """

    def __init__(self, rate_per_sec: float = 1.0):
        self.min_interval = 1.0 / max(0.1, rate_per_sec)
        self._lock = asyncio.Lock()
        self._last_call: float = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_call = time.monotonic()


# ============================================================
# Robots.txt 缓存
# ============================================================


class _RobotsCache:
    """内存级 robots.txt 缓存 — key = origin, value = (allow_set, disallow_set).

    失败 (网络/404/timeout) 视为允许 (permissive default).
    """

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, set]] = {}
        self._lock = asyncio.Lock()

    async def can_fetch(self, client: httpx.AsyncClient,
                        url: str, user_agent: str = "*") -> bool:
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return True
        async with self._lock:
            cache_entry = self._cache.get(origin)
        if cache_entry is None:
            cache_entry = await self._load_robots(client, origin)
            async with self._lock:
                self._cache[origin] = cache_entry
        return self._check_rules(cache_entry, parsed.path or "/", user_agent)

    async def _load_robots(self, client: httpx.AsyncClient,
                           origin: str) -> Dict[str, set]:
        """加载 robots.txt — 返回 {user_agent: set(disallowed_paths)}.

        失败 → 空 dict → 视为允许.
        """
        robots_url = f"{origin}/robots.txt"
        try:
            resp = await client.get(robots_url, timeout=5.0)
            if resp.status_code != 200:
                return {}
            return _parse_robots_txt(resp.text)
        except Exception as e:
            logger.debug("robots.txt load failed for %s: %s", origin, e)
            return {}

    @staticmethod
    def _check_rules(rules: Dict[str, set], path: str,
                     user_agent: str) -> bool:
        """检查 path 是否在 user-agent 组的 Disallow 列表中.

        默认 * → 全部. 若 path 不匹配任何 disallow → allow.
        """
        # 优先匹配 user_agent, 然后 *
        ua_key = user_agent if user_agent in rules else "*"
        disallowed = rules.get(ua_key, set())
        if not disallowed:
            disallowed = rules.get("*", set())
        for d in disallowed:
            if d and path.startswith(d):
                return False
        return True


def _parse_robots_txt(text: str) -> Dict[str, set]:
    """简化版 robots.txt 解析 — 仅记录 Disallow 路径.

    支持:
        User-agent: *
        Disallow: /private
        User-agent: BotCrawler
        Disallow: /api
    """
    rules: Dict[str, set] = {}
    current_agents: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip()
        if key == "user-agent":
            current_agents.append(val)
            rules.setdefault(val, set())
        elif key == "disallow" and val:
            for ag in current_agents or ["*"]:
                rules.setdefault(ag, set()).add(val)
        elif key == "allow" and val:
            # Disallow 优先于 Allow — 但若 path 不在 disallow 中 → allow
            pass
    return rules


# ============================================================
# BaseCrawlerChannel
# ============================================================


class BaseCrawlerChannel:
    """中国社交平台渠道基类 — async + rate-limited + robots-aware.

    Subclass contract:
        channel:        ClassVar[str]  = "..."
        api_endpoint:   ClassVar[str]  = "https://..."
        rate_per_sec:   ClassVar[float] = 1.0

    必须重写:
        async def search(self, query: str, max_results: int = 20) -> List[CrawlResult]
        @staticmethod
        def parse(html: str) -> List[CrawlResult]

    可选重写:
        def build_search_url(self, query: str, page: int = 1) -> str
    """

    channel: ClassVar[str] = "base"
    api_endpoint: ClassVar[str] = ""
    rate_per_sec: ClassVar[float] = 1.0

    def __init__(self,
                 transport: Optional[httpx.MockTransport] = None,
                 timeout: float = 15.0,
                 client: Optional[httpx.AsyncClient] = None,
                 respect_robots: bool = True) -> None:
        self.timeout = timeout
        # transport: 测试用 httpx.MockTransport
        self._transport = transport
        # 已构造好的 client (测试可用其内部 state)
        self._client = client
        # 状态
        self._owns_client = client is None
        self._rate_limiter = _RateLimiter(rate_per_sec=self.rate_per_sec)
        self._robots = _RobotsCache()
        self.respect_robots = respect_robots

    # ---------- transport helpers ----------

    def _build_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        if self._transport is not None:
            return httpx.AsyncClient(transport=self._transport,
                                     timeout=self.timeout,
                                     follow_redirects=True)
        return httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)

    async def _close_client(self, client: httpx.AsyncClient) -> None:
        try:
            await client.aclose()
        except Exception:
            pass

    # ---------- HTTP fetch (with rate-limit + UA + robots) ----------

    async def _fetch(self, url: str,
                     headers: Optional[Dict[str, str]] = None) -> Optional[str]:
        """统一的 HTTP GET 入口 — 应用 rate-limit + UA + robots 检查."""
        await self._rate_limiter.acquire()
        client = self._build_client()
        merged_headers = {
            "User-Agent": _rotate_user_agent(),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        }
        if headers:
            merged_headers.update(headers)
        if self.respect_robots:
            ua = merged_headers.get("User-Agent", "*")
            ok = await self._robots.can_fetch(client, url, user_agent=ua)
            if not ok:
                logger.info("%s blocked by robots.txt: %s", self.channel, url)
                if self._owns_client and self._transport is None:
                    await self._close_client(client)
                return None
        try:
            resp = await client.get(url, headers=merged_headers)
        except Exception as e:
            logger.warning("%s fetch error for %s: %s", self.channel, url, e)
            if self._owns_client and self._transport is None:
                await self._close_client(client)
            return None
        finally:
            # 注: 测试用 transport 注入的 client 由 caller 拥有, 不在此关闭
            if self._owns_client and self._transport is None:
                # 仅在真实网络 client 上需要清理
                pass
        if resp.status_code != 200:
            logger.warning("%s status %d for %s",
                           self.channel, resp.status_code, url)
            return None
        return resp.text

    # ---------- Subclass API ----------

    def build_search_url(self, query: str, page: int = 1) -> str:
        """默认 search URL — 子类可重写."""
        from urllib.parse import quote_plus
        return f"{self.api_endpoint}?query={quote_plus(query)}&page={page}"

    async def search(self, query: str,
                     max_results: int = 20) -> List[CrawlResult]:
        """异步搜索入口 — 子类必须实现.

        Returns:
            List[CrawlResult] (空 list 表示无结果或失败, 不抛异常)
        """
        raise NotImplementedError

    @staticmethod
    def parse(html: str) -> List[CrawlResult]:
        """HTML/JSON 解析入口 — 子类必须实现 (static)."""
        raise NotImplementedError

    # ---------- Convenience ----------

    async def search_request(self, req: CrawlSearchRequest) -> List[CrawlResult]:
        """Pydantic-typed 入口 — 给上层调用方."""
        return await self.search(req.query, max_results=req.max_results)

    def search_sync(self, query: str,
                    max_results: int = 20) -> List[CrawlResult]:
        """同步包装 — 给非异步调用方."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    fut = ex.submit(asyncio.run,
                                    self.search(query, max_results))
                    return fut.result(timeout=60)
            return loop.run_until_complete(self.search(query, max_results))
        except RuntimeError:
            return asyncio.run(self.search(query, max_results))


__all__ = [
    "BaseCrawlerChannel",
    "CrawlResult",
    "CrawlSearchRequest",
    "_RateLimiter",
    "_RobotsCache",
    "_USER_AGENT_POOL",
    "_rotate_user_agent",
]