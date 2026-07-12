"""Tests for :mod:`engines.crawler_engine` (P19-B4)."""
from __future__ import annotations

import pytest

from engines.crawler_engine import (
    BaseCrawler,
    CrawlerEngine,
    CrawlerMetrics,
    CrawlJobState,
    CrawlStatus,
)


class _FakeCrawler(BaseCrawler):
    name = "fake-web"

    def __init__(self, pages: int = 3):
        self._pages = pages

    async def crawl(self, config):  # pragma: no cover — protocol only
        for i in range(self._pages):
            yield {"url": f"http://example.com/{i}", "title": f"page-{i}"}


class TestCrawlerEngine:
    def test_instantiate(self):
        engine = CrawlerEngine()
        assert engine is not None
        assert engine.status()["state"] == "idle"

    def test_register_channel(self):
        engine = CrawlerEngine()
        engine.register_channel("web", _FakeCrawler())
        assert "web" in engine.list_channels()

    def test_register_channel_rejects_non_base(self):
        engine = CrawlerEngine()
        with pytest.raises(TypeError):
            engine.register_channel("bad", "not-a-crawler")  # type: ignore[arg-type]

    def test_start_crawl_returns_id(self):
        engine = CrawlerEngine()
        engine.register_channel("web", _FakeCrawler())
        job_id = engine.start_crawl(name="hn", url="https://news.ycombinator.com")
        assert isinstance(job_id, str) and len(job_id) > 0

    def test_status_returns_envelope(self):
        engine = CrawlerEngine()
        engine.register_channel("web", _FakeCrawler())
        job_id = engine.start_crawl(name="hn", url="https://news.ycombinator.com")
        status = engine.status(job_id)
        assert isinstance(status, CrawlStatus)
        assert status.job_id == job_id
        assert status.state in (CrawlJobState.RUNNING, CrawlJobState.PENDING)

    def test_pause_resume_stop_lifecycle(self):
        engine = CrawlerEngine()
        engine.register_channel("web", _FakeCrawler())
        job_id = engine.start_crawl(name="hn", url="https://example.com")
        assert engine.pause_job(job_id) is True
        assert engine.status(job_id).state == CrawlJobState.PAUSED
        assert engine.resume_job(job_id) is True
        assert engine.status(job_id).state == CrawlJobState.RUNNING
        assert engine.stop_job(job_id) is True
        assert engine.status(job_id).state == CrawlJobState.STOPPED

    def test_metrics_envelope(self):
        engine = CrawlerEngine()
        m = engine.metrics()
        assert isinstance(m, CrawlerMetrics)
        d = m.to_dict()
        assert set(d.keys()) == {
            "jobs_total", "jobs_running", "jobs_paused",
            "jobs_completed", "jobs_failed", "pages_total",
            "errors_total", "throughput_pages_per_sec",
        }

    def test_record_pages_updates_state(self):
        engine = CrawlerEngine()
        engine.register_channel("web", _FakeCrawler())
        job_id = engine.start_crawl(name="hn", url="https://example.com")
        engine.record_pages(job_id, count=5, errors=1)
        status = engine.status(job_id)
        assert status.pages_collected >= 5
        assert status.errors >= 1

    def test_shutdown_stops_all_jobs(self):
        engine = CrawlerEngine()
        engine.register_channel("web", _FakeCrawler())
        engine.start_crawl(name="hn", url="https://example.com")
        engine.start_crawl(name="rss", url="https://example.com/feed")
        engine.shutdown()
        for job_id in engine._live_jobs:
            assert engine.status(job_id).state == CrawlJobState.STOPPED