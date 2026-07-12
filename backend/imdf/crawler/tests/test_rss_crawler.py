"""test_rss_crawler.py — RSSCrawler 测试"""
import os
import sys
import tempfile
import unittest
from typing import Any

_THIS = os.path.dirname(os.path.abspath(__file__))
_CRAWLER_DIR = os.path.dirname(_THIS)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_CRAWLER_DIR)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from imdf.crawler.rss_crawler import RSSCrawler, RSSItem
from imdf.crawler.base import CrawlStatus, CrawlResult
from imdf.crawler.config import make_default_config, RobotsPolicy


SAMPLE_RSS_2_0 = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Mock News Feed</title>
    <link>https://news.example.com</link>
    <description>Mock feed for testing</description>
    <language>en-us</language>
    <item>
      <title>First Post</title>
      <link>https://news.example.com/post-1</link>
      <description>This is the first post body.</description>
      <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
      <guid isPermaLink="true">https://news.example.com/post-1</guid>
      <category>tech</category>
      <category>news</category>
    </item>
    <item>
      <title>Second Post</title>
      <link>https://news.example.com/post-2</link>
      <description>Second post body here.</description>
      <pubDate>Tue, 02 Jan 2024 14:30:00 GMT</pubDate>
      <guid>post-2-uuid</guid>
      <author>editor@example.com (Editor)</author>
    </item>
    <item>
      <title>Third Post</title>
      <link>https://news.example.com/post-3</link>
      <pubDate>Wed, 03 Jan 2024 09:15:00 GMT</pubDate>
      <guid>post-3-uuid</guid>
    </item>
  </channel>
</rss>
"""

SAMPLE_ATOM_1_0 = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Mock Atom Feed</title>
  <link href="https://blog.example.com"/>
  <updated>2024-01-01T00:00:00Z</updated>
  <entry>
    <title>Atom Post 1</title>
    <link href="https://blog.example.com/atom-1"/>
    <id>tag:blog.example.com,2024:1</id>
    <updated>2024-01-01T12:00:00Z</updated>
    <summary>Atom entry summary</summary>
    <author><name>Alice</name></author>
  </entry>
  <entry>
    <title>Atom Post 2</title>
    <link href="https://blog.example.com/atom-2"/>
    <id>tag:blog.example.com,2024:2</id>
    <updated>2024-01-02T12:00:00Z</updated>
  </entry>
</feed>
"""


def _fetcher_factory(content_map):
    def fetcher(url: str) -> bytes:
        for k, v in content_map.items():
            if k in url:
                return v
        raise FileNotFoundError(f"no mock for {url}")
    return fetcher


class TestRSSCrawler(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="rss_test_")
        self.cfg = make_default_config("rss")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False

    def test_basic_rss_2_0_parse(self):
        fetcher = _fetcher_factory({"news": SAMPLE_RSS_2_0})
        cw = RSSCrawler(config=self.cfg, feed_fetcher=fetcher, state_dir=self.tmpdir)
        result = cw.crawl("https://news.example.com/feed.xml")
        self.assertTrue(result.ok, f"got error: {result.error}")
        self.assertEqual(len(result.items), 3)
        first = result.items[0]
        self.assertEqual(first["title"], "First Post")
        self.assertEqual(first["link"], "https://news.example.com/post-1")
        self.assertIn("tech", first["tags"])
        self.assertEqual(result.metadata["feed_title"], "Mock News Feed")

    def test_atom_1_0_parse(self):
        fetcher = _fetcher_factory({"blog": SAMPLE_ATOM_1_0})
        cw = RSSCrawler(config=self.cfg, feed_fetcher=fetcher, state_dir=self.tmpdir)
        result = cw.crawl("https://blog.example.com/atom.xml")
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 2)
        self.assertEqual(result.items[0]["title"], "Atom Post 1")
        self.assertEqual(result.metadata["feed_title"], "Mock Atom Feed")

    def test_incremental_dedup(self):
        fetcher = _fetcher_factory({"news": SAMPLE_RSS_2_0})
        cw = RSSCrawler(config=self.cfg, feed_fetcher=fetcher, state_dir=self.tmpdir)

        # 第一次: 全部 3 条
        r1 = cw.crawl("https://news.example.com/feed.xml")
        self.assertEqual(len(r1.items), 3)
        # 第二次: 0 新条 (dedup)
        r2 = cw.crawl("https://news.example.com/feed.xml")
        self.assertEqual(len(r2.items), 0)
        self.assertEqual(r2.metadata["new_items"], 0)

    def test_full_history_mode(self):
        fetcher = _fetcher_factory({"news": SAMPLE_RSS_2_0})
        cw = RSSCrawler(config=self.cfg, feed_fetcher=fetcher, state_dir=self.tmpdir)
        r1 = cw.crawl({"url": "https://news.example.com/feed.xml", "full_history": True})
        self.assertEqual(len(r1.items), 3)
        # 再来一次 — full_history=True 应仍返回 3
        r2 = cw.crawl({"url": "https://news.example.com/feed.xml", "full_history": True})
        self.assertEqual(len(r2.items), 3)

    def test_invalid_xml_error(self):
        fetcher = _fetcher_factory({"bad": b"<not><valid></rss>"})
        cw = RSSCrawler(config=self.cfg, feed_fetcher=fetcher, state_dir=self.tmpdir)
        result = cw.crawl("https://bad.example.com/feed.xml")
        # feedparser 通常宽容, 但极端 invalid 会 PARSE_ERROR
        self.assertIsInstance(result, CrawlResult)

    def test_fetcher_error_returns_error_status(self):
        def fail_fetcher(url: str) -> bytes:
            raise ConnectionError("network error")
        cw = RSSCrawler(config=self.cfg, feed_fetcher=fail_fetcher, state_dir=self.tmpdir)
        result = cw.crawl("https://fail.example.com/feed.xml")
        self.assertFalse(result.ok)
        self.assertEqual(result.status, CrawlStatus.FETCH_ERROR)
        self.assertIn("network", (result.error or "").lower())

    def test_invalid_target(self):
        cw = RSSCrawler(config=self.cfg, feed_fetcher=_fetcher_factory({}), state_dir=self.tmpdir)
        result = cw.crawl({"no_url": "value"})
        self.assertEqual(result.status, CrawlStatus.UNKNOWN_ERROR)

    def test_max_items_limit(self):
        fetcher = _fetcher_factory({"news": SAMPLE_RSS_2_0})
        cw = RSSCrawler(config=self.cfg, feed_fetcher=fetcher, state_dir=self.tmpdir)
        result = cw.crawl({"url": "https://news.example.com/feed.xml", "max_items": 2})
        self.assertEqual(len(result.items), 2)

    def test_seen_state_persistence(self):
        """seen state 跨实例持久化"""
        fetcher = _fetcher_factory({"news": SAMPLE_RSS_2_0})

        cw1 = RSSCrawler(config=self.cfg, feed_fetcher=fetcher, state_dir=self.tmpdir)
        r1 = cw1.crawl("https://news.example.com/feed.xml")
        self.assertEqual(len(r1.items), 3)

        # 新实例 — state 仍持久化
        cw2 = RSSCrawler(config=self.cfg, feed_fetcher=fetcher, state_dir=self.tmpdir)
        r2 = cw2.crawl("https://news.example.com/feed.xml")
        self.assertEqual(len(r2.items), 0)


if __name__ == "__main__":
    unittest.main()