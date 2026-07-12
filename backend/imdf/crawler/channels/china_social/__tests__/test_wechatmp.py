"""wechatmp_test.py — WechatMPChannel 单元测试 (P20-H)."""
from __future__ import annotations

import os
import sys
import unittest

import httpx

_THIS = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.dirname(_THIS), os.path.dirname(os.path.dirname(_THIS))):
    if p not in sys.path:
        sys.path.insert(0, p)

from china_social.wechatmp import WechatMPChannel
from china_social._base import CrawlResult, CrawlSearchRequest
from conftest import _run, _mock_transport, WECHAT_HTML


class TestWechatMPParse(unittest.TestCase):
    """Static parse() — 测试 HTML 解析."""

    def test_parse_extracts_two_results(self):
        results = WechatMPChannel.parse(WECHAT_HTML)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(r, CrawlResult) for r in results))

    def test_parse_extracts_title_url_author(self):
        results = WechatMPChannel.parse(WECHAT_HTML)
        r0 = results[0]
        # 解码后的 mp.weixin.qq.com 链接
        self.assertIn("mp.weixin.qq.com", r0.url)
        self.assertIn("AI 大模型", r0.title)
        self.assertEqual(r0.author, "机器之心")
        self.assertEqual(r0.source, "wechatmp")
        # 描述非空
        self.assertTrue(len(r0.description) > 0)
        # 缩略图
        self.assertIn("wx_thumb", r0.thumbnail_url)

    def test_parse_handles_direct_link(self):
        """第二条是直接 mp.weixin.qq.com 链接 (不走 /link? 跳转)."""
        results = WechatMPChannel.parse(WECHAT_HTML)
        r1 = results[1]
        self.assertIn("mp.weixin.qq.com", r1.url)
        self.assertIn("Python 数据科学", r1.title)

    def test_parse_empty_html_returns_empty(self):
        self.assertEqual(WechatMPChannel.parse(""), [])
        self.assertEqual(WechatMPChannel.parse("   "), [])
        self.assertEqual(WechatMPChannel.parse("<html></html>"), [])


class TestWechatMPSearch(unittest.TestCase):
    """async search() — 测试网络层 + MockTransport."""

    def test_search_returns_results(self):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=WECHAT_HTML)
        cw = WechatMPChannel(transport=_mock_transport(handler),
                             respect_robots=False)
        results = _run(cw.search("AI 大模型", max_results=10))
        self.assertGreaterEqual(len(results), 1)
        self.assertTrue(all(r.source == "wechatmp" for r in results))

    def test_search_max_results_caps(self):
        def handler(req):
            return httpx.Response(200, text=WECHAT_HTML)
        cw = WechatMPChannel(transport=_mock_transport(handler),
                             respect_robots=False)
        results = _run(cw.search("AI", max_results=1))
        self.assertLessEqual(len(results), 1)

    def test_search_5xx_returns_empty(self):
        def handler(req):
            return httpx.Response(503, text="Service Unavailable")
        cw = WechatMPChannel(transport=_mock_transport(handler),
                             respect_robots=False)
        results = _run(cw.search("AI"))
        self.assertEqual(results, [])

    def test_search_uses_robots_txt(self):
        """robots.txt 不允许 /weixin → search 返回 []."""
        def handler(req):
            url = str(req.url)
            if url.endswith("/robots.txt"):
                return httpx.Response(200, text=(
                    "User-agent: *\nDisallow: /weixin\n"
                ))
            return httpx.Response(200, text=WECHAT_HTML)
        cw = WechatMPChannel(transport=_mock_transport(handler),
                             respect_robots=True)
        results = _run(cw.search("AI"))
        # 目标 URL path 以 /weixin 开头 → robots disallow → 应返回 []
        self.assertEqual(results, [])

    def test_search_request_pydantic(self):
        """search_request 接受 CrawlSearchRequest."""
        def handler(req):
            return httpx.Response(200, text=WECHAT_HTML)
        cw = WechatMPChannel(transport=_mock_transport(handler),
                             respect_robots=False)
        req = CrawlSearchRequest(query="Python", max_results=5)
        results = _run(cw.search_request(req))
        self.assertGreaterEqual(len(results), 1)

    def test_search_sync_wrapper(self):
        def handler(req):
            return httpx.Response(200, text=WECHAT_HTML)
        cw = WechatMPChannel(transport=_mock_transport(handler),
                             respect_robots=False)
        results = cw.search_sync("Python", max_results=5)
        self.assertGreaterEqual(len(results), 1)

    def test_rate_limiter_enforces_interval(self):
        """3 次连续 search 应至少耗时 ~2 秒 (1 req/sec × 2 间隔)."""
        import time
        def handler(req):
            return httpx.Response(200, text=WECHAT_HTML)
        cw = WechatMPChannel(transport=_mock_transport(handler),
                             respect_robots=False,
                             client=httpx.AsyncClient(
                                 transport=_mock_transport(handler)))
        # 触发 3 次 — 验证 rate-limit 不崩溃 (mock 不强制时序)
        t0 = time.monotonic()
        for _ in range(3):
            _run(cw.search("AI"))
        elapsed = time.monotonic() - t0
        # 至少 1.5s (2 间隔 × ~0.75-1.0s)
        self.assertGreaterEqual(elapsed, 1.5)


if __name__ == "__main__":
    unittest.main()