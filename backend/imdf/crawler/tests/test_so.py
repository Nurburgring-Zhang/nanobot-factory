"""test_so.py — 360 Images (image.so.com) 渠道适配器测试 (mock HTTP)"""
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

from imdf.crawler.channels.so_images import SoImagesCrawler
from imdf.crawler.channels._schemas import CrawledItemModel, SearchRequest, SearchResponse
from imdf.crawler.base import CrawlStatus, CrawledItem
from imdf.crawler.config import make_default_config, RobotsPolicy


def _make_so_json_response(query: str, count: int) -> bytes:
    data = [
        {
            "id": i + 1,
            "img": f"https://example.com/so_{query}_{i}.jpg",
            "thumb": f"https://example.com/so_thumb_{query}_{i}.jpg",
            "title": f"360 {query} 模拟 {i+1}",
            "width": 1440,
            "height": 900,
            "url": f"https://example.com/page_{i}",
        }
        for i in range(count)
    ]
    return json.dumps({"list": data, "total": count * 8}, ensure_ascii=False).encode("utf-8")


def _make_so_html_response(query: str, count: int) -> bytes:
    parts = ["<!DOCTYPE html><html><body>"]
    for i in range(count):
        obj = f"https://example.com/so_html_{query}_{i}.jpg"
        parts.append(
            f'<a class="img-link" href="https://example.com/page_{i}">'
            f'<img data-imgurl="{obj}" src="https://example.com/so_thumb_{i}.jpg" '
            f'alt="360 {query} HTML {i+1}">'
            f'</a>'
        )
    parts.append("</body></html>")
    return "".join(parts).encode("utf-8")


def _so_mock_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    if "so.com" not in url:
        return b"", 0, "not mocked"
    m = re.search(r"q=([^&]+)", url)
    query = m.group(1) if m else "test"
    return _make_so_json_response(query, 3), 200, None


def _so_html_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    return _make_so_html_response("q", 3), 200, None


def _failing_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    return b"", 0, "mock timeout"


class TestSoImagesCrawler(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("so_images")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False

    # 1. 默认 mock
    def test_mock_mode_default(self):
        cw = SoImagesCrawler(config=self.cfg)
        self.assertTrue(cw.mock)
        result = cw.crawl({"query": "城市", "count": 4})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 4)
        for it in result.items:
            self.assertEqual(it["source"], "so_images")
            self.assertTrue(it["mock"])

    # 2. string target
    def test_mock_string_target(self):
        cw = SoImagesCrawler(config=self.cfg)
        result = cw.crawl("建筑")
        self.assertTrue(result.ok)
        self.assertGreater(len(result.items), 0)

    # 3. 真实 mock fetcher (JSON)
    def test_with_mock_fetcher_json(self):
        cw = SoImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=_so_mock_fetcher,
        )
        result = cw.crawl({"query": "动物", "count": 3})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)
        self.assertIn("so_动物_0", result.items[0]["url"])
        self.assertEqual(result.metadata["query"], "动物")

    # 4. HTML 解析
    def test_with_mock_fetcher_html(self):
        cw = SoImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=_so_html_fetcher,
        )
        result = cw.crawl({"query": "q", "count": 3})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)
        self.assertIn("so_html_", result.items[0]["url"])

    # 5. 无效 target
    def test_invalid_target(self):
        cw = SoImagesCrawler(config=self.cfg)
        result = cw.crawl({"x": "y"})
        self.assertEqual(result.status, CrawlStatus.UNKNOWN_ERROR)

    # 6. network error
    def test_network_error(self):
        cw = SoImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=_failing_fetcher,
        )
        result = cw.crawl({"query": "q", "count": 3})
        self.assertFalse(result.ok)
        self.assertIn("timeout", (result.error or "").lower())

    # 7. count clamp
    def test_count_clamped(self):
        cw = SoImagesCrawler(config=self.cfg)
        result = cw.crawl({"query": "q", "count": 9999})
        self.assertTrue(result.ok)
        self.assertLessEqual(len(result.items), 100)

    # 8. async search (Pydantic v2)
    def test_async_search(self):
        cw = SoImagesCrawler(config=self.cfg)
        items = asyncio.run(cw.search("海洋", max_results=2))
        self.assertEqual(len(items), 2)
        for it in items:
            self.assertIsInstance(it, CrawledItemModel)
            self.assertEqual(it.source, "so_images")

    # 8b. Pydantic v2 model_dump_json
    def test_pydantic_model_dump_json(self):
        cw = SoImagesCrawler(config=self.cfg)
        items = asyncio.run(cw.search("test", max_results=2))
        for it in items:
            js = it.model_dump_json()
            self.assertIn("so_images", js)
            restored = CrawledItemModel.model_validate_json(js)
            self.assertEqual(restored.url, it.url)

    # 8c. Pydantic v2 search_request
    def test_search_request_pydantic(self):
        cw = SoImagesCrawler(config=self.cfg)
        req = SearchRequest(query="so_q", max_results=2, page=1)
        resp = asyncio.run(cw.search_request(req))
        self.assertIsInstance(resp, SearchResponse)
        self.assertEqual(resp.query, "so_q")
        for it in resp.items:
            self.assertIsInstance(it, CrawledItemModel)
            self.assertEqual(it.source, "so_images")

    # 8b. Pydantic v2 model_dump_json
    def test_pydantic_model_dump_json(self):
        cw = SoImagesCrawler(config=self.cfg)
        items = asyncio.run(cw.search("test", max_results=2))
        for it in items:
            js = it.model_dump_json()
            self.assertIn("so_images", js)
            restored = CrawledItemModel.model_validate_json(js)
            self.assertEqual(restored.url, it.url)

    # 8c. Pydantic v2 search_request
    def test_search_request_pydantic(self):
        cw = SoImagesCrawler(config=self.cfg)
        req = SearchRequest(query="so_q", max_results=2, page=1)
        resp = asyncio.run(cw.search_request(req))
        self.assertIsInstance(resp, SearchResponse)
        self.assertEqual(resp.query, "so_q")
        for it in resp.items:
            self.assertIsInstance(it, CrawledItemModel)
            self.assertEqual(it.source, "so_images")

    # 9. 10 字段契约
    def test_ten_field_contract(self):
        cw = SoImagesCrawler(config=self.cfg)
        result = cw.crawl({"query": "q", "count": 1})
        item = result.items[0]
        for f in CrawledItem.SCHEMA_FIELDS:
            self.assertIn(f, item)

    # 10. extra 字段
    def test_extra_fields(self):
        cw = SoImagesCrawler(config=self.cfg)
        result = cw.crawl({"query": "q", "count": 2})
        item = result.items[0]
        self.assertIn("extra", item)
        self.assertEqual(item["extra"]["license"], "360-crawler-terms")
        self.assertTrue(item["extra"]["mock"])


if __name__ == "__main__":
    unittest.main()
