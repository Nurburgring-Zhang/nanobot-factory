"""test_pixabay_title.py — P19-C1-fix P0 #3
Pixabay title 字段不能填 tags — title 应反映 user/uploader name.

修复: 把 tags 移到 keywords, title 用 user (uploader) 字段.
"""
import os
import sys
import unittest
from typing import Any, Dict

_THIS = os.path.dirname(os.path.abspath(__file__))
_CRAWLER_DIR = os.path.dirname(_THIS)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_CRAWLER_DIR)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from imdf.crawler.channels.pixabay import PixabayCrawler
from imdf.crawler.config import make_default_config, RobotsPolicy


def _mock_pixabay_fetcher(url: str, headers: Dict[str, str], timeout: float):
    import json
    return json.dumps({
        "total": 100, "totalHits": 100,
        "hits": [
            {
                "id": 1000000 + i,
                "pageURL": f"https://pixabay.com/mock/{i}",
                # 故意把 tags 写长, 像真实数据
                "tags": f"sky, sunset, beach, ocean, palm tree, vacation, travel, summer, mock_{i}",
                "previewURL": f"https://example.com/preview_{i}.jpg",
                "webformatURL": f"https://example.com/web_{i}.jpg",
                "largeImageURL": f"https://example.com/large_{i}.jpg",
                "imageWidth": 1920, "imageHeight": 1080,
                "user": f"photographer_{i}",
                "user_id": 1000 + i,
            }
            for i in range(20)
        ],
    }).encode("utf-8"), 200, None


class TestPixabayTitleFix(unittest.TestCase):
    """验证 title 字段不再是 tags 字符串"""

    def setUp(self):
        self.cfg = make_default_config("pixabay")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False
        self.cw = PixabayCrawler(
            config=self.cfg, api_key="fake", mock=False,
            http_fetcher=_mock_pixabay_fetcher,
        )

    def test_title_no_tags_prefix(self):
        """title 字段不应包含 'tags:' 前缀或任何 tag 字符串"""
        result = self.cw.crawl({"query": "travel", "count": 20})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 20)
        for it in result.items:
            # 验证 title 不是 tags 列表
            self.assertNotIn("tags:", it["title"], f"title contains 'tags:': {it['title']}")
            # 验证 title 不含 tags 字符串 (逗号分隔多 tag)
            self.assertFalse(
                it["title"].startswith("sky, "),
                f"title starts with tags list: {it['title']}",
            )
            # 验证 title 是 photographer user name
            self.assertIn("photographer_", it["title"])

    def test_keywords_have_tags(self):
        """keywords 字段应该包含 tags (修正后 tags 移到 keywords)"""
        result = self.cw.crawl({"query": "travel", "count": 5})
        self.assertTrue(result.ok)
        for it in result.items[:3]:
            self.assertIsInstance(it["keywords"], list)
            self.assertGreater(len(it["keywords"]), 0, "keywords should not be empty")

    def test_author_user_field(self):
        """author 字段 = user (uploader name)"""
        result = self.cw.crawl({"query": "travel", "count": 5})
        self.assertTrue(result.ok)
        for it in result.items:
            self.assertIn("photographer_", it["author"])
            # author == title
            self.assertEqual(it["author"], it["title"])

    def test_100_mock_calls_title_consistent(self):
        """100 次 mock 调用全部 title 都用 user 字段"""
        for i in range(100):
            cw = PixabayCrawler(
                config=self.cfg, api_key="fake", mock=False,
                http_fetcher=_mock_pixabay_fetcher,
            )
            result = cw.crawl({"query": f"q{i}", "count": 3})
            self.assertTrue(result.ok)
            for it in result.items:
                self.assertNotIn("tags:", it["title"])
                self.assertNotIn(",", it["title"],
                                  f"title contains comma (likely tags list): {it['title']!r}")
                self.assertIn("photographer_", it["title"])


if __name__ == "__main__":
    unittest.main()
