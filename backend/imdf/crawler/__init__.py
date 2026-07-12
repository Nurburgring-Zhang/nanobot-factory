"""83 渠道爬虫框架 (P19-B3)

公开 API:
    - BaseCrawler: 抽象基类, 所有 crawler 实现此协议
    - CrawlerConfig: 统一配置 (UserAgent pool / Proxy pool / rate limit / 合规检查)
    - WebCrawler: Playwright 驱动的网页爬虫
    - APICrawler: REST / GraphQL API 拉取
    - RSSCrawler: feedparser 增量 RSS 采集
    - CrawlerEngine: 调度 5+ 渠道, 集成到 data_collection_engine
    - channels.*: 5 个首批渠道 (google_images / open_images / flickr / unsplash / pixabay)

集成点:
    - engines.audit_chain (P10-A): 所有 fetch 行为落 audit chain
    - engines.data_collection_engine: history 记录 + SQLite 持久化
"""
from __future__ import annotations

from .base import (
    BaseCrawler,
    CrawlResult,
    CrawlMetrics,
    CrawlStatus,
    CrawledItem,
    RobotsPolicy,
    USER_AGENT_POOL,
)
from .config import CrawlerConfig, AuthConfig, ProxyConfig, RateLimitConfig
from .web_crawler import WebCrawler, WebPage
from .api_crawler import APICrawler, GraphQLCrawler
from .rss_crawler import RSSCrawler, RSSItem
from .engine import CrawlerEngine, CrawlJob, JobStatus

__all__ = [
    # Base
    "BaseCrawler",
    "CrawlResult",
    "CrawlMetrics",
    "CrawlStatus",
    "CrawledItem",
    "RobotsPolicy",
    "USER_AGENT_POOL",
    # Config
    "CrawlerConfig",
    "AuthConfig",
    "ProxyConfig",
    "RateLimitConfig",
    # Concrete crawlers
    "WebCrawler",
    "WebPage",
    "APICrawler",
    "GraphQLCrawler",
    "RSSCrawler",
    "RSSItem",
    # Engine
    "CrawlerEngine",
    "CrawlJob",
    "JobStatus",
] 