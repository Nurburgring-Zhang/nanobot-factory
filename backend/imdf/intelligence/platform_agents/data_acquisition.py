"""智影 V4 — DataAcquisitionAgent: 接管所有 crawl + search + download + upload + export"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from ..agent_commands.parser import ParsedCommand
from ..crawler.base import ChannelType, CrawlerConfig, RawDocument
from ..crawler.dispatcher import CrawlerDispatcher
from ..processing.classify import ClassifyEngine
from ..processing.dedupe import DedupeEngine, DedupStrategy
from ..processing.cleaning import CleaningEngine, CleanStep
from ..processing.auto_label import AutoLabelEngine, LabelModel
from ..processing.scoring import ScoringEngine, ScoreDimension
from ..processing.store import StorageEngine, StorageBackend
from .base import AgentCapability, PlatformAgent

logger = logging.getLogger(__name__)


class DataAcquisitionAgent(PlatformAgent):
    """数据采集 Agent — 所有 crawl / search / download / upload / export"""

    def __init__(self, dispatcher: Optional[CrawlerDispatcher] = None, processing_pipeline: Optional[List] = None):
        super().__init__(
            name="DataAcquisitionAgent",
            description="数据采集: 爬取/搜索/下载/上传/导出 — 8 大类 50+ 渠道",
            capabilities=[
                AgentCapability.CRAWL,
                AgentCapability.SEARCH,
                AgentCapability.STORE,
            ],
        )
        self.dispatcher = dispatcher or CrawlerDispatcher()
        # 默认处理流水线
        self.pipeline = processing_pipeline or [
            DedupeEngine(strategies=[DedupStrategy.URL, DedupStrategy.SHA256, DedupStrategy.SIMHASH]),
            CleaningEngine(steps=list(CleanStep)),
            AutoLabelEngine(models=[LabelModel.RULES, LabelModel.KEYWORDS]),
            ScoringEngine(dimensions=list(ScoreDimension)),
            ClassifyEngine(),
            StorageEngine(content_backend=StorageBackend.LOCAL),
        ]

    def handle(self, cmd: ParsedCommand) -> Any:
        """分发到具体 action"""
        action = cmd.action
        if action in ("crawl_url", "crawl_website", "deep_crawl", "batch_crawl", "academic_crawl", "social_crawl", "rss_subscribe", "file_download"):
            return self._handle_crawl(cmd)
        if action in ("web_search", "image_search", "video_search", "academic_search", "code_search", "crawl_search"):
            return self._handle_search(cmd)
        if action == "upload":
            return self.upload(cmd)
        if action == "export":
            return self.export(cmd)
        return {"error": f"unknown action: {action}"}

    # 公开方法 — 让 router 直接调用 (名称一致)
    def web_search(self, cmd: ParsedCommand) -> Dict[str, Any]:
        return self._handle_search(cmd)

    def image_search(self, cmd: ParsedCommand) -> Dict[str, Any]:
        return self._handle_search(cmd)

    def video_search(self, cmd: ParsedCommand) -> Dict[str, Any]:
        return self._handle_search(cmd)

    def academic_search(self, cmd: ParsedCommand) -> Dict[str, Any]:
        return self._handle_search(cmd)

    def code_search(self, cmd: ParsedCommand) -> Dict[str, Any]:
        return self._handle_search(cmd)

    def crawl_search(self, cmd: ParsedCommand) -> Dict[str, Any]:
        return self._handle_search(cmd)

    def crawl_url(self, cmd: ParsedCommand) -> Dict[str, Any]:
        return self._handle_crawl(cmd)

    def crawl_website(self, cmd: ParsedCommand) -> Dict[str, Any]:
        return self._handle_crawl(cmd)

    def deep_crawl(self, cmd: ParsedCommand) -> Dict[str, Any]:
        return self._handle_crawl(cmd)

    def batch_crawl(self, cmd: ParsedCommand) -> Dict[str, Any]:
        return self._handle_crawl(cmd)

    def academic_crawl(self, cmd: ParsedCommand) -> Dict[str, Any]:
        return self._handle_crawl(cmd)

    def social_crawl(self, cmd: ParsedCommand) -> Dict[str, Any]:
        return self._handle_crawl(cmd)

    def rss_subscribe(self, cmd: ParsedCommand) -> Dict[str, Any]:
        return self._handle_crawl(cmd)

    def file_download(self, cmd: ParsedCommand) -> Dict[str, Any]:
        return self._handle_crawl(cmd)

    def _handle_crawl(self, cmd: ParsedCommand) -> Dict[str, Any]:
        """统一 crawl 处理"""
        url = cmd.get("url", "")
        channel = cmd.get("channel", "web_generic")
        max_pages = cmd.get("max_pages", 100)
        if not url and not cmd.get("urls"):
            self._record(cmd.action, False)
            return {"error": "missing url", "action": cmd.action}
        # 构造 channel
        try:
            ch_enum = ChannelType(channel)
        except ValueError:
            ch_enum = ChannelType.WEB_GENERIC
        config = CrawlerConfig(channel_type=ch_enum, max_pages=max_pages)
        # 业务特殊配置
        if cmd.action == "academic_crawl":
            source = cmd.get("source", "arxiv")
            config.channel_type = ChannelType(f"academic_{source}")
            config.selectors["query"] = cmd.get("query", url)
        elif cmd.action == "social_crawl":
            platform = cmd.get("platform", "auto")
            if platform == "reddit":
                config.channel_type = ChannelType.SOCIAL_REDDIT
            elif platform == "twitter":
                config.channel_type = ChannelType.SOCIAL_TWITTER
            elif platform == "hackernews":
                config.channel_type = ChannelType.SOCIAL_HACKERNEWS
        elif cmd.action == "deep_crawl":
            config.channel_type = ChannelType.DEEP_BFS
            config.selectors["strategy"] = cmd.get("strategy", "bfs")
            config.max_depth = cmd.get("max_depth", 3)
        elif cmd.action == "rss_subscribe":
            config.channel_type = ChannelType.RSS_GENERIC
        elif cmd.action == "file_download":
            url_lower = url.lower()
            if "s3://" in url_lower or "minio://" in url_lower:
                config.channel_type = ChannelType.FILE_S3 if "s3://" in url_lower else ChannelType.FILE_MINIO
            elif "gs://" in url_lower:
                config.channel_type = ChannelType.FILE_GCS
            elif "azure://" in url_lower:
                config.channel_type = ChannelType.FILE_AZURE
            elif "ftp://" in url_lower:
                config.channel_type = ChannelType.FILE_FTP
            else:
                config.channel_type = ChannelType.WEB_GENERIC
        # 异步 crawl + 处理
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(self._crawl_and_process(url, config, cmd))
            finally:
                loop.close()
            self._record(cmd.action)
            return {
                "success": True,
                "action": cmd.action,
                "url": url,
                "channel": config.channel_type.value,
                "items": [_item_to_dict(it) for it in results["items"][:50]],
                "total_crawled": results["total_crawled"],
                "total_kept": len(results["items"]),
                "metrics": results["metrics"],
            }
        except Exception as e:
            self._record(cmd.action, False)
            logger.exception("crawl failed")
            return {"error": str(e), "action": cmd.action}

    async def _crawl_and_process(self, url: str, config: CrawlerConfig, cmd: ParsedCommand) -> Dict[str, Any]:
        """异步 crawl → 处理流水线"""
        crawler = self.dispatcher.get_crawler(config)
        urls = cmd.get("urls") or [url]
        raw_docs: List[RawDocument] = []
        async for doc in crawler.crawl(urls):
            raw_docs.append(doc)
        # 转 ProcessedItem
        from ..processing.base import ProcessedItem
        items: List[ProcessedItem] = []
        for rd in raw_docs:
            items.append(
                ProcessedItem(
                    source_url=rd.url,
                    source_channel=rd.source_channel,
                    source_metadata=rd.source_metadata or {},
                    raw_doc_hash=rd.content_sha256,
                    type=rd.type,
                    title=rd.title,
                    text=rd.text,
                    images=rd.images,
                    files=rd.files,
                    content_hash=rd.content_sha256,
                    size_bytes=rd.content_length,
                    created_at=rd.crawled_at,
                    status="raw",
                )
            )
        # 流水线
        metrics_acc: Dict[str, Any] = {}
        for engine in self.pipeline:
            try:
                items = engine.process(items)
                metrics_acc[engine.name] = engine.get_metrics()
            except Exception as e:
                logger.warning(f"pipeline {engine.name} failed: {e}")
        await crawler.close()
        return {
            "items": items,
            "total_crawled": len(raw_docs),
            "metrics": metrics_acc,
        }

    def _handle_search(self, cmd: ParsedCommand) -> Dict[str, Any]:
        """统一 search 处理"""
        query = cmd.get("query", "")
        provider = cmd.get("provider", "duckduckgo")
        max_results = cmd.get("max_results", 50)
        if not query:
            self._record(cmd.action, False)
            return {"error": "missing query", "action": cmd.action}
        provider_to_channel = {
            "duckduckgo": ChannelType.SEARCH_DUCKDUCKGO,
            "serpapi": ChannelType.SEARCH_SERPAPI,
            "google_cse": ChannelType.SEARCH_GOOGLE_CSE,
            "bing": ChannelType.SEARCH_BING,
            "brave": ChannelType.SEARCH_BRAVE,
        }
        ch = provider_to_channel.get(provider, ChannelType.SEARCH_DUCKDUCKGO)
        config = CrawlerConfig(channel_type=ch, max_pages=max_results)
        config.selectors["query"] = query
        config.selectors["provider"] = provider
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(self._crawl_and_process(query, config, cmd))
            finally:
                loop.close()
            self._record(cmd.action)
            return {
                "success": True,
                "action": cmd.action,
                "query": query,
                "provider": provider,
                "items": [_item_to_dict(it) for it in results["items"][:max_results]],
                "total_results": len(results["items"]),
                "metrics": results["metrics"],
            }
        except Exception as e:
            self._record(cmd.action, False)
            return {"error": str(e), "action": cmd.action}

    def upload(self, cmd: ParsedCommand) -> Dict[str, Any]:
        """上传 — 复用 FileCrawler"""
        source = cmd.get("source", "")
        if not source:
            self._record("upload", False)
            return {"error": "missing source", "action": "upload"}
        config = CrawlerConfig(channel_type=ChannelType.FILE_LOCAL)
        crawler = self.dispatcher.get_crawler(config)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                doc = loop.run_until_complete(crawler.fetch(source))
            finally:
                loop.close()
            self._record("upload")
            return {"success": True, "uploaded": source, "size": doc.content_length, "type": doc.type}
        except Exception as e:
            self._record("upload", False)
            return {"error": str(e), "action": "upload"}

    def export(self, cmd: ParsedCommand) -> Dict[str, Any]:
        """导出 — 简化实现: 返回 in-memory index"""
        self._record("export")
        storage = next((e for e in self.pipeline if isinstance(e, StorageEngine)), None)
        if not storage:
            return {"error": "no storage in pipeline"}
        return {"success": True, "items": storage.export_index()[:200], "total": storage.get_index_size()}


def _item_to_dict(item) -> Dict[str, Any]:
    return {
        "source_url": item.source_url,
        "title": item.title,
        "type": item.type,
        "modality": item.modality,
        "domain": item.domain,
        "labels": item.labels,
        "quality_score": round(item.quality_score, 3),
        "aesthetic_score": round(item.aesthetic_score, 3),
        "status": item.status,
        "text_preview": (item.text or "")[:200],
    }
