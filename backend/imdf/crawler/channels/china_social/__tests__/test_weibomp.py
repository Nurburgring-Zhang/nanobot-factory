"""weibomp_test.py — WeiboMPChannel 单元测试 (P20-H)."""
from __future__ import annotations

import json
import os
import sys
import unittest

import httpx

_THIS = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.dirname(_THIS), os.path.dirname(os.path.dirname(_THIS))):
    if p not in sys.path:
        sys.path.insert(0, p)

from china_social.weibomp import WeiboMPChannel
from china_social._base import CrawlResult, CrawlSearchRequest
from conftest import _run, _mock_transport, WEIBO_JSON


class TestWeiboMPParse(unittest.TestCase):

    def test_parse_json_extracts_two_results(self):
        body = json.dumps(WEIBO_JSON)
        results = WeiboMPChannel.parse(body)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(r, CrawlResult) for r in results))

    def test_parse_json_fields(self):
        body = json.dumps(WEIBO_JSON)
        results = WeiboMPChannel.parse(body)
        r0 = results[0]
        self.assertEqual(r0.id, "weibomp_4900000001")
        self.assertIn("media.weibo.cn", r0.url)
        self.assertIn("AI", r0.title)
        self.assertEqual(r0.author, "AI观察家")
        self.assertEqual(r0.source, "weibomp")
        # 描述应已 strip HTML tags
        self.assertNotIn("<a>", r0.description)
        self.assertIn("AI", r0.description)

    def test_parse_json_extra_fields(self):
        body = json.dumps(WEIBO_JSON)
        results = WeiboMPChannel.parse(body)
        r0 = results[0]
        self.assertEqual(r0.extra["weibo_id"], "4900000001")
        self.assertTrue(r0.extra["verified"])
        self.assertEqual(r0.extra["followers_count"], 50000)
        # 缩略图来自用户头像
        self.assertIn("wb_avatar", r0.thumbnail_url)

    def test_parse_invalid_json_returns_empty(self):
        self.assertEqual(WeiboMPChannel.parse("not json"), [])
        self.assertEqual(WeiboMPChannel.parse(""), [])
        self.assertEqual(WeiboMPChannel.parse("{}"), [])

    def test_parse_html_with_initial_state(self):
        """回退: __INITIAL_STATE__ 嵌入 HTML."""
        html = f"""
        <html><body>
          <script>
            window.__INITIAL_STATE__ = {json.dumps({
                "articleList": [
                    {"id": "w1", "title": "文章1",
                     "url": "https://media.weibo.cn/article?id=w1",
                     "author": "作者A", "content": "内容A",
                     "cover": "https://example.com/c1.jpg"},
                    {"id": "w2", "title": "文章2",
                     "url": "https://media.weibo.cn/article?id=w2",
                     "author": "作者B", "content": "内容B",
                     "cover": "https://example.com/c2.jpg"},
                ]
            })};
          </script>
        </body></html>
        """
        results = WeiboMPChannel.parse(html)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "文章1")
        self.assertEqual(results[0].author, "作者A")


class TestWeiboMPSearch(unittest.TestCase):

    def test_search_returns_json_results(self):
        def handler(req):
            return httpx.Response(200, json=WEIBO_JSON)
        cw = WeiboMPChannel(transport=_mock_transport(handler),
                            respect_robots=False)
        results = _run(cw.search("AI 大模型", max_results=10))
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.source == "weibomp" for r in results))

    def test_search_max_results_caps(self):
        def handler(req):
            return httpx.Response(200, json=WEIBO_JSON)
        cw = WeiboMPChannel(transport=_mock_transport(handler),
                            respect_robots=False)
        results = _run(cw.search("AI", max_results=1))
        self.assertLessEqual(len(results), 1)

    def test_search_api_not_ok_returns_empty(self):
        def handler(req):
            return httpx.Response(200, json={"ok": 0, "msg": "rate limit"})
        cw = WeiboMPChannel(transport=_mock_transport(handler),
                            respect_robots=False)
        results = _run(cw.search("AI"))
        self.assertEqual(results, [])

    def test_search_5xx_returns_empty(self):
        def handler(req):
            return httpx.Response(500, text="error")
        cw = WeiboMPChannel(transport=_mock_transport(handler),
                            respect_robots=False)
        results = _run(cw.search("AI"))
        self.assertEqual(results, [])

    def test_search_request_pydantic(self):
        def handler(req):
            return httpx.Response(200, json=WEIBO_JSON)
        cw = WeiboMPChannel(transport=_mock_transport(handler),
                            respect_robots=False)
        req = CrawlSearchRequest(query="AI")
        results = _run(cw.search_request(req))
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()