"""Tests for the GoogleScholarChannel crawler (P20-D)."""
from __future__ import annotations

import time

import httpx
import pytest

from imdf.crawler.channels.academic import GoogleScholarChannel
from imdf.crawler.channels.academic.paper import Paper


_HTML = """<!DOCTYPE html>
<html>
<head><title>Scholar</title></head>
<body>
<div class="gs_r gs_or gs_scl">
  <h3 class="gs_rt">
    <a href="https://example.org/p1.pdf">
      Knowledge distillation: a survey
    </a>
  </h3>
  <div class="gs_a">
    Alice Author, Bob Builder, Carol Chung - IEEE Trans. PAMI, 2023 - example.org
  </div>
  <div class="gs_rs">
    We survey recent techniques in knowledge distillation for neural networks.
  </div>
  <div class="gs_fl">
    <a href="https://scholar.google.com/scholar?cites=1234567890">
      Cited by 42
    </a>
    <a href="https://example.org/p1.pdf">[PDF]</a>
  </div>
</div>
<div class="gs_r gs_or gs_scl">
  <h3 class="gs_rt">
    <a href="https://example.org/p2">
      Distilling transformers into smaller models
    </a>
  </h3>
  <div class="gs_a">
    Dan Distiller, Eva Example - NeurIPS, 2024 - arxiv.org
  </div>
  <div class="gs_rs">
    We discuss methods to compress transformers for production.
  </div>
  <div class="gs_fl">
    <a href="https://scholar.google.com/scholar?cites=9876543210">
      Cited by 7
    </a>
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
        raise httpx.ConnectError("simulated network error")
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_search_returns_results():
    cw = GoogleScholarChannel(transport=_make_mock(), rate_limit_seconds=0)
    papers = await cw.search("knowledge distillation", max_results=5)
    assert len(papers) == 2
    p0 = papers[0]
    assert isinstance(p0, Paper)
    assert "Knowledge distillation" in p0.title
    assert "Alice Author" in p0.authors
    assert p0.year == 2023
    assert "survey" in p0.abstract.lower()
    assert p0.citation_count == 42
    assert p0.pdf_url and p0.pdf_url.endswith("p1.pdf")


@pytest.mark.asyncio
async def test_parse_extracts_fields():
    records = GoogleScholarChannel.parse(_HTML)
    assert len(records) == 2
    r0 = records[0]
    assert "Knowledge distillation" in r0["title"]
    assert r0["year"] == 2023
    assert r0["citation_count"] == 42
    assert "Alice Author" in r0["authors"]


@pytest.mark.asyncio
async def test_error_handling_returns_empty():
    cw = GoogleScholarChannel(transport=_make_failing(), rate_limit_seconds=0)
    papers = await cw.search("x")
    assert papers == []


@pytest.mark.asyncio
async def test_http_500_returns_empty():
    cw = GoogleScholarChannel(transport=_make_mock(status=500),
                              rate_limit_seconds=0)
    papers = await cw.search("x")
    assert papers == []


@pytest.mark.asyncio
async def test_rate_limit_serializes_calls():
    cw = GoogleScholarChannel(transport=_make_mock(), rate_limit_seconds=0.3)
    t0 = time.monotonic()
    await cw.search("a")
    await cw.search("b")
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.25


@pytest.mark.asyncio
async def test_parse_empty_html_returns_empty():
    assert GoogleScholarChannel.parse("") == []
    assert GoogleScholarChannel.parse("<html></html>") == []
