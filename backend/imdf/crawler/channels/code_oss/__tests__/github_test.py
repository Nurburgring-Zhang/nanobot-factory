"""GitHub channel tests (P20-E).

Covers:
    - search() returns parsed CrawlResult list
    - parse() extracts fields from HTML
    - network failure → empty list
    - rate limiting fires on consecutive searches
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
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
from imdf.crawler.channels.code_oss.github import GitHubChannel  # noqa: E402


GH_PAYLOAD = {
    "total_count": 2,
    "incomplete_results": False,
    "items": [
        {
            "id": 12345,
            "full_name": "owner/repo1",
            "name": "repo1",
            "owner": {"login": "owner", "avatar_url": "https://gh.com/u.png"},
            "html_url": "https://github.com/owner/repo1",
            "description": "Sample repo 1",
            "language": "Python",
            "stargazers_count": 1000,
            "forks_count": 200,
            "license": {"spdx_id": "MIT"},
            "topics": ["cli", "awesome"],
            "updated_at": "2024-06-01T00:00:00Z",
            "default_branch": "main",
            "private": False,
            "archived": False,
            "open_issues_count": 5,
            "watchers_count": 1000,
        },
        {
            "id": 67890,
            "full_name": "owner/repo2",
            "name": "repo2",
            "owner": {"login": "owner2"},
            "html_url": "https://github.com/owner2/repo2",
            "description": "Sample repo 2",
            "language": "Go",
            "stargazers_count": 50,
            "forks_count": 5,
            "license": None,
            "topics": [],
            "updated_at": "2024-05-01T00:00:00Z",
            "default_branch": "master",
            "private": True,
            "archived": True,
            "open_issues_count": 0,
            "watchers_count": 50,
        },
    ],
}


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


def _gh_mock(payload):
    def handler(request):
        if "api.github.com" in str(request.url):
            return httpx.Response(200, json=payload)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


class TestGitHubChannel(unittest.TestCase):

    def test_search_returns_results(self):
        ch = GitHubChannel(transport=_gh_mock(GH_PAYLOAD))
        results = _run(ch.search("openai", max_results=5))
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(r, CrawlResult) for r in results))

    def test_search_field_population(self):
        ch = GitHubChannel(transport=_gh_mock(GH_PAYLOAD))
        results = _run(ch.search("test"))
        r0 = results[0]
        self.assertEqual(r0.title, "owner/repo1")
        self.assertEqual(r0.url, "https://github.com/owner/repo1")
        self.assertEqual(r0.author, "owner")
        self.assertEqual(r0.language, "Python")
        self.assertEqual(r0.stars, 1000)
        self.assertEqual(r0.forks, 200)
        self.assertEqual(r0.license, "MIT")
        self.assertEqual(r0.keywords, ["cli", "awesome"])
        self.assertEqual(r0.last_updated, "2024-06-01T00:00:00Z")
        self.assertEqual(r0.extra["default_branch"], "main")

    def test_parse_html_extracts_repos(self):
        html = """
        <html><body>
          <div>
            <a class="Link--primary" itemprop="name codeRepository" href="/owner/repo1">owner / repo1</a>
            <p>Awesome repo</p>
          </div>
          <div>
            <a class="Link--primary" itemprop="name codeRepository" href="/owner/repo2">owner / repo2</a>
            <p>Another repo</p>
          </div>
        </body></html>
        """
        results = GitHubChannel.parse(html)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "owner / repo1")
        self.assertEqual(results[0].url, "https://github.com/owner/repo1")

    def test_network_failure_returns_empty(self):
        def fail(request):
            raise httpx.ConnectError("boom")
        ch = GitHubChannel(transport=httpx.MockTransport(fail))
        results = _run(ch.search("x"))
        self.assertEqual(results, [])

    def test_rate_limit_waits(self):
        ch = GitHubChannel(transport=_gh_mock(GH_PAYLOAD), rate_limit_seconds=0.2)
        t0 = time.monotonic()
        _run(ch.search("a"))
        _run(ch.search("b"))
        _run(ch.search("c"))
        elapsed = time.monotonic() - t0
        # 3 calls at 0.2s spacing = at least 0.4s of waiting
        self.assertGreaterEqual(elapsed, 0.35)


if __name__ == "__main__":
    unittest.main()