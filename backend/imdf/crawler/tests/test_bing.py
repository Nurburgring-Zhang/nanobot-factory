"""test_bing.py — Bing Images 渠道适配器测试 (mock HTTP)"""
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

from imdf.crawler.channels.bing_images import BingImagesCrawler
from imdf.crawler.channels._schemas import CrawledItemModel, SearchRequest, SearchResponse
from imdf.crawler.base import CrawlStatus, CrawledItem
from imdf.crawler.config import make_default_config, RobotsPolicy


def _make_bing_html_iusc(query: str, count: int) -> bytes:
    parts = ["<!DOCTYPE html><html><body><div class='dgControl'>"]
    for i in range(count):
        m = {
            "murl": f"https://example.com/bing_{query}_{i}.jpg",
            "turl": f"https://example.com/bing_thumb_{query}_{i}.jpg",
            "t": f"Bing {query} mock {i+1}",
            "desc": f"Description for {query} result {i+1}",
            "mid": f"bing_{query}_{i:04d}",
            "purl": f"https://example.com/page_{i}",
            "mw": 1920,
            "mh": 1080,
        }
        m_json = json.dumps(m, ensure_ascii=False)
        parts.append(f'<a class="iusc" m=\'{m_json}\'></a>')
    parts.append("</div></body></html>")
    return "".join(parts).encode("utf-8")


def _make_bing_html_img(query: str, count: int) -> bytes:
    parts = ["<!DOCTYPE html><html><body>"]
    for i in range(count):
        src = f"https://example.com/bing_fallback_{query}_{i}.jpg"
        parts.append(
            f'<img data-src="{src}" src="https://example.com/bing_thumb_{i}.jpg" '
            f'alt="Bing fallback {query} {i+1}">'
        )
    parts.append("</body></html>")
    return "".join(parts).encode("utf-8")


def _bing_iusc_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    if "bing.com" not in url:
        return b"", 0, "not mocked"
    m = re.search(r"q=([^&]+)", url)
    query = m.group(1) if m else "test"
    return _make_bing_html_iusc(query, 3), 200, None


def _bing_fallback_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    return _make_bing_html_img("q", 3), 200, None


def _failing_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    return b"", 0, "mock error"


class TestBingImagesCrawler(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("bing_images")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False

    # 1. 默认 mock
    def test_mock_mode_default(self):
        cw = BingImagesCrawler(config=self.cfg)
        self.assertTrue(cw.mock)
        result = cw.crawl({"query": "ocean", "count": 4})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 4)
        for it in result.items:
            self.assertEqual(it["source"], "bing_images")
            self.assertIn("bing_", it["url"])
            self.assertTrue(it["mock"])

    # 2. string target
    def test_mock_string_target(self):
        cw = BingImagesCrawler(config=self.cfg)
        result = cw.crawl("mountain")
        self.assertTrue(result.ok)
        self.assertGreater(len(result.items), 0)

    # 3. 真实 mock fetcher (iusc 模式)
    def test_with_mock_fetcher_iusc(self):
        cw = BingImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=_bing_iusc_fetcher,
        )
        result = cw.crawl({"query": "sunset", "count": 3})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)
        self.assertIn("bing_sunset_0", result.items[0]["url"])
        self.assertIn("Description for sunset", result.items[0]["description"])

    # 4. 兜底 img 模式
    def test_with_mock_fetcher_fallback(self):
        cw = BingImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=_bing_fallback_fetcher,
        )
        result = cw.crawl({"query": "q", "count": 3})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)
        self.assertIn("bing_fallback_", result.items[0]["url"])

    # 5. 无效 target
    def test_invalid_target(self):
        cw = BingImagesCrawler(config=self.cfg)
        result = cw.crawl({"no_query": 1})
        self.assertEqual(result.status, CrawlStatus.UNKNOWN_ERROR)

    # 6. network error
    def test_network_error(self):
        cw = BingImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=_failing_fetcher,
        )
        result = cw.crawl({"query": "q", "count": 3})
        self.assertFalse(result.ok)
        self.assertIn("mock error", result.error or "")

    # 7. count clamp
    def test_count_clamped(self):
        cw = BingImagesCrawler(config=self.cfg)
        result = cw.crawl({"query": "q", "count": 9999})
        self.assertTrue(result.ok)
        self.assertLessEqual(len(result.items), 100)

    # 8. async search (Pydantic v2)
    def test_async_search(self):
        cw = BingImagesCrawler(config=self.cfg)
        items = asyncio.run(cw.search("forest", max_results=2))
        self.assertEqual(len(items), 2)
        for it in items:
            self.assertIsInstance(it, CrawledItemModel)
            self.assertEqual(it.source, "bing_images")

    # 8b. Pydantic v2 model_dump_json
    def test_pydantic_model_dump_json(self):
        cw = BingImagesCrawler(config=self.cfg)
        items = asyncio.run(cw.search("test", max_results=2))
        for it in items:
            js = it.model_dump_json()
            self.assertIn("bing_images", js)
            restored = CrawledItemModel.model_validate_json(js)
            self.assertEqual(restored.url, it.url)

    # 8c. Pydantic v2 search_request
    def test_search_request_pydantic(self):
        cw = BingImagesCrawler(config=self.cfg)
        req = SearchRequest(query="b_q", max_results=2, page=1)
        resp = asyncio.run(cw.search_request(req))
        self.assertIsInstance(resp, SearchResponse)
        self.assertEqual(resp.query, "b_q")
        for it in resp.items:
            self.assertIsInstance(it, CrawledItemModel)
            self.assertEqual(it.source, "bing_images")

    # 9. 10 字段契约
    def test_ten_field_contract(self):
        cw = BingImagesCrawler(config=self.cfg)
        result = cw.crawl({"query": "q", "count": 1})
        item = result.items[0]
        for f in CrawledItem.SCHEMA_FIELDS:
            self.assertIn(f, item)

    # 10. extra 字段
    def test_extra_fields(self):
        cw = BingImagesCrawler(config=self.cfg)
        result = cw.crawl({"query": "q", "count": 1})
        item = result.items[0]
        self.assertEqual(item["extra"]["license"], "bing-crawler-terms")
        self.assertIn("page_url", item["extra"])


if __name__ == "__main__":
    unittest.main()
