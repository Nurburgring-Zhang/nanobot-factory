"""GitLab channel tests (P20-E)."""
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
from imdf.crawler.channels.code_oss.gitlab import GitLabChannel  # noqa: E402


GL_PAYLOAD = [
    {
        "id": 100,
        "name": "proj1",
        "path_with_namespace": "owner1/proj1",
        "web_url": "https://gitlab.com/owner1/proj1",
        "description": "Test project 1",
        "namespace": {"full_path": "owner1", "name": "Owner 1"},
        "programming_language": "Ruby",
        "star_count": 42,
        "forks_count": 7,
        "topics": ["ci", "tools"],
        "license": {"name": "MIT"},
        "last_activity_at": "2024-05-01T00:00:00Z",
        "default_branch": "main",
        "visibility": "public",
        "open_issues_count": 1,
    },
    {
        "id": 200,
        "name": "proj2",
        "path_with_namespace": "owner2/proj2",
        "web_url": "https://gitlab.com/owner2/proj2",
        "description": "Test project 2",
        "namespace": {"full_path": "owner2"},
        "programming_language": "Python",
        "star_count": 5,
        "forks_count": 0,
        "topics": [],
        "license": None,
        "last_activity_at": "2024-04-01T00:00:00Z",
        "default_branch": "master",
        "visibility": "public",
        "open_issues_count": 0,
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


def _gl_mock(payload):
    def handler(request):
        if "gitlab.com/api/v4/projects" in str(request.url):
            return httpx.Response(200, json=payload)
        if "gitlab.com/search" in str(request.url):
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(404)
    return httpx.MockTransport(handler)


class TestGitLabChannel(unittest.TestCase):

    def test_search_returns_results(self):
        ch = GitLabChannel(transport=_gl_mock(GL_PAYLOAD))
        results = _run(ch.search("ci", max_results=5))
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(r, CrawlResult) for r in results))

    def test_search_field_population(self):
        ch = GitLabChannel(transport=_gl_mock(GL_PAYLOAD))
        results = _run(ch.search("test"))
        r0 = results[0]
        self.assertEqual(r0.title, "owner1/proj1")
        self.assertEqual(r0.url, "https://gitlab.com/owner1/proj1")
        self.assertEqual(r0.author, "owner1")
        self.assertEqual(r0.language, "Ruby")
        self.assertEqual(r0.stars, 42)
        self.assertEqual(r0.forks, 7)
        self.assertEqual(r0.license, "MIT")
        self.assertIn("ci", r0.keywords)

    def test_parse_html_extracts_repos(self):
        html = """
        <html><body>
          <ul>
            <li>
              <a class="gl-link" data-testid="project-name-link" href="/owner/proj1">owner / proj1</a>
              <p>Project 1 description</p>
            </li>
            <li>
              <a class="gl-link" data-testid="project-name-link" href="/owner/proj2">owner / proj2</a>
              <p>Project 2 description</p>
            </li>
          </ul>
        </body></html>
        """
        results = GitLabChannel.parse(html)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "owner / proj1")
        self.assertEqual(results[0].url, "https://gitlab.com/owner/proj1")

    def test_network_failure_returns_empty(self):
        def fail(request):
            raise httpx.ConnectError("boom")
        ch = GitLabChannel(transport=httpx.MockTransport(fail))
        results = _run(ch.search("x"))
        self.assertEqual(results, [])

    def test_html_fallback_path(self):
        ch = GitLabChannel(transport=_gl_mock(GL_PAYLOAD), use_html_fallback=True)
        # mock returns empty html from /search → expect []
        results = _run(ch.search("test"))
        self.assertEqual(results, [])

    def test_rate_limit_waits(self):
        ch = GitLabChannel(transport=_gl_mock(GL_PAYLOAD), rate_limit_seconds=0.2)
        t0 = time.monotonic()
        _run(ch.search("a"))
        _run(ch.search("b"))
        elapsed = time.monotonic() - t0
        self.assertGreaterEqual(elapsed, 0.15)


if __name__ == "__main__":
    unittest.main()