"""Tests for RSSHubChannel."""
from __future__ import annotations

import json
import time

import httpx
import pytest

from backend.imdf.crawler.channels.rss import RsshubChannel
from backend.imdf.crawler.channels.rss import rsshub as rsshub_mod

SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>RSSHub Sample</title>
  <entry>
    <title>Machine Learning 综述</title>
    <link href="https://example.com/a"/>
    <id>https://example.com/a</id>
    <updated>Wed, 02 Jul 2025 10:00:00 GMT</updated>
    <summary>ML summary text</summary>
    <author><name>Alice</name></author>
  </entry>
  <entry>
    <title>RAG 实战</title>
    <link href="https://example.com/b"/>
    <id>https://example.com/b</id>
    <updated>Wed, 02 Jul 2025 11:00:00 GMT</updated>
    <summary>RAG implementation</summary>
  </entry>
</feed>
"""

SAMPLE_SEARCH_JSON = json.dumps({"data": ["telegram/channel/ml"]})


def client_for(search_payload: str = SAMPLE_SEARCH_JSON,
               feed_payload: str = SAMPLE_FEED) -> httpx.AsyncClient:
    """Construct an httpx.AsyncClient whose transport returns canned payloads."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "/search/" in request.url.path:
            return httpx.Response(200, text=search_payload, request=request)
        return httpx.Response(200, text=feed_payload, request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def failing_client() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_search_returns_results() -> None:
    channel = RsshubChannel(client=client_for())
    results = await channel.search("machine learning", max_results=5)
    assert len(results) >= 1
    assert results[0].source == "rsshub"
    assert results[0].title
    assert results[0].url.startswith("https://")


@pytest.mark.asyncio
async def test_search_empty_query_returns_empty() -> None:
    channel = RsshubChannel(client=client_for())
    assert await channel.search("", max_results=5) == []
    assert await channel.search("   ", max_results=5) == []


@pytest.mark.asyncio
async def test_search_handles_network_errors() -> None:
    channel = RsshubChannel(client=failing_client())
    assert await channel.search("anything", max_results=5) == []


def test_parse_atom_feed_extracts_entries() -> None:
    items = RsshubChannel.parse(SAMPLE_FEED)
    assert len(items) == 2
    assert items[0].url == "https://example.com/a"
    assert items[0].author == "Alice"
    assert items[1].title == "RAG 实战"
    assert items[1].source == "rsshub"


@pytest.mark.asyncio
async def test_search_handles_invalid_json() -> None:
    channel = RsshubChannel(client=client_for(search_payload="<html>not json</html>"))
    assert await channel.search("ml", max_results=5) == []


@pytest.mark.asyncio
async def test_rate_limit_waits_before_request(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    import asyncio as asyncio_mod
    monkeypatch.setattr(asyncio_mod, "sleep", fake_sleep)
    channel = RsshubChannel(client=client_for())
    # Force throttle to wait (last call just happened)
    channel._last_call_ts = time.monotonic()
    await channel.search("ml", max_results=2)
    # At least one sleep should be called, bounded by 1 RPS limit
    assert sleeps and 0.0 < sleeps[0] <= 1.0
    # rsshub_mod import is intentional — keeps module available for future tests
    assert rsshub_mod.RsshubChannel is RsshubChannel