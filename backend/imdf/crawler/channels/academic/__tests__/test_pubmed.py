"""Tests for the PubMedChannel crawler (P20-D)."""
from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest

from imdf.crawler.channels.academic import PubMedChannel
from imdf.crawler.channels.academic.paper import Paper


_ESEARCH_BODY = {
    "esearchresult": {
        "count": "2",
        "retmax": "5",
        "idlist": ["37234567", "36543210"],
    }
}

_ESUMMARY_BODY = {
    "result": {
        "uids": ["37234567", "36543210"],
        "37234567": {
            "uid": "37234567",
            "title": "Mock COVID-19 vaccine trial outcomes",
            "sortfirstauthor": "Smith J",
            "pubdate": "2023 Apr",
            "fulljournalname": "The Lancet",
            "source": "Lancet",
            "volume": "401",
            "issue": "10382",
            "pages": "1234-1245",
            "articleids": [
                {"idtype": "pubmed", "value": "37234567"},
                {"idtype": "doi",   "value": "10.1016/mock.001"},
            ],
            "authors": [
                {"name": "Smith J"},
                {"name": "Doe AB"},
                {"name": "Liu X"},
            ],
            "lang": ["eng"],
            "pubtype": ["Journal Article", "Randomized Controlled Trial"],
        },
        "36543210": {
            "uid": "36543210",
            "title": "Mock mRNA booster study in adolescents",
            "sortfirstauthor": "Garcia E",
            "pubdate": "2022",
            "fulljournalname": "NEJM",
            "source": "N Engl J Med",
            "articleids": [
                {"idtype": "pubmed", "value": "36543210"},
            ],
            "authors": [{"name": "Garcia E"}],
            "lang": ["eng"],
            "pubtype": ["Journal Article"],
        },
    }
}


def _mock_transport_2step(search_body, summary_body):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "esearch.fcgi" in url:
            return httpx.Response(200,
                content=json.dumps(search_body).encode("utf-8"),
                headers={"content-type": "application/json"})
        if "esummary.fcgi" in url:
            return httpx.Response(200,
                content=json.dumps(summary_body).encode("utf-8"),
                headers={"content-type": "application/json"})
        return httpx.Response(404, content=b"not found")
    return httpx.MockTransport(handler)


def _make_failing():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated network error")
    return httpx.MockTransport(handler)


def _make_status(code: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, content=b"err")
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_search_returns_results():
    cw = PubMedChannel(
        transport=_mock_transport_2step(_ESEARCH_BODY, _ESUMMARY_BODY),
        rate_limit_seconds=0,
    )
    papers = await cw.search("covid vaccine", max_results=5)
    assert len(papers) == 2
    p0 = papers[0]
    assert isinstance(p0, Paper)
    assert p0.id == "pmid:37234567"
    assert p0.url == "https://pubmed.ncbi.nlm.nih.gov/37234567/"
    assert p0.title.startswith("Mock COVID-19")
    assert p0.venue == "The Lancet"
    assert p0.year == 2023
    assert p0.doi == "10.1016/mock.001"
    assert "Smith J" in p0.authors


@pytest.mark.asyncio
async def test_parse_extracts_fields():
    cw = PubMedChannel(rate_limit_seconds=0)
    papers = cw.parse_records(
        [_ESUMMARY_BODY["result"][uid]
         for uid in _ESUMMARY_BODY["result"]["uids"]],
        query="covid",
    )
    assert len(papers) == 2
    assert "Garcia E" in papers[1].authors
    assert papers[1].venue == "NEJM"
    assert papers[1].year == 2022


@pytest.mark.asyncio
async def test_error_handling_returns_empty():
    cw = PubMedChannel(transport=_make_failing(), rate_limit_seconds=0)
    papers = await cw.search("x")
    assert papers == []


@pytest.mark.asyncio
async def test_esearch_no_results():
    empty = {"esearchresult": {"count": "0", "idlist": []}}
    cw = PubMedChannel(
        transport=_mock_transport_2step(empty, {}),
        rate_limit_seconds=0,
    )
    papers = await cw.search("noresults_xyz")
    assert papers == []


@pytest.mark.asyncio
async def test_rate_limit_serializes_calls():
    cw = PubMedChannel(
        transport=_mock_transport_2step(_ESEARCH_BODY, _ESUMMARY_BODY),
        rate_limit_seconds=0.3,
    )
    t0 = time.monotonic()
    await cw.search("a")
    await cw.search("b")
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.25


def test_pubmed_authors_helper():
    from imdf.crawler.channels.academic.pubmed import _parse_pubmed_authors
    parsed = _parse_pubmed_authors(
        {"authors": [{"name": "X"}, {"name": "Y"}]}
    )
    assert parsed == ["X", "Y"]
    parsed2 = _parse_pubmed_authors(
        {"authors": [], "authorlist": {"complete": "Foo Bar; Baz Qux"}},
    )
    assert parsed2 == ["Foo Bar", "Baz Qux"]
