"""BaseCrawler — 抽象基类 (P19-B3 §2)

所有具体 crawler (WebCrawler / APICrawler / RSSCrawler / channels.*) 继承此基类。

标准 crawl 流程 (8 步):
    1. 构造请求参数 (URL / headers / body)
    2. 合规检查 (robots.txt + 自定义 allowlist / blocklist)
    3. 应用 UA 池 + Proxy 池
    4. 鉴权 (Bearer / API Key / OAuth2)
    5. 限速 (token bucket 简化)
    6. 实际 fetch (子类实现 _do_fetch)
    7. 解析 / 提取 (子类实现 _parse)
    8. 记录 metrics + audit chain + history

线程安全:
    - metrics 用 threading.Lock 保护
    - semaphore 控制并发
    - 子类 fetch 不应阻塞主线程
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
import urllib.robotparser as robotparser
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .config import CrawlerConfig, RobotsPolicy, USER_AGENT_POOL

logger = logging.getLogger(__name__)


class CrawlStatus(str, Enum):
    """单条 fetch 的最终状态"""
    SUCCESS = "success"
    BLOCKED = "blocked"            # robots.txt disallowed
    FETCH_ERROR = "fetch_error"
    PARSE_ERROR = "parse_error"
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"
    TIMEOUT = "timeout"
    ROBOTS_DENIED = "robots_denied"
    PROXY_ERROR = "proxy_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class CrawlMetrics:
    """metrics 累加器 — 线程安全"""
    fetched: int = 0       # 实际发出请求数
    success: int = 0       # 成功返回 (status=SUCCESS)
    errors: int = 0        # 任何错误
    blocked: int = 0       # 被 robots / allowlist 拦下
    bytes_downloaded: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    by_status: Dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def incr(self, status: CrawlStatus, bytes_: int = 0) -> None:
        with self._lock:
            self.fetched += 1
            if status == CrawlStatus.SUCCESS:
                self.success += 1
            elif status == CrawlStatus.BLOCKED or status == CrawlStatus.ROBOTS_DENIED:
                self.blocked += 1
            else:
                self.errors += 1
            self.bytes_downloaded += bytes_
            key = status.value
            self.by_status[key] = self.by_status.get(key, 0) + 1

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "fetched": self.fetched,
                "success": self.success,
                "errors": self.errors,
                "blocked": self.blocked,
                "bytes_downloaded": self.bytes_downloaded,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "by_status": dict(self.by_status),
            }


@dataclass
class CrawlResult:
    """单次 fetch 的最终产物 — 通用结构"""
    url: str
    status: CrawlStatus
    status_code: int = 0
    items: List[Dict[str, Any]] = field(default_factory=list)
    raw: Optional[Any] = None  # 原始 bytes / dict / feed
    elapsed_seconds: float = 0.0
    bytes_downloaded: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == CrawlStatus.SUCCESS

    @property
    def count(self) -> int:
        return len(self.items)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "status": self.status.value,
            "status_code": self.status_code,
            "items_count": self.count,
            "elapsed_seconds": self.elapsed_seconds,
            "bytes_downloaded": self.bytes_downloaded,
            "error": self.error,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------
# CrawledItem — 5 渠道统一 10 字段 schema (P19-C1-fix P0 #2)
# ---------------------------------------------------------------
@dataclass
class CrawledItem:
    """统一 10 字段 — 所有 5 渠道的 _build_item() 返回此类型.

    字段:
        id            渠道内 item id (string)
        url           主要图片/资源 URL (必填)
        title         标题 (可选, 空字符串代替 None)
        description   描述 (可选, 空字符串代替 None)
        source        渠道名 (google_images/open_images/flickr/unsplash/pixabay)
        author        作者/uploader (可选)
        keywords      关键词列表 (空列表代替 None)
        created_at    抓取时间 (UTC datetime)
        thumbnail_url 缩略图 URL (可选)
        extra         渠道特定扩展字段 (Dict, license/width/height/mock 等)
    """
    id: str
    url: str
    title: str = ""
    description: str = ""
    source: str = ""
    author: str = ""
    keywords: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    thumbnail_url: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    # 标准 10 字段名 — 给测试 + 序列化参考
    SCHEMA_FIELDS = (
        "id", "url", "title", "description", "source",
        "author", "keywords", "created_at", "thumbnail_url", "extra",
    )

    # 这些字段会被同时写入顶层 + extra — 兼容老测试直接访问 item["mock"] 等
    TOP_LEVEL_COMPAT_KEYS = ("mock", "license", "width", "height", "tags")

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 dict — 与 CrawlResult.items 类型契约兼容

        - 保留全部 10 字段
        - 同时把 extra 中常用字段 (mock/license/width/height/tags) 提升到顶层
          以保持向后兼容 (旧测试通过 item["mock"] 直接访问)
        """
        out: Dict[str, Any] = {}
        for f in self.SCHEMA_FIELDS:
            v = getattr(self, f)
            if isinstance(v, datetime):
                out[f] = v.isoformat()
            else:
                out[f] = v
        # 兼容性: 把 extra 中的常见字段提升到顶层
        for k in self.TOP_LEVEL_COMPAT_KEYS:
            if k in out["extra"] and k not in out:
                out[k] = out["extra"][k]
        return out


# ---------------------------------------------------------------
# robots.txt 缓存 — 线程安全
# ---------------------------------------------------------------
class _RobotsCache:
    def __init__(self, ttl_seconds: int = 3600):
        self._cache: Dict[str, Tuple[robotparser.RobotFileParser, float]] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def get(self, url: str, fetcher: Callable[[str], str]) -> robotparser.RobotFileParser:
        """获取 url 对应 host 的 robots.txt (缓存 1h)"""
        host = urlparse(url).netloc
        now = time.time()
        with self._lock:
            cached = self._cache.get(host)
            if cached and (now - cached[1]) < self._ttl:
                return cached[0]
        # 缓存 miss — 拉取
        robots_url = f"{urlparse(url).scheme}://{host}/robots.txt"
        rp = robotparser.RobotFileParser()
        try:
            content = fetcher(robots_url)
            rp.parse(content.splitlines())
        except Exception as e:
            logger.debug("robots.txt fetch failed for %s: %s", host, e)
            rp = robotparser.RobotFileParser()  # empty, allow all
        with self._lock:
            self._cache[host] = (rp, now)
        return rp


# ---------------------------------------------------------------
# 限速器 — token bucket 简化 (sleep + jitter)
# ---------------------------------------------------------------
class RateLimiter:
    """简易 token bucket — 每次调用 acquire() 等到下一可用 token."""
    def __init__(self, rps: float = 1.0, jitter_seconds: float = 0.0):
        self._min_interval = 1.0 / max(rps, 0.01)
        self._jitter = max(jitter_seconds, 0.0)
        self._last_call = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """返回等待秒数 (已经过 0)."""
        with self._lock:
            now = time.time()
            wait = (self._last_call + self._min_interval) - now
            if wait < 0:
                wait = 0
            self._last_call = now + wait
        if self._jitter > 0:
            import random
            wait += random.uniform(0, self._jitter)
        if wait > 0:
            time.sleep(wait)
        return wait


# ---------------------------------------------------------------
# BaseCrawler
# ---------------------------------------------------------------
class BaseCrawler(ABC):
    """抽象爬虫基类 — 所有具体 crawler 继承此."""

    channel: str = "base"

    def __init__(self, config: Optional[CrawlerConfig] = None,
                 http_fetcher: Optional[Callable[[str, Dict[str, str], float], bytes]] = None):
        self.config = config or CrawlerConfig(name="base", channel="base")
        if not self.config.user_agent_pool:
            self.config.user_agent_pool = list(USER_AGENT_POOL)
        self.metrics = CrawlMetrics()
        self._robots_cache = _RobotsCache()
        self._rate_limiter = RateLimiter(
            rps=self.config.rate_limit.rps,
            jitter_seconds=self.config.rate_limit.jitter_seconds,
        )
        self._sem = threading.Semaphore(self.config.max_concurrent)
        # 注入 HTTP fetcher (供测试 mock), 默认用 urllib
        self._http_fetcher = http_fetcher or self._default_http_fetcher
        # audit chain 集成 (lazy import, 避免硬依赖)
        self._audit_chain = None
        # 简单 robots fetch 钩子 (供 mock)

    # ============== Public API ==============

    def crawl(self, target: Any, **kwargs: Any) -> CrawlResult:
        """对外统一入口 — 单个 target."""
        self.metrics.started_at = datetime.now().isoformat()
        try:
            # 1. 准备请求
            prep = self._prepare(target, **kwargs)
            if prep is None:
                self.metrics.incr(CrawlStatus.UNKNOWN_ERROR)
                return CrawlResult(
                    url=str(target), status=CrawlStatus.UNKNOWN_ERROR,
                    error="_prepare returned None",
                )

            url = prep["url"]
            headers = prep.get("headers", {})
            # 2. 合规检查 (robots + 自定义)
            allowed, block_reason = self._check_compliance(url)
            if not allowed:
                self.metrics.incr(CrawlStatus.BLOCKED)
                return CrawlResult(
                    url=url, status=CrawlStatus.BLOCKED,
                    error=block_reason,
                )
            # 3. 应用 UA + auth headers
            headers.setdefault("User-Agent", self.config.get_user_agent())
            auth_headers = self.config.auth.get_headers()
            for k, v in auth_headers.items():
                headers.setdefault(k, v)
            # 4. 限速 (sleep 一下)
            self._rate_limiter.acquire()
            # 5. 实际 fetch — 传 url 作为单独参数, prep 中其他键
            t0 = time.time()
            try:
                # 提取 prep 中非 url / headers 的键, 避免与位置参数 url/headers 冲突
                prep_extras = {k: v for k, v in prep.items() if k not in ("url", "headers")}
                raw, status_code, fetch_error = self._do_fetch(url, headers, **prep_extras)
            except Exception as e:
                raw, status_code, fetch_error = None, 0, str(e)
            elapsed = time.time() - t0
            # 6. 解析
            if fetch_error or raw is None:
                status = self._classify_error(fetch_error or "no response")
                self.metrics.incr(status)
                result = CrawlResult(
                    url=url, status=status, status_code=status_code,
                    error=fetch_error, elapsed_seconds=elapsed,
                )
            else:
                try:
                    items, metadata = self._parse(raw, prep)
                    self.metrics.incr(CrawlStatus.SUCCESS, bytes_=len(raw) if isinstance(raw, (bytes, str)) else 0)
                    result = CrawlResult(
                        url=url, status=CrawlStatus.SUCCESS,
                        status_code=status_code, items=items, raw=raw,
                        elapsed_seconds=elapsed,
                        bytes_downloaded=len(raw) if isinstance(raw, (bytes, str)) else 0,
                        metadata=metadata,
                    )
                except Exception as e:
                    self.metrics.incr(CrawlStatus.PARSE_ERROR)
                    result = CrawlResult(
                        url=url, status=CrawlStatus.PARSE_ERROR,
                        status_code=status_code, error=f"parse: {e}",
                        raw=raw, elapsed_seconds=elapsed,
                    )
            # 7. audit chain 记录 (best-effort, 失败不抛)
            self._audit(result)
            # 8. history 记录
            return result
        finally:
            self.metrics.finished_at = datetime.now().isoformat()

    def crawl_many(self, targets: List[Any], **kwargs: Any) -> List[CrawlResult]:
        """批量 — 顺序执行 (并发版本由 CrawlerEngine 提供)"""
        results = []
        for t in targets:
            results.append(self.crawl(t, **kwargs))
        return results

    # ============== 模板方法 — 子类实现 ==============

    @abstractmethod
    def _prepare(self, target: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """构造 fetch 参数 — url / headers / body 等.
        返回 None 表示准备失败."""
        raise NotImplementedError

    @abstractmethod
    def _do_fetch(self, url: str, headers: Dict[str, str], **prep: Any) -> Tuple[Any, int, Optional[str]]:
        """实际 fetch — 返回 (raw, status_code, error_str)."""
        raise NotImplementedError

    @abstractmethod
    def _parse(self, raw: Any, prep: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """解析 raw 为标准 items + metadata."""
        raise NotImplementedError

    # ============== 内部 helpers ==============

    def _check_compliance(self, url: str) -> Tuple[bool, Optional[str]]:
        """robots.txt + 自定义 allowlist/blocklist 检查"""
        if self.config.robots_policy == RobotsPolicy.IGNORE:
            return True, None

        # 自定义 blocklist
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower()
        blocked_hosts = self.config.extra.get("blocked_hosts", [])
        if any(b in host for b in blocked_hosts):
            return False, f"host blocklist hit: {host}"

        if self.config.robots_policy == RobotsPolicy.HONOR:
            try:
                rp = self._robots_cache.get(url, self._fetch_robots_text)
                ua = self.config.get_user_agent()
                if not rp.can_fetch(ua, url):
                    return False, f"robots.txt disallowed: {url}"
            except Exception as e:
                logger.debug("robots check failed (allow by default): %s", e)
        return True, None

    def _fetch_robots_text(self, robots_url: str) -> str:
        """抓 robots.txt 文本 — 可被 mock."""
        try:
            content, _, _ = self._http_fetcher(robots_url, {}, 10.0)
            return content.decode("utf-8", errors="replace") if isinstance(content, bytes) else str(content)
        except Exception as e:
            logger.debug("robots fetch error: %s", e)
            return ""

    def _classify_error(self, error_str: str) -> CrawlStatus:
        """根据错误字符串分类"""
        s = error_str.lower()
        if "timeout" in s:
            return CrawlStatus.TIMEOUT
        if "401" in s or "403" in s or "auth" in s:
            return CrawlStatus.AUTH_ERROR
        if "429" in s or "rate" in s:
            return CrawlStatus.RATE_LIMITED
        if "proxy" in s:
            return CrawlStatus.PROXY_ERROR
        return CrawlStatus.FETCH_ERROR

    def _default_http_fetcher(self, url: str, headers: Dict[str, str],
                               timeout: float) -> Tuple[bytes, int, Optional[str]]:
        """默认 urllib fetcher — 避免引入 requests 硬依赖."""
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), resp.status, None
        except Exception as e:
            return b"", 0, str(e)

    def _audit(self, result: CrawlResult) -> None:
        """写 audit chain — best-effort, 失败 warn 不抛."""
        if not self.config.enable_audit_chain:
            return
        try:
            # lazy import — 避免 engine 模块硬依赖循环
            from engines.audit_chain import get_chain  # type: ignore
            chain = get_chain()
            chain.append(
                timestamp=datetime.now().isoformat(),
                method="CRAWLER",
                path=f"/crawler/{self.channel}{urlparse(result.url).path[:200]}",
                user=f"channel={self.channel}",
                body_hash=hashlib.sha256(
                    (result.url + (result.error or "")).encode("utf-8")
                ).hexdigest()[:32],
                status_code=result.status_code or (200 if result.ok else 500),
            )
        except Exception as e:
            logger.debug("audit chain append failed (non-fatal): %s", e)


# 工具函数 — 公开给 channels 用
def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def parse_iso(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.utcnow()