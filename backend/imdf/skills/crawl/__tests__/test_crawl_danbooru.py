"""Tests for crawl_danbooru."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_danbooru import (
    SKILL_ID,
    DanbooruRequest,
    crawl_danbooru,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path():
    out = _run(crawl_danbooru(SkillInput(params={"tags": "blue_hair 1girl",
                                                   "limit": 3})))
    assert out.success is True
    posts = out.result["posts"]
    assert 1 <= len(posts) <= 3
    assert isinstance(posts[0]["tags"], list)
    assert posts[0]["file_url"]


def test_default_no_tags():
    """Empty tags string is allowed."""
    req = DanbooruRequest.model_validate({})
    assert req.tags == ""
    assert req.limit == 10


def test_limit_capped_to_100():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DanbooruRequest.model_validate({"limit": 1000})


def test_invalid_params_payload():
    out = _run(crawl_danbooru(SkillInput(params={"limit": "abc"})))
    assert out.success is False