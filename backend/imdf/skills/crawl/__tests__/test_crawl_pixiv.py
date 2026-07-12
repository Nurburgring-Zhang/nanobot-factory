"""Tests for crawl_pixiv."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_pixiv import (
    SKILL_ID,
    PixivRequest,
    crawl_pixiv,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path():
    out = _run(crawl_pixiv(SkillInput(params={"query": "anime",
                                                 "count": 3})))
    assert out.success is True
    illusts = out.result["illusts"]
    assert 1 <= len(illusts) <= 3
    assert illusts[0]["url"].startswith("https://www.pixiv.net/artworks/")


def test_query_required():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PixivRequest.model_validate({})


def test_invalid_params_payload():
    out = _run(crawl_pixiv(SkillInput(params={"query": "x",
                                                 "count": "huge"})))
    assert out.success is False