"""test_job51.py — 前程无忧 (51job) 渠道适配器测试 (P20-B2)

覆盖: parse 提取 / 容错 / 异步 search / 网络失败 / 限速 / 截断 / schema
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import unittest
from typing import Any

import httpx

_THIS = os.path.dirname(os.path.abspath(__file__))
_JOBS_DIR = os.path.dirname(_THIS)
_CHANNELS_DIR = os.path.dirname(_JOBS_DIR)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_CHANNELS_DIR)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from imdf.crawler.channels.jobs import CrawlResult, Job51Channel, JobPosting  # noqa: E402


SAMPLE_HTML = """
<!DOCTYPE html>
<html><body><div class="jjoblist">
  <div class="el">
    <p class="t1">
      <a class="el" href="https://jobs.51job.com/all/co1234567.html">Python 高级开发工程师</a>
    </p>
    <span class="t2">网易</span>
    <span class="t3">20-35万/年</span>
    <span class="t4">杭州</span>
    <span class="t5">5-10年|本科</span>
    <span class="t6">互联网|上市公司</span>
    <div class="t7"><span>弹性工作</span><span>五险一金</span></div>
  </div>
  <div class="el">
    <p class="t1">
      <a class="el" href="https://jobs.51job.com/all/co7654321.html">数据分析师</a>
    </p>
    <span class="t2">携程</span>
    <span class="t3">15-25K·13薪</span>
    <span class="t4">上海</span>
    <span class="t5">3-5年|本科</span>
  </div>
  <div class="el">
    <p class="t1">
      <a class="el" href="https://jobs.51job.com/all/co9999999.html">运维开发工程师</a>
    </p>
    <span class="t2">滴滴</span>
    <span class="t3">18-30K</span>
    <span class="t4">北京</span>
    <span class="t5">3-5年|本科</span>
    <div class="t7"><span>补充医疗</span></div>
  </div>
</div></body></html>
"""

EMPTY_HTML = "<html><body><div class='empty'>没有找到相关职位</div></body></html>"
BROKEN_HTML = "<div class=\"el\"><p class=\"t1\"><a class=\"el\" href=\""


def _job51_mock_factory(payload: str, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "51job.com" in str(request.url):
            return httpx.Response(status, text=payload)
        return httpx.Response(404, text="not mocked")
    return httpx.MockTransport(handler)


def _failing_factory() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("mock network down", request=request)
    return httpx.MockTransport(handler)


class TestJob51Parse(unittest.TestCase):

    def test_parse_extracts_three(self):
        results = Job51Channel.parse(SAMPLE_HTML)
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertIsInstance(r, JobPosting)
            self.assertEqual(r.source, "job51")

    def test_parse_field_values(self):
        results = Job51Channel.parse(SAMPLE_HTML)
        first = results[0]
        self.assertEqual(first.title, "Python 高级开发工程师")
        self.assertEqual(first.company, "网易")
        self.assertEqual(first.salary, "20-35万/年")
        self.assertEqual(first.location, "杭州")
        self.assertIn("5-10", first.extra.get("experience", ""))
        self.assertIn("互联网", first.extra.get("company_type", ""))
        self.assertIn("弹性工作", first.tags)

    def test_parse_empty(self):
        self.assertEqual(Job51Channel.parse(EMPTY_HTML), [])

    def test_parse_broken_does_not_raise(self):
        results = Job51Channel.parse(BROKEN_HTML)
        self.assertIsInstance(results, list)

    def test_parse_empty_string(self):
        self.assertEqual(Job51Channel.parse(""), [])


class TestJob51SearchAsync(unittest.TestCase):

    def test_search_returns_results(self):
        async def run():
            async with Job51Channel(transport=_job51_mock_factory(SAMPLE_HTML)) as ch:
                return await ch.search("Python", max_results=10)
        results = asyncio.run(run())
        self.assertEqual(len(results), 3)
        self.assertIsInstance(results[0], CrawlResult)
        self.assertEqual(results[0].source, "job51")
        self.assertEqual(results[0].posting.title, "Python 高级开发工程师")

    def test_search_max_results_truncation(self):
        async def run():
            async with Job51Channel(transport=_job51_mock_factory(SAMPLE_HTML)) as ch:
                return await ch.search("Python", max_results=1)
        results = asyncio.run(run())
        self.assertEqual(len(results), 1)

    def test_search_network_failure(self):
        async def run():
            async with Job51Channel(transport=_failing_factory(), timeout=2.0) as ch:
                return await ch.search("Python", max_results=5)
        results = asyncio.run(run())
        self.assertEqual(results, [])

    def test_search_empty_query(self):
        async def run():
            async with Job51Channel(transport=_job51_mock_factory(SAMPLE_HTML)) as ch:
                return await ch.search("", max_results=5)
        results = asyncio.run(run())
        self.assertEqual(results, [])

    def test_pydantic_schema_roundtrip(self):
        results = Job51Channel.parse(SAMPLE_HTML)
        js = results[0].model_dump_json()
        restored = JobPosting.model_validate_json(js)
        self.assertEqual(restored.id, results[0].id)
        self.assertEqual(restored.title, results[0].title)


class TestJob51RateLimit(unittest.TestCase):

    def test_rate_limiter_enforces_interval(self):
        async def run():
            ch = Job51Channel(
                transport=_job51_mock_factory(SAMPLE_HTML), rate_limit_rps=2.0,
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
