"""P22-P2a: tests for 12 new P2 channels.

Covers:
- import: all 12 channel modules can be imported
- instantiation: each API class can be constructed
- fetch: each channel returns a FetchResult with deterministic data
- channel name: each module exposes the correct `channel` attribute
- result count: each fetch returns 3 entries (mock data)
- latency metadata: each fetch reports a non-negative latency_ms
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "imdf"))


# ─── Expected 12 P2 channels ─────────────────────────────────────────────
NEW_CHANNELS = [
    ("feedly", "FeedlyAPI"),
    ("digg", "DiggAPI"),
    ("pinterest", "PinterestAPI"),
    ("vimeo", "VimeoAPI"),
    ("delicious", "DeliciousAPI"),
    ("stumbleupon", "StumbleuponAPI"),
    ("tumblr", "TumblrAPI"),
    ("pocket", "PocketAPI"),
    ("instapaper", "InstapaperAPI"),
    ("medium", "MediumAPI"),
    ("substack", "SubstackAPI"),
    ("hackernews", "HackernewsAPI"),
]


# ─── import + channel attribute ──────────────────────────────────────────

@pytest.mark.parametrize("channel_id,class_name", NEW_CHANNELS)
def test_channel_imports(channel_id, class_name):
    mod = __import__(
        f"intelligence.agent_reach.channels.{channel_id}",
        fromlist=["*"],
    )
    cls = getattr(mod, class_name)
    assert cls.channel == channel_id


# ─── instantiation + fetch ──────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("channel_id,class_name", NEW_CHANNELS)
async def test_channel_fetch_returns_deterministic_results(channel_id, class_name):
    mod = __import__(
        f"intelligence.agent_reach.channels.{channel_id}",
        fromlist=["*"],
    )
    cls = getattr(mod, class_name)
    api = cls()
    out = await api.fetch("test query")
    assert out.success is True
    assert out.channel == channel_id
    assert out.query == "test query"
    assert out.content  # non-empty
    assert out.url.startswith(f"https://{channel_id}")
    assert out.metadata.get("count", 0) == 3
    assert out.metadata.get("engine") == f"{channel_id}-mock"
    assert len(out.metadata.get("results", [])) == 3
    assert isinstance(out.latency_ms, (int, float))
    assert out.latency_ms >= 0


# ─── determinism: same query → same content hash ───────────────────────

@pytest.mark.asyncio
async def test_digg_deterministic_for_same_query():
    from intelligence.agent_reach.channels.digg import DiggAPI
    api = DiggAPI()
    r1 = await api.fetch("hello world")
    r2 = await api.fetch("hello world")
    assert r1.content == r2.content
    assert r1.metadata["results"] == r2.metadata["results"]


@pytest.mark.asyncio
async def test_digg_different_for_different_query():
    from intelligence.agent_reach.channels.digg import DiggAPI
    api = DiggAPI()
    r1 = await api.fetch("foo")
    r2 = await api.fetch("bar")
    # Different query → different results (because hash differs)
    assert r1.content != r2.content


# ─── __init__ exports ───────────────────────────────────────────────────

def test_all_12_p2_in_package_all():
    from intelligence.agent_reach.channels import __all__ as exported
    expected_names = {name for _, name in NEW_CHANNELS}
    missing = expected_names - set(exported)
    assert not missing, f"channels __all__ missing: {missing}"


def test_total_channels_count():
    from intelligence.agent_reach.channels import __all__ as exported
    # 14 P19-B3 + 12 P22-P2a = 26
    assert len(exported) == 26, f"expected 26 channels, got {len(exported)}"


# ─── Latency: all 12 finish in < 100ms (no I/O) ─────────────────────────

@pytest.mark.asyncio
async def test_all_12_channels_fast():
    """Mock channels must not block on I/O — all 12 should complete in
    well under 100ms each (total < 1.2s for the batch)."""
    import time
    t0 = time.perf_counter()
    for channel_id, class_name in NEW_CHANNELS:
        mod = __import__(
            f"intelligence.agent_reach.channels.{channel_id}",
            fromlist=["*"],
        )
        cls = getattr(mod, class_name)
        api = cls()
        await api.fetch("perf test")
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.2, f"12 channels took {elapsed:.2f}s (expected < 1.2s)"
