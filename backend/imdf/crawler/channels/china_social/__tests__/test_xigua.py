"""xigua_test.py — XiguaChannel 单元测试 (P20-H)."""
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

from china_social.xigua import XiguaChannel
from china_social._base import CrawlResult, CrawlSearchRequest
from conftest import _run, _mock_transport, XIGUA_JSON


class TestXiguaParse(unittest.TestCase):

    def test_parse_json_extracts_two_videos(self):
        body = json.dumps(XIGUA_JSON)
        results = XiguaChannel.parse(body)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(r, CrawlResult) for r in results))

    def test_parse_json_video_fields(self):
        body = json.dumps(XIGUA_JSON)
        results = XiguaChannel.parse(body)
        r0 = results[0]
        self.assertEqual(r0.id, "xigua_7000000001")
        self.assertIn("红烧肉", r0.title)
        self.assertEqual(r0.author, "厨房日记")
        self.assertEqual(r0.source, "xigua")
        self.assertIn("ixigua.com", r0.url)
        self.assertIn("poster", r0.thumbnail_url)

    def test_parse_json_extra(self):
        body = json.dumps(XIGUA_JSON)
        results = XiguaChannel.parse(body)
        r0 = results[0]
        self.assertEqual(r0.extra["video_id"], "7000000001")
        self.assertEqual(r0.extra["play_count"], 12345)
        self.assertEqual(r0.extra["duration"], 320)

    def test_parse_invalid_json_returns_empty(self):
        self.assertEqual(XiguaChannel.parse("xxx"), [])
        self.assertEqual(XiguaChannel.parse(""), [])
        self.assertEqual(XiguaChannel.parse("{}"), [])

    def test_parse_html_with_initial_state(self):
        """回退: __INITIAL_STATE__ 嵌入 HTML."""
        html = (
            '<html><body><script>'
            'window.__INITIAL_STATE__ = ' +
            json.dumps({
                "data": {"searchResult": {"data": [
                    {"video_id": "v1", "title": "视频1",
                     "abstract": "简介1", "video_url": "https://www.ixigua.com/v1",
                     "user": "用户1", "poster_url": "https://example.com/p1.jpg"},
                    {"video_id": "v2", "title": "视频2",
                     "abstract": "简介2", "video_url": "https://www.ixigua.com/v2",
                     "user": "用户2", "poster_url": "https://example.com/p2.jpg"},
                ]}}
            }) +
            ';</script></body></html>'
        )
        results = XiguaChannel.parse(html)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "视频1")


class TestXiguaSearch(unittest.TestCase):

    def test_search_returns_results(self):
        def handler(req):
            return httpx.Response(200, json=XIGUA_JSON)
        cw = XiguaChannel(transport=_mock_transport(handler),
                          respect_robots=False)
        results = _run(cw.search("美食", max_results=10))
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.source == "xigua" for r in results))

    def test_search_max_results_caps(self):
        def handler(req):
            return httpx.Response(200, json=XIGUA_JSON)
        cw = XiguaChannel(transport=_mock_transport(handler),
                          respect_robots=False)
        results = _run(cw.search("美食", max_results=1))
        self.assertLessEqual(len(results), 1)

    def test_search_empty_returns_empty(self):
        def handler(req):
            return httpx.Response(200, json={"data": []})
        cw = XiguaChannel(transport=_mock_transport(handler),
                          respect_robots=False)
        results = _run(cw.search("nothing"))
        self.assertEqual(results, [])

    def test_search_5xx_returns_empty(self):
        def handler(req):
            return httpx.Response(500, text="error")
        cw = XiguaChannel(transport=_mock_transport(handler),
                          respect_robots=False)
        results = _run(cw.search("美食"))
        self.assertEqual(results, [])

    def test_search_request_pydantic(self):
        def handler(req):
            return httpx.Response(200, json=XIGUA_JSON)
        cw = XiguaChannel(transport=_mock_transport(handler),
                          respect_robots=False)
        req = CrawlSearchRequest(query="Python", max_results=5)
        results = _run(cw.search_request(req))
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()