"""test_item_schema_10.py — P19-C1-fix P0 #2
5 渠道全部 _build_item() 返回统一 10 字段 CrawledItem.

10 字段:
    id, url, title, description, source, author, keywords,
    created_at, thumbnail_url, extra

验证 (5 渠道 × N 项目):
- 所有 10 字段都存在
- 字段类型正确
- source = 渠道名
- extra 是 Dict (可空)
- 一次 mock 调用能返回多个 CrawledItem
"""
import os
import sys
import unittest
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_THIS = os.path.dirname(os.path.abspath(__file__))
_CRAWLER_DIR = os.path.dirname(_THIS)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_CRAWLER_DIR)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from imdf.crawler.base import CrawledItem
from imdf.crawler.config import make_default_config, RobotsPolicy
from imdf.crawler.channels.google_images import GoogleImagesCrawler
from imdf.crawler.channels.open_images import OpenImagesCrawler
from imdf.crawler.channels.flickr import FlickrCrawler
from imdf.crawler.channels.unsplash import UnsplashCrawler
from imdf.crawler.channels.pixabay import PixabayCrawler


def _make_mock_fetcher(channel_name: str, count: int = 5):
    """按渠道返回不同 mock 数据"""

    def fetcher(url: str, headers: Dict[str, str], timeout: float):
        if channel_name == "google_images":
            return _mock_json({
                "items": [
                    {
                        "title": f"google_img_{i}",
                        "link": f"https://example.com/g_{i}.jpg",
                        "snippet": "google mock",
                        "cacheId": f"gid_{i}",
                        "image": {
                            "thumbnailLink": f"https://example.com/g_thumb_{i}.jpg",
                            "width": 1024, "height": 768,
                            "contextLink": f"https://example.com/page_{i}",
                        },
                    } for i in range(count)
                ],
                "searchInformation": {"totalResults": str(count * 100)},
            }), 200, None
        if channel_name == "open_images":
            lines = ["ImageID,OriginalURL,Rotation,License"]
            for i in range(max(count, 10)):
                lines.append(f"img_{i:04d},https://example.com/open_{i}.jpg,0,CC-BY 2.0")
            return "\n".join(lines).encode("utf-8"), 200, None
        if channel_name == "flickr":
            return _mock_json({
                "photos": {
                    "page": 1, "pages": 1, "perpage": count, "total": str(count * 10),
                    "photo": [
                        {
                            "id": f"f_{i}", "owner": f"owner_{i}",
                            "secret": "sec", "server": "1", "farm": 1,
                            "title": f"flickr_{i}", "license": "4",
                        } for i in range(count)
                    ],
                }
            }), 200, None
        if channel_name == "unsplash":
            return _mock_json({
                "total": count * 100, "total_pages": 5,
                "results": [
                    {
                        "id": f"u_{i}", "description": f"unsplash desc {i}",
                        "alt_description": f"unsplash_{i}",
                        "width": 1920, "height": 1080, "color": "#abc",
                        "urls": {
                            "raw": f"https://example.com/raw_{i}",
                            "full": f"https://example.com/full_{i}",
                            "regular": f"https://example.com/regular_{i}",
                            "small": f"https://example.com/small_{i}",
                            "thumb": f"https://example.com/thumb_{i}",
                        },
                        "user": {"name": f"Photographer {i}",
                                 "links": {"html": f"https://unsplash.com/@user{i}"}},
                    } for i in range(count)
                ],
            }), 200, None
        if channel_name == "pixabay":
            return _mock_json({
                "total": count * 50, "totalHits": count * 50,
                "hits": [
                    {
                        "id": 1000000 + i,
                        "pageURL": f"https://pixabay.com/mock/{i}",
                        "tags": "test, mock, fixture",  # ⚠ tags — 不能再进 title
                        "previewURL": f"https://example.com/preview_{i}.jpg",
                        "webformatURL": f"https://example.com/web_{i}.jpg",
                        "largeImageURL": f"https://example.com/large_{i}.jpg",
                        "imageWidth": 1920, "imageHeight": 1080,
                        "user": f"pixabay_uploader_{i}",
                        "user_id": 1000 + i,
                    } for i in range(count)
                ],
            }), 200, None
        return b"", 0, "not mocked"

    return fetcher


def _mock_json(obj: dict) -> bytes:
    import json
    return json.dumps(obj).encode("utf-8")


# 10 字段 schema
SCHEMA = (
    "id", "url", "title", "description", "source",
    "author", "keywords", "created_at", "thumbnail_url", "extra",
)


def _validate_item(item: Dict[str, Any], expected_source: str) -> None:
    """断言 item 是合法 CrawledItem.to_dict()"""
    assert isinstance(item, dict), f"item not dict: {type(item)}"
    for f in SCHEMA:
        assert f in item, f"missing field {f} in item keys={list(item.keys())}"
    assert item["source"] == expected_source, f"source={item['source']} != {expected_source}"
    # 类型校验
    assert isinstance(item["id"], str)
    assert isinstance(item["url"], str)
    assert isinstance(item["title"], str)
    assert isinstance(item["description"], str)
    assert isinstance(item["source"], str)
    assert isinstance(item["author"], str)
    assert isinstance(item["keywords"], list)
    assert isinstance(item["created_at"], str)  # ISO format after to_dict()
    assert isinstance(item["thumbnail_url"], str)
    assert isinstance(item["extra"], dict)


class TestGoogleImages10Fields(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("google_images")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False
        self.cw = GoogleImagesCrawler(
            config=self.cfg, api_key="fake", cx="fake", mock=False,
            http_fetcher=_make_mock_fetcher("google_images", count=3),
        )

    def test_10_fields(self):
        result = self.cw.crawl({"query": "x", "count": 3})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)
        for it in result.items:
            _validate_item(it, "google_images")
        # url/thumbnail 非空
        for it in result.items:
            self.assertTrue(it["url"])
            self.assertTrue(it["thumbnail_url"])
        # 验证 _build_item 直接返回 CrawledItem
        ci = self.cw._build_item({
            "title": "t", "link": "https://x.com/a.jpg", "cacheId": "abc",
            "image": {"thumbnailLink": "https://x.com/thumb.jpg",
                       "width": 100, "height": 200, "contextLink": ""},
        }, {"query": "x"}, 0)
        self.assertIsInstance(ci, CrawledItem)
        self.assertEqual(ci.source, "google_images")
        self.assertEqual(ci.extra["width"], 100)


class TestOpenImages10Fields(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("open_images")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False
        self.cw = OpenImagesCrawler(
            config=self.cfg, mock=False,
            http_fetcher=_make_mock_fetcher("open_images"),
        )

    def test_10_fields(self):
        result = self.cw.crawl({"query": "trees", "count": 5})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 5)
        for it in result.items:
            _validate_item(it, "open_images")
        # open_images: license 在 extra, top-level compat 也应该有
        for it in result.items:
            self.assertEqual(it.get("license"), "CC-BY 2.0")


class TestFlickr10Fields(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("flickr")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False
        self.cw = FlickrCrawler(
            config=self.cfg, api_key="fake", mock=False,
            http_fetcher=_make_mock_fetcher("flickr"),
        )

    def test_10_fields(self):
        result = self.cw.crawl({"query": "sunset", "count": 5})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 5)
        for it in result.items:
            _validate_item(it, "flickr")
        # author = owner
        self.assertEqual(result.items[0]["author"], "owner_0")


class TestUnsplash10Fields(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("unsplash")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False
        self.cw = UnsplashCrawler(
            config=self.cfg, api_key="fake", mock=False,
            http_fetcher=_make_mock_fetcher("unsplash"),
        )

    def test_10_fields(self):
        result = self.cw.crawl({"query": "beach", "count": 5})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 5)
        for it in result.items:
            _validate_item(it, "unsplash")
        # author = user.name
        self.assertIn("Photographer", result.items[0]["author"])
        # width/height 在 extra
        self.assertEqual(result.items[0]["width"], 1920)


class TestPixabay10Fields(unittest.TestCase):

    def setUp(self):
        self.cfg = make_default_config("pixabay")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False
        self.cw = PixabayCrawler(
            config=self.cfg, api_key="fake", mock=False,
            http_fetcher=_make_mock_fetcher("pixabay"),
        )

    def test_10_fields(self):
        result = self.cw.crawl({"query": "flowers", "count": 5})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 5)
        for it in result.items:
            _validate_item(it, "pixabay")
        # author = user
        self.assertEqual(result.items[0]["author"], "pixabay_uploader_0")
        # title 应该 != tags
        self.assertNotIn("tags:", result.items[0]["title"])


class TestCrawledItemToDict(unittest.TestCase):
    """CrawledItem.to_dict() 序列化 — 顶层兼容字段 (mock/license/width/height/tags)"""

    def test_to_dict_includes_compat_fields(self):
        ci = CrawledItem(
            id="abc", url="https://x.com/a.jpg", title="t",
            description="d", source="test", author="me",
            keywords=["k1", "k2"],
            created_at=datetime(2026, 7, 1, 12, 0, 0),
            thumbnail_url="https://x.com/thumb.jpg",
            extra={"mock": True, "license": "MIT", "width": 100, "height": 200},
        )
        d = ci.to_dict()
        for f in SCHEMA:
            self.assertIn(f, d)
        # 顶层兼容字段
        self.assertTrue(d["mock"])
        self.assertEqual(d["license"], "MIT")
        self.assertEqual(d["width"], 100)
        self.assertEqual(d["height"], 200)
        # datetime 序列化为 ISO
        self.assertEqual(d["created_at"], "2026-07-01T12:00:00")

    def test_to_dict_defaults(self):
        ci = CrawledItem(id="x", url="http://x")
        d = ci.to_dict()
        self.assertEqual(d["title"], "")
        self.assertEqual(d["description"], "")
        self.assertEqual(d["source"], "")
        self.assertEqual(d["author"], "")
        self.assertEqual(d["keywords"], [])
        self.assertEqual(d["thumbnail_url"], "")
        self.assertEqual(d["extra"], {})
        # created_at auto-filled
        self.assertIsNotNone(d["created_at"])

    def test_schema_fields_count(self):
        """SCHEMA_FIELDS 必须恰好 10 个"""
        self.assertEqual(len(CrawledItem.SCHEMA_FIELDS), 10)


class TestAllFiveChannelsBuildItem(unittest.TestCase):
    """5 渠道 _build_item() 直接返回 CrawledItem 实例"""

    def _check_build_item(self, channel_cls, raw_data, prep,
                           needs_api_key: bool = True):
        # 仅 requires_key 渠道传 api_key
        if needs_api_key and getattr(channel_cls, "requires_key", False):
            cw = channel_cls(config=make_default_config(channel_cls.channel),
                             mock=False, api_key="fake")
        else:
            cw = channel_cls(config=make_default_config(channel_cls.channel),
                             mock=False)
        ci = cw._build_item(raw_data, prep, 0)
        self.assertIsInstance(ci, CrawledItem)
        self.assertEqual(ci.source, channel_cls.channel)
        return ci

    def test_google_build_item(self):
        ci = self._check_build_item(GoogleImagesCrawler, {
            "title": "t", "link": "http://x.com/a.jpg",
            "cacheId": "abc", "image": {"thumbnailLink": "http://x.com/thumb.jpg",
                                         "width": 100, "height": 200, "contextLink": ""}
        }, {"query": "x"})
        self.assertEqual(ci.id, "abc")
        self.assertEqual(ci.url, "http://x.com/a.jpg")

    def test_open_build_item(self):
        ci = self._check_build_item(OpenImagesCrawler, {
            "ImageID": "img001", "OriginalURL": "http://x.com/open.jpg",
            "Rotation": "0", "License": "CC-BY 2.0",
        }, {"query": "x"}, needs_api_key=False)
        self.assertEqual(ci.id, "img001")
        self.assertEqual(ci.extra.get("license"), "CC-BY 2.0")

    def test_flickr_build_item(self):
        ci = self._check_build_item(FlickrCrawler, {
            "id": "f_001", "owner": "owner_x", "secret": "s", "server": "1", "farm": 1,
            "title": "flickr_title", "license": "4",
        }, {"query": "x"})
        self.assertEqual(ci.id, "f_001")
        self.assertEqual(ci.author, "owner_x")

    def test_unsplash_build_item(self):
        ci = self._check_build_item(UnsplashCrawler, {
            "id": "u_001", "description": "d", "alt_description": "a",
            "width": 100, "height": 200, "color": "#fff",
            "urls": {"regular": "http://x.com/r.jpg", "thumb": "http://x.com/t.jpg"},
            "user": {"name": "Photographer", "links": {"html": "http://u.com"}},
        }, {"query": "x"})
        self.assertEqual(ci.id, "u_001")
        self.assertEqual(ci.author, "Photographer")

    def test_pixabay_build_item(self):
        ci = self._check_build_item(PixabayCrawler, {
            "id": 100, "tags": "sky, cloud, blue", "user": "uploader_X",
            "imageWidth": 800, "imageHeight": 600,
            "largeImageURL": "http://x.com/l.jpg",
            "previewURL": "http://x.com/p.jpg",
            "pageURL": "http://x.com/page",
        }, {"query": "x"})
        self.assertEqual(ci.id, "100")
        self.assertEqual(ci.author, "uploader_X")
        # title 应该是 user, 不是 tags
        self.assertEqual(ci.title, "uploader_X")
        self.assertNotIn("tags:", ci.title)


if __name__ == "__main__":
    unittest.main()
