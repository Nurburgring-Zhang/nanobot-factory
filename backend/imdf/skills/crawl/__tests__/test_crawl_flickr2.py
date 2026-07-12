"""Tests for crawl_flickr2."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_flickr2 import (
    SKILL_ID,
    FlickrRequest,
    crawl_flickr2,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path():
    out = _run(crawl_flickr2(SkillInput(params={"query": "mountain",
                                                  "count": 3})))
    assert out.success is True
    photos = out.result["photos"]
    assert 1 <= len(photos) <= 3
    assert photos[0]["url_o"].startswith("https://")


def test_query_required():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FlickrRequest.model_validate({})


def test_count_capped_to_50():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FlickrRequest.model_validate({"query": "x", "count": 1000})


def test_invalid_params_payload():
    out = _run(crawl_flickr2(SkillInput(params={"query": "x",
                                                  "count": "abc"})))
    assert out.success is False