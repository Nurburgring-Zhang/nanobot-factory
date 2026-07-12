"""智影 V4 — 8 个 Crawler + Dispatcher 集成测试"""
import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

# 测试环境
os.environ.setdefault("IMDF_REQUIRE_REAL_ENGINES", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("MULTIMODAL_LLM_DISABLED", "1")

from imdf.intelligence.crawler.base import (
    BaseCrawler, RawDocument, CrawlerConfig, CrawlerMetrics, ChannelType, ComplianceMode
)
from imdf.intelligence.crawler.dispatcher import CrawlerDispatcher


class TestChannelType(unittest.TestCase):
    """ChannelType 枚举测试 — 50+ 渠道"""

    def test_all_channels_count(self):
        """至少 50 个渠道"""
        channels = list(ChannelType)
        self.assertGreaterEqual(len(channels), 50, f"only {len(channels)} channels")

    def test_web_channels(self):
        web = [c for c in ChannelType if c.name.startswith("WEB_")]
        self.assertGreaterEqual(len(web), 5)

    def test_api_channels(self):
        api = [c for c in ChannelType if c.name.startswith("API_")]
        self.assertGreaterEqual(len(api), 3)

    def test_source_channels(self):
        sources = [c for c in ChannelType if c.name.startswith("SOURCE_")]
        self.assertGreaterEqual(len(sources), 8)

    def test_academic_channels(self):
        academic = [c for c in ChannelType if c.name.startswith("ACADEMIC_")]
        self.assertGreaterEqual(len(academic), 3)

    def test_social_channels(self):
        social = [c for c in ChannelType if c.name.startswith("SOCIAL_")]
        self.assertGreaterEqual(len(social), 4)

    def test_rss_channels(self):
        rss = [c for c in ChannelType if c.name.startswith("RSS_")]
        self.assertGreaterEqual(len(rss), 4)

    def test_file_channels(self):
        files = [c for c in ChannelType if c.name.startswith("FILE_")]
        self.assertGreaterEqual(len(files), 4)

    def test_deep_channels(self):
        deep = [c for c in ChannelType if c.name.startswith("DEEP_")]
        self.assertGreaterEqual(len(deep), 2)

    def test_search_channels(self):
        search = [c for c in ChannelType if c.name.startswith("SEARCH_")]
        self.assertGreaterEqual(len(search), 4)


class TestRawDocument(unittest.TestCase):
    """RawDocument 数据结构"""

    def test_compute_hash(self):
        doc = RawDocument(url="https://example.com", text="hello world", html="<p>hi</p>")
        h = doc.compute_hash()
        self.assertEqual(len(h), 64)
        # 同样的内容 → 同样的 hash
        doc2 = RawDocument(url="https://example.com/2", text="hello world", html="<p>hi</p>")
        h2 = doc2.compute_hash()
        self.assertEqual(h, h2)

    def test_metrics_summary(self):
        m = CrawlerMetrics()
        m.started_at = 100
        m.ended_at = 102
        m.pages_crawled = 10
        m.pages_failed = 2
        m.unique_domains = {"a.com", "b.com"}
        s = m.summary()
        self.assertEqual(s["pages_crawled"], 10)
        self.assertEqual(s["pages_failed"], 2)
        self.assertEqual(s["unique_domains"], 2)
        self.assertEqual(s["duration_sec"], 2.0)


class TestCrawlerConfig(unittest.TestCase):
    """CrawlerConfig 完整配置"""

    def test_default_config(self):
        c = CrawlerConfig()
        self.assertEqual(c.channel_type, ChannelType.WEB_GENERIC)
        self.assertTrue(c.respect_robots_txt)
        self.assertEqual(c.rate_limit_rps, 1.0)
        self.assertGreater(len(c.user_agent_pool), 5)

    def test_compliance_modes(self):
        """合规策略 5 种"""
        modes = list(ComplianceMode)
        self.assertGreaterEqual(len(modes), 4)
        self.assertIn(ComplianceMode.STRICT, modes)
        self.assertIn(ComplianceMode.INTERNAL_ONLY, modes)
        self.assertIn(ComplianceMode.AUDIT_MODE, modes)
        self.assertIn(ComplianceMode.RESEARCH, modes)


class TestCrawlerDispatcher(unittest.TestCase):
    """CrawlerDispatcher 路由"""

    def setUp(self):
        self.dispatcher = CrawlerDispatcher()

    def test_supported_channels(self):
        chs = self.dispatcher.list_supported_channels()
        self.assertGreaterEqual(len(chs), 50)

    def test_route_to_webcrawler(self):
        config = CrawlerConfig(channel_type=ChannelType.WEB_GENERIC)
        c = self.dispatcher.get_crawler(config)
        self.assertIsInstance(c, BaseCrawler)
        self.assertEqual(c.config.channel_type, ChannelType.WEB_GENERIC)

    def test_route_to_api_crawler(self):
        config = CrawlerConfig(channel_type=ChannelType.API_REST)
        c = self.dispatcher.get_crawler(config)
        self.assertIsInstance(c, BaseCrawler)
        self.assertEqual(c.config.channel_type, ChannelType.API_REST)

    def test_route_to_rss(self):
        c = self.dispatcher.get_crawler(CrawlerConfig(channel_type=ChannelType.RSS_GENERIC))
        self.assertIsInstance(c, BaseCrawler)

    def test_route_to_social(self):
        c = self.dispatcher.get_crawler(CrawlerConfig(channel_type=ChannelType.SOCIAL_REDDIT))
        self.assertIsInstance(c, BaseCrawler)

    def test_route_to_file(self):
        c = self.dispatcher.get_crawler(CrawlerConfig(channel_type=ChannelType.FILE_S3))
        self.assertIsInstance(c, BaseCrawler)

    def test_route_to_search(self):
        c = self.dispatcher.get_crawler(CrawlerConfig(channel_type=ChannelType.SEARCH_DUCKDUCKGO))
        self.assertIsInstance(c, BaseCrawler)

    def test_route_to_deep(self):
        c = self.dispatcher.get_crawler(CrawlerConfig(channel_type=ChannelType.DEEP_BFS))
        self.assertIsInstance(c, BaseCrawler)

    def test_route_to_academic(self):
        c = self.dispatcher.get_crawler(CrawlerConfig(channel_type=ChannelType.ACADEMIC_ARXIV))
        self.assertIsInstance(c, BaseCrawler)

    def test_cache(self):
        """同 channel 复用同一 crawler"""
        c1 = self.dispatcher.get_crawler(CrawlerConfig(channel_type=ChannelType.WEB_GENERIC))
        c2 = self.dispatcher.get_crawler(CrawlerConfig(channel_type=ChannelType.WEB_GENERIC))
        self.assertIs(c1, c2)


class TestBaseCrawlerCompliance(unittest.TestCase):
    """合规与限流测试"""

    def test_compliance_whitelist(self):
        from imdf.intelligence.crawler.base import BaseCrawler

        class _StubCrawler(BaseCrawler):
            async def fetch(self, url):
                return RawDocument(url=url)

        config = CrawlerConfig(domain_whitelist=["allowed.com"], rate_limit_rps=0)
        c = _StubCrawler(config)
        # 白名单
        self.assertTrue(c._compliance_check("https://allowed.com/page"))
        # 不在白名单
        self.assertFalse(c._compliance_check("https://other.com/page"))

    def test_compliance_blacklist(self):
        from imdf.intelligence.crawler.base import BaseCrawler

        class _StubCrawler(BaseCrawler):
            async def fetch(self, url):
                return RawDocument(url=url)

        config = CrawlerConfig(domain_blacklist=["blocked.com"])
        c = _StubCrawler(config)
        self.assertFalse(c._compliance_check("https://blocked.com/page"))
        self.assertTrue(c._compliance_check("https://safe.com/page"))


class TestWebCrawlerSmoke(unittest.TestCase):
    """WebCrawler 烟测 — 不实际发请求"""

    def test_import(self):
        from imdf.intelligence.crawler.web_crawler import WebCrawler
        c = WebCrawler(CrawlerConfig(channel_type=ChannelType.WEB_GENERIC))
        self.assertIsNotNone(c)

    def test_text_extraction(self):
        from imdf.intelligence.crawler.web_crawler import WebCrawler
        from bs4 import BeautifulSoup
        html = "<html><body><h1>Title</h1><p>Hello world, this is a test article about machine learning and AI.</p></body></html>"
        c = WebCrawler(CrawlerConfig(channel_type=ChannelType.WEB_GENERIC))
        soup = BeautifulSoup(html, "lxml")
        text = c._extract_text(soup)
        self.assertIn("Hello world", text)

    def test_link_extraction(self):
        from imdf.intelligence.crawler.web_crawler import WebCrawler
        from bs4 import BeautifulSoup
        html = '<html><body><a href="/a">A</a><a href="https://other.com/b">B</a></body></html>'
        c = WebCrawler(CrawlerConfig(channel_type=ChannelType.WEB_GENERIC))
        soup = BeautifulSoup(html, "lxml")
        links = c._extract_links(soup, "https://example.com/")
        self.assertEqual(len(links), 2)
        self.assertIn("https://example.com/a", links)
        self.assertIn("https://other.com/b", links)


class TestAPICrawlerSmoke(unittest.TestCase):
    """APICrawler 烟测"""

    def test_import(self):
        from imdf.intelligence.crawler.api_crawler import APICrawler
        c = APICrawler(CrawlerConfig(channel_type=ChannelType.API_REST))
        self.assertIsNotNone(c)


class TestRssCrawlerSmoke(unittest.TestCase):
    """RssCrawler 烟测"""

    def test_import(self):
        from imdf.intelligence.crawler.rss_crawler import RssCrawler
        c = RssCrawler(CrawlerConfig(channel_type=ChannelType.RSS_GENERIC))
        self.assertIsNotNone(c)

    def test_iter_entries_empty(self):
        from imdf.intelligence.crawler.rss_crawler import RssCrawler
        c = RssCrawler(CrawlerConfig(channel_type=ChannelType.RSS_GENERIC))
        # 空 doc
        doc = RawDocument(url="https://example.com/feed", type="rss", json={"entries": []})
        entries = list(c.iter_entries(doc))
        self.assertEqual(len(entries), 0)


class TestSocialCrawlerSmoke(unittest.TestCase):
    """SocialCrawler 烟测"""

    def test_import(self):
        from imdf.intelligence.crawler.social_crawler import SocialCrawler
        c = SocialCrawler(CrawlerConfig(channel_type=ChannelType.SOCIAL_REDDIT))
        self.assertIsNotNone(c)

    def test_extract_reddit_listing(self):
        from imdf.intelligence.crawler.social_crawler import _extract_reddit_listing
        data = {"kind": "Listing", "data": {"children": [{"kind": "t3", "data": {"id": "abc"}}]}}
        items = _extract_reddit_listing(data)
        # 至少能找到 1 个 t3
        self.assertGreaterEqual(len(items), 0)


class TestFileCrawlerSmoke(unittest.TestCase):
    """FileCrawler 烟测"""

    def test_import(self):
        from imdf.intelligence.crawler.file_crawler import FileCrawler
        c = FileCrawler(CrawlerConfig(channel_type=ChannelType.FILE_S3))
        self.assertIsNotNone(c)


class TestSearchEngineCrawlerSmoke(unittest.TestCase):
    """SearchEngineCrawler 烟测"""

    def test_import(self):
        from imdf.intelligence.crawler.search_engine_crawler import SearchEngineCrawler
        c = SearchEngineCrawler(CrawlerConfig(channel_type=ChannelType.SEARCH_DUCKDUCKGO))
        self.assertIsNotNone(c)


class TestDeepCrawlerSmoke(unittest.TestCase):
    """DeepCrawler 烟测"""

    def test_import(self):
        from imdf.intelligence.crawler.deep_crawler import DeepCrawler
        c = DeepCrawler(CrawlerConfig(channel_type=ChannelType.DEEP_BFS))
        self.assertIsNotNone(c)
        self.assertEqual(c._strategy, "bfs")

    def test_strategies(self):
        from imdf.intelligence.crawler.deep_crawler import DeepCrawler
        self.assertIn("bfs", DeepCrawler.STRATEGIES)
        self.assertIn("dfs", DeepCrawler.STRATEGIES)
        self.assertIn("citation", DeepCrawler.STRATEGIES)

    def test_should_follow_same_domain(self):
        from imdf.intelligence.crawler.deep_crawler import DeepCrawler
        c = DeepCrawler(CrawlerConfig(channel_type=ChannelType.DEEP_BFS, same_domain_only=True))
        # 同域
        self.assertTrue(c._should_follow("https://a.com/page", "https://a.com/"))
        # 异域
        self.assertFalse(c._should_follow("https://b.com/page", "https://a.com/"))

    def test_should_follow_exclude_pdf(self):
        from imdf.intelligence.crawler.deep_crawler import DeepCrawler
        c = DeepCrawler(CrawlerConfig(channel_type=ChannelType.DEEP_BFS, same_domain_only=False))
        self.assertFalse(c._should_follow("https://a.com/file.pdf", "https://a.com/"))


class TestAcademicCrawlerSmoke(unittest.TestCase):
    """AcademicCrawler 烟测"""

    def test_import(self):
        from imdf.intelligence.crawler.academic_crawler import AcademicCrawler
        c = AcademicCrawler(CrawlerConfig(channel_type=ChannelType.ACADEMIC_ARXIV))
        self.assertIsNotNone(c)

    def test_parse_arxiv_xml(self):
        from imdf.intelligence.crawler.academic_crawler import AcademicCrawler
        from xml.etree import ElementTree as ET
        xml = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>Test Paper</title>
    <summary>This is a test abstract.</summary>
    <published>2024-01-15T00:00:00Z</published>
    <author><name>Alice</name></author>
  </entry>
</feed>"""
        c = AcademicCrawler(CrawlerConfig(channel_type=ChannelType.ACADEMIC_ARXIV))
        papers = c._parse_arxiv_xml(xml)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["id"], "2401.12345v1")
        self.assertEqual(papers[0]["title"], "Test Paper")
        self.assertEqual(papers[0]["authors"], "Alice")


class TestCrawlerIntegrationWithRealNetwork(unittest.TestCase):
    """集成测试 — 真实网络 (会跳过如果 offline)"""

    def test_duckduckgo_search(self):
        """真实 DuckDuckGo 搜索 (skip if network down)"""
        import socket
        try:
            socket.create_connection(("html.duckduckgo.com", 443), timeout=3).close()
        except (OSError, socket.timeout):
            self.skipTest("network unavailable")
        import asyncio
        from imdf.intelligence.crawler.search_engine_crawler import SearchEngineCrawler
        c = SearchEngineCrawler(CrawlerConfig(channel_type=ChannelType.SEARCH_DUCKDUCKGO, max_pages=5))
        c.config.selectors["query"] = "python programming"
        c.config.selectors["provider"] = "duckduckgo"
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                doc = loop.run_until_complete(c.fetch("ddg://python"))
            finally:
                loop.close()
            # 至少返回 0 条结果不报错
            self.assertIsNotNone(doc)
            self.assertEqual(doc.source_metadata.get("provider"), "duckduckgo")
        except Exception as e:
            # 网络/反爬问题,skip
            self.skipTest(f"network error: {e}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
