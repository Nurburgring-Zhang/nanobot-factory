"""bilibilimp_test.py — BilibiliMPChannel 单元测试 (P20-H)."""
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

from china_social.bilibilimp import BilibiliMPChannel
from china_social._base import CrawlResult, CrawlSearchRequest
from conftest import _run, _mock_transport, BILIBILI_JSON


class TestBilibiliMPParse(unittest.TestCase):

    def test_parse_json_extracts_two_users(self):
        body = json.dumps(BILIBILI_JSON)
        results = BilibiliMPChannel.parse(body)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(r, CrawlResult) for r in results))

    def test_parse_json_user_fields(self):
        body = json.dumps(BILIBILI_JSON)
        results = BilibiliMPChannel.parse(body)
        r0 = results[0]
        self.assertEqual(r0.id, "bilibilimp_12345")
        self.assertEqual(r0.title, "Python 教程 UP 主")
        self.assertEqual(r0.author, "Python 教程 UP 主")
        self.assertEqual(r0.source, "bilibilimp")
        self.assertEqual(r0.url, "https://space.bilibili.com/12345")
        self.assertIn("bili_avatar", r0.thumbnail_url)
        self.assertIn("Python 教学", r0.description)

    def test_parse_json_extra(self):
        body = json.dumps(BILIBILI_JSON)
        results = BilibiliMPChannel.parse(body)
        r0 = results[0]
        self.assertEqual(r0.extra["mid"], 12345)
        self.assertEqual(r0.extra["level"], 6)
        self.assertEqual(r0.extra["fans"], 100000)
        self.assertEqual(r0.extra["videos"], 200)
        self.assertEqual(r0.extra["official_verify_type"], 0)
        self.assertEqual(r0.extra["official_verify_desc"], "知名 UP 主")

    def test_parse_invalid_json_returns_empty(self):
        self.assertEqual(BilibiliMPChannel.parse("xxx"), [])
        self.assertEqual(BilibiliMPChannel.parse(""), [])
        self.assertEqual(BilibiliMPChannel.parse("{}"), [])

    def test_parse_html_with_initial_state(self):
        """回退: __INITIAL_STATE__ 嵌入 HTML."""
        html = (
            '<html><body><script>'
            'window.__INITIAL_STATE__ = ' +
            json.dumps({
                "data": {"result": [
                    {"mid": 111, "uname": "用户1",
                     "usign": "签名1", "fans": 1000,
                     "upic": "https://example.com/u1.jpg"},
                    {"mid": 222, "uname": "用户2",
                     "usign": "签名2", "fans": 2000,
                     "upic": "https://example.com/u2.jpg"},
                ]}
            }) +
            ';</script></body></html>'
        )
        results = BilibiliMPChannel.parse(html)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "用户1")
        self.assertEqual(results[1].title, "用户2")


class TestBilibiliMPSearch(unittest.TestCase):

    def test_search_returns_results(self):
        def handler(req):
            return httpx.Response(200, json=BILIBILI_JSON)
        cw = BilibiliMPChannel(transport=_mock_transport(handler),
                               respect_robots=False)
        results = _run(cw.search("Python", max_results=10))
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.source == "bilibilimp" for r in results))

    def test_search_max_results_caps(self):
        def handler(req):
            return httpx.Response(200, json=BILIBILI_JSON)
        cw = BilibiliMPChannel(transport=_mock_transport(handler),
                               respect_robots=False)
        results = _run(cw.search("Python", max_results=1))
        self.assertLessEqual(len(results), 1)

    def test_search_empty_result_returns_empty(self):
        def handler(req):
            return httpx.Response(200, json={
                "code": 0, "data": {"result": []}
            })
        cw = BilibiliMPChannel(transport=_mock_transport(handler),
                               respect_robots=False)
        results = _run(cw.search("nothing"))
        self.assertEqual(results, [])

    def test_search_5xx_returns_empty(self):
        def handler(req):
            return httpx.Response(500, text="error")
        cw = BilibiliMPChannel(transport=_mock_transport(handler),
                               respect_robots=False)
        results = _run(cw.search("Python"))
        self.assertEqual(results, [])

    def test_search_request_pydantic(self):
        def handler(req):
            return httpx.Response(200, json=BILIBILI_JSON)
        cw = BilibiliMPChannel(transport=_mock_transport(handler),
                               respect_robots=False)
        req = CrawlSearchRequest(query="Python", max_results=5)
        results = _run(cw.search_request(req))
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()