"""Tests for crawl_artstation."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_artstation import (
    SKILL_ID,
    ArtStationRequest,
    crawl_artstation,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path():
    out = _run(crawl_artstation(SkillInput(params={"query": "concept",
                                                     "count": 3,
                                                     "sorting": "trending"})))
    assert out.success is True
    arts = out.result["artworks"]
    assert 1 <= len(arts) <= 3
    assert arts[0]["image_url"]


def test_query_required():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ArtStationRequest.model_validate({})


def test_invalid_params_payload():
    out = _run(crawl_artstation(SkillInput(params={"query": "x",
                                                     "count": "abc"})))
    assert out.success is False