"""test_registry.py — jobs 包 registry 测试 (P20-B2)

覆盖:
    1. 4 渠道都注册到 CHANNEL_REGISTRY
    2. get_channel() 工厂函数正常返回
    3. list_channels() 返回正确列表
    4. 未知渠道名抛 ValueError
    5. 所有渠道都继承 BaseCrawlerChannel
    6. parse() / search() 接口在所有渠道存在
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest

import httpx

_THIS = os.path.dirname(os.path.abspath(__file__))
_JOBS_DIR = os.path.dirname(_THIS)
_CHANNELS_DIR = os.path.dirname(_JOBS_DIR)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_CHANNELS_DIR)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from imdf.crawler.channels.jobs import (  # noqa: E402
    CHANNEL_REGISTRY,
    BaseCrawlerChannel,
    BossZhipinChannel,
    CrawlResult,
    Job51Channel,
    JobPosting,
    LagouChannel,
    ZhilianChannel,
    get_channel,
    list_channels,
)


class TestJobsRegistry(unittest.TestCase):

    def test_registry_has_four_channels(self):
        self.assertEqual(len(CHANNEL_REGISTRY), 4)

    def test_registry_contains_all_names(self):
        names = set(CHANNEL_REGISTRY.keys())
        self.assertEqual(
            names,
            {"lagou", "bosszhipin", "zhilian", "job51"},
        )

    def test_list_channels_returns_sorted(self):
        names = list_channels()
        self.assertEqual(names, ["bosszhipin", "job51", "lagou", "zhilian"])

    def test_get_channel_returns_instance(self):
        ch = get_channel("lagou")
        self.assertIsInstance(ch, LagouChannel)
        ch2 = get_channel("bosszhipin")
        self.assertIsInstance(ch2, BossZhipinChannel)

    def test_get_channel_unknown_raises(self):
        with self.assertRaises(ValueError) as ctx:
            get_channel("not_a_real_channel")
        self.assertIn("not_a_real_channel", str(ctx.exception))

    def test_get_channel_passes_kwargs(self):
        ch = get_channel("lagou", timeout=5.0, rate_limit_rps=2.5)
        self.assertEqual(ch.timeout, 5.0)

    def test_all_channels_inherit_base(self):
        for cls in CHANNEL_REGISTRY.values():
            self.assertTrue(
                issubclass(cls, BaseCrawlerChannel),
                f"{cls.__name__} does not extend BaseCrawlerChannel",
            )

    def test_all_channels_have_parse_method(self):
        for name, cls in CHANNEL_REGISTRY.items():
            self.assertTrue(
                hasattr(cls, "parse"),
                f"{name} missing parse()",
            )
            self.assertTrue(callable(cls.parse), f"{name}.parse not callable")

    def test_all_channels_have_search_method(self):
        for name, cls in CHANNEL_REGISTRY.items():
            self.assertTrue(
                hasattr(cls, "search"),
                f"{name} missing search()",
            )

    def test_all_channels_have_channel_attr(self):
        for name, cls in CHANNEL_REGISTRY.items():
            self.assertEqual(cls.channel, name)

    def test_all_channels_have_api_endpoint(self):
        for name, cls in CHANNEL_REGISTRY.items():
            self.assertTrue(
                cls.api_endpoint,
                f"{name} missing api_endpoint",
            )
            self.assertIn("http", cls.api_endpoint)


class TestJobPostingModel(unittest.TestCase):

    def test_job_posting_minimal(self):
        p = JobPosting(id="x1", title="Engineer")
        self.assertEqual(p.id, "x1")
        self.assertEqual(p.title, "Engineer")
        self.assertEqual(p.tags, [])
        self.assertIsInstance(p.crawled_at.__class__, type)

    def test_job_posting_full(self):
        p = JobPosting(
            id="x2", title="Senior", company="ACME",
            salary="30-50K", location="BJ", url="https://example.com/x",
            source="lagou", description="Senior Python dev",
            tags=["Python", "Django"],
        )
        d = p.to_dict() if hasattr(p, "to_dict") else p.model_dump()
        self.assertEqual(d["company"], "ACME")
        self.assertEqual(d["tags"], ["Python", "Django"])

    def test_crawl_result_from_posting(self):
        p = JobPosting(id="x3", title="Dev", source="lagou")
        cr = CrawlResult.from_posting(p)
        self.assertEqual(cr.id, "x3")
        self.assertEqual(cr.title, "Dev")
        self.assertEqual(cr.source, "lagou")
        self.assertIs(cr.posting, p)


if __name__ == "__main__":
    unittest.main()
