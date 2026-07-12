"""智影 V4 — 爬虫基类 + 数据结构 + 配置"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ChannelType(str, Enum):
    """50+ 渠道类型 — 多渠道爬虫框架核心枚举"""

    # Web
    WEB_GENERIC = "web_generic"
    WEB_PLAYWRIGHT = "web_playwright"
    WEB_SELENIUM = "web_selenium"
    WEB_SCRAPY = "web_scrapy"
    WEB_BEAUTIFULSOUP = "web_beautifulsoup"
    WEB_NEWSPAPER = "web_newspaper"
    WEB_TRAFILATURA = "web_trafilatura"

    # 公开 API
    API_REST = "api_rest"
    API_GRAPHQL = "api_graphql"
    API_GRPC = "api_grpc"
    API_OPENAI_COMPATIBLE = "api_openai_compatible"

    # 公共数据集 API
    SOURCE_OPEN_IMAGES = "source_open_images"
    SOURCE_COCO = "source_coco"
    SOURCE_IMAGENET = "source_imagenet"
    SOURCE_FLICKR = "source_flickr"
    SOURCE_PIXABAY = "source_pixabay"
    SOURCE_UNSPLASH = "source_unsplash"
    SOURCE_PEXELS = "source_pexels"
    SOURCE_WIKIPEDIA = "source_wikipedia"
    SOURCE_WIKIDATA = "source_wikidata"
    SOURCE_GITHUB = "source_github"
    SOURCE_HUGGINGFACE = "source_huggingface"

    # 搜索引擎
    SEARCH_SERPAPI = "search_serpapi"
    SEARCH_GOOGLE_CSE = "search_google_cse"
    SEARCH_BING = "search_bing"
    SEARCH_DUCKDUCKGO = "search_duckduckgo"
    SEARCH_BRAVE = "search_brave"

    # RSS
    RSS_GENERIC = "rss_generic"
    RSS_YOUTUBE_CHANNEL = "rss_youtube_channel"
    RSS_SUBSTACK = "rss_substack"
    RSS_MEDIUM = "rss_medium"
    RSS_WORDPRESS = "rss_wordpress"
    RSS_HEXO = "rss_hexo"

    # 社交媒体 (公开 API)
    SOCIAL_TWITTER = "social_twitter"
    SOCIAL_REDDIT = "social_reddit"
    SOCIAL_MASTODON = "social_mastodon"
    SOCIAL_HACKERNEWS = "social_hackernews"
    SOCIAL_DEVTO = "social_devto"
    SOCIAL_LEMMY = "social_lemmy"

    # 文件 / OSS
    FILE_S3 = "file_s3"
    FILE_GCS = "file_gcs"
    FILE_AZURE = "file_azure"
    FILE_MINIO = "file_minio"
    FILE_LOCAL = "file_local"
    FILE_FTP = "file_ftp"

    # 学术 / 预印本
    ACADEMIC_ARXIV = "academic_arxiv"
    ACADEMIC_PUBMED = "academic_pubmed"
    ACADEMIC_SEMANTIC_SCHOLAR = "academic_semantic_scholar"
    ACADEMIC_OPENREVIEW = "academic_openreview"
    ACADEMIC_PAPERSWITHCODE = "academic_paperswithcode"

    # P2P / 学术
    P2P_IPFS = "p2p_ipfs"
    P2P_BITTORRENT = "p2p_bittorrent"

    # 深度
    DEEP_BFS = "deep_bfs"
    DEEP_DFS = "deep_dfs"
    DEEP_CITATION = "deep_citation"

    # 其他
    USER_UPLOAD = "user_upload"
    OPERATOR_INTERNAL = "operator_internal"


class ComplianceMode(str, Enum):
    """合规策略 — 操作员可配置"""

    STRICT = "strict"  # 全尊重 (默认)
    INTERNAL_ONLY = "internal"  # 仅内部白名单
    AUDIT_MODE = "audit"  # 全跑但所有活动审计
    RESEARCH = "research"  # 学术研究模式
    OPERATOR_OVERRIDE = "operator_override"  # 操作员明确覆盖


@dataclass
class RawDocument:
    """原始抓取文档 — 跨模态统一结构"""

    url: str
    type: str = "html"  # html / json / image / video / audio / text / pdf
    title: str = ""
    text: str = ""
    html: str = ""
    json: Dict[str, Any] = field(default_factory=dict)
    images: List[str] = field(default_factory=list)  # URLs
    links: List[str] = field(default_factory=list)
    files: List[Dict[str, Any]] = field(default_factory=list)  # 下载的文件

    # 元数据
    source_channel: str = ""
    source_metadata: Dict[str, Any] = field(default_factory=dict)
    crawled_at: str = ""
    crawl_duration_ms: float = 0.0
    http_status: int = 200

    # 内容指纹 (用于去重)
    content_sha256: str = ""
    content_length: int = 0
    language: str = ""
    embedding: Optional[List[float]] = None  # 1024-d

    def compute_hash(self):
        """计算内容 SHA256 (用于去重)"""
        content = (self.text or "") + (self.html or "") + json.dumps(self.json, sort_keys=True)
        self.content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.content_length = len(content)
        return self.content_sha256


@dataclass
class CrawlerConfig:
    """爬虫配置 — 操作员可全维度配置"""

    name: str = "default"
    channel_type: ChannelType = ChannelType.WEB_GENERIC
    seed_urls: List[str] = field(default_factory=list)

    # 合规
    compliance_mode: ComplianceMode = ComplianceMode.STRICT
    respect_robots_txt: bool = True
    respect_rate_limit: bool = True
    rate_limit_rps: float = 1.0
    domain_whitelist: List[str] = field(default_factory=list)
    domain_blacklist: List[str] = field(default_factory=list)

    # 反爬
    user_agent_pool: List[str] = field(default_factory=lambda: _default_ua_pool())
    proxy_pool: List[str] = field(default_factory=list)
    rotate_proxy_every: int = 10
    use_browser_fingerprint: bool = True
    captcha_solver: Optional[str] = None

    # 内容提取
    selectors: Dict[str, str] = field(default_factory=dict)
    wait_selectors: List[str] = field(default_factory=list)
    scroll_to_bottom: bool = False
    click_selectors: List[str] = field(default_factory=list)
    auto_extract: bool = True  # LLM 自动分析

    # 深度
    max_depth: int = 0
    max_pages: int = 100
    same_domain_only: bool = True

    # 过滤
    url_include_patterns: List[str] = field(default_factory=list)
    url_exclude_patterns: List[str] = field(default_factory=list)
    min_content_length: int = 100
    language_filter: Optional[List[str]] = None

    # 输出
    output_format: str = "raw"
    extract_metadata: bool = True
    extract_links: bool = True
    extract_images: bool = True

    # 存储
    storage_backend: str = "minio"
    storage_bucket: str = "imdf-crawled"
    storage_prefix: str = ""

    # 调度
    parallel_workers: int = 4
    rate_per_worker: float = 0.5
    batch_size: int = 100

    # 自动处理
    auto_dedupe: bool = True
    auto_clean: bool = True
    auto_label: bool = True
    auto_score: bool = True


def _default_ua_pool() -> List[str]:
    """默认 User-Agent 池 — 100+ UA"""
    return [
        # Chrome Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Chrome macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Firefox Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        # Safari macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        # Edge
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        # Mobile iOS
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
        # Android
        "Mozilla/5.0 (Linux; Android 14; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    ] * 15  # 重复 15 次模拟池


@dataclass
class CrawlerMetrics:
    """爬虫指标"""

    started_at: float = 0.0
    ended_at: float = 0.0
    pages_crawled: int = 0
    pages_failed: int = 0
    pages_blocked: int = 0  # 合规拦截
    bytes_downloaded: int = 0
    unique_domains: Set[str] = field(default_factory=set)
    rate_actual: float = 0.0
    errors: List[str] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        duration = max(self.ended_at - self.started_at, 0.001) if self.ended_at else 0
        return {
            "duration_sec": round(duration, 2),
            "pages_crawled": self.pages_crawled,
            "pages_failed": self.pages_failed,
            "pages_blocked": self.pages_blocked,
            "bytes_downloaded": self.bytes_downloaded,
            "unique_domains": len(self.unique_domains),
            "rate_actual_rps": round(self.pages_crawled / duration, 2) if duration else 0,
            "errors": len(self.errors),
        }


class BaseCrawler(ABC):
    """所有爬虫的基类 — 多渠道框架核心"""

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self.metrics = CrawlerMetrics()
        self.metrics.started_at = time.time()
        self._last_request = 0.0

    @abstractmethod
    async def fetch(self, url: str) -> RawDocument:
        """子类实现具体抓取逻辑"""
        pass

    async def crawl(self, urls: List[str]) -> AsyncIterator[RawDocument]:
        """标准 crawl 流程 — 通用调度"""
        semaphore = asyncio.Semaphore(self.config.parallel_workers)

        async def _process(url: str) -> Optional[RawDocument]:
            async with semaphore:
                # 合规检查
                if not self._compliance_check(url):
                    self.metrics.pages_blocked += 1
                    return None
                # 限速
                await self._rate_limit()
                try:
                    doc = await self.fetch(url)
                    doc.crawled_at = _now()
                    doc.source_channel = self.config.channel_type.value
                    doc.compute_hash()
                    self.metrics.pages_crawled += 1
                    from urllib.parse import urlparse
                    self.metrics.unique_domains.add(urlparse(url).netloc)
                    return doc
                except Exception as e:
                    self.metrics.pages_failed += 1
                    self.metrics.errors.append(str(e))
                    logger.warning(f"Fetch failed {url}: {e}")
                    return None

        tasks = [_process(url) for url in urls]
        for coro in asyncio.as_completed(tasks):
            doc = await coro
            if doc:
                yield doc

        self.metrics.ended_at = time.time()

    def _compliance_check(self, url: str) -> bool:
        """合规检查 — 域名白/黑名单"""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        if self.config.domain_blacklist and any(b in domain for b in self.config.domain_blacklist):
            return False
        if self.config.domain_whitelist and not any(w in domain for w in self.config.domain_whitelist):
            return False
        return True

    async def _rate_limit(self):
        """限速"""
        if self.config.rate_limit_rps <= 0:
            return
        now = time.time()
        elapsed = now - self._last_request
        wait = (1.0 / self.config.rate_limit_rps) - elapsed
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = time.time()

    def get_metrics(self) -> Dict[str, Any]:
        return self.metrics.summary()


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
