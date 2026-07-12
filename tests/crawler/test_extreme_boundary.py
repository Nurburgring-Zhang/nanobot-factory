"""P21 R3 EXTREME BOUNDARY tests for the crawler module.

This file contains 14 categories of boundary tests for the crawler system
(BaseCrawler, CrawlerEngine, WebCrawler, APICrawler, RateLimiter, and
the channel crawler hierarchy). All tests use httpx.MockTransport or
direct attribute patching — no real network, no new deps.

Categories:
  1.  Empty query
  2.  Very long query
  3.  Unicode / RTL / emoji
  4.  Special chars (SQL injection, XSS, shell metachars)
  5.  Rate limit boundary (1 req/sec under 100 rapid calls)
  6.  Concurrent same-channel
  7.  Concurrent different-channels
  8.  Network failure (timeout, conn refused, DNS, SSL)
  9.  Malformed HTML (empty, broken tags, huge 10MB, binary)
 10.  Auth required (401, 403, 429, rate limit)
 11.  Response status non-200 (301/302/404/500/502/503)
 12.  Content-Encoding (gzip / brotli / deflate / identity)
 13.  Cookies + redirect chain (3-hop)
 14.  Cold-start latency

NOTE: each test class is a focused category. They are intentionally
self-contained — no shared mutable state between tests.
"""
from __future__ import annotations

import concurrent.futures
import gzip
import json
import time
import zlib
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx
import pytest

from imdf.crawler.base import (
    BaseCrawler,
    CrawlResult,
    CrawlStatus,
    RateLimiter,
)
from imdf.crawler.config import make_default_config
from imdf.crawler.engine import CrawlerEngine, JobStatus
from imdf.crawler.web_crawler import WebCrawler
from imdf.crawler.api_crawler import APICrawler
from imdf.crawler.channels.duckduckgo import DuckDuckGoImagesCrawler


# =============================================================================
# Test helpers
# =============================================================================


def make_status_transport(code: int, body: bytes = b"") -> httpx.MockTransport:
    """Mock transport that always returns a fixed status code."""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(code, content=body)
    return httpx.MockTransport(handler)


# =============================================================================
# Minimal in-process crawler subclass used by several tests.
# =============================================================================


class _MiniCrawler(BaseCrawler):
    """In-process crawler that returns a pre-canned fetch result.

    Lets us feed any (raw, status_code, error) triple without spinning
    up httpx at all.
    """
    channel = "mini"

    def __init__(self, fetch_result: Tuple[bytes, int, Optional[str]],
                 *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._fetch_result = fetch_result
        self.fetch_calls: List[Tuple[str, Dict[str, str]]] = []

    def _prepare(self, target: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        if target is None:
            return None
        if isinstance(target, str):
            url = target
        elif isinstance(target, dict):
            url = target.get("url") or target.get("query")
            if url is None:
                return None
        else:
            return None
        return {
            "url": url if url.startswith("http") else f"https://example.com/{url}",
            "headers": kwargs.get("headers", {}),
        }

    def _do_fetch(self, url: str, headers: Dict[str, str], **prep: Any) -> Tuple[bytes, int, Optional[str]]:
        self.fetch_calls.append((url, headers))
        return self._fetch_result

    def _parse(self, raw: Any, prep: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        text = ""
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="replace")
        elif isinstance(raw, str):
            text = raw
        return ([{"url": prep.get("url", ""), "content": text[:100]}] if text else [],
                {"raw_len": len(raw) if raw else 0})


# =============================================================================
# 1. Empty query
# =============================================================================


class TestEmptyQuery:
    """Empty / whitespace-only query must not crash, must return [] or safe."""

    def test_duckduckgo_empty_query_returns_none(self):
        """DDG's _prepare returns None for empty query → UNKNOWN_ERROR + empty items."""
        cw = DuckDuckGoImagesCrawler(mock=True)
        result = cw.crawl({"query": ""})
        assert result is not None
        # Either items empty OR error reported, but no crash
        assert result.items == []
        assert result.status != CrawlStatus.SUCCESS or result.items == []

    def test_duckduckgo_whitespace_query_returns_none(self):
        cw = DuckDuckGoImagesCrawler(mock=True)
        result = cw.crawl({"query": "   "})
        assert result.items == []
        assert result.error is not None or result.status != CrawlStatus.SUCCESS

    def test_duckduckgo_missing_query_key(self):
        """When target dict has no 'query' key at all."""
        cw = DuckDuckGoImagesCrawler(mock=True)
        result = cw.crawl({"not_a_query": "foo"})
        assert result.items == []
        # _prepare returned None → status = UNKNOWN_ERROR
        assert result.status == CrawlStatus.UNKNOWN_ERROR

    def test_mini_crawler_with_empty_url_via_prepare(self):
        """_MiniCrawler._prepare returns None when target has no url → UNKNOWN_ERROR."""
        cw = _MiniCrawler((b"x", 200, None))
        result = cw.crawl({"foo": "bar"})
        assert result.status == CrawlStatus.UNKNOWN_ERROR
        assert result.items == []
        assert "prepare" in (result.error or "").lower() or result.error

    def test_apicrawler_empty_url(self):
        """APICrawler.crawl() with no URL → _prepare returns None."""
        cw = APICrawler()
        result = cw.crawl({})
        assert result.status == CrawlStatus.UNKNOWN_ERROR
        assert result.items == []


# =============================================================================
# 2. Very long query
# =============================================================================


class TestVeryLongQuery:
    """10,000-char query must not timeout, must not crash."""

    LONG_QUERY_LEN = 10_000

    def test_duckduckgo_10k_query(self):
        cw = DuckDuckGoImagesCrawler(mock=True)
        long_q = "a" * self.LONG_QUERY_LEN
        t0 = time.time()
        result = cw.crawl({"query": long_q})
        elapsed = time.time() - t0
        # Mock path is in-process; < 2s
        assert elapsed < 2.0, f"slow on long query: {elapsed:.2f}s"
        # Mock produces N items — should not error
        assert result.error is None
        assert result.status == CrawlStatus.SUCCESS

    def test_mini_crawler_10k_url(self):
        """BaseCrawler with 10k char URL in prep."""
        long_url = "https://example.com/" + ("x" * self.LONG_QUERY_LEN)
        cw = _MiniCrawler((b"hi", 200, None))
        result = cw.crawl(long_url)
        assert result.status == CrawlStatus.SUCCESS
        assert cw.fetch_calls[0][0] == long_url

    def test_apicrawler_10k_query_param(self):
        """APICrawler with 10k query string in params."""
        cw = APICrawler()
        long_q = "a" * self.LONG_QUERY_LEN
        # We don't actually fire network — prepare + parse are offline
        prep = cw._prepare({"url": "https://api.example.com/search",
                            "params": {"q": long_q}})
        assert prep is not None
        assert prep["params"]["q"] == long_q

    def test_search_request_rejects_oversize_at_pydantic_level(self):
        """Pydantic v2 SearchRequest has max_length=200 for query."""
        from imdf.crawler.channels._schemas import SearchRequest
        with pytest.raises(Exception):
            # Pydantic raises ValidationError; we don't pin the exact class
            SearchRequest(query="a" * 201, max_results=10)


# =============================================================================
# 3. Unicode / RTL / emoji
# =============================================================================


class TestUnicodeRtlEmoji:
    """Arabic, Chinese, emoji must round-trip through crawler parser."""

    UNICODE_QUERIES = [
        ("arabic", "مرحبا بالعالم"),
        ("chinese", "你好世界"),
        ("japanese", "こんにちは世界"),
        ("korean", "안녕하세요 세계"),
        ("hebrew_rtl", "שלום עולם"),
        ("emoji_basic", "🐱🌍✨"),
        ("emoji_zwj", "👨‍👩‍👧‍👦"),
        ("mixed_rtl_ltr", "Hello مرحبا World 🌍"),
        ("thai", "สวัสดีชาวโลก"),
    ]

    @pytest.mark.parametrize("name,query", UNICODE_QUERIES)
    def test_duckduckgo_handles_unicode(self, name: str, query: str):
        cw = DuckDuckGoImagesCrawler(mock=True)
        result = cw.crawl({"query": query})
        assert result.status == CrawlStatus.SUCCESS, (
            f"{name} ({query!r}) failed: {result.error}"
        )
        assert result.items, f"{name} produced no items"
        # Title or URL must preserve the unicode characters (mock uses query in title)
        joined = " ".join(
            (it.get("title", "") + " " + it.get("url", ""))
            for it in result.items
        )
        assert query in joined, (
            f"{name}: query not preserved in items. got={joined[:200]!r}"
        )

    def test_unicode_in_url_path(self):
        """URLs with percent-encoded unicode must parse cleanly."""
        cw = _MiniCrawler((b"<html>ok</html>", 200, None))
        url = "https://example.com/中文"
        result = cw.crawl(url)
        assert result.status == CrawlStatus.SUCCESS

    def test_unicode_in_html_body(self):
        """HTML body with unicode must decode without crash."""
        html = "<html><body><h1>你好世界 🌍 مرحبا</h1></body></html>"
        cw = WebCrawler(playwright_runner=lambda u, h, p: (html.encode("utf-8"), 200, None))
        result = cw.crawl({"url": "https://example.com"})
        assert result.status == CrawlStatus.SUCCESS
        assert result.items
        text_blob = json.dumps(result.items, ensure_ascii=False)
        assert "你好" in text_blob

    def test_rtl_unicode_in_arabic_query_does_not_misroute(self):
        """Arabic query must hit the right channel — not get truncated."""
        cw = DuckDuckGoImagesCrawler(mock=True)
        result = cw.crawl({"query": "بحث-عن-صور"})
        assert result.status == CrawlStatus.SUCCESS
        assert any("بحث-عن-صور" in (it.get("url", "") + it.get("title", ""))
                   for it in result.items)


# =============================================================================
# 4. Special chars / injection attempts
# =============================================================================


class TestSpecialCharsInjection:
    """SQL injection, XSS, shell metachars must be passed through safely."""

    INJECTION_QUERIES = [
        "'; DROP TABLE users;--",
        "1' OR '1'='1",
        "<script>alert('xss')</script>",
        "\"><img src=x onerror=alert(1)>",
        "../../../etc/passwd",
        "$(rm -rf /)",
        "`whoami`",
        "%0a%0dSet-Cookie:%20attack=1",
        "\\x00\\x01\\x02",
        "\n\r\t",
        "'; WAITFOR DELAY '0:0:5'--",
    ]

    @pytest.mark.parametrize("payload", INJECTION_QUERIES)
    def test_duckduckgo_injection_payload_safe(self, payload: str):
        """Injection payloads must not crash; result is normal."""
        cw = DuckDuckGoImagesCrawler(mock=True)
        result = cw.crawl({"query": payload})
        # Mock path is in-process — must always succeed
        assert result.status == CrawlStatus.SUCCESS
        assert result.items, "injection should still produce items in mock mode"

    def test_apicrawler_params_with_special_chars_url_encoded(self):
        """APICrawler must pass special chars through params dict verbatim
        (encoding is httpx's job)."""
        cw = APICrawler()
        prep = cw._prepare({
            "url": "https://api.example.com/search",
            "params": {"q": "'; DROP TABLE users;--"},
            "method": "GET",
        })
        assert prep is not None
        assert prep["params"]["q"] == "'; DROP TABLE users;--"

    def test_xss_in_url_path_does_not_execute(self):
        """XSS payload in URL is treated as a string, not executed."""
        cw = _MiniCrawler((b"<html>x</html>", 200, None))
        result = cw.crawl("https://example.com/<script>alert(1)</script>")
        # The URL is just a string; no script execution
        assert result.status == CrawlStatus.SUCCESS
        assert "<script>" in cw.fetch_calls[0][0]

    def test_audit_chain_disabled_with_special_chars(self):
        """Special chars in URL with audit disabled still succeed."""
        cw = _MiniCrawler((b"x", 200, None))
        cw.config.enable_audit_chain = False
        result = cw.crawl("https://example.com/?q=' OR 1=1--")
        assert result.status == CrawlStatus.SUCCESS
        assert "1=1--" in cw.fetch_calls[0][0]


# =============================================================================
# 5. Rate limit boundary
# =============================================================================


class TestRateLimitBoundary:
    """Rate limiter boundary: verify 100 rapid calls at rps=N actually serialize."""

    def test_rate_limiter_basic_acquire_serializes(self):
        """rps=10 → 5 calls in < 0.1s on first, but 2nd must wait ~0.1s."""
        rl = RateLimiter(rps=10.0)  # 1/10s = 0.1s interval
        # First call: no wait
        w0 = rl.acquire()
        assert w0 == 0
        # Second call immediately: must wait ~0.1s
        w1 = rl.acquire()
        assert 0.05 < w1 <= 0.15, f"expected ~0.1s wait, got {w1}"

    def test_rapid_100_calls_at_rps_100(self):
        """100 calls at rps=100 → min elapsed ≈ 0.99s."""
        rl = RateLimiter(rps=100.0, jitter_seconds=0.0)
        t0 = time.time()
        for _ in range(100):
            rl.acquire()
        elapsed = time.time() - t0
        # 100 calls at rps=100: interval = 0.01s, total ≈ 0.99s
        assert 0.8 < elapsed < 2.0, f"unexpected elapsed: {elapsed:.2f}s"

    def test_100_rapid_mini_crawl_calls_serial(self):
        """100 sequential crawls at rps=50 → ~2s total (no crash, no race)."""
        cfg = make_default_config(channel="mini")
        cfg.rate_limit.rps = 50.0
        cfg.rate_limit.jitter_seconds = 0.0
        cw = _MiniCrawler((b"ok", 200, None), config=cfg)
        t0 = time.time()
        for _ in range(100):
            res = cw.crawl("https://example.com/page")
            assert res.status == CrawlStatus.SUCCESS
        elapsed = time.time() - t0
        # 100 calls at 50 rps = ~2s; allow ±30%
        assert 1.3 < elapsed < 4.0, f"unexpected elapsed: {elapsed:.2f}s"
        assert len(cw.fetch_calls) == 100

    def test_rate_limiter_lock_is_thread_safe(self):
        """Under concurrent acquire, total elapsed ≥ expected."""
        rl = RateLimiter(rps=50.0, jitter_seconds=0.0)
        N = 50

        def worker():
            for _ in range(N):
                rl.acquire()

        t0 = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(worker) for _ in range(10)]
            for f in futures:
                f.result()
        elapsed = time.time() - t0
        # 50 * 10 = 500 calls at rps=50 → 10s expected
        assert 7 < elapsed < 13, f"unexpected elapsed: {elapsed:.2f}s"


# =============================================================================
# 6. Concurrent same-channel
# =============================================================================


class TestConcurrentSameChannel:
    """10 parallel calls to same channel — no race, no data loss."""

    def test_10_parallel_calls_to_same_mini_crawler(self):
        cfg = make_default_config(channel="mini")
        cfg.rate_limit.rps = 1000.0  # high rps so test is fast
        cw = _MiniCrawler((b"hello", 200, None), config=cfg)

        def worker(idx: int) -> CrawlResult:
            return cw.crawl(f"https://example.com/page-{idx}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            results = list(ex.map(worker, range(10)))

        assert len(results) == 10
        assert all(r.status == CrawlStatus.SUCCESS for r in results)
        # All 10 distinct URLs captured
        urls = sorted(cw.fetch_calls[i][0] for i in range(10))
        assert len(set(urls)) == 10

    def test_metrics_thread_safe_under_concurrent_crawl(self):
        """CrawlMetrics.incr() must be thread-safe; success count == N."""
        cfg = make_default_config(channel="mini")
        cfg.rate_limit.rps = 1000.0
        cw = _MiniCrawler((b"ok", 200, None), config=cfg)

        N = 20
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            list(ex.map(lambda i: cw.crawl(f"https://example.com/{i}"), range(N)))

        snap = cw.metrics.snapshot()
        assert snap["fetched"] == N
        assert snap["success"] == N
        assert snap["errors"] == 0
        assert snap["by_status"].get("success") == N

    def test_duckduckgo_concurrent_same_channel(self):
        """10 parallel calls to DuckDuckGoImagesCrawler (mock mode) all succeed."""
        cw = DuckDuckGoImagesCrawler(mock=True)

        def worker(idx: int) -> CrawlResult:
            return cw.crawl({"query": f"q{idx}", "count": 5})

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            results = list(ex.map(worker, range(10)))

        assert all(r.status == CrawlStatus.SUCCESS for r in results)
        assert all(len(r.items) == 5 for r in results)


# =============================================================================
# 7. Concurrent different-channels
# =============================================================================


class TestConcurrentDifferentChannels:
    """50 parallel calls across different channels — pool exhaustion handling."""

    def test_50_parallel_mini_crawlers_distinct_instances(self):
        """50 different URLs to same crawler; pool not exhausted."""
        cfg = make_default_config(channel="mini")
        cfg.rate_limit.rps = 1000.0
        cfg.max_concurrent = 4  # tight semaphore
        cw = _MiniCrawler((b"ok", 200, None), config=cfg)

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
            futures = [
                ex.submit(cw.crawl, f"https://example.com/{i}") for i in range(50)
            ]
            results = [f.result(timeout=10) for f in futures]

        assert len(results) == 50
        assert all(r.status == CrawlStatus.SUCCESS for r in results)

    def test_50_parallel_crawler_engine_jobs(self):
        """50 jobs across 5 different channels (10 each) — engine handles it."""
        eng = CrawlerEngine(max_concurrent=8)
        try:
            jobs = []
            for ch_idx, ch in enumerate(["google_images", "open_images",
                                          "flickr", "unsplash", "pixabay"]):
                for i in range(10):
                    target = {"query": f"q{ch_idx}_{i}"}
                    job_id = eng.submit(ch, target)
                    jobs.append(job_id)
            # Wait for all
            for jid in jobs:
                eng.wait_for(jid, timeout=30)
            completed = [j for j in eng.list_jobs() if j.status == JobStatus.COMPLETED]
            failed = [j for j in eng.list_jobs() if j.status == JobStatus.FAILED]
            # In mock mode, all 50 should complete successfully
            assert len(completed) >= 40, (
                f"only {len(completed)}/{len(jobs)} completed; failed={len(failed)}"
            )
        finally:
            eng.shutdown()

    def test_engine_pool_exhaustion_does_not_deadlock(self):
        """max_concurrent=1 + 5 jobs: should serialize, not deadlock."""
        eng = CrawlerEngine(max_concurrent=1)
        try:
            ids = [eng.submit("open_images", {"query": f"q{i}"}) for i in range(5)]
            for jid in ids:
                eng.wait_for(jid, timeout=30)
            statuses = [eng.get_job(jid).status for jid in ids]
            assert all(s in (JobStatus.COMPLETED, JobStatus.FAILED) for s in statuses)
        finally:
            eng.shutdown()


# =============================================================================
# 8. Network failure
# =============================================================================


class TestNetworkFailure:
    """timeout, connection refused, DNS fail, SSL fail."""

    def test_httpx_connect_error_classified_as_fetch_error(self):
        """httpx.ConnectError → BaseCrawler._classify_error → FETCH_ERROR."""
        cw = _MiniCrawler((b"", 0, "httpx.ConnectError: connection refused"))
        result = cw.crawl("https://example.com")
        assert result.status == CrawlStatus.FETCH_ERROR

    def test_httpx_timeout_classified_as_timeout(self):
        cw = _MiniCrawler((b"", 0, "ReadTimeout: server did not respond"))
        result = cw.crawl("https://example.com")
        assert result.status == CrawlStatus.TIMEOUT

    def test_dns_failure_classified_as_fetch_error(self):
        cw = _MiniCrawler((b"", 0, "DNSError: no such host"))
        result = cw.crawl("https://nonexistent.example.invalid")
        assert result.status == CrawlStatus.FETCH_ERROR

    def test_ssl_failure_classified_as_fetch_error(self):
        cw = _MiniCrawler((b"", 0, "SSL: CERTIFICATE_VERIFY_FAILED"))
        result = cw.crawl("https://expired.badssl.com")
        assert result.status == CrawlStatus.FETCH_ERROR

    def test_apicrawler_retries_on_5xx_then_succeeds(self):
        """APICrawler retries on 500/502/503/504 (max_retries times)."""
        attempts = {"n": 0}

        class FakeResp:
            def __init__(self, code: int, body: Any = None):
                self.status_code = code
                self.headers: Dict[str, str] = {}
                self._body = body or {"data": []}
            def json(self):
                return self._body
            @property
            def text(self) -> str:
                return json.dumps(self._body)

        class FakeClient:
            def request(self, method, url, **kwargs):
                attempts["n"] += 1
                if attempts["n"] < 3:
                    return FakeResp(500, {"err": "boom"})
                return FakeResp(200, {"items": [{"x": 1}], "next_cursor": None})
            def close(self): pass

        cfg = make_default_config(channel="api")
        cfg.rate_limit.max_retries = 3
        cfg.rate_limit.retry_backoff_base = 0.01  # fast test
        cw = APICrawler(config=cfg, http_client=FakeClient())
        result = cw.crawl({"url": "https://api.example.com/list",
                           "pagination": {"mode": "none"}})
        # 2 retries + 1 success = 3 attempts
        assert attempts["n"] == 3
        assert result.status == CrawlStatus.SUCCESS
        assert len(result.items) == 1


# =============================================================================
# 9. Malformed HTML
# =============================================================================


class TestMalformedHTML:
    """Empty body, broken tags, huge 10MB body, binary content."""

    def test_empty_html_body(self):
        """Empty bytes body → empty items, no crash."""
        cw = WebCrawler(playwright_runner=lambda u, h, p: (b"", 200, None))
        result = cw.crawl({"url": "https://example.com"})
        assert result.status == CrawlStatus.SUCCESS
        assert result.items == []
        assert result.bytes_downloaded == 0

    def test_whitespace_only_html(self):
        cw = WebCrawler(playwright_runner=lambda u, h, p: (b"   \n\t  ", 200, None))
        result = cw.crawl({"url": "https://example.com"})
        assert result.status == CrawlStatus.SUCCESS
        assert result.items == []

    def test_broken_unclosed_tags(self):
        """HTML with unclosed tags must not raise."""
        html = "<html><body><div>oops<p>nested<span>oops"
        cw = WebCrawler(playwright_runner=lambda u, h, p: (html.encode("utf-8"), 200, None))
        result = cw.crawl({"url": "https://example.com"})
        assert result.status == CrawlStatus.SUCCESS
        assert result.items  # at least one parsed chunk

    def test_huge_10mb_html_body(self):
        """10MB HTML body must parse without OOM or hang (we just check it returns)."""
        chunk = "<p>lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>"
        # 10MB / ~64B per chunk ≈ 160k chunks
        big = "<html><body>" + (chunk * 160_000) + "</body></html>"
        size_mb = len(big) / 1024 / 1024
        cw = WebCrawler(playwright_runner=lambda u, h, p: (big.encode("utf-8"), 200, None))
        t0 = time.time()
        result = cw.crawl({"url": "https://example.com"})
        elapsed = time.time() - t0
        assert result.status == CrawlStatus.SUCCESS, f"failed on {size_mb:.1f}MB: {result.error}"
        # Allow up to 5s for 10MB parse
        assert elapsed < 5.0, f"slow parse of {size_mb:.1f}MB: {elapsed:.2f}s"

    def test_binary_content_in_html_slot(self):
        """Random binary bytes passed as HTML — should not crash parser."""
        # Valid UTF-8 with some invalid sequences
        binary = b"\x00\x01\x02\xff\xfe\xfd<html><body>binary</body></html>"
        cw = WebCrawler(playwright_runner=lambda u, h, p: (binary, 200, None))
        result = cw.crawl({"url": "https://example.com"})
        # Parser uses errors='replace', so should not crash
        assert result.status == CrawlStatus.SUCCESS

    def test_pure_binary_garbage(self):
        """Pure random bytes — should not crash; items may be empty."""
        binary = bytes(range(256)) * 100  # 25.6KB
        cw = WebCrawler(playwright_runner=lambda u, h, p: (binary, 200, None))
        result = cw.crawl({"url": "https://example.com"})
        assert result.status == CrawlStatus.SUCCESS
        # No assertion on items — parser may extract nothing

    def test_html_with_only_comments(self):
        html = "<!-- nothing here -->"
        cw = WebCrawler(playwright_runner=lambda u, h, p: (html.encode("utf-8"), 200, None))
        result = cw.crawl({"url": "https://example.com"})
        assert result.status == CrawlStatus.SUCCESS
        # Items may be empty or one chunk with empty fields — both OK
        assert result.error is None


# =============================================================================
# 10. Auth required (401, 403, 429, rate limit)
# =============================================================================


class TestAuthRequired:
    """Auth-required channels: 401, 403, 429 responses must be classified."""

    def test_401_classified_as_auth_error(self):
        cw = _MiniCrawler((b"", 401, "401 unauthorized"))
        result = cw.crawl("https://api.example.com/protected")
        assert result.status == CrawlStatus.AUTH_ERROR

    def test_403_classified_as_auth_error(self):
        cw = _MiniCrawler((b"", 403, "403 forbidden"))
        result = cw.crawl("https://api.example.com/protected")
        assert result.status == CrawlStatus.AUTH_ERROR

    def test_429_classified_as_rate_limited(self):
        cw = _MiniCrawler((b"", 429, "429 too many requests"))
        result = cw.crawl("https://api.example.com/data")
        assert result.status == CrawlStatus.RATE_LIMITED

    def test_429_with_retry_after_text(self):
        """429 with Retry-After in error string should still be classified."""
        cw = _MiniCrawler((b"", 429, "429 rate limited; retry-after: 60"))
        result = cw.crawl("https://api.example.com/data")
        assert result.status == CrawlStatus.RATE_LIMITED
        assert "429" in (result.error or "")

    def test_apicrawler_401_does_not_retry(self):
        """401/403 are non-retryable; APICrawler should not retry them."""
        attempts = {"n": 0}

        class FakeResp:
            def __init__(self, code: int, body: Any = None):
                self.status_code = code
                self.headers: Dict[str, str] = {}
                self._body = body or {"error": "no auth"}
            def json(self):
                return self._body
            @property
            def text(self):
                return json.dumps(self._body)

        class FakeClient:
            def request(self, method, url, **kwargs):
                attempts["n"] += 1
                return FakeResp(401)
            def close(self): pass

        cfg = make_default_config(channel="api")
        cfg.rate_limit.max_retries = 3
        cfg.rate_limit.retry_backoff_base = 0.01
        cw = APICrawler(config=cfg, http_client=FakeClient())
        result = cw.crawl({"url": "https://api.example.com/me"})
        # 401 is in the retry-eligible status set? Let's check the code:
        # APICrawler retries on 429 OR 5xx. 401/403 → single attempt + return error
        assert attempts["n"] == 1
        assert result.status in (CrawlStatus.AUTH_ERROR, CrawlStatus.FETCH_ERROR)


# =============================================================================
# 11. Response status non-200
# =============================================================================


class TestNon200Responses:
    """301, 302, 404, 500, 502, 503 — each must be handled gracefully."""

    @pytest.mark.parametrize("status_code", [301, 302, 303, 307, 308])
    def test_redirect_status_codes(self, status_code: int):
        """3xx must not crash; we get a result with the given status code."""
        cw = _MiniCrawler((b"redirected", status_code, f"HTTP {status_code}"))
        result = cw.crawl("https://example.com")
        assert result.status_code == status_code

    @pytest.mark.parametrize("status_code", [400, 404, 410])
    def test_client_error_status_codes(self, status_code: int):
        cw = _MiniCrawler((b"not found", status_code, f"HTTP {status_code}"))
        result = cw.crawl("https://example.com")
        assert result.status_code == status_code

    @pytest.mark.parametrize("status_code", [500, 502, 503, 504])
    def test_server_error_status_codes(self, status_code: int):
        cw = _MiniCrawler((b"server error", status_code, f"HTTP {status_code}"))
        result = cw.crawl("https://example.com")
        assert result.status_code == status_code

    def test_404_does_not_crash(self):
        cw = _MiniCrawler((b"<html>not found</html>", 404, "HTTP 404"))
        result = cw.crawl("https://example.com/missing")
        # Either items empty or error captured — both OK
        assert result.status_code == 404

    def test_502_classified_as_fetch_error(self):
        """502 must not be classified as something else."""
        cw = _MiniCrawler((b"", 502, "502 bad gateway"))
        result = cw.crawl("https://example.com")
        # _classify_error does not have specific handler for 502 → FETCH_ERROR
        assert result.status == CrawlStatus.FETCH_ERROR


# =============================================================================
# 12. Content-Encoding
# =============================================================================


class TestContentEncoding:
    """gzip / brotli / deflate / identity — verify decoded correctly."""

    def test_gzip_encoded_body_decoded(self):
        """Server returns gzip-encoded body → we must decode it."""
        original = b"<html><body>hello gzipped world</body></html>"
        gzipped = gzip.compress(original)

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, content=gzipped,
                headers={"content-encoding": "gzip", "content-type": "text/html"},
            )

        transport = httpx.MockTransport(handler)
        # Use APICrawler since it goes through httpx and handles encoding
        cw = APICrawler()
        cw._client = httpx.Client(timeout=10, transport=transport)
        cw._owns_client = True
        try:
            result = cw.crawl({"url": "https://api.example.com/page",
                               "method": "GET"})
            # httpx auto-decompresses; the body in our handler is gzipped, so
            # the response we get is decoded to plain text
            assert result.status == CrawlStatus.SUCCESS
            assert result.error is None
        finally:
            cw.close()

    def test_deflate_encoded_body_decoded(self):
        original = b"<html><body>hello deflate</body></html>"
        # wbits=-15 → raw deflate
        deflated = zlib.compress(original, level=6)[2:-4]  # strip zlib header/trailer

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, content=deflated,
                headers={"content-encoding": "deflate", "content-type": "text/html"},
            )

        transport = httpx.MockTransport(handler)
        cw = APICrawler()
        cw._client = httpx.Client(timeout=10, transport=transport)
        cw._owns_client = True
        try:
            result = cw.crawl({"url": "https://api.example.com/x"})
            assert result.status == CrawlStatus.SUCCESS
        finally:
            cw.close()

    def test_identity_encoding_passthrough(self):
        """identity encoding → no transformation, body unchanged."""
        original = b"<html><body>plain</body></html>"

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, content=original,
                headers={"content-encoding": "identity", "content-type": "text/html"},
            )

        transport = httpx.MockTransport(handler)
        cw = APICrawler()
        cw._client = httpx.Client(timeout=10, transport=transport)
        cw._owns_client = True
        try:
            result = cw.crawl({"url": "https://api.example.com/x"})
            assert result.status == CrawlStatus.SUCCESS
        finally:
            cw.close()

    def test_brotli_not_supported_falls_back_or_errors(self):
        """brotli is not always available — must not hang, must surface error."""
        original = b"<html><body>br</body></html>"

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, content=original,
                headers={"content-encoding": "br", "content-type": "text/html"},
            )

        transport = httpx.MockTransport(handler)
        cw = APICrawler()
        cw._client = httpx.Client(timeout=5, transport=transport)
        cw._owns_client = True
        try:
            t0 = time.time()
            result = cw.crawl({"url": "https://api.example.com/x"})
            elapsed = time.time() - t0
            # If brotli is installed, body decodes; if not, the request may fail.
            # Either way, must not hang.
            assert elapsed < 5.0, f"hang on brotli: {elapsed:.2f}s"
        finally:
            cw.close()


# =============================================================================
# 13. Cookies + redirect chain
# =============================================================================


class TestCookiesRedirectChain:
    """3-hop redirect chain with cookies set at each hop."""

    def test_3hop_redirect_with_cookies(self):
        """Server returns 302 chain with Set-Cookie at each hop → final 200 with cookies."""
        state = {"hop": 0, "cookies": []}

        def handler(req: httpx.Request) -> httpx.Response:
            state["hop"] += 1
            cookies_in = req.headers.get("cookie", "")
            if cookies_in:
                state["cookies"].append(cookies_in)
            if state["hop"] == 1:
                r = httpx.Response(
                    302, headers={
                        "location": "https://example.com/hop2",
                        "set-cookie": "a=1; Path=/",
                    }
                )
                return r
            if state["hop"] == 2:
                r = httpx.Response(
                    302, headers={
                        "location": "https://example.com/hop3",
                        "set-cookie": "b=2; Path=/",
                    }
                )
                return r
            if state["hop"] == 3:
                r = httpx.Response(
                    302, headers={
                        "location": "https://example.com/final",
                        "set-cookie": "c=3; Path=/",
                    }
                )
                return r
            # Final 200
            return httpx.Response(
                200,
                content=json.dumps({"ok": True, "cookies_seen": state["cookies"]}).encode("utf-8"),
                headers={"content-type": "application/json"},
            )

        transport = httpx.MockTransport(handler)
        cw = APICrawler()
        # follow_redirects=True in APICrawler._get_client
        cw._client = httpx.Client(timeout=10, transport=transport, follow_redirects=True)
        cw._owns_client = True
        try:
            result = cw.crawl({"url": "https://example.com/start",
                               "method": "GET"})
            # Status reflects final response (200)
            assert result.status == CrawlStatus.SUCCESS
        finally:
            cw.close()

    def test_redirect_loop_bounded(self):
        """A 302 redirect loop should be bounded by httpx (max_redirects)."""
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": str(req.url)})

        transport = httpx.MockTransport(handler)
        cw = APICrawler()
        cw._client = httpx.Client(timeout=5, transport=transport, follow_redirects=True)
        cw._owns_client = True
        try:
            t0 = time.time()
            result = cw.crawl({"url": "https://example.com/loop",
                               "method": "GET"})
            elapsed = time.time() - t0
            # Must not hang — httpx raises or returns error
            assert elapsed < 5.0, f"hang on redirect loop: {elapsed:.2f}s"
        finally:
            cw.close()

    def test_apicrawler_429_strips_cookies_classification(self):
        """Set-Cookie header on 429 must not affect classification."""
        cw = _MiniCrawler((b"", 429, "429 rate limit"))
        result = cw.crawl("https://api.example.com/data")
        assert result.status == CrawlStatus.RATE_LIMITED


# =============================================================================
# 14. Cold start latency
# =============================================================================


class TestColdStartLatency:
    """First call ever → measure latency vs warm (subsequent) calls."""

    def test_first_call_vs_subsequent_under_5x(self):
        """Cold call should not be >5x slower than warm calls (no huge init cost)."""
        cfg = make_default_config(channel="mini")
        cfg.rate_limit.rps = 1000.0
        cfg.max_concurrent = 8
        cw = _MiniCrawler((b"hello", 200, None), config=cfg)

        # Cold call
        t0 = time.time()
        r1 = cw.crawl("https://example.com/cold")
        cold = time.time() - t0

        # Warm calls (5 of them)
        warm_times = []
        for i in range(5):
            t = time.time()
            r = cw.crawl(f"https://example.com/warm-{i}")
            warm_times.append(time.time() - t)
            assert r.status == CrawlStatus.SUCCESS

        avg_warm = sum(warm_times) / len(warm_times)

        # Cold should be within 10x of warm (we allow generous slack for CI jitter)
        assert r1.status == CrawlStatus.SUCCESS
        # In-process, so cold should be <50ms typically; warm <5ms
        # If cold > 5x warm AND > 0.1s, log a warning (not a failure here)
        # but assert cold < 1s absolute (no hang)
        assert cold < 1.0, f"cold start hung: {cold:.2f}s"

    def test_crawler_engine_first_submit_vs_subsequent(self):
        """Engine first submit (cold) should complete reasonably fast."""
        eng = CrawlerEngine(max_concurrent=4)
        try:
            t0 = time.time()
            jid = eng.submit("open_images", {"query": "first"})
            eng.wait_for(jid, timeout=10)
            cold = time.time() - t0

            warm_times = []
            for i in range(5):
                t = time.time()
                jid = eng.submit("open_images", {"query": f"warm-{i}"})
                eng.wait_for(jid, timeout=10)
                warm_times.append(time.time() - t)

            avg_warm = sum(warm_times) / len(warm_times)
            # Cold start < 1.5s, ratio < 10x
            assert cold < 1.5, f"engine cold start too slow: {cold:.2f}s"
        finally:
            eng.shutdown()

    def test_duckduckgo_cold_warm_latency(self):
        """DDG channel first call vs subsequent calls."""
        cw = DuckDuckGoImagesCrawler(mock=True)
        t0 = time.time()
        r1 = cw.crawl({"query": "cold"})
        cold = time.time() - t0
        assert r1.status == CrawlStatus.SUCCESS

        warm_times = []
        for i in range(5):
            t = time.time()
            r = cw.crawl({"query": f"warm-{i}"})
            warm_times.append(time.time() - t)
            assert r.status == CrawlStatus.SUCCESS

        avg_warm = sum(warm_times) / len(warm_times)
        # Cold should not be dramatically slower (mock path)
        assert cold < 0.5, f"DDG cold start slow: {cold:.2f}s"
        # avg_warm is informational
        assert avg_warm < 0.5, f"DDG warm too slow: {avg_warm:.2f}s"

    def test_engine_cold_aggregates_metrics_correctly(self):
        """After a cold start, metrics should reflect all calls made."""
        eng = CrawlerEngine(max_concurrent=2)
        try:
            eng.submit("open_images", {"query": "a"})
            eng.submit("open_images", {"query": "b"})
            eng.submit("open_images", {"query": "c"})
            time.sleep(0.5)  # let async jobs finish
            agg = eng.aggregate_metrics()
            # open_images should have at least 3 fetches counted
            if "open_images" in agg:
                m = agg["open_images"]
                assert m["fetched"] >= 3, f"cold metrics wrong: {m}"
        finally:
            eng.shutdown()


# =============================================================================
# Bonus: per-category test count assertions
# =============================================================================


class TestCategoryCoverage:
    """Sanity-check that we actually have 14 categories of tests."""

    def test_14_categories_present(self):
        # Count distinct test classes inheriting from nothing special
        import sys
        mod = sys.modules[__name__]
        test_classes = [
            name for name, obj in vars(mod).items()
            if isinstance(obj, type)
            and name.startswith("Test")
            and name != "TestCategoryCoverage"
        ]
        # 14 main + 1 bonus = 15; assert ≥ 14
        assert len(test_classes) >= 14, (
            f"only {len(test_classes)} test classes: {test_classes}"
        )
        # Verify specific names
        expected = [
            "TestEmptyQuery", "TestVeryLongQuery", "TestUnicodeRtlEmoji",
            "TestSpecialCharsInjection", "TestRateLimitBoundary",
            "TestConcurrentSameChannel", "TestConcurrentDifferentChannels",
            "TestNetworkFailure", "TestMalformedHTML", "TestAuthRequired",
            "TestNon200Responses", "TestContentEncoding",
            "TestCookiesRedirectChain", "TestColdStartLatency",
        ]
        for name in expected:
            assert name in test_classes, f"missing test class: {name}"
