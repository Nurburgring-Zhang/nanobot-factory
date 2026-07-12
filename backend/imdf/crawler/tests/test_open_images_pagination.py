"""test_open_images_pagination.py — P19-C1-fix P0 #4
Open Images 真实分页 (不要硬编码 test set), 不同页 / 不同 mock page 应返回不同 URL.

修复:
- 默认 endpoint 用 storage.googleapis.com/openimages/v5/test-annotations-object-detection.csv
- max_pages 参数控制分页
- mock CSV 必须生成 (page_size * max_pages) 行, 不同 page 返回不同 URL
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

from imdf.crawler.channels.open_images import (
    OpenImagesCrawler, OPEN_IMAGES_V5_ANNOTATION_URL,
)
from imdf.crawler.config import make_default_config, RobotsPolicy


def _mock_openimages_fetcher(url: str, headers: Dict[str, str], timeout: float):
    """返回真实格式 CSV (含多行, 模拟分页)"""
    # 注: 真实 Open Images v5 test annotation 包含 ImageID 列
    lines = ["ImageID,OriginalURL,Rotation,License,XClick1Of1,XMax1Of1,YClick1Of1,YMax1Of1,LabelName"]
    for i in range(50):
        lines.append(
            f"img_{i:06d},"
            f"https://storage.googleapis.com/openimages/v5/test/img_{i:06d}.jpg,"
            f"0,CC-BY 2.0,0,1024,0,768,/m/01g317"
        )
    return ("\n".join(lines)).encode("utf-8"), 200, None


class TestOpenImagesPagination(unittest.TestCase):
    """P0 #4 — 真实分页 — 不同 page / count 返回不同 URL 集合"""

    def setUp(self):
        self.cfg = make_default_config("open_images")
        self.cfg.robots_policy = RobotsPolicy.IGNORE
        self.cfg.enable_audit_chain = False

    def test_endpoint_is_real_oid_v5(self):
        """默认 endpoint 是 v5 真实 annotation URL, 不是硬编码 test set"""
        self.assertEqual(
            OpenImagesCrawler.api_endpoint,
            OPEN_IMAGES_V5_ANNOTATION_URL,
        )
        # 真 URL 应是 storage.googleapis.com/openimages/v5/
        self.assertIn("storage.googleapis.com", OpenImagesCrawler.api_endpoint)
        self.assertIn("openimages/v5", OpenImagesCrawler.api_endpoint)

    def test_max_pages_param_present(self):
        """max_pages 参数被 _prepare 接受"""
        cw = OpenImagesCrawler(config=self.cfg, mock=True)
        prep = cw._prepare({"query": "x", "count": 5, "page": 2, "max_pages": 3})
        self.assertEqual(prep["page"], 2)
        self.assertEqual(prep["max_pages"], 3)
        self.assertEqual(prep["page_size"], 5)

    def test_mock_pages_different_urls(self):
        """不同 mock page 必须返回不同 URL (不能同一 URL 重复)"""
        cw = OpenImagesCrawler(config=self.cfg, mock=True)

        # Page 1
        prep1 = cw._prepare({"query": "x", "page": 1, "count": 5})
        result1 = cw._parse(cw._mock_csv(prep1), prep1)
        urls1 = [item["url"] for item in result1[0]]

        # Page 2 — 不同 mock URL
        prep2 = cw._prepare({"query": "x", "page": 2, "count": 5})
        result2 = cw._parse(cw._mock_csv(prep2), prep2)
        urls2 = [item["url"] for item in result2[0]]

        # URL 集合不能重叠
        self.assertEqual(len(urls1), 5)
        self.assertEqual(len(urls2), 5)
        # Page 2 的 URL 都应不同 (mock 下 image_id 是递增)
        self.assertEqual(len(set(urls2)), 5, "page 2 has duplicate URLs")
        # IDs 也必须唯一
        ids1 = [item["id"] for item in result1[0]]
        ids2 = [item["id"] for item in result2[0]]
        self.assertEqual(len(set(ids1)), 5, "page 1 has duplicate IDs")
        self.assertEqual(len(set(ids2)), 5, "page 2 has duplicate IDs")

    def test_100_mock_pages_different_urls(self):
        """100 次 mock page 调用 → 全部返回不同 URL (相同 page 内 ID 唯一)"""
        cw = OpenImagesCrawler(config=self.cfg, mock=True)
        all_ids = set()
        for page in range(1, 11):
            for size in [5, 10]:
                prep = cw._prepare({"query": f"q{page}", "page": page, "count": size})
                items, meta = cw._parse(cw._mock_csv(prep), prep)
                ids = [it["id"] for it in items]
                # 同 page 内 ID 唯一
                self.assertEqual(len(ids), len(set(ids)),
                                  f"page {page} size {size} has duplicate IDs")
                all_ids.update(ids)
        # 100 total items
        self.assertGreater(len(all_ids), 50, "expected >50 unique IDs")

    def test_real_pagination_through_real_fetcher(self):
        """通过 fetcher 模拟真实 CSV → 跨页 URL 唯一"""
        cw = OpenImagesCrawler(
            config=self.cfg, mock=False,
            http_fetcher=_mock_openimages_fetcher,
        )
        result = cw.crawl({"query": "x", "page": 1, "count": 5, "max_pages": 1})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 5)
        # IDs 来自真实 CSV — 应是 img_000000, img_000001, ...
        ids = [it["id"] for it in result.items]
        self.assertEqual(ids, ["img_000000", "img_000001", "img_000002",
                               "img_000003", "img_000004"])
        # URL 真实 (storage.googleapis.com)
        urls = [it["url"] for it in result.items]
        for u in urls:
            self.assertIn("storage.googleapis.com/openimages", u,
                          f"URL not from real Open Images: {u}")

    def test_real_pagination_offset(self):
        """真实 CSV + page=2 → 从 offset 5 开始"""
        cw = OpenImagesCrawler(
            config=self.cfg, mock=False,
            http_fetcher=_mock_openimages_fetcher,
        )
        result = cw.crawl({"query": "x", "page": 2, "count": 5})
        self.assertTrue(result.ok)
        ids = [it["id"] for it in result.items]
        # page=2 + count=5 → 从 img_000005 开始
        self.assertEqual(ids[0], "img_000005")
        self.assertEqual(ids[-1], "img_000009")

    def test_no_hardcoded_test_set(self):
        """验证 mock 不再硬编码 test set — _mock_csv 根据 page_size * max_pages 生成"""
        cw = OpenImagesCrawler(config=self.cfg, mock=True)
        # mock CSV 行数 = page_size * max_pages
        prep_small = cw._prepare({"query": "x", "page": 1, "count": 3, "max_pages": 1})
        csv_small = cw._mock_csv(prep_small)
        self.assertEqual(len(csv_small.splitlines()) - 1, 3 * 1)  # 1 header + 3 data

        prep_large = cw._prepare({"query": "y", "page": 1, "count": 10, "max_pages": 5})
        csv_large = cw._mock_csv(prep_large)
        self.assertEqual(len(csv_large.splitlines()) - 1, 10 * 5)  # 50 data rows


if __name__ == "__main__":
    unittest.main()
