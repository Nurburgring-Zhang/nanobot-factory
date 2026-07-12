"""test_lagou.py — Lagou (拉勾网) 渠道适配器测试 (P20-B2)

测试覆盖:
    1. parse() 静态解析 — 提取职位卡片
    2. parse() 容错 — 烂 HTML 不抛
    3. async search() 通过 httpx.MockTransport 拿到结果
    4. 网络失败优雅返回 []
    5. rate-limit 验证 (1 req/sec 不会被 fast-loop 跳过)
    6. max_results 截断
    7. Pydantic v2 JobPosting schema 字段
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import unittest
from typing import Any, Dict

import httpx

_THIS = os.path.dirname(os.path.abspath(__file__))
_JOBS_DIR = os.path.dirname(_THIS)
_CHANNELS_DIR = os.path.dirname(_JOBS_DIR)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_CHANNELS_DIR)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from imdf.crawler.channels.jobs import CrawlResult, JobPosting, LagouChannel  # noqa: E402


# ============================================================
# Sample HTML fixtures
# ============================================================
SAMPLE_HTML = """
<!DOCTYPE html>
<html><body><div class="list">
  <div class="item__10RTO">
    <a class="position_link" href="/jobs/12345.html">高级 Python 工程师</a>
    <div class="company_name__2-x_P">阿里巴巴</div>
    <span class="money__3Lkgq">30-50K·16 薪</span>
    <div class="p_top__1SC7r">
      <span>北京</span><span>5-10 年</span><span>本科</span>
    </div>
    <div class="li_b_r"><span>弹性工作</span><span>六险一金</span></div>
  </div>
  <div class="item__10RTO">
    <a class="position_link" href="/jobs/67890.html">后端开发 (Go/Python)</a>
    <div class="company_name__2-x_P">字节跳动</div>
    <span class="money__3Lkgq">25-45K</span>
    <div class="p_top__1SC7r">
      <span>上海</span><span>3-5 年</span><span>本科</span>
    </div>
    <div class="li_b_r"><span>免费三餐</span></div>
  </div>
  <div class="item__10RTO">
    <a class="position_link" href="/jobs/11111.html">Python 数据工程师</a>
    <div class="company_name__2-x_P">美团</div>
    <span class="money__3Lkgq">20-35K</span>
    <div class="p_top__1SC7r">
      <span>深圳</span><span>1-3 年</span><span>硕士</span>
    </div>
  </div>
</div></body></html>
"""

EMPTY_HTML = "<html><body><div class='empty'>no jobs</div></body></html>"

BROKEN_HTML = "<html><body><div class=\"item__10RTO\"><a class=\"position_link\""


# ============================================================
# Mock factories
# ============================================================
def _lagou_mock_factory(payload: str, status: int = 200) -> httpx.MockTransport:
    """Mock transport — 返回固定 HTML."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "lagou.com" in str(request.url):
            return httpx.Response(status, text=payload)
        return httpx.Response(404, text="not mocked")
    return httpx.MockTransport(handler)


def _failing_factory(*args: Any, **kwargs: Any) -> httpx.MockTransport:
    """Mock transport — 全部失败 (模拟断网)."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("mock network down", request=request)
    return httpx.MockTransport(handler)


# ============================================================
# Tests
# ============================================================
class TestLagouParse(unittest.TestCase):
    """静态 parse() 测试 — 不走网络."""

    def test_parse_extracts_three_postings(self):
        results = LagouChannel.parse(SAMPLE_HTML)
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertIsInstance(r, JobPosting)
            self.assertEqual(r.source, "lagou")
            self.assertTrue(r.title)
            self.assertTrue(r.url)

    def test_parse_field_values(self):
        results = LagouChannel.parse(SAMPLE_HTML)
        first = results[0]
        self.assertEqual(first.title, "高级 Python 工程师")
        self.assertEqual(first.company, "阿里巴巴")
        self.assertEqual(first.salary, "30-50K·16 薪")
        self.assertEqual(first.location, "北京")
        self.assertIn("12345", first.id)
        self.assertIn("5-10", first.extra.get("experience", ""))
        self.assertIn("本科", first.extra.get("education", ""))

    def test_parse_empty(self):
        results = LagouChannel.parse(EMPTY_HTML)
        self.assertEqual(results, [])

    def test_parse_broken_html_does_not_raise(self):
        """烂 HTML 不应抛 — 返回空或部分结果."""
        results = LagouChannel.parse(BROKEN_HTML)
        self.assertIsInstance(results, list)

    def test_parse_empty_string(self):
        self.assertEqual(LagouChannel.parse(""), [])


class TestLagouSearchAsync(unittest.TestCase):
    """async search() 测试 — 走 httpx.MockTransport."""

    def test_search_returns_results(self):
        async def run():
            async with LagouChannel(transport=_lagou_mock_factory(SAMPLE_HTML)) as ch:
                results = await ch.search("Python", max_results=10)
                return results
        results = asyncio.run(run())
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 3)
        self.assertIsInstance(results[0], CrawlResult)
        self.assertEqual(results[0].source, "lagou")
        self.assertEqual(results[0].posting.title, "高级 Python 工程师")

    def test_search_max_results_truncation(self):
        async def run():
            async with LagouChannel(transport=_lagou_mock_factory(SAMPLE_HTML)) as ch:
                return await ch.search("Python", max_results=2)
        results = asyncio.run(run())
        self.assertEqual(len(results), 2)

    def test_search_network_failure_returns_empty(self):
        async def run():
            async with LagouChannel(transport=_failing_factory(), timeout=2.0) as ch:
                return await ch.search("Python", max_results=5)
        results = asyncio.run(run())
        self.assertEqual(results, [])

    def test_search_empty_query(self):
        async def run():
            async with LagouChannel(transport=_lagou_mock_factory(SAMPLE_HTML)) as ch:
                return await ch.search("", max_results=5)
        results = asyncio.run(run())
        self.assertEqual(results, [])

    def test_search_max_results_clamp_upper(self):
        """max_results > 100 应被截到 100 (不报错)."""
        async def run():
            async with LagouChannel(transport=_lagou_mock_factory(SAMPLE_HTML)) as ch:
                return await ch.search("Python", max_results=9999)
        results = asyncio.run(run())
        self.assertLessEqual(len(results), 100)

    def test_pydantic_schema_roundtrip(self):
        """JobPosting 序列化 + 反序列化."""
        results = LagouChannel.parse(SAMPLE_HTML)
        js = results[0].model_dump_json()
        restored = JobPosting.model_validate_json(js)
        self.assertEqual(restored.title, results[0].title)
        self.assertEqual(restored.company, results[0].company)
        self.assertEqual(restored.id, results[0].id)


class TestLagouRateLimit(unittest.TestCase):
    """1 req/sec 限速验证."""

    def test_rate_limiter_enforces_interval(self):
        async def run():
            ch = LagouChannel(transport=_lagou_mock_factory(SAMPLE_HTML), rate_limit_rps=2.0)
            t0 = time.monotonic()
            for _ in range(3):
                await ch._rate_limiter.acquire()
            elapsed = time.monotonic() - t0
            await ch.close()
            return elapsed
        elapsed = asyncio.run(run())
        # 2 rps = 0.5s 间隔, 3 次至少 1.0s (允许 0.1s 误差)
        self.assertGreaterEqual(elapsed, 0.9)


if __name__ == "__main__":
    unittest.main()
