from __future__ import annotations

import time

import httpx
import pytest

from backend.imdf.crawler.channels.social import DouyinChannel
from backend.imdf.crawler.channels.social import _base as social_base

HTML = """
<html><body>
  <div class="search-result-card">
    <a href="/video/7001"><h3 class="title">AI 短视频教程</h3></a>
    <span class="author">创作者A</span>
    <p class="desc">热门视频摘要</p>
    <img src="//p3.douyinpic.com/thumb.jpg" />
  </div>
  <div data-e2e="search-video-item">
    <a href="https://www.douyin.com/video/7002"><span data-e2e="video-desc">机器人舞蹈</span></a>
    <span data-e2e="video-author">创作者B</span>
  </div>
</body></html>
"""


def transport_for(payload: str = HTML) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n", request=request)
        return httpx.Response(200, text=payload, request=request)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_search_returns_results() -> None:
    channel = DouyinChannel(transport=transport_for())
    results = await channel.search("AI 视频", max_results=5)
    assert len(results) == 2
    assert results[0].source == "douyin"
    assert "短视频" in results[0].title


def test_parse_extracts_fields() -> None:
    results = DouyinChannel.parse(HTML)
    assert results[0].url == "https://www.douyin.com/video/7001"
    assert results[0].author == "创作者A"
    assert results[0].thumbnail_url == "https://p3.douyinpic.com/thumb.jpg"


@pytest.mark.asyncio
async def test_search_handles_network_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    channel = DouyinChannel(transport=httpx.MockTransport(handler))
    assert await channel.search("AI", max_results=3) == []


@pytest.mark.asyncio
async def test_rate_limit_waits_before_request(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(social_base.asyncio, "sleep", fake_sleep)
    channel = DouyinChannel(transport=transport_for())
    channel._last_request_at = time.monotonic()
    await channel.search("AI", max_results=1)
    assert sleeps and 0.0 < sleeps[0] <= 1.0
