"""Tests for crawl_dribbble."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_dribbble import (
    SKILL_ID,
    DribbbleRequest,
    crawl_dribbble,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path():
    out = _run(crawl_dribbble(SkillInput(params={"query": "icons",
                                                  "count": 3})))
    assert out.success is True
    shots = out.result["shots"]
    assert 1 <= len(shots) <= 3
    assert shots[0]["url"].startswith("https://dribbble.com/")


def test_query_required():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DribbbleRequest.model_validate({})


def test_invalid_params_payload():
    out = _run(crawl_dribbble(SkillInput(params={"query": "x",
                                                  "count": "abc"})))
    assert out.success is False