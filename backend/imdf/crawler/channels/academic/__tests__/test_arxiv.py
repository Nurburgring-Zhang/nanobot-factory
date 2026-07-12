"""Tests for the ArxivChannel crawler (P20-D)."""
from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from imdf.crawler.channels.academic import ArxivChannel
from imdf.crawler.channels.academic.paper import Paper


_ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <title type="html">ArXiv Query: search_query=all:transformer&amp;start=0</title>
  <id>http://arxiv.org/api/query-transformer</id>
  <updated>2024-05-01T00:00:00Z</updated>
  <totalResults>2</totalResults>
  <entry>
    <id>http://arxiv.org/abs/2303.08774v2</id>
    <title>Attention Is All You Need (Mock)</title>
    <summary>We propose a new architecture based on attention mechanisms.</summary>
    <published>2023-03-15T00:00:00Z</published>
    <updated>2023-06-01T00:00:00Z</updated>
    <author><name>Alice Author</name></author>
    <author><name>Bob Builder</name></author>
    <arxiv:doi>10.1234/mock.001</arxiv:doi>
    <arxiv:journal_ref>Nature 2023</arxiv:journal_ref>
    <arxiv:comment>14 pages, 4 figures</arxiv:comment>
    <category term="cs.LG" />
    <category term="cs.CL" />
    <link href="http://arxiv.org/pdf/2303.08774v2" rel="related" type="application/pdf" title="pdf"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.01234v1</id>
    <title>A Survey on Transformers</title>
    <summary>This survey reviews recent transformer variants.</summary>
    <published>2024-01-02T00:00:00Z</published>
    <updated>2024-01-02T00:00:00Z</updated>
    <author><name>Eve Example</name></author>
    <arxiv:doi>10.1234/mock.002</arxiv:doi>
    <category term="cs.LG" />
    <link href="http://arxiv.org/pdf/2401.01234v1" rel="related" type="application/pdf" title="pdf"/>
  </entry>
</feed>
"""


def _make_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ATOM_FEED.encode("utf-8"),
                              headers={"content-type": "application/atom+xml"})
    return httpx.MockTransport(handler)


def _make_failing_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated connection error")
    return httpx.MockTransport(handler)


def _make_status_transport(code: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, content=b"error")
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_search_returns_results():
    cw = ArxivChannel(transport=_make_mock_transport(), rate_limit_seconds=0)
    papers = await cw.search("transformer", max_results=10)
    assert isinstance(papers, list)
    assert len(papers) == 2
    assert all(isinstance(p, Paper) for p in papers)
    p0 = papers[0]
    assert "Attention" in p0.title
    assert p0.url == "https://arxiv.org/abs/2303.08774v2"
    assert "Alice Author" in p0.authors
    assert p0.doi == "10.1234/mock.001"
    assert p0.venue == "arXiv"
    assert p0.year == 2023
    assert p0.pdf_url == "http://arxiv.org/pdf/2303.08774v2"
    assert "cs.LG" in p0.keywords


@pytest.mark.asyncio
async def test_parse_extracts_fields():
    """Static parse() returns list of dicts; parse_records builds Paper."""
    records = ArxivChannel.parse(_ATOM_FEED)
    assert len(records) == 2
    r0 = records[0]
    assert r0["arxiv_id"] == "2303.08774v2"
    assert r0["title"].startswith("Attention")
    assert r0["url"] == "https://arxiv.org/abs/2303.08774v2"
    assert r0["authors"] == ["Alice Author", "Bob Builder"]
    assert r0["doi"] == "10.1234/mock.001"
    assert "cs.LG" in r0["categories"]


@pytest.mark.asyncio
async def test_error_handling_returns_empty():
    """Network failure returns empty list, no exception."""
    cw = ArxivChannel(transport=_make_failing_transport(),
                      rate_limit_seconds=0)
    papers = await cw.search("anything")
    assert papers == []


@pytest.mark.asyncio
async def test_http_500_returns_empty():
    """Non-200 response returns empty list, no exception."""
    cw = ArxivChannel(transport=_make_status_transport(500),
                      rate_limit_seconds=0)
    papers = await cw.search("anything")
    assert papers == []


@pytest.mark.asyncio
async def test_rate_limiter_serializes_calls():
    """Two back-to-back .search() calls should respect rate_limit_seconds."""
    cw = ArxivChannel(transport=_make_mock_transport(),
                      rate_limit_seconds=0.3)
    t0 = time.monotonic()
    await cw.search("x")
    await cw.search("y")
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.25, f"rate limit not enforced, elapsed={elapsed}"


@pytest.mark.asyncio
async def test_arxiv_id_preserved_in_extras():
    """Extras dict should contain arxiv_id for downstream uses."""
    cw = ArxivChannel(transport=_make_mock_transport(), rate_limit_seconds=0)
    papers = await cw.search("transformer")
    assert papers[0].extra.get("arxiv_id") == "2303.08774v2"
