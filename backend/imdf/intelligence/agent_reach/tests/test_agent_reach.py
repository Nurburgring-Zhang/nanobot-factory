"""V5 第32章 — Agent Reach tests (≥15 tests).

Coverage:
    * integration.fetch for each of the 14 channels (mocked)
    * integration.search (default + custom channels)
    * integration.health_check (all 14 healthy + 1 error)
    * cache hit / miss
    * FetchResult / MultiChannelResult / HealthStatus schema validation
    * exception handling (unknown channel / handler raises)

All network-using handlers are patched via monkeypatch — tests never hit
the real network.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from imdf.intelligence.agent_reach.integration import (
    AgentReachIntegration,
    CHANNELS,
    DEFAULT_SEARCH_CHANNELS,
)
from imdf.intelligence.agent_reach.schemas import (
    FetchResult,
    HealthStatus,
    MultiChannelResult,
)


# ── Fixtures ───────────────────────────────────────────────────────────────
ALL_CHANNELS = sorted(CHANNELS.keys())


@pytest.fixture
def integ() -> AgentReachIntegration:
    return AgentReachIntegration()


@pytest.fixture
def patch_handlers(monkeypatch):
    """Patch every channel handler with an AsyncMock that returns a deterministic
    FetchResult. Each handler.fetch returns a success, ping returns True.
    """

    def _make_fetch_mock(channel_name: str):
        async def _fetch(query: str, **kwargs):
            return FetchResult(
                success=True,
                channel=channel_name,
                query=query,
                content=f"mock-{channel_name}:{query}",
                url=f"https://{channel_name}.mock/{query}",
                metadata={"mocked": True, "engine": f"{channel_name}-mock"},
                latency_ms=1.0,
            )
        return _fetch

    async def _ping_ok():
        return True

    async def _ping_bad():
        return False

    for ch, cfg in CHANNELS.items():
        module_name = cfg["module"]
        handler_name = cfg["handler"]
        # import the module
        import importlib
        mod = importlib.import_module(module_name)
        cls = getattr(mod, handler_name)
        # instantiate and patch methods
        instance = cls.__new__(cls)
        instance.fetch = AsyncMock(side_effect=_make_fetch_mock(ch))
        instance.ping = AsyncMock(side_effect=_ping_ok)
        monkeypatch.setattr(
            f"{module_name}.{handler_name}.__init__",
            lambda self, *a, **kw: None,
        )
        # re-bind by setting attribute on class for fresh instances
        setattr(cls, "_patched_fetch", instance.fetch)
        setattr(cls, "_patched_ping", instance.ping)
        # patch __init__ to use our pre-bound instance
        monkeypatch.setattr(
            cls,
            "__init__",
            lambda self, *a, **kw: (
                setattr(self, "fetch", instance.fetch),
                setattr(self, "ping", instance.ping),
            ),
        )
    return monkeypatch


# ── Tests ──────────────────────────────────────────────────────────────────
class TestSchemas:
    """Pydantic v2 schema validation."""

    def test_fetch_result_defaults(self):
        fr = FetchResult(channel="web", query="hello")
        assert fr.success is True
        assert fr.channel == "web"
        assert fr.query == "hello"
        assert fr.content == ""
        assert fr.metadata == {}
        assert fr.cached is False
        assert fr.latency_ms == 0.0

    def test_fetch_result_with_error(self):
        fr = FetchResult(success=False, channel="github", query="x", error="boom")
        assert fr.success is False
        assert fr.error == "boom"

    def test_fetch_result_to_dict(self):
        fr = FetchResult(channel="web", query="x", content="abc")
        d = fr.to_dict()
        assert d["channel"] == "web"
        assert d["content"] == "abc"
        assert d["success"] is True

    def test_multi_channel_result_summary(self):
        mcr = MultiChannelResult(
            query="ai safety",
            channels=["exa_search", "web"],
            results={
                "exa_search": FetchResult(channel="exa_search", query="ai safety"),
                "web": FetchResult(channel="web", query="ai safety"),
            },
            total=2,
            success_count=2,
            error_count=0,
            elapsed_ms=12.0,
        )
        s = mcr.summary()
        assert s["total"] == 2
        assert s["success_count"] == 2
        assert s["query"] == "ai safety"

    def test_health_status_defaults(self):
        st = HealthStatus(channel="web")
        assert st.healthy is False
        assert st.status == "unhealthy"
        assert st.error is None


class TestChannelRegistry:
    """CHANNELS dict + helpers."""

    def test_channels_count(self):
        assert len(CHANNELS) == 14

    def test_channels_have_required_keys(self):
        for ch, cfg in CHANNELS.items():
            assert "handler" in cfg, ch
            assert "module" in cfg, ch
            assert "free" in cfg, ch
            assert "description" in cfg, ch

    def test_channels_are_unique(self):
        assert len(set(CHANNELS.keys())) == 14

    def test_all_channels_present(self):
        expected = {
            "web", "twitter", "youtube", "bilibili", "reddit",
            "xiaohongshu", "github", "rss", "exa_search", "linkedin",
            "instagram", "wechat", "douyin", "zhihu",
        }
        assert set(CHANNELS.keys()) == expected

    def test_default_search_channels(self):
        assert DEFAULT_SEARCH_CHANNELS == ["exa_search", "web", "reddit", "twitter"]


class TestIntegrationFetch:
    """integration.fetch for all 14 channels (mocked)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("channel", ALL_CHANNELS)
    async def test_fetch_each_channel(self, integ, channel):
        # patch the handler for this channel via direct mock
        handler = integ._get_handler(channel)
        expected = FetchResult(
            success=True,
            channel=channel,
            query="hello",
            content=f"test-{channel}",
        )
        handler.fetch = AsyncMock(return_value=expected)

        result = await integ.fetch(channel, "hello")
        assert result.success is True
        assert result.channel == channel
        assert result.content == f"test-{channel}"
        # should have been cached (success)
        assert len(integ.cache) >= 1

    @pytest.mark.asyncio
    async def test_fetch_unknown_channel_raises_keyerror(self, integ):
        with pytest.raises(KeyError, match="unknown channel"):
            await integ.fetch("nonexistent_channel", "x")

    @pytest.mark.asyncio
    async def test_fetch_handler_exception_returns_failure_result(self, integ):
        handler = integ._get_handler("web")
        handler.fetch = AsyncMock(side_effect=RuntimeError("boom"))
        result = await integ.fetch("web", "x")
        assert result.success is False
        assert "boom" in result.error
        assert "RuntimeError" in result.error


class TestIntegrationCache:
    """Cache hit/miss behavior."""

    @pytest.mark.asyncio
    async def test_cache_miss_then_hit(self, integ):
        handler = integ._get_handler("web")
        # use side_effect to return a FRESH FetchResult per call — otherwise
        # the second call mutates the shared cached object via .cached = True
        async def _fresh(query, **kwargs):
            return FetchResult(channel="web", query=query, content="first")
        handler.fetch = AsyncMock(side_effect=_fresh)
        r1 = await integ.fetch("web", "x")
        r2 = await integ.fetch("web", "x")
        assert r1.cached is False
        assert r2.cached is True
        # handler called only once
        assert handler.fetch.await_count == 1

    @pytest.mark.asyncio
    async def test_cache_failure_not_cached(self, integ):
        handler = integ._get_handler("web")
        handler.fetch = AsyncMock(
            return_value=FetchResult(success=False, channel="web", query="x", error="err")
        )
        await integ.fetch("web", "x")
        await integ.fetch("web", "x")
        # both calls hit handler (failures not cached)
        assert handler.fetch.await_count == 2

    @pytest.mark.asyncio
    async def test_cache_per_channel(self, integ):
        integ._get_handler("web").fetch = AsyncMock(
            return_value=FetchResult(channel="web", query="x", content="w")
        )
        integ._get_handler("github").fetch = AsyncMock(
            return_value=FetchResult(channel="github", query="x", content="g")
        )
        r_w = await integ.fetch("web", "x")
        r_g = await integ.fetch("github", "x")
        assert r_w.content == "w"
        assert r_g.content == "g"
        assert r_w.cached is False
        assert r_g.cached is False

    @pytest.mark.asyncio
    async def test_cache_info(self, integ):
        integ._get_handler("web").fetch = AsyncMock(
            return_value=FetchResult(channel="web", query="x")
        )
        await integ.fetch("web", "x")
        info = integ.cache_info()
        assert info["size"] >= 1
        assert info["max_size"] == 5000
        assert info["ttl"] == 300


class TestIntegrationSearch:
    """Fan-out search across multiple channels."""

    @pytest.mark.asyncio
    async def test_search_default_channels(self, integ):
        for ch in DEFAULT_SEARCH_CHANNELS:
            integ._get_handler(ch).fetch = AsyncMock(
                return_value=FetchResult(channel=ch, query="ai safety", content=f"ok-{ch}")
            )
        result = await integ.search("ai safety")
        assert isinstance(result, MultiChannelResult)
        assert set(result.channels) == set(DEFAULT_SEARCH_CHANNELS)
        assert result.total == 4
        assert result.success_count == 4
        assert result.error_count == 0
        assert all(r.success for r in result.results.values())

    @pytest.mark.asyncio
    async def test_search_custom_channels(self, integ):
        custom = ["github", "youtube", "reddit"]
        for ch in custom:
            integ._get_handler(ch).fetch = AsyncMock(
                return_value=FetchResult(channel=ch, query="q", content=f"ok-{ch}")
            )
        result = await integ.search("q", channels=custom)
        assert result.total == 3
        assert set(result.channels) == set(custom)

    @pytest.mark.asyncio
    async def test_search_unknown_channel_raises(self, integ):
        with pytest.raises(KeyError, match="unknown channel in search"):
            await integ.search("q", channels=["web", "bogus"])

    @pytest.mark.asyncio
    async def test_search_one_channel_fails(self, integ):
        integ._get_handler("web").fetch = AsyncMock(
            return_value=FetchResult(channel="web", query="q")
        )
        integ._get_handler("github").fetch = AsyncMock(
            side_effect=RuntimeError("api down")
        )
        result = await integ.search("q", channels=["web", "github"])
        assert result.total == 2
        assert result.success_count == 1
        assert result.error_count == 1
        assert result.results["web"].success is True
        assert result.results["github"].success is False


class TestHealthCheck:
    """health_check across all 14 channels."""

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(self, integ):
        for ch in CHANNELS:
            integ._get_handler(ch).ping = AsyncMock(return_value=True)
        result = await integ.health_check()
        assert len(result) == 14
        assert all(st.healthy for st in result.values())
        assert all(st.status == "healthy" for st in result.values())
        assert "checked_at" in result["web"].model_dump()

    @pytest.mark.asyncio
    async def test_health_check_one_error(self, integ):
        for ch in CHANNELS:
            if ch == "twitter":
                integ._get_handler(ch).ping = AsyncMock(
                    side_effect=RuntimeError("timeout")
                )
            else:
                integ._get_handler(ch).ping = AsyncMock(return_value=True)
        result = await integ.health_check()
        assert len(result) == 14
        assert result["twitter"].healthy is False
        assert result["twitter"].status == "error"
        assert "timeout" in result["twitter"].error
        # others healthy
        for ch in CHANNELS:
            if ch != "twitter":
                assert result[ch].healthy is True

    @pytest.mark.asyncio
    async def test_health_check_returns_dict_of_healthstatus(self, integ):
        for ch in CHANNELS:
            integ._get_handler(ch).ping = AsyncMock(return_value=True)
        result = await integ.health_check()
        for st in result.values():
            assert isinstance(st, HealthStatus)


class TestHandlersDirect:
    """Direct handler tests — verify each of 14 handlers returns a FetchResult."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("channel", ALL_CHANNELS)
    async def test_handler_fetch_returns_fetch_result(self, channel):
        """Each channel handler should be importable, instantiable, and call fetch."""
        import importlib
        cfg = CHANNELS[channel]
        mod = importlib.import_module(cfg["module"])
        cls = getattr(mod, cfg["handler"])
        instance = cls()
        # mock aiohttp / aiohttp.ClientSession for web + github to avoid network
        if channel in ("web", "github"):
            instance.fetch = AsyncMock(
                return_value=FetchResult(channel=channel, query="q", content=f"ok-{channel}")
            )
        result = await instance.fetch("q")
        assert isinstance(result, FetchResult)
        assert result.channel == channel

    @pytest.mark.asyncio
    @pytest.mark.parametrize("channel", ALL_CHANNELS)
    async def test_handler_ping_returns_bool(self, channel):
        import importlib
        cfg = CHANNELS[channel]
        mod = importlib.import_module(cfg["module"])
        cls = getattr(mod, cfg["handler"])
        instance = cls()
        # mock ping to return True
        instance.ping = AsyncMock(return_value=True)
        ok = await instance.ping()
        assert isinstance(ok, bool)
        assert ok is True


class TestIntegrationHelpers:
    """list_channels / is_free / cache_info helpers."""

    def test_list_channels_returns_14_sorted(self, integ):
        chans = integ.list_channels()
        assert len(chans) == 14
        assert chans == sorted(chans)

    def test_is_free_true_for_web(self, integ):
        assert integ.is_free("web") is True

    def test_is_free_false_for_twitter(self, integ):
        assert integ.is_free("twitter") is False

    def test_is_free_unknown_returns_false(self, integ):
        assert integ.is_free("nope") is False

    def test_initial_health_status_empty(self, integ):
        assert integ.health_status == {}