from __future__ import annotations

import json
import time

import httpx
import pytest

from backend.imdf.crawler.channels.social import BilibiliChannel
from backend.imdf.crawler.channels.social import _base as social_base

PAYLOAD = json.dumps(
    {
        "data": {
            "result": [
                {
                    "bvid": "BV1001",
                    "title": "<em>AI</em> 视频教程",
                    "description": "B站教程摘要",
                    "author": "UP主A",
                    "pic": "//i0.hdslb.com/bfs/archive/thumb.jpg",
                    "play": 100,
                },
                {
                    "arcurl": "https://www.bilibili.com/video/BV1002",
                    "title": "机器人评测",
                    "description": "第二条视频",
                    "author": "UP主B",
                },
            ]
        }
    },
    ensure_ascii=False,
)


def transport_for(payload: str = PAYLOAD) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n", request=request)
        return httpx.Response(200, text=payload, request=request)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_search_returns_results() -> None:
    channel = BilibiliChannel(transport=transport_for())
    results = await channel.search("AI 视频", max_results=5)
    assert len(results) == 2
    assert results[0].source == "bilibili"
    assert results[0].title == "AI 视频教程"


def test_parse_extracts_fields() -> None:
    results = BilibiliChannel.parse(PAYLOAD)
    assert results[0].url == "https://www.bilibili.com/video/BV1001"
    assert results[0].author == "UP主A"
    assert results[0].thumbnail_url == "https://i0.hdslb.com/bfs/archive/thumb.jpg"


@pytest.mark.asyncio
async def test_search_handles_network_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    channel = BilibiliChannel(transport=httpx.MockTransport(handler))
    assert await channel.search("AI", max_results=3) == []


@pytest.mark.asyncio
async def test_rate_limit_waits_before_request(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(social_base.asyncio, "sleep", fake_sleep)
    channel = BilibiliChannel(transport=transport_for())
    channel._last_request_at = time.monotonic()
    await channel.search("AI", max_results=1)
    assert sleeps and 0.0 < sleeps[0] <= 1.0
