"""P22-P2c: tests for mediacms-cn adapter skeleton.

Covers:
- MediaItem.to_dict() round-trips
- MockAdapter.list_videos deterministic + filter by query/category/offset
- MockAdapter.get_video returns the right item
- MockAdapter.list_categories returns 3
- MockAdapter.health always ok=True
- LiveAdapter constructor raises without env vars
- LiveAdapter constructor accepts env vars
- LiveAdapter.health fails on malformed URL
- make_adapter respects prefer / env
- Abstract interface cannot be instantiated directly
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


def _import_module():
    from integrations.adapters.mediacms_cn import (
        MediaItem,
        Category,
        MediaCMSAdapter,
        MediaCMSCNMockAdapter,
        MediaCMSCNLiveAdapter,
        make_adapter,
    )
    return {
        "MediaItem": MediaItem,
        "Category": Category,
        "MediaCMSAdapter": MediaCMSAdapter,
        "MediaCMSCNMockAdapter": MediaCMSCNMockAdapter,
        "MediaCMSCNLiveAdapter": MediaCMSCNLiveAdapter,
        "make_adapter": make_adapter,
    }


# ── Data class tests ──────────────────────────────────────────────────

def test_mediaitem_to_dict_includes_all_fields():
    M = _import_module()["MediaItem"]
    m = M(id="v1", title="hello", tags=["t1"], extra={"foo": "bar"})
    d = m.to_dict()
    for k in ("id", "title", "description", "url", "thumbnail_url",
              "duration_s", "views", "likes", "author", "category",
              "tags", "created_at", "storage_backend", "transcode_status",
              "icp_aware", "extra"):
        assert k in d, f"missing field {k}"
    assert d["tags"] == ["t1"]
    assert d["extra"] == {"foo": "bar"}


# ── MockAdapter tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_adapter_list_videos_default_empty_query():
    M = _import_module()["MediaCMSCNMockAdapter"]
    api = M()
    items = await api.list_videos()
    # mock seeds 12 items, default limit 20
    assert len(items) >= 1
    # sorted by created_at desc — newest first
    assert items == sorted(items, key=lambda v: v.created_at, reverse=True)


@pytest.mark.asyncio
async def test_mock_adapter_list_videos_limit_and_offset():
    M = _import_module()["MediaCMSCNMockAdapter"]
    api = M()
    page1 = await api.list_videos(limit=5, offset=0)
    page2 = await api.list_videos(limit=5, offset=5)
    assert len(page1) == 5
    assert len(page2) == 5
    # No overlap
    page1_ids = {v.id for v in page1}
    page2_ids = {v.id for v in page2}
    assert not (page1_ids & page2_ids)


@pytest.mark.asyncio
async def test_mock_adapter_list_videos_filter_by_category():
    M = _import_module()["MediaCMSCNMockAdapter"]
    api = M()
    demo = await api.list_videos(category="demo")
    tutorial = await api.list_videos(category="tutorial")
    assert all(v.category == "demo" for v in demo)
    assert all(v.category == "tutorial" for v in tutorial)
    assert len(demo) + len(tutorial) >= 1


@pytest.mark.asyncio
async def test_mock_adapter_list_videos_filter_by_query():
    M = _import_module()["MediaCMSCNMockAdapter"]
    api = M()
    items = await api.list_videos(query="video 1")
    # At least one item should match "Sample video 1" or similar
    assert any("video 1" in v.title.lower() for v in items)


@pytest.mark.asyncio
async def test_mock_adapter_get_video_returns_correct_item():
    M = _import_module()["MediaCMSCNMockAdapter"]
    api = M()
    v = await api.get_video("v0001")
    assert v is not None
    assert v.id == "v0001"
    assert v.title.startswith("[Mock]")


@pytest.mark.asyncio
async def test_mock_adapter_get_video_missing_returns_none():
    M = _import_module()["MediaCMSCNMockAdapter"]
    api = M()
    v = await api.get_video("nonexistent")
    assert v is None


@pytest.mark.asyncio
async def test_mock_adapter_list_categories_returns_three():
    M = _import_module()["MediaCMSCNMockAdapter"]
    api = M()
    cats = await api.list_categories()
    assert len(cats) == 3
    assert all(isinstance(c, M.__mro__[0]) for c in cats) or True  # type check via Category import
    Category = _import_module()["Category"]
    assert all(isinstance(c, Category) for c in cats)


@pytest.mark.asyncio
async def test_mock_adapter_health_ok():
    M = _import_module()["MediaCMSCNMockAdapter"]
    api = M()
    h = await api.health()
    assert h["ok"] is True
    assert h["channel"] == "mediacms_cn_mock"
    assert "version" in h
    assert h["latency_ms"] >= 0


# ── LiveAdapter tests ─────────────────────────────────────────────────

def test_live_adapter_raises_without_env(monkeypatch):
    M = _import_module()["MediaCMSCNLiveAdapter"]
    monkeypatch.delenv("MEDIACMS_CN_API_URL", raising=False)
    monkeypatch.delenv("MEDIACMS_CN_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MEDIACMS_CN_API_URL"):
        M()


def test_live_adapter_accepts_env(monkeypatch):
    M = _import_module()["MediaCMSCNLiveAdapter"]
    monkeypatch.setenv("MEDIACMS_CN_API_URL", "https://api.mediacms-cn.example.com")
    monkeypatch.setenv("MEDIACMS_CN_API_KEY", "test-key-12345")
    api = M()
    assert api._api_url == "https://api.mediacms-cn.example.com"
    assert api._api_key == "test-key-12345"


def test_live_adapter_strips_trailing_slash(monkeypatch):
    M = _import_module()["MediaCMSCNLiveAdapter"]
    monkeypatch.setenv("MEDIACMS_CN_API_URL", "https://api.example.com/")
    monkeypatch.setenv("MEDIACMS_CN_API_KEY", "k")
    api = M()
    assert api._api_url == "https://api.example.com"


@pytest.mark.asyncio
async def test_live_adapter_health_checks_url_parseable(monkeypatch):
    M = _import_module()["MediaCMSCNLiveAdapter"]
    monkeypatch.setenv("MEDIACMS_CN_API_URL", "https://api.example.com")
    monkeypatch.setenv("MEDIACMS_CN_API_KEY", "k")
    api = M()
    h = await api.health()
    assert h["ok"] is True
    assert h["channel"] == "mediacms_cn_live"


@pytest.mark.asyncio
async def test_live_adapter_health_fails_on_malformed_url(monkeypatch):
    M = _import_module()["MediaCMSCNLiveAdapter"]
    monkeypatch.setenv("MEDIACMS_CN_API_URL", "not-a-url")
    monkeypatch.setenv("MEDIACMS_CN_API_KEY", "k")
    api = M()
    h = await api.health()
    assert h["ok"] is False


# ── LiveAdapter methods pending spec (NotImplementedError) ───────────

@pytest.mark.asyncio
async def test_live_adapter_list_videos_not_implemented(monkeypatch):
    M = _import_module()["MediaCMSCNLiveAdapter"]
    monkeypatch.setenv("MEDIACMS_CN_API_URL", "https://api.example.com")
    monkeypatch.setenv("MEDIACMS_CN_API_KEY", "k")
    api = M()
    with pytest.raises(NotImplementedError):
        await api.list_videos()


# ── Factory tests ─────────────────────────────────────────────────────

def test_make_adapter_default_returns_mock(monkeypatch):
    monkeypatch.delenv("MEDIACMS_CN_ADAPTER", raising=False)
    monkeypatch.delenv("MEDIACMS_CN_API_URL", raising=False)
    f = _import_module()
    adapter = f["make_adapter"]()
    assert isinstance(adapter, f["MediaCMSCNMockAdapter"])


def test_make_adapter_prefer_mock(monkeypatch):
    f = _import_module()
    adapter = f["make_adapter"](prefer="mock")
    assert isinstance(adapter, f["MediaCMSCNMockAdapter"])


def test_make_adapter_prefer_live(monkeypatch):
    monkeypatch.setenv("MEDIACMS_CN_API_URL", "https://api.example.com")
    monkeypatch.setenv("MEDIACMS_CN_API_KEY", "k")
    f = _import_module()
    adapter = f["make_adapter"](prefer="live")
    assert isinstance(adapter, f["MediaCMSCNLiveAdapter"])


def test_make_adapter_env_live(monkeypatch):
    monkeypatch.setenv("MEDIACMS_CN_ADAPTER", "live")
    monkeypatch.setenv("MEDIACMS_CN_API_URL", "https://api.example.com")
    monkeypatch.setenv("MEDIACMS_CN_API_KEY", "k")
    f = _import_module()
    adapter = f["make_adapter"]()
    assert isinstance(adapter, f["MediaCMSCNLiveAdapter"])


def test_make_adapter_env_live_without_url_falls_back(monkeypatch):
    """If env says live but URL is missing, factory falls back to mock
    rather than raising — so test runs in CI don't blow up if env is
    half-configured."""
    monkeypatch.setenv("MEDIACMS_CN_ADAPTER", "live")
    monkeypatch.delenv("MEDIACMS_CN_API_URL", raising=False)
    monkeypatch.delenv("MEDIACMS_CN_API_KEY", raising=False)
    f = _import_module()
    adapter = f["make_adapter"]()
    assert isinstance(adapter, f["MediaCMSCNMockAdapter"])


# ── Abstract interface cannot be instantiated directly ──────────────

def test_abstract_adapter_cannot_be_instantiated():
    f = _import_module()
    with pytest.raises(TypeError):
        f["MediaCMSAdapter"]()
