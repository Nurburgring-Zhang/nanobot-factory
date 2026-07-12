"""Tests for the SemanticScholarChannel crawler (P20-D)."""
from __future__ import annotations

import json
import time

import httpx
import pytest

from imdf.crawler.channels.academic import SemanticScholarChannel
from imdf.crawler.channels.academic.paper import Paper


_S2_BODY = {
    "total": 2,
    "offset": 0,
    "next": 25,
    "data": [
        {
            "paperId": "abc123def456",
            "title": "Attention Is All You Need (S2 Mock)",
            "abstract": "We propose the Transformer architecture...",
            "year": 2023,
            "venue": "NeurIPS",
            "url": "https://www.semanticscholar.org/paper/abc123def456",
            "citationCount": 1234,
            "authors": [
                {"authorId": "u1", "name": "Vaswani, A."},
                {"authorId": "u2", "name": "Shazeer, N."},
            ],
            "externalIds": {
                "DOI": "10.1234/mock.001",
                "ArXiv": "1706.03762",
            },
            "publicationDate": "2023-06-15",
            "openAccessPdf": {"url": "https://example.org/p.pdf"},
        },
        {
            "paperId": "xyz789ghi012",
            "title": "A Survey on Transformers (S2)",
            "abstract": "This survey reviews...",
            "year": 2024,
            "venue": "JMLR",
            "url": "https://www.semanticscholar.org/paper/xyz789ghi012",
            "citationCount": 5,
            "authors": [{"authorId": "u3", "name": "Lin, T."}],
            "externalIds": {},
            "publicationDate": "2024-02-01",
        },
    ],
}


def _make_mock(body=_S2_BODY, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=json.dumps(body).encode("utf-8"),
                              headers={"content-type": "application/json"})
    return httpx.MockTransport(handler)


def _make_failing():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated network error")
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_search_returns_results():
    cw = SemanticScholarChannel(transport=_make_mock(), rate_limit_seconds=0)
    papers = await cw.search("transformer", max_results=10)
    assert len(papers) == 2
    p0 = papers[0]
    assert isinstance(p0, Paper)
    assert p0.title.startswith("Attention")
    assert p0.year == 2023
    assert p0.venue == "NeurIPS"
    assert p0.doi == "10.1234/mock.001"
    assert p0.citation_count == 1234
    assert p0.pdf_url == "https://example.org/p.pdf"
    assert p0.id == "ss:abc123def456"
    assert "Vaswani, A." in p0.authors


@pytest.mark.asyncio
async def test_parse_extracts_fields():
    cw = SemanticScholarChannel(rate_limit_seconds=0)
    papers = cw.parse_records(_S2_BODY["data"], query="x")
    assert len(papers) == 2
    assert papers[1].venue == "JMLR"
    assert papers[1].year == 2024


@pytest.mark.asyncio
async def test_error_handling_returns_empty():
    cw = SemanticScholarChannel(transport=_make_failing(), rate_limit_seconds=0)
    papers = await cw.search("x")
    assert papers == []


@pytest.mark.asyncio
async def test_http_500_returns_empty():
    cw = SemanticScholarChannel(transport=_make_mock(status=500),
                                rate_limit_seconds=0)
    papers = await cw.search("x")
    assert papers == []


@pytest.mark.asyncio
async def test_rate_limit_serializes_calls():
    cw = SemanticScholarChannel(transport=_make_mock(), rate_limit_seconds=0.3)
    t0 = time.monotonic()
    await cw.search("a")
    await cw.search("b")
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.25


@pytest.mark.asyncio
async def test_max_results_truncates():
    cw = SemanticScholarChannel(transport=_make_mock(), rate_limit_seconds=0)
    papers = await cw.search("x", max_results=1)
    assert len(papers) == 1
