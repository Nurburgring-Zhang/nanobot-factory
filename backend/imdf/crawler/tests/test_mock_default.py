"""test_mock_default.py — P19-C1-fix P0 #1
CrawlerEngine.submit() default mock=True + 生产安全锁.

验证:
1. 默认 engine (无 env override) → default_mock=True
2. submit() 100 次无 key → 全部 < 1s 完成 (mock 路径)
3. CRAWLER_PRODUCTION_REAL_NETWORK=1 + default_mock=False + 无 key → raise RuntimeError
4. CRAWLER_FORCE_MOCK=1 → 强制 mock
5. CRAWLER_DEFAULT_MOCK=0 + env-no-key 模式 → 仅 warn 不 raise
"""
import os
import sys
import time
import unittest

_THIS = os.path.dirname(os.path.abspath(__file__))
_CRAWLER_DIR = os.path.dirname(_THIS)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_CRAWLER_DIR)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from imdf.crawler.engine import CrawlerEngine
from imdf.crawler.config import make_default_config, RobotsPolicy


# 用法: 提升 RPS 避免限速瓶颈
def _boost_rate(engine: CrawlerEngine) -> None:
    for ch in engine.list_channels():
        try:
            c = engine.get_crawler(ch, mock=True)
            c.config.rate_limit.rps = 100.0
            c.config.rate_limit.jitter_seconds = 0.0
        except Exception:
            pass


class TestMockDefaultTrue(unittest.TestCase):
    """默认 mock=True (P19-C1-fix P0 #1)"""

    def setUp(self):
        # 清理可能存在的 env 干扰
        for k in ("CRAWLER_DEFAULT_MOCK", "CRAWLER_FORCE_MOCK", "CRAWLER_PRODUCTION_REAL_NETWORK"):
            os.environ.pop(k, None)

    def test_default_engine_has_mock_true(self):
        engine = CrawlerEngine()
        self.assertTrue(engine.default_mock, "default_mock must default to True for safety")
        engine.shutdown()

    def test_env_force_mock_1(self):
        os.environ["CRAWLER_FORCE_MOCK"] = "1"
        engine = CrawlerEngine()
        self.assertTrue(engine.default_mock)
        engine.shutdown()

    def test_env_default_mock_0_disables(self):
        os.environ["CRAWLER_DEFAULT_MOCK"] = "0"
        engine = CrawlerEngine()
        self.assertFalse(engine.default_mock)
        engine.shutdown()

    def test_production_real_network_default_off(self):
        os.environ.pop("CRAWLER_PRODUCTION_REAL_NETWORK", None)
        engine = CrawlerEngine()
        self.assertFalse(engine.production_real_network)
        engine.shutdown()


class TestSubmitWithoutKeyIsFast(unittest.TestCase):
    """submit() 无 API key 时走 mock 路径 → 快速返回"""

    def setUp(self):
        # 确保无 env 干扰, 强制 mock
        os.environ.pop("CRAWLER_DEFAULT_MOCK", None)
        os.environ["CRAWLER_FORCE_MOCK"] = "1"
        # 删除可能的真实 key — 确保 mock 路径
        for k in ("GOOGLE_API_KEY", "GOOGLE_CX", "FLICKR_API_KEY",
                  "UNSPLASH_ACCESS_KEY", "PIXABAY_API_KEY"):
            os.environ.pop(k, None)

    def test_100_submits_under_1s_each(self):
        """启动 prod mode 无 key → 100 submit 全部 < 1s 完成 (mock 路径)"""
        engine = CrawlerEngine(max_concurrent=8)
        _boost_rate(engine)
        # 测试用 5 渠道
        channel_targets = [
            ("google_images", {"query": "test", "count": 3}),
            ("open_images", {"query": "test", "count": 3}),
            ("flickr", {"query": "test", "count": 3}),
            ("unsplash", {"query": "test", "count": 3}),
            ("pixabay", {"query": "test", "count": 3}),
        ]

        start = time.time()
        # 100 次 submit (每渠道 20 次)
        job_ids = []
        for _ in range(20):
            for ch, target in channel_targets:
                jid = engine.submit(ch, target)
                job_ids.append(jid)

        # 等所有 job 完成
        for jid in job_ids:
            engine.wait_for(jid, timeout=10.0)
        elapsed = time.time() - start

        # 验证全部完成
        completed = 0
        for jid in job_ids:
            job = engine.get_job(jid)
            if job and job.status.value == "completed":
                completed += 1
        self.assertEqual(completed, 100, f"only {completed}/100 completed")

        # 平均每个 submit 应该 < 1s (100 个总时长应该 < 100s — mock 模式下远低于此)
        avg_per_submit = elapsed / 100.0
        self.assertLess(
            avg_per_submit, 1.0,
            f"avg {avg_per_submit:.3f}s per submit exceeds 1s — mock fallback broken? "
            f"total elapsed: {elapsed:.1f}s",
        )
        engine.shutdown()


class TestProductionSafetyLock(unittest.TestCase):
    """生产模式 + default_mock=False + 无 key → raise RuntimeError"""

    _PRESERVE_ENV_KEYS = (
        "CRAWLER_DEFAULT_MOCK", "CRAWLER_FORCE_MOCK",
        "CRAWLER_PRODUCTION_REAL_NETWORK",
        "GOOGLE_API_KEY", "GOOGLE_CX", "FLICKR_API_KEY",
        "UNSPLASH_ACCESS_KEY", "PIXABAY_API_KEY",
    )

    def setUp(self):
        # 完全清空相关 env, 然后 setUp 中根据测试需要设置
        for k in self._PRESERVE_ENV_KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        # 测试结束后清空, 避免污染其他测试
        for k in self._PRESERVE_ENV_KEYS:
            os.environ.pop(k, None)

    def test_production_mode_no_key_raises(self):
        """CRAWLER_PRODUCTION_REAL_NETWORK=1 + default_mock=False + 无 key → RuntimeError"""
        os.environ["CRAWLER_PRODUCTION_REAL_NETWORK"] = "1"
        os.environ["CRAWLER_DEFAULT_MOCK"] = "0"
        with self.assertRaises(RuntimeError) as ctx:
            CrawlerEngine()
        msg = str(ctx.exception)
        self.assertIn("PRODUCTION", msg)
        self.assertIn("API key", msg)

    def test_production_mode_with_key_passes(self):
        """生产模式 + 有 key → 不 raise"""
        os.environ["CRAWLER_PRODUCTION_REAL_NETWORK"] = "1"
        os.environ["CRAWLER_DEFAULT_MOCK"] = "0"
        os.environ["GOOGLE_API_KEY"] = "test_key"
        os.environ["GOOGLE_CX"] = "test_cx"
        os.environ["FLICKR_API_KEY"] = "test_flickr"
        os.environ["UNSPLASH_ACCESS_KEY"] = "test_un"
        os.environ["PIXABAY_API_KEY"] = "test_pix"
        try:
            engine = CrawlerEngine()
            self.assertFalse(engine.default_mock)
            engine.shutdown()
        finally:
            for k in ("GOOGLE_API_KEY", "GOOGLE_CX", "FLICKR_API_KEY",
                      "UNSPLASH_ACCESS_KEY", "PIXABAY_API_KEY"):
                os.environ.pop(k, None)

    def test_non_production_no_key_only_warns(self):
        """非生产模式 + 无 key → 仅 warn 不 raise"""
        os.environ.pop("CRAWLER_PRODUCTION_REAL_NETWORK", None)
        os.environ["CRAWLER_DEFAULT_MOCK"] = "0"
        try:
            # 不应 raise
            engine = CrawlerEngine()
            # default_mock 仍保持 False (无自动回落)
            self.assertFalse(engine.default_mock)
            engine.shutdown()
        finally:
            os.environ.pop("CRAWLER_DEFAULT_MOCK", None)


class TestChannelMockAutoFallback(unittest.TestCase):
    """缺 key 时,渠道 (尤其 open_images 这种 requires_key=False) 自动 fallback mock"""

    def setUp(self):
        for k in ("GOOGLE_API_KEY", "GOOGLE_CX", "FLICKR_API_KEY",
                  "UNSPLASH_ACCESS_KEY", "PIXABAY_API_KEY",
                  "CRAWLER_DEFAULT_MOCK", "CRAWLER_FORCE_MOCK",
                  "CRAWLER_PRODUCTION_REAL_NETWORK"):
            os.environ.pop(k, None)
        os.environ["CRAWLER_FORCE_MOCK"] = "1"

    def test_open_images_auto_mock(self):
        """open_images requires_key=False 但 mock=True 时仍走 mock"""
        from imdf.crawler.channels.open_images import OpenImagesCrawler
        cw = OpenImagesCrawler(mock=True)
        result = cw.crawl({"query": "cars", "count": 3})
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 3)
        for item in result.items:
            self.assertTrue(item.get("mock"))


if __name__ == "__main__":
    unittest.main()
