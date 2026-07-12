from __future__ import annotations

import time

import httpx
import pytest

from backend.imdf.crawler.channels.social import TiebaChannel
from backend.imdf.crawler.channels.social import _base as social_base

HTML = """
<html><body>
  <div class="s_post">
    <h3 class="p_title"><a href="/p/8001">AI 模型训练讨论帖</a></h3>
    <span class="p_violet">贴吧用户A</span>
    <p class="p_content">帖子摘要内容</p>
    <img src="//imgsrc.baidu.com/forum/thumb.jpg" />
  </div>
  <div class="threadlist_li">
    <a class="threadlist_title" href="https://tieba.baidu.com/p/8002">机器人数据采集</a>
    <span class="frs-author-name">贴吧用户B</span>
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
    channel = TiebaChannel(transport=transport_for())
    results = await channel.search("AI 模型", max_results=5)
    assert len(results) == 2
    assert results[0].source == "tieba"
    assert "模型训练" in results[0].title


def test_parse_extracts_fields() -> None:
    results = TiebaChannel.parse(HTML)
    assert results[0].url == "https://tieba.baidu.com/p/8001"
    assert results[0].author == "贴吧用户A"
    assert results[0].thumbnail_url == "https://imgsrc.baidu.com/forum/thumb.jpg"


@pytest.mark.asyncio
async def test_search_handles_network_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    channel = TiebaChannel(transport=httpx.MockTransport(handler))
    assert await channel.search("AI", max_results=3) == []


@pytest.mark.asyncio
async def test_rate_limit_waits_before_request(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(social_base.asyncio, "sleep", fake_sleep)
    channel = TiebaChannel(transport=transport_for())
    channel._last_request_at = time.monotonic()
    await channel.search("AI", max_results=1)
    assert sleeps and 0.0 < sleeps[0] <= 1.0
