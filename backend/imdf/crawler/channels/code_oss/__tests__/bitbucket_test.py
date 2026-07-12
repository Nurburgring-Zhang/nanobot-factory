"""Bitbucket channel tests (P20-E)."""
from __future__ import annotations

import asyncio
import os
import sys
import unittest

import httpx

_THIS = os.path.dirname(os.path.abspath(__file__))
_CODE_OSS_DIR = os.path.dirname(_THIS)
_CHANNELS_DIR = os.path.dirname(_CODE_OSS_DIR)
_CRAWLER_DIR = os.path.dirname(_CHANNELS_DIR)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_CRAWLER_DIR)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from imdf.crawler.channels.code_oss import CrawlResult  # noqa: E402
from imdf.crawler.channels.code_oss.bitbucket import BitbucketChannel  # noqa: E402


BB_HTML = """
<html><body>
  <article class="search-result">
    <a class="repo-link" href="/alice/awesome-tool">
      <span class="repo-name">awesome-tool</span>
      <span class="owner-name">alice</span>
    </a>
    <p class="repo-description">An awesome tool</p>
  </article>
  <article class="search-result">
    <a class="repo-link" href="/bob/cool-lib">
      <span class="repo-name">cool-lib</span>
      <span class="owner-name">bob</span>
    </a>
    <p class="repo-description">Cool library</p>
  </article>
</body></html>
"""


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(asyncio.run, coro)
                return fut.result(timeout=30)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _bb_mock(html):
    def handler(request):
        if "bitbucket.org/search" in str(request.url):
            return httpx.Response(200, text=html)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


class TestBitbucketChannel(unittest.TestCase):

    def test_search_returns_results(self):
        ch = BitbucketChannel(transport=_bb_mock(BB_HTML))
        results = _run(ch.search("tool", max_results=5))
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(r, CrawlResult) for r in results))

    def test_search_field_population(self):
        ch = BitbucketChannel(transport=_bb_mock(BB_HTML))
        results = _run(ch.search("tool"))
        r0 = results[0]
        self.assertIn("awesome-tool", r0.title)
        self.assertEqual(r0.url, "https://bitbucket.org/alice/awesome-tool")
        self.assertEqual(r0.source, "bitbucket")

    def test_parse_html_extracts_repos(self):
        results = BitbucketChannel.parse(BB_HTML)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "alice/awesome-tool")
        self.assertEqual(results[0].url, "https://bitbucket.org/alice/awesome-tool")

    def test_network_failure_returns_empty(self):
        def fail(request):
            raise httpx.ConnectError("boom")
        ch = BitbucketChannel(transport=httpx.MockTransport(fail))
        results = _run(ch.search("x"))
        self.assertEqual(results, [])

    def test_empty_html_returns_empty(self):
        ch = BitbucketChannel(transport=_bb_mock("<html></html>"))
        results = _run(ch.search("x"))
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()