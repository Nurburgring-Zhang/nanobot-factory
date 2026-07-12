"""test_duckduckgo.py — DuckDuckGo Images 渠道适配器测试 (mock HTTP)"""
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

from imdf.crawler.channels.duckduckgo import DuckDuckGoImagesCrawler
from imdf.crawler.channels._schemas import CrawledItemModel, SearchRequest, SearchResponse
from imdf.crawler.base import CrawlStatus, CrawledItem
from imdf.crawler.config import make_default_config, RobotsPolicy


def _make_ddg_i_js_response(query: str, count: int) -> bytes:
    data = [
        {
            "image": f"https://example.com/ddg_{query}_{i}.jpg",
            "thumbnail": f"https://example.com/ddg_thumb_{query}_{i}.jpg",
            "title": f"DDG {query} mock {i+1}",
            "width": 1280,
            "height": 720,
            "url": f"https://example.com/page_{i}",
            "source": f"Mock Source {i % 3}",
        }
        for i in range(count)
    ]
    return json.dumps({"query": query, "results": data}, ensure_ascii=False).encode("utf-8")


def _make_ddg_vqd_html(vqd: str = "4-123456789012345-6") -> bytes:
    return (
        f'<!DOCTYPE html><html><head></head><body>'
        f'<input name="q" value="test"/>'
        f'<input name="vqd" value="{vqd}"/>'
        f'</body></html>'
    ).encode("utf-8")


def _ddg_vqd_then_json_fetcher(vqd: str = "4-987654321098765-3", count: int = 3):
    """两阶段 fetcher: 第一次返回 vqd HTML, 第二次返回 i.js JSON"""
    state = {"calls": 0, "vqd_calls": 0, "ijs_calls": 0}

    def fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
        state["calls"] += 1
        if "i.js" in url:
            state["ijs_calls"] += 1
            m = re.search(r"q=([^&]+)", url)
            query = m.group(1) if m else "test"
            return _make_ddg_i_js_response(query, count), 200, None
        state["vqd_calls"] += 1
        return _make_ddg_vqd_html(vqd), 200, None

    fetcher.state = state  # for inspection in tests
    return fetcher


def _ddg_vqd_fail_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    if "i.js" in url:
        return _make_ddg_i_js_response("q", 3), 200, None
    return b"", 0, "vqd page down"


def _failing_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    return b"", 0, "mock error"


class TestDuckDuckGoImagesCrawler(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("duckduckgo_images")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False

    # 1. 默认 mock
    def test_mock_mode_default(self):
        cw = DuckDuckGoImagesCrawler(config=self.cfg)
        self.assertTrue(cw.mock)
        result = cw.crawl({"query": "python", "count": 4})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 4)
        for it in result.items:
            self.assertEqual(it["source"], "duckduckgo_images")
            self.assertTrue(it["mock"])
            self.assertIn("ddg_", it["url"])

    # 2. string target
    def test_mock_string_target(self):
        cw = DuckDuckGoImagesCrawler(config=self.cfg)
        result = cw.crawl("javascript")
        self.assertTrue(result.ok)
        self.assertGreater(len(result.items), 0)

    # 3. 真实 mock fetcher — 两阶段 (vqd + i.js)
    def test_with_mock_fetcher_two_step(self):
        fetcher = _ddg_vqd_then_json_fetcher(vqd="4-abc-12345-xyz", count=3)
        cw = DuckDuckGoImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=fetcher,
        )
        result = cw.crawl({"query": "rust", "count": 3})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)
        self.assertGreaterEqual(fetcher.state["vqd_calls"], 1)
        self.assertGreaterEqual(fetcher.state["ijs_calls"], 1)
        self.assertEqual(fetcher.state["vqd_calls"], 1)
        self.assertEqual(fetcher.state["ijs_calls"], 1)

    # 4. prep["vqd"] 注入 (跳过 vqd 抓取)
    def test_vqd_injection(self):
        calls = {"i_js": 0, "other": 0}

        def fetcher(url, headers, timeout):
            if "i.js" in url:
                calls["i_js"] += 1
                return _make_ddg_i_js_response("q", 3), 200, None
            calls["other"] += 1
            return b"", 0, "should not call vqd"

        cw = DuckDuckGoImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=fetcher,
        )
        result = cw.crawl({"query": "q", "count": 3, "vqd": "4-injected-token-9"})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)
        self.assertEqual(calls["other"], 0, "vqd fetch should be skipped")
        self.assertEqual(calls["i_js"], 1)

    # 5. 无效 target
    def test_invalid_target(self):
        cw = DuckDuckGoImagesCrawler(config=self.cfg)
        result = cw.crawl({"no_query": 1})
        self.assertEqual(result.status, CrawlStatus.UNKNOWN_ERROR)

    # 6. vqd 抓取失败
    def test_vqd_fetch_failure(self):
        cw = DuckDuckGoImagesCrawler(
            config=self.cfg, mock=False, http_fetcher=_ddg_vqd_fail_fetcher,
        )
        result = cw.crawl({"query": "q", "count": 3})
        self.assertFalse(result.ok)
        self.assertIn("vqd", (result.error or "").lower())

    # 7. vqd token regex 解析
    def test_vqd_token_regex(self):
        html = _make_ddg_vqd_html("4-123456789012345-6").decode("utf-8")
        m = re.search(r'name=["\']vqd["\']\s+value=["\']([\w-]+)["\']', html)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "4-123456789012345-6")

    # 8. count clamp
    def test_count_clamped(self):
        cw = DuckDuckGoImagesCrawler(config=self.cfg)
        result = cw.crawl({"query": "q", "count": 9999})
        self.assertTrue(result.ok)
        self.assertLessEqual(len(result.items), 100)

    # 9. async search (Pydantic v2)
    def test_async_search(self):
        cw = DuckDuckGoImagesCrawler(config=self.cfg)
        items = asyncio.run(cw.search("kotlin", max_results=2))
        self.assertEqual(len(items), 2)
        for it in items:
            self.assertIsInstance(it, CrawledItemModel)
            self.assertEqual(it.source, "duckduckgo_images")

    # 9b. Pydantic v2 model_dump_json
    def test_pydantic_model_dump_json(self):
        cw = DuckDuckGoImagesCrawler(config=self.cfg)
        items = asyncio.run(cw.search("test", max_results=2))
        for it in items:
            js = it.model_dump_json()
            self.assertIn("duckduckgo_images", js)
            restored = CrawledItemModel.model_validate_json(js)
            self.assertEqual(restored.url, it.url)

    # 9c. Pydantic v2 search_request
    def test_search_request_pydantic(self):
        cw = DuckDuckGoImagesCrawler(config=self.cfg)
        req = SearchRequest(query="ddg_q", max_results=2, page=1)
        resp = asyncio.run(cw.search_request(req))
        self.assertIsInstance(resp, SearchResponse)
        self.assertEqual(resp.query, "ddg_q")
        for it in resp.items:
            self.assertIsInstance(it, CrawledItemModel)
            self.assertEqual(it.source, "duckduckgo_images")

    # 9d. Pydantic v2 SearchRequest 验证
    def test_search_request_validation(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            SearchRequest(query="")
        with self.assertRaises(ValidationError):
            SearchRequest(query="x", max_results=0)
        with self.assertRaises(ValidationError):
            SearchRequest(query="x", page=0)
        req = SearchRequest(query="ok")
        self.assertEqual(req.query, "ok")
        self.assertEqual(req.max_results, 50)  # default

    # 10. 10 字段契约
    def test_ten_field_contract(self):
        cw = DuckDuckGoImagesCrawler(config=self.cfg)
        result = cw.crawl({"query": "q", "count": 1})
        item = result.items[0]
        for f in CrawledItem.SCHEMA_FIELDS:
            self.assertIn(f, item)

    # 11. extra 字段
    def test_extra_fields(self):
        cw = DuckDuckGoImagesCrawler(config=self.cfg)
        result = cw.crawl({"query": "q", "count": 1})
        item = result.items[0]
        self.assertEqual(item["extra"]["license"], "duckduckgo-crawler-terms")
        self.assertIn("page_url", item["extra"])
        self.assertTrue(item["extra"]["mock"])


if __name__ == "__main__":
    unittest.main()
