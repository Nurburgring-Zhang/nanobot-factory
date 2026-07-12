"""Tests for crawl_youtube."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_youtube import (
    SKILL_ID,
    YouTubeRequest,
    crawl_youtube,
    _parse_iso8601_duration,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_iso8601_duration_parser():
    assert _parse_iso8601_duration("PT1H2M3S") == 1 * 3600 + 2 * 60 + 3
    assert _parse_iso8601_duration("PT45M") == 45 * 60
    assert _parse_iso8601_duration("") == 0
    assert _parse_iso8601_duration("garbage") == 0


def test_happy_path_returns_mock_videos():
    out = _run(crawl_youtube(SkillInput(params={"query": "data engineering",
                                                  "max_results": 3})))
    assert out.success is True
    assert out.metadata["skill_id"] == SKILL_ID
    assert out.metadata["api_key_present"] is False
    videos = out.result["videos"]
    assert 1 <= len(videos) <= 3
    assert videos[0]["title"]


def test_empty_query_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        YouTubeRequest.model_validate({"query": ""})


def test_invalid_params_payload():
    out = _run(crawl_youtube(SkillInput(params={"query": "x",
                                                  "max_results": "ten"})))
    assert out.success is False
    assert "invalid_params" in out.error