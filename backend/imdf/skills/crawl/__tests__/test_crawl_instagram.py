"""Tests for crawl_instagram."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_instagram import (
    SKILL_ID,
    InstagramRequest,
    crawl_instagram,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path():
    out = _run(crawl_instagram(SkillInput(params={"tag": "travel",
                                                     "count": 3})))
    assert out.success is True
    posts = out.result["posts"]
    assert 1 <= len(posts) <= 3
    assert posts[0]["url"].startswith("https://www.instagram.com/p/")


def test_tag_required():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        InstagramRequest.model_validate({})


def test_count_bounds():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        InstagramRequest.model_validate({"tag": "x", "count": 9999})


def test_invalid_params_returns_failure():
    out = _run(crawl_instagram(SkillInput(params={"tag": 12})))
    assert out.success is False
    assert "invalid_params" in out.error