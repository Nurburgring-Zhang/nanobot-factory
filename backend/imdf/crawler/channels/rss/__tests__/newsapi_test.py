"""Tests for NewsApiChannel."""
from __future__ import annotations

import json
import os
from datetime import datetime
from unittest.mock import patch

import httpx
import pytest

from backend.imdf.crawler.channels.rss import NewsApiChannel

SAMPLE_ARTICLES = json.dumps(
    {
        "status": "ok",
        "totalResults": 2,
        "articles": [
            {
                "url": "https://news.example.com/a",
                "title": "AI breakthrough",
                "description": "Researchers report ...",
                "author": "Jane Reporter",
                "urlToImage": "https://news.example.com/a.jpg",
                "publishedAt": "2025-07-02T10:00:00Z",
                "source": {"name": "TechCrunch"},
            },
            {
                "url": "https://news.example.com/b",
                "title": "Open Source LLM",
                "description": "A new model ...",
                "author": "Bob",
                "publishedAt": "2025-07-01T09:00:00Z",
                "source": {"name": "The Verge"},
            },
        ],
    }
)


def api_client(payload: str = SAMPLE_ARTICLES) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=payload, request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def failing_client() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_search_with_api_key_returns_articles() -> None:
    with patch.dict(os.environ, {"NEWSAPI_KEY": "test-key-123"}):
        channel = NewsApiChannel(client=api_client())
        results = await channel.search("open source", max_results=10)
    assert len(results) == 2
    assert results[0].source == "newsapi"
    assert results[0].title == "AI breakthrough"
    assert results[0].url == "https://news.example.com/a"
    assert results[0].thumbnail_url == "https://news.example.com/a.jpg"
    assert isinstance(results[0].created_at, datetime)
    assert results[1].author == "Bob"


@pytest.mark.asyncio
async def test_search_without_api_key_falls_back_to_public() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("NEWSAPI_KEY", None)
        channel = NewsApiChannel(client=api_client())
        results = await channel.search("machine learning", max_results=5)
    assert len(results) == 1
    assert results[0].source == "newsapi"
    assert "machine learning" in results[0].title
    assert "newsapi.org/search" in results[0].url
    assert results[0].extra.get("mode") == "public-fallback"
    assert results[0].extra.get("needs_api_key") is True


@pytest.mark.asyncio
async def test_search_handles_network_errors() -> None:
    with patch.dict(os.environ, {"NEWSAPI_KEY": "test-key"}):
        channel = NewsApiChannel(client=failing_client())
        results = await channel.search("ai", max_results=5)
    assert results == []


def test_parse_articles_json() -> None:
    items = NewsApiChannel.parse(SAMPLE_ARTICLES)
    assert len(items) == 2
    assert items[0].url == "https://news.example.com/a"
    assert items[1].description.startswith("A new model")


def test_parse_handles_invalid_json() -> None:
    assert NewsApiChannel.parse("<html>not json</html>") == []
    assert NewsApiChannel.parse("") == []
    assert NewsApiChannel.parse('{"articles": "not-a-list"}') == []