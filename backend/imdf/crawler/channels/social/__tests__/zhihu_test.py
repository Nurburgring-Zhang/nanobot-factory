from __future__ import annotations

import time

import httpx
import pytest

from backend.imdf.crawler.channels.social import ZhihuChannel
from backend.imdf.crawler.channels.social import _base as social_base

HTML = """
<html><body>
  <div class="List-item">
    <h2 class="ContentItem-title"><a href="/question/5001/answer/1">AI 数据治理怎么做？</a></h2>
    <span class="AuthorInfo-name">知乎作者A</span>
    <div class="RichContent-inner">问答摘要内容</div>
    <img src="//pic1.zhimg.com/thumb.jpg" />
  </div>
  <div class="SearchResult-Card">
    <h2 class="ContentItem-title"><a href="https://www.zhihu.com/question/5002">机器人标注流程</a></h2>
    <span class="AuthorInfo-name">知乎作者B</span>
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
    channel = ZhihuChannel(transport=transport_for())
    results = await channel.search("AI 数据", max_results=5)
    assert len(results) == 2
    assert results[0].source == "zhihu"
    assert "数据治理" in results[0].title


def test_parse_extracts_fields() -> None:
    results = ZhihuChannel.parse(HTML)
    assert results[0].url == "https://www.zhihu.com/question/5001/answer/1"
    assert results[0].author == "知乎作者A"
    assert results[0].thumbnail_url == "https://pic1.zhimg.com/thumb.jpg"


@pytest.mark.asyncio
async def test_search_handles_network_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    channel = ZhihuChannel(transport=httpx.MockTransport(handler))
    assert await channel.search("AI", max_results=3) == []


@pytest.mark.asyncio
async def test_rate_limit_waits_before_request(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(social_base.asyncio, "sleep", fake_sleep)
    channel = ZhihuChannel(transport=transport_for())
    channel._last_request_at = time.monotonic()
    await channel.search("AI", max_results=1)
    assert sleeps and 0.0 < sleeps[0] <= 1.0
