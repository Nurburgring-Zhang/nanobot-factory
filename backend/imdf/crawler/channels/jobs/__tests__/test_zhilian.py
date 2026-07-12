"""test_zhilian.py — 智联招聘 渠道适配器测试 (P20-B2)

覆盖: parse 提取 / 容错 / 异步 search / 网络失败 / 限速 / 截断 / schema
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
import time
from typing import Any

import httpx

_THIS = os.path.dirname(os.path.abspath(__file__))
_JOBS_DIR = os.path.dirname(_THIS)
_CHANNELS_DIR = os.path.dirname(_JOBS_DIR)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_CHANNELS_DIR)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from imdf.crawler.channels.jobs import CrawlResult, JobPosting, ZhilianChannel  # noqa: E402


SAMPLE_HTML = """
<!DOCTYPE html>
<html><body><div class="joblist">
  <div class="joblist-box__item">
    <a class="jobinfo__name" href="/jobs/CC123456789J.html">Python 工程师</a>
    <div class="company__name">华为</div>
    <p class="jobinfo__salary">15-25K·14薪</p>
    <div class="jobinfo__other">北京·海淀区|3-5年|本科</div>
    <div class="welfare"><span class="welfare__item">五险一金</span><span class="welfare__item">弹性工作</span></div>
  </div>
  <div class="joblist-box__item">
    <a class="jobinfo__name" href="/jobs/CC987654321J.html">数据科学家</a>
    <div class="company__name">京东</div>
    <p class="jobinfo__salary">30-50K</p>
    <div class="jobinfo__other">上海|5-10年|硕士</div>
  </div>
  <div class="joblist-box__item">
    <a class="jobinfo__name" href="/jobs/CC111111111J.html">AI 工程师</a>
    <div class="company__name">百度</div>
    <p class="jobinfo__salary">25-45K·15薪</p>
    <div class="jobinfo__other">北京|经验不限|博士</div>
  </div>
</div></body></html>
"""

EMPTY_HTML = "<html><body><p>no jobs found</p></body></html>"
BROKEN_HTML = "<div class=\"joblist-box__item\"><a class=\"jobinfo__name\""


def _zhaopin_mock_factory(payload: str, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "zhaopin.com" in str(request.url):
            return httpx.Response(status, text=payload)
        return httpx.Response(404, text="not mocked")
    return httpx.MockTransport(handler)


def _failing_factory() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("mock network down", request=request)
    return httpx.MockTransport(handler)


class TestZhilianParse(unittest.TestCase):

    def test_parse_extracts_three(self):
        results = ZhilianChannel.parse(SAMPLE_HTML)
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertIsInstance(r, JobPosting)
            self.assertEqual(r.source, "zhilian")

    def test_parse_field_values(self):
        results = ZhilianChannel.parse(SAMPLE_HTML)
        first = results[0]
        self.assertEqual(first.title, "Python 工程师")
        self.assertEqual(first.company, "华为")
        self.assertEqual(first.salary, "15-25K·14薪")
        self.assertIn("北京", first.location)
        self.assertIn("3-5", first.extra.get("experience", ""))
        self.assertIn("本科", first.extra.get("education", ""))
        # 福利标签
        self.assertIn("五险一金", first.tags)

    def test_parse_empty(self):
        self.assertEqual(ZhilianChannel.parse(EMPTY_HTML), [])

    def test_parse_broken_does_not_raise(self):
        results = ZhilianChannel.parse(BROKEN_HTML)
        self.assertIsInstance(results, list)

    def test_parse_empty_string(self):
        self.assertEqual(ZhilianChannel.parse(""), [])


class TestZhilianSearchAsync(unittest.TestCase):

    def test_search_returns_results(self):
        async def run():
            async with ZhilianChannel(transport=_zhaopin_mock_factory(SAMPLE_HTML)) as ch:
                return await ch.search("Python", max_results=10)
        results = asyncio.run(run())
        self.assertEqual(len(results), 3)
        self.assertIsInstance(results[0], CrawlResult)
        self.assertEqual(results[0].source, "zhilian")
        self.assertEqual(results[0].posting.title, "Python 工程师")

    def test_search_max_results_truncation(self):
        async def run():
            async with ZhilianChannel(transport=_zhaopin_mock_factory(SAMPLE_HTML)) as ch:
                return await ch.search("Python", max_results=2)
        results = asyncio.run(run())
        self.assertEqual(len(results), 2)

    def test_search_network_failure(self):
        async def run():
            async with ZhilianChannel(transport=_failing_factory(), timeout=2.0) as ch:
                return await ch.search("Python", max_results=5)
        results = asyncio.run(run())
        self.assertEqual(results, [])

    def test_search_empty_query(self):
        async def run():
            async with ZhilianChannel(transport=_zhaopin_mock_factory(SAMPLE_HTML)) as ch:
                return await ch.search("   ", max_results=5)
        results = asyncio.run(run())
        self.assertEqual(results, [])

    def test_pydantic_schema_roundtrip(self):
        results = ZhilianChannel.parse(SAMPLE_HTML)
        js = results[0].model_dump_json()
        restored = JobPosting.model_validate_json(js)
        self.assertEqual(restored.id, results[0].id)
        self.assertEqual(restored.title, results[0].title)


class TestZhilianRateLimit(unittest.TestCase):

    def test_rate_limiter_enforces_interval(self):
        async def run():
            ch = ZhilianChannel(
                transport=_zhaopin_mock_factory(SAMPLE_HTML), rate_limit_rps=2.0,
            )
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
