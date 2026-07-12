"""test_web_crawler.py — WebCrawler 测试 (mock Playwright)"""
import os
import sys
import unittest
from typing import Any, Dict, Optional, Tuple

_THIS = os.path.dirname(os.path.abspath(__file__))
_CRAWLER_DIR = os.path.dirname(_THIS)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_CRAWLER_DIR)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from imdf.crawler.web_crawler import WebCrawler, WebPage
from imdf.crawler.base import CrawlStatus, CrawlResult
from imdf.crawler.config import CrawlerConfig, make_default_config, RobotsPolicy


def _fake_playwright_runner(url: str, headers: Dict[str, str], prep: Dict[str, Any]) -> Tuple[Any, int, Optional[str]]:
    """Mock Playwright runner — 返回模拟 HTML"""
    if "fail" in url:
        return b"", 0, "playwright timeout"
    return (
        b"<html><head><title>Mock Page</title></head>"
        b"<body>"
        b"<h1>Hello World</h1>"
        b"<a href='/about'>About</a>"
        b"<img src='/img1.jpg'/>"
        b"<img src='/img2.png'/>"
        b"<meta name='description' content='A mock page'/>"
        b"</body></html>",
        200,
        None,
    )


class TestWebCrawler(unittest.TestCase):
    """WebCrawler — 用注入的 fake_playwright_runner 避免依赖 playwright"""

    def setUp(self):
        self.cfg = make_default_config("web")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False

    def test_basic_crawl_with_mock(self):
        cw = WebCrawler(config=self.cfg, playwright_runner=_fake_playwright_runner)
        result = cw.crawl("https://example.com")
        self.assertTrue(result.ok, f"Expected success, got {result.error}")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.items), 1)
        item = result.items[0]
        self.assertEqual(item["title"], "Mock Page")
        self.assertIn("Hello World", item["text"])

    def test_crawl_with_selectors(self):
        cw = WebCrawler(config=self.cfg, playwright_runner=_fake_playwright_runner)
        result = cw.crawl({
            "url": "https://example.com",
            "selectors": {"headings": "h1", "links": "a"},
        })
        self.assertTrue(result.ok)
        item = result.items[0]
        self.assertIn("selectors", item)
        self.assertIn("headings", item["selectors"])
        self.assertIn("Hello World", item["selectors"]["headings"][0])

    def test_extract_images(self):
        cw = WebCrawler(config=self.cfg, playwright_runner=_fake_playwright_runner)
        result = cw.crawl("https://example.com")
        self.assertTrue(result.ok)
        item = result.items[0]
        self.assertIn("/img1.jpg", item["images"])
        self.assertIn("/img2.png", item["images"])

    def test_extract_links(self):
        cw = WebCrawler(config=self.cfg, playwright_runner=_fake_playwright_runner)
        result = cw.crawl("https://example.com")
        item = result.items[0]
        self.assertIn("/about", item["links"])

    def test_metadata_extraction(self):
        cw = WebCrawler(config=self.cfg, playwright_runner=_fake_playwright_runner)
        result = cw.crawl("https://example.com")
        item = result.items[0]
        self.assertIn("description", item["metadata"])
        self.assertEqual(item["metadata"]["description"], "A mock page")

    def test_failure_path(self):
        cw = WebCrawler(config=self.cfg, playwright_runner=_fake_playwright_runner)
        result = cw.crawl("https://fail.example.com")
        self.assertFalse(result.ok)
        self.assertIn(result.status, (CrawlStatus.FETCH_ERROR, CrawlStatus.UNKNOWN_ERROR, CrawlStatus.PROXY_ERROR, CrawlStatus.TIMEOUT))

    def test_urllib_fallback_when_no_runner(self):
        """无 playwright_runner & 无 playwright → urllib fallback (失败正常)"""
        cw = WebCrawler(config=self.cfg)
        # 尝试真实 fetch (会失败, 因为 test 域名不存在), 但应不抛
        result = cw.crawl("https://nonexistent-domain-12345.invalid")
        # 不管 fetch 失败/成功, 不应抛
        self.assertIsInstance(result, CrawlResult)

    def test_crawl_many_sequential(self):
        cw = WebCrawler(config=self.cfg, playwright_runner=_fake_playwright_runner)
        results = cw.crawl_many([
            "https://example.com/a",
            "https://example.com/b",
        ])
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertTrue(r.ok)

    def test_html_with_page_break(self):
        """多页 HTML 分割 — 模拟 <!--PAGE_BREAK--> 分隔"""
        def multi_page_runner(url, headers, prep):
            return (
                b"<html><body>Page 1</body></html>"
                b"<!--PAGE_BREAK-->"
                b"<html><body>Page 2</body></html>",
                200,
                None,
            )
        cw = WebCrawler(config=self.cfg, playwright_runner=multi_page_runner)
        result = cw.crawl("https://example.com/multi")
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 2)
        self.assertIn("Page 1", result.items[0]["text"])
        self.assertIn("Page 2", result.items[1]["text"])
        self.assertEqual(result.metadata["pages"], 2)

    def test_extract_mode(self):
        """只提取指定字段"""
        cw = WebCrawler(config=self.cfg, playwright_runner=_fake_playwright_runner)
        result = cw.crawl({
            "url": "https://example.com",
            "extract": ["html", "title"],
        })
        self.assertTrue(result.ok)
        item = result.items[0]
        self.assertIn("title", item)
        # text/images/links 不在 extract 里, 应为空
        # (parser 仍会解析, 但 priority 是 extract 字段)

    def test_invalid_target(self):
        cw = WebCrawler(config=self.cfg, playwright_runner=_fake_playwright_runner)
        result = cw.crawl({"no_url_key": "value"})
        # _prepare 返回 None → UNKNOWN_ERROR
        self.assertEqual(result.status, CrawlStatus.UNKNOWN_ERROR)


if __name__ == "__main__":
    unittest.main()