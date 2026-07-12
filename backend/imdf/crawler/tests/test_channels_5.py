"""test_channels_5.py — 5 渠道适配器测试 (全部 mock)"""
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

from imdf.crawler.channels.google_images import GoogleImagesCrawler
from imdf.crawler.channels.open_images import OpenImagesCrawler
from imdf.crawler.channels.flickr import FlickrCrawler
from imdf.crawler.channels.unsplash import UnsplashCrawler
from imdf.crawler.channels.pixabay import PixabayCrawler
from imdf.crawler.engine import CrawlerEngine
from imdf.crawler.base import CrawlStatus, CrawlResult
from imdf.crawler.config import make_default_config, RobotsPolicy


def _mock_http_fetcher(url: str, headers: Dict[str, str], timeout: float) -> Tuple[bytes, int, Optional[str]]:
    """通用 mock fetcher — 按 URL 路径返回不同 JSON"""
    # 顺序很重要: openimages 比 googleapis 更具体 (都是 google 域名)
    if "openimages" in url:
        lines = ["ImageID,OriginalURL,Rotation,License"]
        for i in range(3):
            lines.append(f"img_{i},https://example.com/open_{i}.jpg,0,CC-BY 2.0")
        return "\n".join(lines).encode("utf-8"), 200, None
    if "googleapis" in url:
        return json.dumps({
            "items": [
                {"title": f"google_img {i}", "link": f"https://example.com/g_{i}.jpg",
                 "snippet": "google", "cacheId": f"gid_{i}",
                 "image": {"thumbnailLink": f"https://example.com/g_thumb_{i}.jpg",
                           "width": 1024, "height": 768, "contextLink": "https://example.com"}}
                for i in range(3)
            ],
            "searchInformation": {"totalResults": "300"},
        }).encode("utf-8"), 200, None
    if "flickr" in url:
        return json.dumps({
            "photos": {
                "page": 1, "pages": 1, "perpage": 3, "total": "30",
                "photo": [
                    {"id": f"f_{i}", "owner": "owner", "secret": "sec", "server": "1", "farm": 1,
                     "title": f"flickr_{i}", "license": "4"}
                    for i in range(3)
                ],
            }
        }).encode("utf-8"), 200, None
    if "unsplash" in url:
        return json.dumps({
            "total": 100, "total_pages": 5,
            "results": [
                {"id": f"u_{i}", "description": f"unsplash {i}",
                 "alt_description": f"unsplash_{i}", "width": 1920, "height": 1080,
                 "color": "#abc", "urls": {"raw": f"https://example.com/raw_{i}",
                                            "full": f"https://example.com/full_{i}",
                                            "regular": f"https://example.com/regular_{i}",
                                            "small": f"https://example.com/small_{i}",
                                            "thumb": f"https://example.com/thumb_{i}"},
                 "user": {"name": "user", "links": {"html": "https://unsplash.com/@user"}}}
                for i in range(3)
            ],
        }).encode("utf-8"), 200, None
    if "pixabay" in url:
        return json.dumps({
            "total": 50, "totalHits": 50,
            "hits": [
                {"id": i, "pageURL": f"https://pixabay.com/mock/{i}",
                 "tags": "test, mock", "previewURL": f"https://example.com/preview_{i}.jpg",
                 "webformatURL": f"https://example.com/web_{i}.jpg",
                 "largeImageURL": f"https://example.com/large_{i}.jpg",
                 "imageWidth": 1920, "imageHeight": 1080,
                 "user": f"user_{i}", "user_id": 1000 + i}
                for i in range(3)
            ],
        }).encode("utf-8"), 200, None
    return b"", 0, "not mocked"


class TestGoogleImagesChannel(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("google_images")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False

    def test_mock_mode_no_key(self):
        cw = GoogleImagesCrawler(config=self.cfg, mock=True)
        self.assertTrue(cw.mock)
        result = cw.crawl({"query": "cats", "count": 5})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 5)
        self.assertEqual(result.items[0]["source"], "google_images")
        self.assertTrue(result.items[0]["mock"])

    def test_with_mock_fetcher(self):
        cw = GoogleImagesCrawler(
            config=self.cfg,
            api_key="fake_key_12345",
            cx="fake_cx_12345",
            mock=False,
            http_fetcher=_mock_http_fetcher,
        )
        result = cw.crawl({"query": "dogs", "count": 3})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)
        self.assertIn("google_img", result.items[0]["title"])
        self.assertEqual(result.metadata["query"], "dogs")

    def test_string_target(self):
        cw = GoogleImagesCrawler(config=self.cfg, mock=True)
        result = cw.crawl("cats")
        self.assertTrue(result.ok)

    def test_invalid_target(self):
        cw = GoogleImagesCrawler(config=self.cfg, mock=True)
        result = cw.crawl({"no_query": "value"})
        self.assertEqual(result.status, CrawlStatus.UNKNOWN_ERROR)


class TestOpenImagesChannel(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("open_images")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False

    def test_mock_mode(self):
        cw = OpenImagesCrawler(config=self.cfg, mock=True)
        result = cw.crawl({"query": "cars", "count": 4})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 4)
        for item in result.items:
            self.assertEqual(item["source"], "open_images")
            self.assertEqual(item["license"], "CC-BY 2.0")
            self.assertTrue(item["mock"])

    def test_with_mock_fetcher(self):
        cw = OpenImagesCrawler(config=self.cfg, mock=False, http_fetcher=_mock_http_fetcher)
        result = cw.crawl({"query": "trees", "count": 3})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)

    def test_no_key_required(self):
        cw = OpenImagesCrawler(config=self.cfg, mock=False)
        # 无 key 时仍能拉取 (公开 CSV)
        self.assertFalse(cw.requires_key)


class TestFlickrChannel(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("flickr")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False

    def test_mock_mode_no_key(self):
        cw = FlickrCrawler(config=self.cfg, mock=True)
        self.assertTrue(cw.mock)
        result = cw.crawl({"query": "sunsets", "count": 5})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 5)
        self.assertIn("mock_sunsets_0000", result.items[0]["id"])

    def test_with_mock_fetcher(self):
        cw = FlickrCrawler(
            config=self.cfg,
            api_key="fake_flickr_key",
            mock=False,
            http_fetcher=_mock_http_fetcher,
        )
        result = cw.crawl({"query": "mountains", "count": 3})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)
        # Verify Flickr URL pattern
        self.assertIn("staticflickr.com", result.items[0]["url"])
        self.assertEqual(result.metadata["query"], "mountains")


class TestUnsplashChannel(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("unsplash")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False

    def test_mock_mode(self):
        cw = UnsplashCrawler(config=self.cfg, mock=True)
        result = cw.crawl({"query": "beach", "count": 5})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 5)
        self.assertEqual(result.items[0]["source"], "unsplash")

    def test_with_mock_fetcher(self):
        cw = UnsplashCrawler(
            config=self.cfg,
            api_key="fake_unsplash_key",
            mock=False,
            http_fetcher=_mock_http_fetcher,
        )
        result = cw.crawl({"query": "ocean", "count": 3})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)
        # URL 应是 regular 或 full 之一
        self.assertIn("regular", result.items[0]["url"])

    def test_string_target(self):
        cw = UnsplashCrawler(config=self.cfg, mock=True)
        result = cw.crawl("forest")
        self.assertTrue(result.ok)


class TestPixabayChannel(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("pixabay")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False

    def test_mock_mode(self):
        cw = PixabayCrawler(config=self.cfg, mock=True)
        result = cw.crawl({"query": "flowers", "count": 5})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 5)
        self.assertEqual(result.items[0]["source"], "pixabay")
        self.assertTrue(result.items[0]["mock"])

    def test_with_mock_fetcher(self):
        cw = PixabayCrawler(
            config=self.cfg,
            api_key="fake_pixabay_key",
            mock=False,
            http_fetcher=_mock_http_fetcher,
        )
        result = cw.crawl({"query": "sky", "count": 3})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)
        self.assertEqual(result.items[0]["license"], "pixabay-license")

    def test_string_target(self):
        cw = PixabayCrawler(config=self.cfg, mock=True)
        result = cw.crawl("night")
        self.assertTrue(result.ok)


def _make_mock_factory(channel: str):
    """构造一个 mock 模式的渠道 crawler 工厂 — 给 engine 用,避免真实网络调用.

    兼容 P19-C1-fix P0 #1: 引擎可能会传 mock= kwarg (从 self.default_mock).
    工厂优先使用传入的 mock, 否则默认 True.
    """
    from imdf.crawler.channels.google_images import GoogleImagesCrawler
    from imdf.crawler.channels.open_images import OpenImagesCrawler
    from imdf.crawler.channels.flickr import FlickrCrawler
    from imdf.crawler.channels.unsplash import UnsplashCrawler
    from imdf.crawler.channels.pixabay import PixabayCrawler

    table = {
        "google_images": GoogleImagesCrawler,
        "open_images": OpenImagesCrawler,
        "flickr": FlickrCrawler,
        "unsplash": UnsplashCrawler,
        "pixabay": PixabayCrawler,
    }
    cls = table[channel]

    def factory(config=None, **kwargs):
        # 接收引擎传入的 mock (engine.get_crawler 会传) — pop 避免重复
        # 默认 mock=True (keyless 渠道 open_images 也强制 mock)
        mock_flag = kwargs.pop("mock", True)
        return cls(config=config, mock=mock_flag, **kwargs)
    factory.channel = channel
    return factory


class TestCrawlerEngine(unittest.TestCase):
    """CrawlerEngine — 集成 5 渠道 (全部 mock=True 避免真网络)"""

    def setUp(self):
        self.cfg_robots = RobotsPolicy.IGNORE
        # 提升 RPS 避免限速卡住
        os.environ["CRAWLER_TEST_FAST"] = "1"

    def _make_engine(self, max_concurrent: int = 4) -> CrawlerEngine:
        engine = CrawlerEngine(max_concurrent=max_concurrent)
        # 用 mock=True 工厂替换 5 渠道 — 避免真网络
        for ch in ("google_images", "open_images", "flickr", "unsplash", "pixabay"):
            engine.register(ch, _make_mock_factory(ch))
        # 提升 RPS 避免限速瓶颈 (rate_limit.rps)
        # crawler 实例在 get_crawler() 时懒创建, 所以先获取再改 rps
        return engine

    def _boost_rate(self, engine: CrawlerEngine) -> None:
        """预热并把 rps 提到 100, 避免测试限速瓶颈"""
        for ch in engine.list_channels():
            try:
                c = engine.get_crawler(ch)
                c.config.rate_limit.rps = 100.0
                c.config.rate_limit.jitter_seconds = 0.0
            except Exception:
                pass

    def test_engine_registers_5_default_channels(self):
        engine = self._make_engine(max_concurrent=4)
        channels = engine.list_channels()
        for ch in ("google_images", "open_images", "flickr", "unsplash", "pixabay"):
            self.assertIn(ch, channels, f"missing channel: {ch}")
        # 也应注册通用 crawler
        for ch in ("web", "api", "rss"):
            self.assertIn(ch, channels)
        engine.shutdown()

    def test_submit_and_wait(self):
        engine = self._make_engine(max_concurrent=2)
        self._boost_rate(engine)
        job_id = engine.submit("google_images", {"query": "test", "count": 3})
        result = engine.get_result(job_id, timeout=10)
        self.assertIsNotNone(result)
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)
        engine.shutdown()

    def test_crawl_batch_sequential(self):
        engine = self._make_engine(max_concurrent=4)
        self._boost_rate(engine)
        results = engine.crawl_batch([
            ("google_images", {"query": "a", "count": 2}),
            ("open_images", {"query": "b", "count": 2}),
            ("unsplash", {"query": "c", "count": 2}),
        ], sync=True)
        self.assertGreaterEqual(len(results), 3)
        for r in results.values():
            self.assertTrue(r.ok, f"job failed: error={r.error!r} status={r.status.value}")
        engine.shutdown()

    def test_crawl_batch_async(self):
        engine = self._make_engine(max_concurrent=8)
        self._boost_rate(engine)
        results = engine.crawl_batch([
            ("google_images", {"query": "async_a", "count": 2}),
            ("pixabay", {"query": "async_b", "count": 2}),
        ], sync=False)
        self.assertGreaterEqual(len(results), 2)
        engine.shutdown()

    def test_unknown_channel_raises(self):
        engine = self._make_engine()
        with self.assertRaises(ValueError):
            engine.submit("nonexistent_channel", {})
        engine.shutdown()

    def test_get_job_returns_state(self):
        engine = self._make_engine(max_concurrent=2)
        self._boost_rate(engine)
        job_id = engine.submit("flickr", {"query": "test", "count": 2})
        job = engine.get_job(job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job.channel, "flickr")
        engine.shutdown()

    def test_list_jobs_filter(self):
        engine = self._make_engine(max_concurrent=4)
        self._boost_rate(engine)
        engine.submit("google_images", {"query": "x", "count": 2})
        engine.submit("unsplash", {"query": "y", "count": 2})
        import time as t
        t.sleep(0.2)
        pix_job = engine.submit("pixabay", {"query": "z", "count": 2})
        engine.wait_for(pix_job, timeout=10)
        t.sleep(0.5)
        completed = engine.list_jobs()
        self.assertGreater(len(completed), 0)
        engine.shutdown()


if __name__ == "__main__":
    import time as _t
    unittest.main()