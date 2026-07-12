"""test_api_crawler.py — APICrawler + GraphQLCrawler 测试"""
import json
import os
import sys
import unittest
from typing import Any, Dict, Optional, Tuple

_THIS = os.path.dirname(os.path.abspath(__file__))
_CRAWLER_DIR = os.path.dirname(_THIS)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_CRAWLER_DIR)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from imdf.crawler.api_crawler import APICrawler, GraphQLCrawler, PaginationConfig
from imdf.crawler.base import CrawlStatus, CrawlResult
from imdf.crawler.config import (
    CrawlerConfig, make_default_config, AuthConfig, AuthType, RobotsPolicy,
)


class MockHTTPResponse:
    """Mock HTTP response"""
    def __init__(self, status_code: int = 200, body: Any = None, headers: Optional[Dict[str, str]] = None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.text = json.dumps(self._body) if not isinstance(self._body, str) else self._body

    def json(self):
        if isinstance(self._body, (dict, list)):
            return self._body
        return json.loads(self._body)


class MockHTTPClient:
    """Mock HTTP client — 可配置按 URL 返回不同 response

    matching: 优先尝试响应 key 包含完整 URL; 否则把 params 合并到 URL 再匹配.
    """
    def __init__(self, responses: Optional[Dict[str, MockHTTPResponse]] = None,
                 default_response: Optional[MockHTTPResponse] = None):
        self.responses = responses or {}
        self.default_response = default_response or MockHTTPResponse(200, {})
        self.calls: list = []

    def request(self, method: str, url: str, **kwargs) -> MockHTTPResponse:
        # 构造完整 URL (含 params) 用于匹配
        params = kwargs.get("params") or {}
        if params:
            from urllib.parse import urlencode
            sep = "&" if "?" in url else "?"
            url_with_params = url + sep + urlencode(params, doseq=True)
        else:
            url_with_params = url
        self.calls.append({"method": method, "url": url, "url_with_params": url_with_params, **kwargs})
        for k, resp in self.responses.items():
            if k in url_with_params:
                return resp
        return self.default_response


class TestAPICrawler(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("api")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False

    def test_basic_get_request(self):
        client = MockHTTPClient(default_response=MockHTTPResponse(
            200, {"items": [{"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}]}
        ))
        cw = APICrawler(config=self.cfg, http_client=client)
        result = cw.crawl({"url": "https://api.example.com/list", "method": "GET"})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 2)
        self.assertEqual(result.items[0]["name"], "alpha")

    def test_post_json_body(self):
        client = MockHTTPClient(default_response=MockHTTPResponse(
            200, {"id": 1, "created": True}
        ))
        cw = APICrawler(config=self.cfg, http_client=client)
        result = cw.crawl({
            "url": "https://api.example.com/items",
            "method": "POST",
            "json": {"name": "new_item"},
        })
        self.assertTrue(result.ok)
        self.assertEqual(result.items[0]["created"], True)
        # Verify request
        call = client.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["json"], {"name": "new_item"})

    def test_pagination_offset(self):
        # offset=0: 50 items
        # offset=50: 30 items (不足 page_size, 停止)
        responses = {
            "offset=50": MockHTTPResponse(200, {"items": [{"i": i} for i in range(50, 80)]}),
        }
        client = MockHTTPClient(
            responses=responses,
            default_response=MockHTTPResponse(200, {"items": [{"i": i} for i in range(50)]}),
        )
        cw = APICrawler(config=self.cfg, http_client=client)
        result = cw.crawl({
            "url": "https://api.example.com/items",
            "pagination": {"mode": "offset", "page_size": 50, "max_pages": 10},
        })
        self.assertTrue(result.ok)
        # 应该有 50 + 30 = 80 items
        self.assertEqual(len(result.items), 80)
        # 验证两页都 fetch 了
        self.assertEqual(len(client.calls), 2)

    def test_pagination_cursor(self):
        # 第一页 (no cursor): 2 items + next_cursor=ABC
        # 第二页 (cursor=ABC): 2 items + next_cursor=DEF
        # 第三页 (cursor=DEF): 1 item + next_cursor=None
        responses = {
            "cursor=ABC": MockHTTPResponse(200, {
                "items": [{"i": 3}, {"i": 4}],
                "next_cursor": "DEF",
            }),
            "cursor=DEF": MockHTTPResponse(200, {
                "items": [{"i": 5}],
                "next_cursor": None,
            }),
        }
        # 默认 (no cursor in URL) → 第一页
        client = MockHTTPClient(
            responses=responses,
            default_response=MockHTTPResponse(200, {
                "items": [{"i": 1}, {"i": 2}],
                "next_cursor": "ABC",
            }),
        )
        cw = APICrawler(config=self.cfg, http_client=client)
        result = cw.crawl({
            "url": "https://api.example.com/items",
            "pagination": {
                "mode": "cursor",
                "cursor_response_path": "next_cursor",
                "max_pages": 10,
            },
        })
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 5)
        # 验证三页都被 fetch
        self.assertGreaterEqual(len(client.calls), 3)

    def test_404_returns_error(self):
        client = MockHTTPClient(default_response=MockHTTPResponse(404, {"error": "not found"}))
        cw = APICrawler(config=self.cfg, http_client=client)
        result = cw.crawl("https://api.example.com/missing")
        # 404 被重试 3 次都失败, 返回非 OK
        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 404)
        self.assertIn("HTTP 404", result.error or "")

    def test_429_retry(self):
        # 429 + 5000 retry — 第一次失败, 第二次成功
        call_count = [0]
        def request_factory(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockHTTPResponse(429, {"error": "rate limited"})
            return MockHTTPResponse(200, {"items": [{"ok": True}]})
        client = MockHTTPClient()
        # 替换 request method
        client.request = lambda method, url, **kw: request_factory(method, url, **kw)
        cw = APICrawler(config=self.cfg, http_client=client)
        result = cw.crawl("https://api.example.com/items")
        self.assertTrue(result.ok)
        self.assertGreaterEqual(call_count[0], 2)  # 重试过

    def test_data_path_dig(self):
        client = MockHTTPClient(default_response=MockHTTPResponse(
            200, {"response": {"nested": {"data": [{"x": 1}, {"x": 2}]}}}
        ))
        cw = APICrawler(config=self.cfg, http_client=client)
        result = cw.crawl({
            "url": "https://api.example.com/x",
            "pagination": {"data_path": "response.nested.data"},
        })
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 2)

    def test_link_header_pagination(self):
        responses = {
            "page=1": MockHTTPResponse(200, [{"id": 1}], headers={
                "Link": '<https://api.example.com/items?page=2>; rel="next"'
            }),
            "page=2": MockHTTPResponse(200, [{"id": 2}], headers={}),  # no next
        }
        client = MockHTTPClient(responses=responses)
        cw = APICrawler(config=self.cfg, http_client=client)
        result = cw.crawl({
            "url": "https://api.example.com/items?page=1",
            "pagination": {"mode": "link_header", "link_header_rel": "next"},
        })
        self.assertTrue(result.ok)
        self.assertGreaterEqual(len(result.items), 2)

    def test_auth_bearer_headers(self):
        cfg = make_default_config("api")
        cfg.auth = AuthConfig(auth_type=AuthType.BEARER, token="test_bearer_xyz")
        cfg.robots_policy = RobotsPolicy.IGNORE
        cfg.enable_audit_chain = False
        client = MockHTTPClient(default_response=MockHTTPResponse(200, {"ok": 1}))
        cw = APICrawler(config=cfg, http_client=client)
        cw.crawl("https://api.example.com/secure")
        self.assertEqual(client.calls[0]["headers"]["Authorization"], "Bearer test_bearer_xyz")

    def test_invalid_target(self):
        cw = APICrawler(config=self.cfg, http_client=MockHTTPClient())
        result = cw.crawl({"no_url": "value"})
        self.assertEqual(result.status, CrawlStatus.UNKNOWN_ERROR)


class TestGraphQLCrawler(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("graphql")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False

    def test_graphql_query(self):
        client = MockHTTPClient(default_response=MockHTTPResponse(
            200, {"data": {"user": {"id": 1, "name": "alice"}}}
        ))
        cw = GraphQLCrawler(config=self.cfg, http_client=client)
        result = cw.crawl_query(
            endpoint="https://api.example.com/graphql",
            query="{ user { id name } }",
            variables={"id": 1},
        )
        self.assertTrue(result.ok)
        # 验证 POST + JSON body
        call = client.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertIn("query", call["json"])
        self.assertEqual(call["json"]["variables"], {"id": 1})


if __name__ == "__main__":
    unittest.main()