"""test_sogou.py — Sogou Images 渠道适配器测试 (mock HTTP)"""
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

from imdf.crawler.channels.sogou import SogouImagesCrawler
from imdf.crawler.channels._schemas import CrawledItemModel, SearchRequest, SearchResponse
from imdf.crawler.base import CrawlStatus, CrawledItem
from imdf.crawler.config import make_default_config, RobotsPolicy


def _make_sogou_json_response(query: str, count: int) -> bytes:
    data = [
        {
            "id": f"sogou_{query}_{i:04d}",
            "picUrl": f"https://example.com/sogou_{query}_{i}.jpg",
            "thumbUrl": f"https://example.com/sogou_thumb_{query}_{i}.jpg",
            "title": f"搜狗 {query} 模拟 {i+1}",
            "width": 1280,
            "height": 720,
            "fromUrl": f"https://example.com/page_{i}",
        }
        for i in range(count)
    ]
    return json.dumps({"items": data, "total": count * 10}, ensure_ascii=False).encode("utf-8")


def _make_sogou_html_response(query: str, count: int) -> bytes:
    parts = ["<!DOCTYPE html><html><body>"]
    for i in range(count):
        obj = f"https://example.com/sogou_html_{query}_{i}.jpg"
        parts.append(
            f'<a class="link" href="https://example.com/page_{i}">'
            f'<img class="img-tag" data-imgurl="{obj}" '
            f'src="https://example.com/sogou_thumb_{i}.jpg" alt="搜狗 {query} HTML {i+1}">'
            f'</a>'
        )
    parts.append("</body></html>")
    return "".join(parts).encode("utf-8")


def _make_sogou_embedded_html(query: str, count: int) -> bytes:
    data = [
        {
            "id": f"emb_{query}_{i:04d}",
            "picUrl": f"https://example.com/emb_{query}_{i}.jpg",
            "thumbUrl": f"https://example.com/emb_thumb_{query}_{i}.jpg",
            "title": f"搜狗嵌入 {query} {i+1}",
        }
        for i in range(count)
    ]
    init_state = json.dumps({"items": data, "query": query}, ensure_ascii=False)
    return (
        f'<!DOCTYPE html><html><head>'
        f'<script>window.__INITIAL_STATE__ = {init_state};</script>'
        f'</head><body></body></html>'
    ).encode("utf-8")


def _sogou_mock_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    if "sogou" not in url:
        return b"", 0, "not mocked"
    m = re.search(r"query=([^&]+)", url)
    query = m.group(1) if m else "test"
    return _make_sogou_json_response(query, 3), 200, None


def _sogou_html_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    return _make_sogou_html_response("q", 4), 200, None


def _sogou_embedded_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    return _make_sogou_embedded_html("q", 3), 200, None


def _failing_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    return b"", 500, "server error"


class TestSogouImagesCrawler(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("sogou_images")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False

    # 1. 默认 mock
    def test_mock_mode_default(self):
        cw = SogouImagesCrawler(config=self.cfg)
        self.assertTrue(cw.mock)
        result = cw.crawl({"query": "山水", "count": 5})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 5)
        for it in result.items:
            self.assertEqual(it["source"], "sogou_images")
            self.assertTrue(it["mock"])

    # 2. string target
    def test_mock_string_target(self):
        cw = SogouImagesCrawler(config=self.cfg)
        result = cw.crawl("花鸟")
        self.assertTrue(result.ok)
        self.assertGreater(len(result.items), 0)

    # 3. 真实 mock fetcher (JSON)
    def test_with_mock_fetcher_json(self):
        cw = SogouImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=_sogou_mock_fetcher,
        )
        result = cw.crawl({"query": "旅行", "count": 3})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)
        self.assertIn("sogou_旅行_0", result.items[0]["url"])

    # 4. HTML 解析
    def test_with_mock_fetcher_html(self):
        cw = SogouImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=_sogou_html_fetcher,
        )
        result = cw.crawl({"query": "q", "count": 4})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 4)
        self.assertIn("sogou_html_", result.items[0]["url"])

    # 5. 嵌入 JSON 解析
    def test_embedded_initial_state(self):
        cw = SogouImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=_sogou_embedded_fetcher,
        )
        result = cw.crawl({"query": "q", "count": 3})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)
        self.assertIn("emb_q_0", result.items[0]["url"])

    # 6. 无效 target
    def test_invalid_target(self):
        cw = SogouImagesCrawler(config=self.cfg)
        result = cw.crawl({"missing_query": 1})
        self.assertEqual(result.status, CrawlStatus.UNKNOWN_ERROR)

    # 7. 网络错误
    def test_network_error(self):
        cw = SogouImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=_failing_fetcher,
        )
        result = cw.crawl({"query": "q", "count": 3})
        self.assertFalse(result.ok)
        self.assertIn("server error", result.error or "")

    # 8. count clamp
    def test_count_clamped(self):
        cw = SogouImagesCrawler(config=self.cfg)
        result = cw.crawl({"query": "q", "count": 9999})
        self.assertTrue(result.ok)
        self.assertLessEqual(len(result.items), 100)

    # 9. async search (Pydantic v2)
    def test_async_search(self):
        cw = SogouImagesCrawler(config=self.cfg)
        items = asyncio.run(cw.search("海岛", max_results=2))
        self.assertEqual(len(items), 2)
        for it in items:
            self.assertIsInstance(it, CrawledItemModel)
            self.assertEqual(it.source, "sogou_images")

    # 9b. Pydantic v2 model_dump_json
    def test_pydantic_model_dump_json(self):
        cw = SogouImagesCrawler(config=self.cfg)
        items = asyncio.run(cw.search("test", max_results=2))
        for it in items:
            js = it.model_dump_json()
            self.assertIn("sogou_images", js)
            restored = CrawledItemModel.model_validate_json(js)
            self.assertEqual(restored.url, it.url)

    # 9c. Pydantic v2 search_request
    def test_search_request_pydantic(self):
        cw = SogouImagesCrawler(config=self.cfg)
        req = SearchRequest(query="s_q", max_results=2, page=1)
        resp = asyncio.run(cw.search_request(req))
        self.assertIsInstance(resp, SearchResponse)
        self.assertEqual(resp.query, "s_q")
        for it in resp.items:
            self.assertIsInstance(it, CrawledItemModel)
            self.assertEqual(it.source, "sogou_images")

    # 10. 10 字段契约
    def test_ten_field_contract(self):
        cw = SogouImagesCrawler(config=self.cfg)
        result = cw.crawl({"query": "q", "count": 1})
        item = result.items[0]
        for f in CrawledItem.SCHEMA_FIELDS:
            self.assertIn(f, item)


if __name__ == "__main__":
    unittest.main()
