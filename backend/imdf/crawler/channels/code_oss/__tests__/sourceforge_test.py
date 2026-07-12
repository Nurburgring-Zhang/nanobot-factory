"""SourceForge channel tests (P20-E)."""
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
from imdf.crawler.channels.code_oss.sourceforge import SourceForgeChannel  # noqa: E402


SF_HTML = """
<html><body>
  <div class="project-card">
    <a class="project-name" href="/projects/alice/cool-app/">
      <span>cool-app</span>
    </a>
    <p class="description">A cool desktop app</p>
    <div class="language">C++</div>
    <div class="stars">123 stars</div>
  </div>
  <div class="project-card">
    <a class="project-name" href="/projects/bob/awesome-lib/">
      <span>awesome-lib</span>
    </a>
    <p class="description">Awesome library</p>
    <div class="language">Python</div>
    <div class="stars">5,678 stars</div>
  </div>
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


def _sf_mock(html):
    def handler(request):
        if "sourceforge.net/directory" in str(request.url):
            return httpx.Response(200, text=html)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


class TestSourceForgeChannel(unittest.TestCase):

    def test_search_returns_results(self):
        ch = SourceForgeChannel(transport=_sf_mock(SF_HTML))
        results = _run(ch.search("app", max_results=5))
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(r, CrawlResult) for r in results))

    def test_search_field_population(self):
        ch = SourceForgeChannel(transport=_sf_mock(SF_HTML))
        results = _run(ch.search("app"))
        r0 = results[0]
        self.assertEqual(r0.title, "cool-app")
        self.assertEqual(r0.url, "https://sourceforge.net/projects/alice/cool-app/")
        self.assertEqual(r0.author, "alice")
        self.assertEqual(r0.language, "C++")
        self.assertEqual(r0.stars, 123)

    def test_parse_html_extracts_repos(self):
        results = SourceForgeChannel.parse(SF_HTML)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "cool-app")
        self.assertEqual(results[0].url, "https://sourceforge.net/projects/alice/cool-app/")

    def test_network_failure_returns_empty(self):
        def fail(request):
            raise httpx.ConnectError("boom")
        ch = SourceForgeChannel(transport=httpx.MockTransport(fail))
        results = _run(ch.search("x"))
        self.assertEqual(results, [])

    def test_empty_html_returns_empty(self):
        ch = SourceForgeChannel(transport=_sf_mock("<html></html>"))
        results = _run(ch.search("x"))
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()