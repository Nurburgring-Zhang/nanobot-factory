"""Tests for crawl_deviantart."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_deviantart import (
    SKILL_ID,
    DeviantArtRequest,
    crawl_deviantart,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path():
    out = _run(crawl_deviantart(SkillInput(params={"query": "fantasy",
                                                     "count": 3})))
    assert out.success is True
    works = out.result["works"]
    assert 1 <= len(works) <= 3
    assert works[0]["title"]
    assert works[0]["image_url"]


def test_query_required():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DeviantArtRequest.model_validate({})


def test_invalid_params_payload():
    out = _run(crawl_deviantart(SkillInput(params={"query": "x",
                                                     "count": "abc"})))
    assert out.success is False