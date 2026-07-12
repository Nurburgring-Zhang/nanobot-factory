"""Tests for crawl_unsplash2."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_unsplash2 import (
    SKILL_ID,
    UnsplashRequest,
    crawl_unsplash2,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path():
    out = _run(crawl_unsplash2(SkillInput(params={"query": "forest",
                                                     "per_page": 3})))
    assert out.success is True
    photos = out.result["photos"]
    assert 1 <= len(photos) <= 3
    assert "regular" in photos[0]["urls"]


def test_query_required():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        UnsplashRequest.model_validate({})


def test_invalid_params_payload():
    out = _run(crawl_unsplash2(SkillInput(params={"query": "x",
                                                     "per_page": "abc"})))
    assert out.success is False