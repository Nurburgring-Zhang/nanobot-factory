from __future__ import annotations

import time

import httpx
import pytest

from backend.imdf.crawler.channels.social import WeiboChannel
from backend.imdf.crawler.channels.social import _base as social_base

HTML = """
<html><body>
  <div class="card">
    <a href="/detail/1001"><span class="weibo-text">AI 绘画热搜第一条</span></a>
    <span class="m-text-cut">央视新闻</span>
    <p class="desc">微博热搜讨论摘要</p>
    <img src="//wx1.sinaimg.cn/thumb.jpg" />
  </div>
  <div class="card">
    <a href="https://m.weibo.cn/status/1002"><span class="weibo-text">机器人视频</span></a>
    <span class="m-text-cut">科技博主</span>
    <p class="desc">第二条结果</p>
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
    channel = WeiboChannel(transport=transport_for())
    results = await channel.search("AI 绘画", max_results=5)
    assert len(results) == 2
    assert results[0].source == "weibo"
    assert "AI 绘画" in results[0].title


def test_parse_extracts_fields() -> None:
    results = WeiboChannel.parse(HTML)
    assert results[0].url == "https://m.weibo.cn/detail/1001"
    assert results[0].author == "央视新闻"
    assert results[0].thumbnail_url == "https://wx1.sinaimg.cn/thumb.jpg"


@pytest.mark.asyncio
async def test_search_handles_network_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    channel = WeiboChannel(transport=httpx.MockTransport(handler))
    assert await channel.search("AI", max_results=3) == []


@pytest.mark.asyncio
async def test_rate_limit_waits_before_request(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(social_base.asyncio, "sleep", fake_sleep)
    channel = WeiboChannel(transport=transport_for())
    channel._last_request_at = time.monotonic()
    await channel.search("AI", max_results=1)
    assert sleeps and 0.0 < sleeps[0] <= 1.0
