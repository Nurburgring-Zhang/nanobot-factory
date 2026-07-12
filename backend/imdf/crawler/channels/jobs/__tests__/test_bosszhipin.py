"""test_bosszhipin.py — BOSS直聘 渠道适配器测试 (P20-B2)

覆盖: parse 提取 / 容错 / 异步 search / 网络失败 / 限速 / 截断 / schema
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from typing import Any

import httpx

_THIS = os.path.dirname(os.path.abspath(__file__))
_JOBS_DIR = os.path.dirname(_THIS)
_CHANNELS_DIR = os.path.dirname(_JOBS_DIR)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_CHANNELS_DIR)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from imdf.crawler.channels.jobs import BossZhipinChannel, CrawlResult, JobPosting  # noqa: E402


SAMPLE_HTML = """
<!DOCTYPE html>
<html><body><ul class="job-list">
  <li class="job-card-wrapper" data-jobid="1001">
    <a class="job-title" href="/job_detail/1001.html">Python 高级开发</a>
    <div class="company-name">腾讯</div>
    <span class="salary">25-40K·14薪</span>
    <div class="job-area">深圳·南山区</div>
    <div class="job-tag">
      <span>5-10年</span><span>本科</span><span>Python</span>
    </div>
  </li>
  <li class="job-card-wrapper" data-jobid="1002">
    <a class="job-title" href="/job_detail/1002.html">数据工程师</a>
    <div class="company-name">美团</div>
    <span class="salary">20-35K</span>
    <div class="job-area">北京</div>
    <div class="job-tag">
      <span>3-5年</span><span>本科</span>
    </div>
  </li>
  <li class="job-card-wrapper" data-jobid="1003">
    <a class="job-title" href="/job_detail/1003.html">后端架构师</a>
    <div class="company-name">小米</div>
    <span class="salary">40-70K</span>
    <div class="job-area">北京</div>
    <div class="job-tag">
      <span>10年以上</span><span>本科</span><span>Go</span><span>分布式</span>
    </div>
  </li>
</ul></body></html>
"""

EMPTY_HTML = "<html><body><div>no result</div></body></html>"
BROKEN_HTML = "<li class=\"job-card-wrapper\"><a class=\"job-title\" href=\""


def _boss_mock_factory(payload: str, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "zhipin.com" in str(request.url):
            return httpx.Response(status, text=payload)
        return httpx.Response(404, text="not mocked")
    return httpx.MockTransport(handler)


def _failing_factory() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("mock network down", request=request)
    return httpx.MockTransport(handler)


class TestBossZhipinParse(unittest.TestCase):

    def test_parse_extracts_three(self):
        results = BossZhipinChannel.parse(SAMPLE_HTML)
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertIsInstance(r, JobPosting)
            self.assertEqual(r.source, "bosszhipin")
            self.assertTrue(r.title)
            self.assertIn("zhipin.com", r.url)

    def test_parse_field_values(self):
        results = BossZhipinChannel.parse(SAMPLE_HTML)
        first = results[0]
        self.assertEqual(first.title, "Python 高级开发")
        self.assertEqual(first.company, "腾讯")
        self.assertEqual(first.salary, "25-40K·14薪")
        self.assertEqual(first.location, "深圳·南山区")
        self.assertEqual(first.id, "1001")
        # tags
        self.assertIn("Python", first.tags)

    def test_parse_empty(self):
        self.assertEqual(BossZhipinChannel.parse(EMPTY_HTML), [])

    def test_parse_broken_does_not_raise(self):
        results = BossZhipinChannel.parse(BROKEN_HTML)
        self.assertIsInstance(results, list)

    def test_parse_empty_string(self):
        self.assertEqual(BossZhipinChannel.parse(""), [])


class TestBossZhipinSearchAsync(unittest.TestCase):

    def test_search_returns_results(self):
        async def run():
            async with BossZhipinChannel(transport=_boss_mock_factory(SAMPLE_HTML)) as ch:
                return await ch.search("Python", max_results=10)
        results = asyncio.run(run())
        self.assertEqual(len(results), 3)
        self.assertIsInstance(results[0], CrawlResult)
        self.assertEqual(results[0].source, "bosszhipin")
        self.assertEqual(results[0].posting.title, "Python 高级开发")

    def test_search_max_results_truncation(self):
        async def run():
            async with BossZhipinChannel(transport=_boss_mock_factory(SAMPLE_HTML)) as ch:
                return await ch.search("Python", max_results=1)
        results = asyncio.run(run())
        self.assertEqual(len(results), 1)

    def test_search_network_failure(self):
        async def run():
            async with BossZhipinChannel(transport=_failing_factory(), timeout=2.0) as ch:
                return await ch.search("Python", max_results=5)
        results = asyncio.run(run())
        self.assertEqual(results, [])

    def test_search_empty_query(self):
        async def run():
            async with BossZhipinChannel(transport=_boss_mock_factory(SAMPLE_HTML)) as ch:
                return await ch.search("", max_results=5)
        results = asyncio.run(run())
        self.assertEqual(results, [])

    def test_pydantic_schema_roundtrip(self):
        results = BossZhipinChannel.parse(SAMPLE_HTML)
        js = results[0].model_dump_json()
        restored = JobPosting.model_validate_json(js)
        self.assertEqual(restored.id, results[0].id)
        self.assertEqual(restored.title, results[0].title)


class TestBossZhipinRateLimit(unittest.TestCase):

    def test_rate_limiter_enforces_interval(self):
        async def run():
            ch = BossZhipinChannel(
                transport=_boss_mock_factory(SAMPLE_HTML), rate_limit_rps=2.0,
            )
            import time
            t0 = time.monotonic()
            for _ in range(3):
                await ch._rate_limiter.acquire()
            elapsed = time.monotonic() - t0
            await ch.close()
            return elapsed
        elapsed = asyncio.run(run())
        self.assertGreaterEqual(elapsed, 0.9)


if __name__ == "__main__":
    unittest.main()
