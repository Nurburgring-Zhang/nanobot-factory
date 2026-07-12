"""RedditChannel tests."""
from __future__ import annotations

import json
import time

import httpx
import pytest

from backend.imdf.crawler.channels.rss import RedditChannel

SAMPLE_PAYLOAD = json.dumps(
    {
        "kind": "Listing",
        "data": {
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "id": "abc123",
                        "title": "Best open source LLMs 2025",
                        "selftext": "Discussion thread content ...",
                        "url": "https://example.com/article",
                        "permalink": "/r/MachineLearning/comments/abc123/best_llm/",
                        "subreddit": "MachineLearning",
                        "author": "user_one",
                        "thumbnail": "https://example.com/thumb.jpg",
                        "score": 142,
                        "num_comments": 37,
                        "created_utc": 1720000000.0,
                    },
                },
                {
                    "kind": "t3",
                    "data": {
                        "id": "def456",
                        "title": "Self post without external URL",
                        "selftext": "Just a self-post",
                        "permalink": "/r/MachineLearning/comments/def456/self_post/",
                        "subreddit": "MachineLearning",
                        "author": "user_two",
                        "thumbnail": "",
                        "score": 5,
                        "num_comments": 1,
                        "created_utc": 1720000100.0,
                    },
                },
            ]
        },
    }
)


def reddit_client(payload=SAMPLE_PAYLOAD):
    def handler(request):
        return httpx.Response(200, text=payload, request=request)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def failing_client():
    def handler(request):
        raise httpx.ConnectError("network down", request=request)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_search_returns_results():
    channel = RedditChannel(client=reddit_client())
    results = await channel.search("open source llm", max_results=10)
    assert len(results) == 2
    assert results[0].source == "reddit"
    assert results[0].title == "Best open source LLMs 2025"
    assert results[0].url == "https://example.com/article"
    assert results[0].thumbnail_url == "https://example.com/thumb.jpg"
    assert results[0].extra.get("subreddit") == "MachineLearning"
    assert results[0].extra.get("score") == 142


@pytest.mark.asyncio
async def test_search_self_post_builds_permalink_url():
    channel = RedditChannel(client=reddit_client())
    results = await channel.search("self-post", max_results=10)
    self_post = results[1]
    assert "old.reddit.com" in self_post.url
    assert self_post.url.endswith("/comments/def456/self_post/")


@pytest.mark.asyncio
async def test_search_empty_query_returns_empty():
    channel = RedditChannel(client=reddit_client())
    assert await channel.search("", max_results=5) == []
    assert await channel.search("   ", max_results=5) == []


@pytest.mark.asyncio
async def test_search_handles_network_errors():
    channel = RedditChannel(client=failing_client())
    assert await channel.search("anything", max_results=5) == []


def test_parse_search_payload():
    items = RedditChannel.parse(SAMPLE_PAYLOAD)
    assert len(items) == 2
    assert items[0].id == "reddit_abc123"
    assert items[1].keywords == ["MachineLearning"]


def test_parse_handles_invalid_json():
    assert RedditChannel.parse("<html>not json</html>") == []
    assert RedditChannel.parse("") == []
    assert RedditChannel.parse('{"data": {"children": "not-a-list"}}') == []
    assert RedditChannel.parse('{"data": "wrong-shape"}') == []


@pytest.mark.asyncio
async def test_rate_limit_waits_before_request(monkeypatch):
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    import asyncio as asyncio_mod
    monkeypatch.setattr(asyncio_mod, "sleep", fake_sleep)
    channel = RedditChannel(client=reddit_client())
    channel._last_call_ts = time.monotonic()
    await channel.search("llm", max_results=2)
    assert sleeps and 0.0 < sleeps[0] <= 1.0