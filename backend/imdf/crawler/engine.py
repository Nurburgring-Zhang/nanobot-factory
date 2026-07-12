"""CrawlerEngine — 调度 5+ 渠道爬虫 (P19-B3 §7)

特性:
- 渠道注册表 (5 首批 + 自定义)
- 任务调度 (sync / async / 并发)
- 进度监控 (回调 hook + WebSocket 可选)
- 限速 + 并发 (全局 semaphore)
- 集成 data_collection_engine 的 history 持久化

集成点:
- engines.data_collection_engine.create_crawler_job(): 创建任务时持久化
- engines.data_collection_engine.list_crawler_jobs(): 任务列表
- engines.data_collection_engine._log_history(): 写 history
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

from .base import BaseCrawler, CrawlResult, CrawlMetrics, CrawlStatus
from .config import CrawlerConfig, make_default_config
from .web_crawler import WebCrawler
from .api_crawler import APICrawler
from .rss_crawler import RSSCrawler

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CrawlJob:
    """单个 crawl 任务 — 调度单元"""
    id: str
    channel: str
    target: Any
    config: Optional[CrawlerConfig] = None
    status: JobStatus = JobStatus.PENDING
    result: Optional[CrawlResult] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "channel": self.channel,
            "target": self.target,
            "status": self.status.value,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result.to_dict() if self.result else None,
        }


class CrawlerEngine:
    """83 渠道爬虫调度器

    使用:
        engine = CrawlerEngine()
        job_id = engine.submit("google_images", {"query": "cat"})
        result = engine.get_result(job_id)
        # 或批量:
        results = engine.crawl_batch([
            ("google_images", {"query": "dog"}),
            ("unsplash", {"query": "beach"}),
            ("pixabay", {"query": "mountains"}),
        ])

    安全 (P19-C1-fix P0 #1):
        - 默认 mock=True (无 API key 时一律返回 mock 数据, 不真网络)
        - 环境变量:
            CRAWLER_DEFAULT_MOCK = "1" (default) / "0" — 控制默认是否走 mock
            CRAWLER_PRODUCTION_REAL_NETWORK = "1" / "0" (default) — 显式打开
              真网络 (生产模式强制要求)
            CRAWLER_FORCE_MOCK = "1" — 强制 mock (测试用)
        - 生产模式下 (CRAWLER_PRODUCTION_REAL_NETWORK=1):
            无 API key + 真实网络请求 → raise RuntimeError
            这防止"启动 prod 无 key 挂死"的灾难场景.
    """

    DEFAULT_CHANNELS = (
        "google_images", "open_images", "flickr", "unsplash", "pixabay",
        # P20-B1 — 5 web image crawlers
        "baidu_images", "sogou_images", "so_images", "bing_images", "duckduckgo_images",
    )

    def __init__(self, max_concurrent: int = 8,
                 data_collection_engine: Optional[Any] = None,
                 default_mock: Optional[bool] = None):
        self.max_concurrent = max_concurrent
        self._sem = threading.Semaphore(max_concurrent)
        self._jobs: Dict[str, CrawlJob] = {}
        self._jobs_lock = threading.Lock()
        self._registry: Dict[str, Type[BaseCrawler]] = {}
        self._crawler_instances: Dict[str, BaseCrawler] = {}
        self._instance_lock = threading.Lock()
        # 进度回调
        self._progress_hooks: List[Callable[[CrawlJob], None]] = []
        # data_collection 集成 (历史持久化)
        self._data_collection = data_collection_engine
        # mock 默认值 (P19-C1-fix P0 #1)
        # 优先级: 构造参数 > CRAWLER_FORCE_MOCK > CRAWLER_DEFAULT_MOCK > True (safe default)
        if default_mock is None:
            force = os.environ.get("CRAWLER_FORCE_MOCK")
            if force is not None:
                default_mock = (force == "1")
            else:
                env_default = os.environ.get("CRAWLER_DEFAULT_MOCK", "1")
                default_mock = (env_default != "0")  # "1" 或缺失 → True
        self.default_mock = bool(default_mock)
        # 生产真网络模式 (默认 False)
        self.production_real_network = (
            os.environ.get("CRAWLER_PRODUCTION_REAL_NETWORK", "0") == "1"
        )
        # 注册默认渠道
        self._register_default_channels()
        # 启动期检查 (P19-C1-fix P0 #1)
        self._startup_safety_check()

    def _register_default_channels(self) -> None:
        """注册 5 个首批渠道 — 延迟 import 避免循环依赖"""
        try:
            from .channels.google_images import GoogleImagesCrawler
            self.register("google_images", GoogleImagesCrawler)
        except ImportError as e:
            logger.debug("google_images register failed: %s", e)
        try:
            from .channels.open_images import OpenImagesCrawler
            self.register("open_images", OpenImagesCrawler)
        except ImportError as e:
            logger.debug("open_images register failed: %s", e)
        try:
            from .channels.flickr import FlickrCrawler
            self.register("flickr", FlickrCrawler)
        except ImportError as e:
            logger.debug("flickr register failed: %s", e)
        try:
            from .channels.unsplash import UnsplashCrawler
            self.register("unsplash", UnsplashCrawler)
        except ImportError as e:
            logger.debug("unsplash register failed: %s", e)
        try:
            from .channels.pixabay import PixabayCrawler
            self.register("pixabay", PixabayCrawler)
        except ImportError as e:
            logger.debug("pixabay register failed: %s", e)
        # P20-B1 — 5 web image crawlers (Baidu / Sogou / 360 / Bing / DuckDuckGo)
        try:
            from .channels.baidu_images import BaiduImagesCrawler
            self.register("baidu_images", BaiduImagesCrawler)
        except ImportError as e:
            logger.debug("baidu_images register failed: %s", e)
        try:
            from .channels.sogou import SogouImagesCrawler
            self.register("sogou_images", SogouImagesCrawler)
        except ImportError as e:
            logger.debug("sogou_images register failed: %s", e)
        try:
            from .channels.so_images import SoImagesCrawler
            self.register("so_images", SoImagesCrawler)
        except ImportError as e:
            logger.debug("so_images register failed: %s", e)
        try:
            from .channels.bing_images import BingImagesCrawler
            self.register("bing_images", BingImagesCrawler)
        except ImportError as e:
            logger.debug("bing_images register failed: %s", e)
        try:
            from .channels.duckduckgo import DuckDuckGoImagesCrawler
            self.register("duckduckgo_images", DuckDuckGoImagesCrawler)
        except ImportError as e:
            logger.debug("duckduckgo_images register failed: %s", e)
        # 通用 crawler
        self.register("web", WebCrawler)
        self.register("api", APICrawler)
        self.register("rss", RSSCrawler)

    # ============== 注册表 ==============

    def register(self, channel: str, crawler_class: Type[BaseCrawler]) -> None:
        """注册一个渠道"""
        with self._instance_lock:
            self._registry[channel] = crawler_class
            # 失效已缓存实例
            self._crawler_instances.pop(channel, None)

    def list_channels(self) -> List[str]:
        return list(self._registry.keys())

    def get_crawler(self, channel: str, **kwargs: Any) -> BaseCrawler:
        """懒加载渠道 crawler 实例 (单例缓存)

        默认行为 (P19-C1-fix P0 #1): mock=True
        - 缺 API key 时 → 自动 mock (避免挂死)
        - 显式传 mock=False 可关闭 mock
        - 用户构造 kwargs 中显式提供 api_key 且未传 mock → 检查真实可用性
        """
        if channel not in self._registry:
            raise ValueError(f"Unknown channel: {channel}. Available: {self.list_channels()}")
        # kwargs 中显式 mock 优先; 否则使用引擎 default_mock
        explicit_mock = kwargs.pop("mock", self.default_mock)
        # config 也 pop — 避免与下方 instance = cls(config=cfg, ...) 重复
        user_config = kwargs.pop("config", None)
        with self._instance_lock:
            if channel not in self._crawler_instances:
                cls = self._registry[channel]
                cfg = user_config or make_default_config(channel=channel)
                # 合并 kwargs (覆盖默认) — 注意 mock/config 已 pop, 不会被误合并到 config
                for k, v in kwargs.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
                # 构造 crawler — 传入显式 mock 标记
                instance = cls(config=cfg, mock=explicit_mock, **kwargs)
                self._crawler_instances[channel] = instance
                logger.debug(
                    "crawler %s instantiated mock=%s",
                    channel, getattr(instance, "mock", "?"),
                )
            return self._crawler_instances[channel]

    def _startup_safety_check(self) -> None:
        """启动期安全检查 (P19-C1-fix P0 #1)

        - 生产模式 (CRAWLER_PRODUCTION_REAL_NETWORK=1):
            default_mock=False (显式关闭 mock) + 缺 API key → raise RuntimeError
            防止"启动 prod 无 key 挂死"的灾难场景 (fail-fast).
        - 非生产模式: 仅 warn 不 raise.
        """
        if not self.production_real_network:
            # 非生产模式 — warn 不 raise
            if not self.default_mock:
                logger.warning(
                    "CrawlerEngine default_mock=False but NOT in production "
                    "(CRAWLER_PRODUCTION_REAL_NETWORK=0). Channels without API key "
                    "will fall back to mock automatically (no hang)."
                )
            return
        # 生产模式
        if not self.default_mock:
            # 检查 5 渠道 key 是否齐全 (open_images 不要求)
            missing = self._check_required_api_keys()
            if missing:
                raise RuntimeError(
                    f"PRODUCTION mode (CRAWLER_PRODUCTION_REAL_NETWORK=1) but "
                    f"default_mock=False. Missing required API keys: {missing}. "
                    f"Either provide keys or set CRAWLER_DEFAULT_MOCK=1 to use mock data. "
                    f"This check prevents prod startup with no-key real-network hangs."
                )

    def _check_required_api_keys(self) -> List[str]:
        """返回缺失的 API key 列表 — 渠道名(env-var-list-formatted)"""
        missing = []
        checks = [
            ("google_images", ["GOOGLE_API_KEY", "GOOGLE_CX"]),
            ("flickr", ["FLICKR_API_KEY"]),
            ("unsplash", ["UNSPLASH_ACCESS_KEY"]),
            ("pixabay", ["PIXABAY_API_KEY"]),
            # open_images 不需要 key
        ]
        for ch_name, env_vars in checks:
            if not all(os.environ.get(v) for v in env_vars):
                missing.append(f"{ch_name}({','.join(env_vars)})")
        return missing

    # ============== 任务调度 ==============

    def submit(self, channel: str, target: Any,
               job_id: Optional[str] = None,
               config: Optional[CrawlerConfig] = None) -> str:
        """提交一个任务 — 异步执行, 返回 job_id"""
        if channel not in self._registry:
            raise ValueError(f"Unknown channel: {channel}")
        job_id = job_id or str(uuid.uuid4())[:8]
        job = CrawlJob(
            id=job_id, channel=channel, target=target,
            config=config or make_default_config(channel=channel),
        )
        with self._jobs_lock:
            self._jobs[job_id] = job
        # 异步执行
        threading.Thread(target=self._run_job, args=(job_id,), daemon=True).start()
        return job_id

    def _run_job(self, job_id: str) -> None:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now().isoformat()
        try:
            self._sem.acquire()
            try:
                # _run_job 不传 mock 标志, 让 get_crawler 用 self.default_mock
                crawler = self.get_crawler(job.channel)
                # 应用 job-level config 覆盖
                if job.config and crawler.config != job.config:
                    crawler.config = job.config
                result = crawler.crawl(job.target)
                with self._jobs_lock:
                    job.result = result
                    job.status = JobStatus.COMPLETED if result.ok else JobStatus.FAILED
                    if not result.ok:
                        job.error = result.error or "fetch failed"
            finally:
                self._sem.release()
        except Exception as e:
            logger.exception("job %s failed", job_id)
            with self._jobs_lock:
                job.status = JobStatus.FAILED
                job.error = str(e)
        finally:
            with self._jobs_lock:
                job.finished_at = datetime.now().isoformat()
            # 历史持久化
            self._log_to_data_collection(job)
            # 进度回调
            for hook in self._progress_hooks:
                try:
                    hook(job)
                except Exception as e:
                    logger.debug("progress hook failed: %s", e)

    def get_job(self, job_id: str) -> Optional[CrawlJob]:
        with self._jobs_lock:
            return self._jobs.get(job_id)

    def list_jobs(self, status: Optional[JobStatus] = None) -> List[CrawlJob]:
        with self._jobs_lock:
            jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        return jobs

    def wait_for(self, job_id: str, timeout: float = 60.0) -> Optional[CrawlJob]:
        """阻塞等待 job 完成"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.get_job(job_id)
            if job and job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                return job
            time.sleep(0.1)
        return self.get_job(job_id)

    def get_result(self, job_id: str, timeout: float = 60.0) -> Optional[CrawlResult]:
        job = self.wait_for(job_id, timeout)
        return job.result if job else None

    # ============== 批量 ==============

    def crawl_batch(self, items: List[Any],
                    channels: Optional[List[str]] = None,
                    max_workers: Optional[int] = None,
                    sync: bool = True) -> Dict[str, CrawlResult]:
        """批量同步/异步执行

        items 接受:
        - list of (channel, target) tuples
        - list of dicts {channel, target}
        - list of targets (配合 channels 参数)
        """
        if not items:
            return {}
        # 标准化输入
        jobs_spec: List[tuple] = []
        if channels and len(channels) == len(items) and isinstance(items[0], dict):
            for ch, t in zip(channels, items):
                jobs_spec.append((ch, t))
        elif isinstance(items[0], tuple) and len(items[0]) == 2:
            jobs_spec = items
        elif isinstance(items[0], dict) and "channel" in items[0]:
            jobs_spec = [(it["channel"], it["target"]) for it in items]
        else:
            raise ValueError("items must be list of (channel, target) or dict {channel, target}")

        results: Dict[str, CrawlResult] = {}

        if sync:
            # 顺序执行
            for ch, target in jobs_spec:
                job_id = self.submit(ch, target)
                job = self.wait_for(job_id, timeout=120.0)
                if job and job.result:
                    results[job_id] = job.result
        else:
            # 并发执行
            with ThreadPoolExecutor(max_workers=max_workers or self.max_concurrent) as ex:
                futures = {}
                for ch, target in jobs_spec:
                    job_id = self.submit(ch, target)
                    futures[job_id] = ex.submit(self.wait_for, job_id, 120.0)
                for job_id, fut in futures.items():
                    try:
                        job = fut.result(timeout=130.0)
                        if job and job.result:
                            results[job_id] = job.result
                    except Exception as e:
                        logger.warning("batch job %s failed: %s", job_id, e)
        return results

    # ============== 进度回调 ==============

    def add_progress_hook(self, hook: Callable[[CrawlJob], None]) -> None:
        """添加进度回调 — 可用于 WebSocket 推送"""
        self._progress_hooks.append(hook)

    # ============== 集成 data_collection ==============

    def _log_to_data_collection(self, job: CrawlJob) -> None:
        """写历史到 data_collection_engine (best-effort)"""
        if not self._data_collection:
            return
        try:
            history_fn = getattr(self._data_collection, "_log_history", None)
            if history_fn:
                items_count = job.result.count if job.result else 0
                duration = ""
                if job.started_at and job.finished_at:
                    try:
                        s = datetime.fromisoformat(job.started_at)
                        f = datetime.fromisoformat(job.finished_at)
                        duration = f"{(f - s).total_seconds():.1f}s"
                    except Exception:
                        duration = ""
                history_fn({
                    "type": f"channel_{job.channel}",
                    "name": f"channel:{job.channel}",
                    "source": str(job.target)[:200],
                    "status": "completed" if job.status == JobStatus.COMPLETED else "failed",
                    "items_collected": items_count,
                    "duration": duration,
                })
        except Exception as e:
            logger.debug("history log failed: %s", e)

    # ============== 聚合 metrics ==============

    def aggregate_metrics(self) -> Dict[str, Dict[str, Any]]:
        """聚合所有渠道 crawler 实例的 metrics"""
        out: Dict[str, Dict[str, Any]] = {}
        for ch, crawler in self._crawler_instances.items():
            out[ch] = crawler.metrics.snapshot()
        return out

    def shutdown(self) -> None:
        """清理 — 关闭所有 crawler 持有的客户端"""
        for ch, crawler in self._crawler_instances.items():
            close_fn = getattr(crawler, "close", None)
            if close_fn:
                try:
                    close_fn()
                except Exception:
                    pass
        self._crawler_instances.clear()


__all__ = ["CrawlerEngine", "CrawlJob", "JobStatus"]