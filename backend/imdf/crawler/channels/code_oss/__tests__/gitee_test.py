"""Gitee channel tests (P20-E)."""
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
from imdf.crawler.channels.code_oss.gitee import GiteeChannel  # noqa: E402


GT_PAYLOAD = [
    {
        "id": 1001,
        "full_name": "alice/web-app",
        "path": "alice/web-app",
        "name": "web-app",
        "html_url": "https://gitee.com/alice/web-app",
        "url": "https://gitee.com/alice/web-app",
        "description": "A nice web app",
        "namespace": {"name": "alice", "path": "alice"},
        "language": "JavaScript",
        "stargazers_count": 999,
        "forks_count": 100,
        "license": "MIT",
        "updated_at": "2024-06-01T00:00:00Z",
        "last_push_at": "2024-06-01T00:00:00Z",
        "default_branch": "main",
        "private": False,
        "open_issues_count": 3,
        "watchers_count": 999,
    },
]


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


def _gt_mock(payload):
    def handler(request):
        if "gitee.com/api/v5/search" in str(request.url):
            return httpx.Response(200, json=payload)
        if "gitee.com/search" in str(request.url):
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(404)
    return httpx.MockTransport(handler)


class TestGiteeChannel(unittest.TestCase):

    def test_search_returns_results(self):
        ch = GiteeChannel(transport=_gt_mock(GT_PAYLOAD))
        results = _run(ch.search("web", max_results=5))
        self.assertEqual(len(results), 1)
        self.assertTrue(isinstance(results[0], CrawlResult))

    def test_search_field_population(self):
        ch = GiteeChannel(transport=_gt_mock(GT_PAYLOAD))
        results = _run(ch.search("web"))
        r0 = results[0]
        self.assertEqual(r0.title, "alice/web-app")
        self.assertEqual(r0.url, "https://gitee.com/alice/web-app")
        self.assertEqual(r0.author, "alice")
        self.assertEqual(r0.language, "JavaScript")
        self.assertEqual(r0.stars, 999)
        self.assertEqual(r0.forks, 100)
        self.assertEqual(r0.license, "MIT")

    def test_parse_html_extracts_repos(self):
        html = """
        <html><body>
          <div class="item">
            <a class="title" href="/bob/proj1">bob / proj1</a>
            <div class="desc">Bob's project 1</div>
          </div>
          <div class="item">
            <a class="title" href="/carol/proj2">carol / proj2</a>
            <div class="desc">Carol's project 2</div>
          </div>
        </body></html>
        """
        results = GiteeChannel.parse(html)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "bob / proj1")
        self.assertEqual(results[0].url, "https://gitee.com/bob/proj1")

    def test_network_failure_returns_empty(self):
        def fail(request):
            raise httpx.ConnectError("boom")
        ch = GiteeChannel(transport=httpx.MockTransport(fail))
        results = _run(ch.search("x"))
        self.assertEqual(results, [])

    def test_html_fallback_path(self):
        ch = GiteeChannel(transport=_gt_mock(GT_PAYLOAD), use_html_fallback=True)
        results = _run(ch.search("web"))
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()