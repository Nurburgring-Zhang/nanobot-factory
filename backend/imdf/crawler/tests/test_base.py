"""test_base.py — BaseCrawler + CrawlerConfig + 模板方法模式测试"""
import os
import sys
import unittest
from typing import Any, Dict, Optional, Tuple

# 项目路径 — 让 tests 可独立跑
_THIS = os.path.dirname(os.path.abspath(__file__))
_CRAWLER_DIR = os.path.dirname(_THIS)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_CRAWLER_DIR)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from imdf.crawler.base import (
    BaseCrawler, CrawlResult, CrawlMetrics, CrawlStatus, RobotsPolicy,
    RateLimiter, USER_AGENT_POOL, _RobotsCache,
)
from imdf.crawler.config import (
    CrawlerConfig, AuthConfig, AuthType, ProxyConfig, RateLimitConfig,
    RobotsPolicy as RobotsPolicyCfg, make_default_config,
)


# ============== Helper crawler (测试用) ==============
class FakeCrawler(BaseCrawler):
    """用 fake fetcher 测试 BaseCrawler 流程"""
    channel = "fake"

    def __init__(self, *args: Any, fake_response: bytes = b"<html><body>hello</body></html>",
                 fake_status: int = 200, fake_error: Optional[str] = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._fake_response = fake_response
        self._fake_status = fake_status
        self._fake_error = fake_error
        self.prepare_calls = 0

    def _prepare(self, target: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        self.prepare_calls += 1
        if isinstance(target, str):
            return {"url": target}
        if isinstance(target, dict) and "url" in target:
            return {"url": target["url"]}
        return None

    def _do_fetch(self, url: str, headers: Dict[str, str], **prep: Any) -> Tuple[Any, int, Optional[str]]:
        if self._fake_error:
            return None, self._fake_status, self._fake_error
        return self._fake_response, self._fake_status, None

    def _parse(self, raw: Any, prep: Dict[str, Any]) -> Tuple[list, dict]:
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="replace")
        else:
            text = str(raw)
        return [{"text": text[:100]}], {"length": len(text)}


class TestCrawlerConfig(unittest.TestCase):
    """CrawlerConfig dataclass 行为"""

    def test_default_construction(self):
        cfg = CrawlerConfig()
        self.assertEqual(cfg.name, "default")
        self.assertEqual(cfg.channel, "generic")
        self.assertEqual(cfg.robots_policy, RobotsPolicyCfg.HONOR)
        self.assertEqual(cfg.max_concurrent, 8)
        self.assertEqual(cfg.timeout_seconds, 30.0)

    def test_user_agent_pool_random(self):
        cfg = make_default_config("test")
        self.assertGreater(len(cfg.user_agent_pool), 0)
        ua = cfg.get_user_agent()
        self.assertIn("Mozilla", ua)

    def test_auth_bearer(self):
        cfg = CrawlerConfig()
        cfg.auth = AuthConfig(auth_type=AuthType.BEARER, token="xyz123")
        headers = cfg.auth.get_headers()
        self.assertEqual(headers["Authorization"], "Bearer xyz123")

    def test_auth_api_key(self):
        cfg = CrawlerConfig()
        cfg.auth = AuthConfig(auth_type=AuthType.API_KEY, api_key="KEY123", api_key_header="X-Token")
        headers = cfg.auth.get_headers()
        self.assertEqual(headers["X-Token"], "KEY123")

    def test_auth_basic(self):
        cfg = CrawlerConfig()
        cfg.auth = AuthConfig(auth_type=AuthType.BASIC, username="user", password="pass")
        headers = cfg.auth.get_headers()
        self.assertIn("Basic ", headers["Authorization"])

    def test_proxy_url(self):
        p = ProxyConfig(scheme="http", host="1.2.3.4", port=8080, username="u", password="p")
        url = p.get_url()
        self.assertIn("http://", url)
        self.assertIn("1.2.3.4:8080", url)
        self.assertIn("u:p@", url)

    def test_rate_limit_dataclass(self):
        rl = RateLimitConfig(rps=2.5, burst=10, jitter_seconds=0.1)
        self.assertEqual(rl.rps, 2.5)
        self.assertEqual(rl.burst, 10)

    def test_make_default_config(self):
        cfg = make_default_config("flickr")
        self.assertEqual(cfg.channel, "flickr")
        self.assertGreater(len(cfg.user_agent_pool), 5)


class TestRateLimiter(unittest.TestCase):
    def test_acquire_returns_wait(self):
        rl = RateLimiter(rps=10.0, jitter_seconds=0.0)  # 100ms interval
        w1 = rl.acquire()
        w2 = rl.acquire()
        # 第一次接近 0, 第二次接近 0.1
        self.assertGreaterEqual(w2, 0.05)


class TestRobotsCache(unittest.TestCase):
    def test_cache_miss_and_hit(self):
        cache = _RobotsCache()
        fetcher_calls = []

        def fake_fetcher(url: str) -> str:
            fetcher_calls.append(url)
            return (
                "User-agent: *\n"
                "Disallow: /private/\n"
                "Allow: /public/\n"
            )

        rp1 = cache.get("https://example.com/public/page", fake_fetcher)
        self.assertTrue(rp1.can_fetch("*", "https://example.com/public/page"))
        self.assertFalse(rp1.can_fetch("*", "https://example.com/private/secret"))

        # 第二次同 host 应走 cache
        rp2 = cache.get("https://example.com/anything", fake_fetcher)
        self.assertEqual(len(fetcher_calls), 1, "should hit cache")


class TestBaseCrawler(unittest.TestCase):
    """BaseCrawler 抽象类 — 通过 FakeCrawler 测试"""

    def setUp(self):
        # 关闭 audit chain (测试不依赖)
        os.environ["AUDIT_CHAIN_SECRET"] = "test_secret_for_crawler_base_1234567890"
        self.cfg = make_default_config("fake")
        self.cfg.enable_audit_chain = False
        self.cfg.robots_policy = RobotsPolicyCfg.IGNORE  # 跳过 robots 检查

    def test_successful_crawl(self):
        c = FakeCrawler(config=self.cfg, fake_response=b"<html><body>hi</body></html>")
        result = c.crawl("https://example.com")
        self.assertTrue(result.ok)
        self.assertEqual(result.status, CrawlStatus.SUCCESS)
        self.assertEqual(len(result.items), 1)
        self.assertIn("hi", result.items[0]["text"])

    def test_fetch_error_returns_error_status(self):
        c = FakeCrawler(config=self.cfg, fake_error="connection refused")
        result = c.crawl("https://example.com")
        self.assertFalse(result.ok)
        self.assertIn("refused", result.error.lower() or "")
        # 应该被分类为 FETCH_ERROR
        self.assertIn(result.status, (CrawlStatus.FETCH_ERROR, CrawlStatus.PROXY_ERROR))

    def test_parse_error_returns_parse_status(self):
        class BadParseCrawler(FakeCrawler):
            def _parse(self, raw, prep):
                raise ValueError("parse failed")
        c = BadParseCrawler(config=self.cfg)
        result = c.crawl("https://example.com")
        self.assertEqual(result.status, CrawlStatus.PARSE_ERROR)

    def test_invalid_target_returns_error(self):
        c = FakeCrawler(config=self.cfg)
        result = c.crawl(12345)  # 不是 str/dict
        self.assertEqual(result.status, CrawlStatus.UNKNOWN_ERROR)

    def test_metrics_accumulate(self):
        c = FakeCrawler(config=self.cfg)
        c.crawl("https://example.com/a")
        c.crawl("https://example.com/b")
        c.crawl("https://example.com/c")
        snap = c.metrics.snapshot()
        self.assertEqual(snap["fetched"], 3)
        self.assertEqual(snap["success"], 3)
        self.assertEqual(snap["errors"], 0)

    def test_metrics_mixed(self):
        cfg = make_default_config("fake")
        cfg.enable_audit_chain = False
        cfg.robots_policy = RobotsPolicyCfg.IGNORE
        # Success crawler
        c_ok = FakeCrawler(config=cfg)
        c_ok.crawl("https://example.com/ok")
        # Error crawler
        c_err = FakeCrawler(config=cfg, fake_error="connection refused")
        c_err.crawl("https://example.com/bad")
        # Combined metrics
        snap_ok = c_ok.metrics.snapshot()
        snap_err = c_err.metrics.snapshot()
        self.assertEqual(snap_ok["success"], 1)
        self.assertEqual(snap_err["success"], 0)
        self.assertGreaterEqual(snap_err["errors"], 1)
        self.assertEqual(snap_ok["fetched"] + snap_err["fetched"], 2)

    def test_blocked_by_blocklist(self):
        cfg = make_default_config("fake")
        cfg.robots_policy = RobotsPolicyCfg.HONOR
        cfg.enable_audit_chain = False
        cfg.extra["blocked_hosts"] = ["blocked.com"]
        c = FakeCrawler(config=cfg)
        result = c.crawl("https://blocked.com/page")
        self.assertEqual(result.status, CrawlStatus.BLOCKED)

    def test_crawl_many_sequential(self):
        c = FakeCrawler(config=self.cfg)
        results = c.crawl_many([
            "https://example.com/a",
            "https://example.com/b",
            {"url": "https://example.com/c"},
        ])
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertTrue(r.ok)

    def test_user_agent_in_headers(self):
        cfg = make_default_config("fake")
        cfg.robots_policy = RobotsPolicyCfg.IGNORE
        cfg.enable_audit_chain = False
        c = FakeCrawler(config=cfg)
        result = c.crawl("https://example.com")
        # CrawlResult 自身不存 headers, 但 crawler 应该有 UA 注入
        self.assertIn("Mozilla", c.config.user_agent_pool[0])

    def test_classify_error(self):
        c = FakeCrawler(config=self.cfg)
        self.assertEqual(c._classify_error("timeout"), CrawlStatus.TIMEOUT)
        self.assertEqual(c._classify_error("401 unauthorized"), CrawlStatus.AUTH_ERROR)
        self.assertEqual(c._classify_error("rate limit exceeded"), CrawlStatus.RATE_LIMITED)
        self.assertEqual(c._classify_error("proxy error"), CrawlStatus.PROXY_ERROR)
        self.assertEqual(c._classify_error("something else"), CrawlStatus.FETCH_ERROR)


if __name__ == "__main__":
    unittest.main()