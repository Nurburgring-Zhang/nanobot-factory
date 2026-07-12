"""Tests for the IEEEChannel crawler (P20-D)."""
from __future__ import annotations

import time

import httpx
import pytest

from imdf.crawler.channels.academic import IEEEChannel
from imdf.crawler.channels.academic.paper import Paper


_HTML = """
<html>
<head><title>IEEE Xplore Search Results</title></head>
<body>
<div class="List-results">
  <div class="result-item">
    <h2>
      <a href="/document/9876543">A Deep Learning Approach to 5G Network Slicing</a>
    </h2>
    <div class="description">
      We propose a novel deep-learning architecture for 5G network slicing.
    </div>
    <div class="authors">
      <a href="/author/123">Alice A</a>
      <a href="/author/456">Bob B</a>
    </div>
    <div class="publication">IEEE Transactions on Wireless Communications</div>
    <div class="publication-year">2023</div>
    <div class="article-number">9876543</div>
  </div>
  <div class="result-item">
    <h2>
      <a href="/document/1234567">Federated Learning at the Edge</a>
    </h2>
    <div class="description">
      Federated learning techniques for distributed edge devices.
    </div>
    <div class="authors">
      <a href="/author/789">Carol C</a>
    </div>
    <div class="publication">IEEE Internet of Things Journal</div>
    <div class="publication-year">2024</div>
    <div class="article-number">1234567</div>
  </div>
</div>
</body>
</html>
"""


def _make_mock(html=_HTML, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=html.encode("utf-8"),
                              headers={"content-type": "text/html"})
    return httpx.MockTransport(handler)


def _make_failing():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated connection error")
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_search_returns_results():
    cw = IEEEChannel(transport=_make_mock(), rate_limit_seconds=0)
    papers = await cw.search("5G network slicing", max_results=10)
    assert len(papers) == 2
    p = papers[0]
    assert isinstance(p, Paper)
    assert "5G" in p.title
    assert p.url.startswith("https://ieeexplore.ieee.org")
    assert p.year == 2023
    assert "Alice A" in p.authors
    assert p.venue == "IEEE Transactions on Wireless Communications"


@pytest.mark.asyncio
async def test_parse_extracts_fields():
    records = IEEEChannel.parse(_HTML)
    assert len(records) == 2
    r0 = records[0]
    assert "5G" in r0["title"]
    assert "IEEE Transactions" in (r0["venue"] or "")
    assert r0["year"] == 2023
    assert "Alice A" in r0["authors"]


@pytest.mark.asyncio
async def test_error_handling_returns_empty():
    cw = IEEEChannel(transport=_make_failing(), rate_limit_seconds=0)
    papers = await cw.search("x")
    assert papers == []


@pytest.mark.asyncio
async def test_http_500_returns_empty():
    cw = IEEEChannel(transport=_make_mock(status=500), rate_limit_seconds=0)
    papers = await cw.search("x")
    assert papers == []


@pytest.mark.asyncio
async def test_rate_limit_serializes_calls():
    cw = IEEEChannel(transport=_make_mock(), rate_limit_seconds=0.3)
    t0 = time.monotonic()
    await cw.search("a")
    await cw.search("b")
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.25


@pytest.mark.asyncio
async def test_parse_empty_html_returns_empty():
    assert IEEEChannel.parse("") == []
    assert IEEEChannel.parse("<html></html>") == []
