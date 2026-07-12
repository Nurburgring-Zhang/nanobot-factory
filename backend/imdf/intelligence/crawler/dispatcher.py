"""智影 V4 — CrawlerDispatcher: 渠道 → 实例自动路由"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type

from .base import BaseCrawler, ChannelType, CrawlerConfig, RawDocument

logger = logging.getLogger(__name__)


# ChannelType → Crawler class 路由表
# 懒加载: 避免 import 时全部依赖
_CHANNEL_REGISTRY: Dict[ChannelType, str] = {
    # Web
    ChannelType.WEB_GENERIC: "web_crawler.WebCrawler",
    ChannelType.WEB_PLAYWRIGHT: "web_crawler.WebCrawler",
    ChannelType.WEB_SELENIUM: "web_crawler.WebCrawler",
    ChannelType.WEB_SCRAPY: "web_crawler.WebCrawler",
    ChannelType.WEB_BEAUTIFULSOUP: "web_crawler.WebCrawler",
    ChannelType.WEB_NEWSPAPER: "web_crawler.WebCrawler",
    ChannelType.WEB_TRAFILATURA: "web_crawler.WebCrawler",
    # API
    ChannelType.API_REST: "api_crawler.APICrawler",
    ChannelType.API_GRAPHQL: "api_crawler.APICrawler",
    ChannelType.API_GRPC: "api_crawler.APICrawler",
    ChannelType.API_OPENAI_COMPATIBLE: "api_crawler.APICrawler",
    # 公共数据集 API → APICrawler
    ChannelType.SOURCE_OPEN_IMAGES: "api_crawler.APICrawler",
    ChannelType.SOURCE_COCO: "api_crawler.APICrawler",
    ChannelType.SOURCE_IMAGENET: "api_crawler.APICrawler",
    ChannelType.SOURCE_FLICKR: "api_crawler.APICrawler",
    ChannelType.SOURCE_PIXABAY: "api_crawler.APICrawler",
    ChannelType.SOURCE_UNSPLASH: "api_crawler.APICrawler",
    ChannelType.SOURCE_PEXELS: "api_crawler.APICrawler",
    ChannelType.SOURCE_WIKIPEDIA: "api_crawler.APICrawler",
    ChannelType.SOURCE_WIKIDATA: "api_crawler.APICrawler",
    ChannelType.SOURCE_GITHUB: "api_crawler.APICrawler",
    ChannelType.SOURCE_HUGGINGFACE: "api_crawler.APICrawler",
    # 搜索
    ChannelType.SEARCH_SERPAPI: "search_engine_crawler.SearchEngineCrawler",
    ChannelType.SEARCH_GOOGLE_CSE: "search_engine_crawler.SearchEngineCrawler",
    ChannelType.SEARCH_BING: "search_engine_crawler.SearchEngineCrawler",
    ChannelType.SEARCH_DUCKDUCKGO: "search_engine_crawler.SearchEngineCrawler",
    ChannelType.SEARCH_BRAVE: "search_engine_crawler.SearchEngineCrawler",
    # RSS
    ChannelType.RSS_GENERIC: "rss_crawler.RssCrawler",
    ChannelType.RSS_YOUTUBE_CHANNEL: "rss_crawler.RssCrawler",
    ChannelType.RSS_SUBSTACK: "rss_crawler.RssCrawler",
    ChannelType.RSS_MEDIUM: "rss_crawler.RssCrawler",
    ChannelType.RSS_WORDPRESS: "rss_crawler.RssCrawler",
    ChannelType.RSS_HEXO: "rss_crawler.RssCrawler",
    # 社交
    ChannelType.SOCIAL_TWITTER: "social_crawler.SocialCrawler",
    ChannelType.SOCIAL_REDDIT: "social_crawler.SocialCrawler",
    ChannelType.SOCIAL_MASTODON: "social_crawler.SocialCrawler",
    ChannelType.SOCIAL_HACKERNEWS: "social_crawler.SocialCrawler",
    ChannelType.SOCIAL_DEVTO: "social_crawler.SocialCrawler",
    ChannelType.SOCIAL_LEMMY: "social_crawler.SocialCrawler",
    # 文件 / OSS
    ChannelType.FILE_S3: "file_crawler.FileCrawler",
    ChannelType.FILE_GCS: "file_crawler.FileCrawler",
    ChannelType.FILE_AZURE: "file_crawler.FileCrawler",
    ChannelType.FILE_MINIO: "file_crawler.FileCrawler",
    ChannelType.FILE_LOCAL: "file_crawler.FileCrawler",
    ChannelType.FILE_FTP: "file_crawler.FileCrawler",
    # 学术
    ChannelType.ACADEMIC_ARXIV: "academic_crawler.AcademicCrawler",
    ChannelType.ACADEMIC_PUBMED: "academic_crawler.AcademicCrawler",
    ChannelType.ACADEMIC_SEMANTIC_SCHOLAR: "academic_crawler.AcademicCrawler",
    ChannelType.ACADEMIC_OPENREVIEW: "academic_crawler.AcademicCrawler",
    ChannelType.ACADEMIC_PAPERSWITHCODE: "academic_crawler.AcademicCrawler",
    # 深度
    ChannelType.DEEP_BFS: "deep_crawler.DeepCrawler",
    ChannelType.DEEP_DFS: "deep_crawler.DeepCrawler",
    ChannelType.DEEP_CITATION: "deep_crawler.DeepCrawler",
    # 其他 — 默认 WebCrawler
    ChannelType.USER_UPLOAD: "file_crawler.FileCrawler",
    ChannelType.OPERATOR_INTERNAL: "file_crawler.FileCrawler",
    # P2P 暂未实现 → 退化到 web
    ChannelType.P2P_IPFS: "web_crawler.WebCrawler",
    ChannelType.P2P_BITTORRENT: "web_crawler.WebCrawler",
}


class CrawlerDispatcher:
    """统一调度器 — 根据 ChannelType 自动选 crawler + 实例池"""

    def __init__(self):
        self._cache: Dict[ChannelType, BaseCrawler] = {}
        self._class_cache: Dict[str, Type[BaseCrawler]] = {}

    def _resolve_class(self, channel: ChannelType) -> Type[BaseCrawler]:
        """懒加载 — 解析 channel → crawler class"""
        cls_path = _CHANNEL_REGISTRY.get(channel)
        if cls_path is None:
            raise ValueError(f"Unknown channel: {channel}")
        if cls_path not in self._class_cache:
            module_name, class_name = cls_path.split(".", 1)
            import importlib
            from . import (
                web_crawler,
                api_crawler,
                rss_crawler,
                social_crawler,
                file_crawler,
                search_engine_crawler,
                deep_crawler,
                academic_crawler,
            )

            mod = {
                "web_crawler": web_crawler,
                "api_crawler": api_crawler,
                "rss_crawler": rss_crawler,
                "social_crawler": social_crawler,
                "file_crawler": file_crawler,
                "search_engine_crawler": search_engine_crawler,
                "deep_crawler": deep_crawler,
                "academic_crawler": academic_crawler,
            }.get(module_name)
            if mod is None:
                mod = importlib.import_module(f".{module_name}", package="imdf.intelligence.crawler")
            self._class_cache[cls_path] = getattr(mod, class_name)
        return self._class_cache[cls_path]

    def get_crawler(self, config: CrawlerConfig) -> BaseCrawler:
        """获取指定 channel 的 crawler (复用缓存)"""
        if config.channel_type not in self._cache:
            cls = self._resolve_class(config.channel_type)
            self._cache[config.channel_type] = cls(config)
        return self._cache[config.channel_type]

    def dispatch(self, channel: ChannelType, urls: List[str], config_overrides: Optional[Dict[str, Any]] = None):
        """分发抓取任务 — 返回 async iterator"""
        import asyncio
        from .base import CrawlerConfig

        config = CrawlerConfig(channel_type=channel)
        if config_overrides:
            for k, v in config_overrides.items():
                setattr(config, k, v)
        crawler = self.get_crawler(config)
        return crawler.crawl(urls)

    def list_supported_channels(self) -> List[ChannelType]:
        return list(_CHANNEL_REGISTRY.keys())

    def get_metrics_summary(self) -> Dict[str, Any]:
        return {ch.value: c.get_metrics() for ch, c in self._cache.items()}

    async def close_all(self):
        for c in self._cache.values():
            if hasattr(c, "close"):
                try:
                    result = c.close()
                    if hasattr(result, "__await__"):
                        await result
                except Exception as e:
                    logger.warning(f"close crawler failed: {e}")
        self._cache.clear()
