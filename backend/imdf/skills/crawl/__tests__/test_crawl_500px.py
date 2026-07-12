"""Tests for crawl_500px."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_500px import (
    SKILL_ID,
    FiveHundredPxRequest,
    crawl_500px,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path():
    out = _run(crawl_500px(SkillInput(params={"query": "aerial",
                                                 "count": 3})))
    assert out.success is True
    photos = out.result["photos"]
    assert 1 <= len(photos) <= 3
    assert photos[0]["image_url"]


def test_query_required():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FiveHundredPxRequest.model_validate({})


def test_invalid_params_payload():
    out = _run(crawl_500px(SkillInput(params={"count": "many"})))
    assert out.success is False