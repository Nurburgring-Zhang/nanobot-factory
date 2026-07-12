"""智影 V4 — 爬虫子包: 多渠道爬虫框架"""
from .base import BaseCrawler, RawDocument, CrawlerMetrics, CrawlerConfig, ChannelType
from .dispatcher import CrawlerDispatcher

__all__ = [
    "BaseCrawler",
    "RawDocument",
    "CrawlerMetrics",
    "CrawlerConfig",
    "ChannelType",
    "CrawlerDispatcher",
]
