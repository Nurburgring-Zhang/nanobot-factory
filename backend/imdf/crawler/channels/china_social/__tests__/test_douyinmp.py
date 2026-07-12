"""douyinmp_test.py — DouyinMPChannel 单元测试 (P20-H)."""
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

from china_social.douyinmp import DouyinMPChannel
from china_social._base import CrawlResult, CrawlSearchRequest
from conftest import _run, _mock_transport, DOUYIN_JSON


class TestDouyinMPParse(unittest.TestCase):

    def test_parse_json_extracts_two_users(self):
        body = json.dumps(DOUYIN_JSON)
        results = DouyinMPChannel.parse(body)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(r, CrawlResult) for r in results))

    def test_parse_json_user_fields(self):
        body = json.dumps(DOUYIN_JSON)
        results = DouyinMPChannel.parse(body)
        r0 = results[0]
        self.assertEqual(r0.id, "douyinmp_100000001")
        self.assertEqual(r0.title, "美食探店达人")
        self.assertEqual(r0.author, "美食探店达人")
        self.assertEqual(r0.source, "douyinmp")
        self.assertIn("douyin.com", r0.url)
        # 描述 = signature
        self.assertIn("美食", r0.description)

    def test_parse_json_extra(self):
        body = json.dumps(DOUYIN_JSON)
        results = DouyinMPChannel.parse(body)
        r0 = results[0]
        self.assertEqual(r0.extra["uid"], "100000001")
        self.assertEqual(r0.extra["follower_count"], 1234567)
        self.assertEqual(r0.extra["aweme_count"], 200)
        self.assertIn("dy_avatar", r0.thumbnail_url)

    def test_parse_invalid_json_returns_empty(self):
        self.assertEqual(DouyinMPChannel.parse("xxx"), [])
        self.assertEqual(DouyinMPChannel.parse(""), [])
        self.assertEqual(DouyinMPChannel.parse("{}"), [])

    def test_parse_html_with_router_data(self):
        """回退: _ROUTER_DATA 嵌入 HTML."""
        html = f"""
        <html><body>
          <script>
            window._ROUTER_DATA = {json.dumps({
                "data": {"user_list": [
                    {"user_info": {
                        "uid": "u1", "nickname": "用户1",
                        "signature": "签名1",
                        "sec_uid": "SEC1",
                        "follower_count": 100, "aweme_count": 5,
                    }},
                    {"user_info": {
                        "uid": "u2", "nickname": "用户2",
                        "signature": "签名2",
                        "sec_uid": "SEC2",
                        "follower_count": 200, "aweme_count": 10,
                    }},
                ]}
            })};
          </script>
        </body></html>
        """
        results = DouyinMPChannel.parse(html)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "用户1")
        self.assertEqual(results[0].author, "用户1")


class TestDouyinMPSearch(unittest.TestCase):

    def test_search_returns_results(self):
        def handler(req):
            return httpx.Response(200, json=DOUYIN_JSON)
        cw = DouyinMPChannel(transport=_mock_transport(handler),
                             respect_robots=False)
        results = _run(cw.search("美食", max_results=10))
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.source == "douyinmp" for r in results))

    def test_search_max_results_caps(self):
        def handler(req):
            return httpx.Response(200, json=DOUYIN_JSON)
        cw = DouyinMPChannel(transport=_mock_transport(handler),
                             respect_robots=False)
        results = _run(cw.search("美食", max_results=1))
        self.assertLessEqual(len(results), 1)

    def test_search_empty_user_list(self):
        def handler(req):
            return httpx.Response(200, json={"status_code": 0, "user_list": []})
        cw = DouyinMPChannel(transport=_mock_transport(handler),
                             respect_robots=False)
        results = _run(cw.search("nothing"))
        self.assertEqual(results, [])

    def test_search_5xx_returns_empty(self):
        def handler(req):
            return httpx.Response(500, text="error")
        cw = DouyinMPChannel(transport=_mock_transport(handler),
                             respect_robots=False)
        results = _run(cw.search("美食"))
        self.assertEqual(results, [])

    def test_search_request_pydantic(self):
        def handler(req):
            return httpx.Response(200, json=DOUYIN_JSON)
        cw = DouyinMPChannel(transport=_mock_transport(handler),
                             respect_robots=False)
        req = CrawlSearchRequest(query="Python", max_results=5)
        results = _run(cw.search_request(req))
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()