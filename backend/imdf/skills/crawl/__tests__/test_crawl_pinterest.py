"""Tests for crawl_pinterest."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_pinterest import (
    SKILL_ID,
    PinterestRequest,
    crawl_pinterest,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path():
    out = _run(crawl_pinterest(SkillInput(params={"query": "interior",
                                                     "count": 3})))
    assert out.success is True
    pins = out.result["pins"]
    assert 1 <= len(pins) <= 3
    assert pins[0]["image_url"]


def test_query_required():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PinterestRequest.model_validate({})


def test_invalid_params_payload():
    out = _run(crawl_pinterest(SkillInput(params={"query": "x",
                                                     "count": "huge"})))
    assert out.success is False