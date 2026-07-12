"""Tests for crawl_gelbooru."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_gelbooru import (
    SKILL_ID,
    GelbooruRequest,
    crawl_gelbooru,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path():
    out = _run(crawl_gelbooru(SkillInput(params={"tags": "1girl smile",
                                                   "limit": 3})))
    assert out.success is True
    posts = out.result["posts"]
    assert 1 <= len(posts) <= 3
    assert isinstance(posts[0]["tags"], list)


def test_default_request():
    req = GelbooruRequest.model_validate({})
    assert req.tags == ""
    assert req.limit == 10


def test_limit_bounds():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GelbooruRequest.model_validate({"limit": 5000})


def test_invalid_params_payload():
    out = _run(crawl_gelbooru(SkillInput(params={"limit": "abc"})))
    assert out.success is False