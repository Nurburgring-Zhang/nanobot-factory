"""Tests for crawl_tumblr."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_tumblr import (
    SKILL_ID,
    TumblrRequest,
    crawl_tumblr,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path():
    out = _run(crawl_tumblr(SkillInput(params={"blog": "staff",
                                                 "limit": 5})))
    assert out.success is True
    posts = out.result["posts"]
    assert 1 <= len(posts) <= 5
    assert posts[0]["post_url"].startswith("https://")


def test_blog_required():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TumblrRequest.model_validate({})


def test_invalid_params_payload():
    out = _run(crawl_tumblr(SkillInput(params={"blog": 12})))
    assert out.success is False