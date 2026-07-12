"""test_baidu_images.py — Baidu Images 渠道适配器测试 (mock HTTP)"""
import asyncio
import json
import os
import re
import sys
import unittest
from typing import Any, Dict, Optional, Tuple

_THIS = os.path.dirname(os.path.abspath(__file__))
_CRAWLER_DIR = os.path.dirname(_THIS)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_CRAWLER_DIR)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from imdf.crawler.channels.baidu_images import BaiduImagesCrawler
from imdf.crawler.channels._schemas import CrawledItemModel, SearchRequest, SearchResponse
from imdf.crawler.base import CrawlStatus, CrawledItem
from imdf.crawler.config import make_default_config, RobotsPolicy


def _make_baidu_json_response(query: str, count: int) -> bytes:
    data = [
        {
            "id": i + 1,
            "objURL": f"https://example.com/baidu_{query}_{i}.jpg",
            "thumbURL": f"https://example.com/baidu_thumb_{query}_{i}.jpg",
            "fromURL": f"https://example.com/page_{i}",
            "title": f"百度 {query} 模拟图 {i+1}",
            "width": 1920,
            "height": 1080,
            "fromPageTitle": f"模拟页面 {i+1}",
        }
        for i in range(count)
    ]
    return json.dumps({"data": data}, ensure_ascii=False).encode("utf-8")


def _make_baidu_html_response(query: str, count: int) -> bytes:
    parts = ["<!DOCTYPE html><html><body>"]
    for i in range(count):
        obj = f"https://example.com/html_{query}_{i}.jpg"
        thumb = f"https://example.com/html_thumb_{query}_{i}.jpg"
        parts.append(
            f'<li class="imgitem" data-objurl="{obj}" data-thumburl="{thumb}" '
            f'data-fromurl="https://example.com/page_{i}">'
            f'<img alt="百度 {query} HTML {i+1}"></li>'
        )
    parts.append("</body></html>")
    return "".join(parts).encode("utf-8")


def _baidu_mock_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    if "image.baidu.com" not in url and "baidu" not in url:
        return b"", 0, "not mocked"
    m = re.search(r"word=([^&]+)", url)
    query = m.group(1) if m else "test"
    m2 = re.search(r"rn=(\d+)", url)
    count = int(m2.group(1)) if m2 else 3
    return _make_baidu_json_response(query, count), 200, None


def _baidu_html_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    return _make_baidu_html_response("html_q", 3), 200, None


def _failing_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    return b"", 0, "mock network error"


class TestBaiduImagesCrawler(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("baidu_images")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False

    # 1. mock 模式
    def test_mock_mode_default(self):
        cw = BaiduImagesCrawler(config=self.cfg)
        self.assertTrue(cw.mock)
        result = cw.crawl({"query": "猫咪", "count": 5})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 5)
        for it in result.items:
            self.assertEqual(it["source"], "baidu_images")
            self.assertTrue(it["mock"])
            self.assertIn("https://example.com/baidu_", it["url"])

    # 2. mock 模式 + string target
    def test_mock_with_string_target(self):
        cw = BaiduImagesCrawler(config=self.cfg)
        result = cw.crawl("风景")
        self.assertTrue(result.ok)
        self.assertGreater(len(result.items), 0)

    # 3. 真实 mock fetcher (JSON response)
    def test_with_mock_fetcher_json(self):
        cw = BaiduImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=_baidu_mock_fetcher,
        )
        result = cw.crawl({"query": "汽车", "count": 4})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 4)
        for it in result.items:
            self.assertIn("example.com/baidu_", it["url"])
            self.assertEqual(it["source"], "baidu_images")
        self.assertEqual(result.metadata["query"], "汽车")

    # 4. 真实 mock fetcher (HTML response)
    def test_with_mock_fetcher_html(self):
        cw = BaiduImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=_baidu_html_fetcher,
        )
        # crawler 的 _prepare 总是走 resultjson, 但 _parse 在 JSON 失败时回退 HTML
        # 通过 _parse 直接传 HTML 文本测试
        text = _make_baidu_html_response("html_q", 3).decode("utf-8")
        items, meta = cw._parse(text, {"query": "html_q", "count": 3, "page": 1})
        self.assertEqual(len(items), 3)
        for it in items:
            self.assertIn("html_", it["url"])

    # 5. 无效 target
    def test_invalid_target_no_query(self):
        cw = BaiduImagesCrawler(config=self.cfg)
        result = cw.crawl({"no_query": "x"})
        self.assertEqual(result.status, CrawlStatus.UNKNOWN_ERROR)

    # 6. invalid type target
    def test_invalid_target_type(self):
        cw = BaiduImagesCrawler(config=self.cfg)
        result = cw.crawl(12345)
        self.assertEqual(result.status, CrawlStatus.UNKNOWN_ERROR)

    # 7. 网络错误
    def test_network_error_handled(self):
        cw = BaiduImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=_failing_fetcher,
        )
        result = cw.crawl({"query": "x", "count": 3})
        self.assertFalse(result.ok)
        self.assertIn("mock network error", result.error or "")

    # 8. count 上限
    def test_count_clamped(self):
        cw = BaiduImagesCrawler(config=self.cfg)
        result = cw.crawl({"query": "q", "count": 99999})
        self.assertTrue(result.ok)
        self.assertLessEqual(len(result.items), 100)

    # 9. async search API (Pydantic v2)
    def test_async_search(self):
        cw = BaiduImagesCrawler(config=self.cfg)
        items = asyncio.run(cw.search("天空", max_results=3))
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 3)
        for it in items:
            self.assertIsInstance(it, CrawledItemModel)  # Pydantic v2 model
            self.assertEqual(it.source, "baidu_images")
            self.assertIn("天空", it.keywords[0] if it.keywords else "")

    # 9b. Pydantic v2 model_dump_json
    def test_pydantic_model_dump_json(self):
        cw = BaiduImagesCrawler(config=self.cfg)
        items = asyncio.run(cw.search("test", max_results=2))
        for it in items:
            js = it.model_dump_json()
            self.assertIsInstance(js, str)
            self.assertIn("baidu_images", js)
            # 反序列化验证
            from imdf.crawler.channels._schemas import CrawledItemModel
            restored = CrawledItemModel.model_validate_json(js)
            self.assertEqual(restored.source, it.source)
            self.assertEqual(restored.url, it.url)

    # 10. 字段契约 (10 字段全在)
    def test_ten_field_contract(self):
        cw = BaiduImagesCrawler(config=self.cfg)
        result = cw.crawl({"query": "q", "count": 1})
        self.assertTrue(result.ok)
        item = result.items[0]
        for f in CrawledItem.SCHEMA_FIELDS:
            self.assertIn(f, item, f"missing field: {f}")

    # 11. Pydantic v2 SearchRequest 输入校验
    def test_pydantic_search_request_validation(self):
        # 空 query 应 raise ValidationError
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            SearchRequest(query="")
        # max_results 越界 (>100)
        with self.assertRaises(ValidationError):
            SearchRequest(query="x", max_results=200)
        # 正常
        req = SearchRequest(query="ok", max_results=10)
        self.assertEqual(req.query, "ok")
        self.assertEqual(req.max_results, 10)
        self.assertEqual(req.page, 1)

    # 12. search_request Pydantic API
    def test_search_request_pydantic(self):
        cw = BaiduImagesCrawler(config=self.cfg)
        req = SearchRequest(query="search_q", max_results=2)
        resp = asyncio.run(cw.search_request(req))
        self.assertIsInstance(resp, SearchResponse)
        self.assertEqual(resp.query, "search_q")
        self.assertEqual(resp.count, 2)
        for it in resp.items:
            self.assertIsInstance(it, CrawledItemModel)
            self.assertEqual(it.source, "baidu_images")


if __name__ == "__main__":
    unittest.main()
