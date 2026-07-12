from __future__ import annotations

import time

import httpx
import pytest

from backend.imdf.crawler.channels.social import XiaohongshuChannel
from backend.imdf.crawler.channels.social import _base as social_base

HTML = """
<html><body>
  <section class="note-item">
    <a href="/explore/9001"><span class="title">AI 绘本制作笔记</span></a>
    <span class="author">小红书作者A</span>
    <p class="desc">图文笔记摘要</p>
    <img src="//sns-img-qc.xhscdn.com/thumb.jpg" />
  </section>
  <section class="note-item">
    <a href="https://www.xiaohongshu.com/explore/9002"><span class="title">机器人摄影</span></a>
    <span class="name">作者B</span>
  </section>
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
    channel = XiaohongshuChannel(transport=transport_for())
    results = await channel.search("AI 绘本", max_results=5)
    assert len(results) == 2
    assert results[0].source == "xiaohongshu"
    assert "绘本" in results[0].title


def test_parse_extracts_fields() -> None:
    results = XiaohongshuChannel.parse(HTML)
    assert results[0].url == "https://www.xiaohongshu.com/explore/9001"
    assert results[0].author == "小红书作者A"
    assert results[0].thumbnail_url == "https://sns-img-qc.xhscdn.com/thumb.jpg"


@pytest.mark.asyncio
async def test_search_handles_network_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    channel = XiaohongshuChannel(transport=httpx.MockTransport(handler))
    assert await channel.search("AI", max_results=3) == []


@pytest.mark.asyncio
async def test_rate_limit_waits_before_request(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(social_base.asyncio, "sleep", fake_sleep)
    channel = XiaohongshuChannel(transport=transport_for())
    channel._last_request_at = time.monotonic()
    await channel.search("AI", max_results=1)
    assert sleeps and 0.0 < sleeps[0] <= 1.0
