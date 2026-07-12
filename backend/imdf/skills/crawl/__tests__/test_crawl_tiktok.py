"""Tests for crawl_tiktok."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_tiktok import (
    SKILL_ID,
    TikTokRequest,
    crawl_tiktok,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path():
    out = _run(crawl_tiktok(SkillInput(params={"query": "recipe",
                                                 "count": 3})))
    assert out.success is True
    assert out.metadata["skill_id"] == SKILL_ID
    videos = out.result["videos"]
    assert 1 <= len(videos) <= 3
    assert videos[0]["url"].startswith("https://www.tiktok.com")


def test_query_required():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TikTokRequest.model_validate({})


def test_count_capped_to_30():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TikTokRequest.model_validate({"query": "x", "count": 100})


def test_invalid_params_payload_returns_failure():
    out = _run(crawl_tiktok(SkillInput(params={"query": "x",
                                                 "count": "abc"})))
    assert out.success is False
    assert "invalid_params" in out.error