"""Tests for crawl_behance."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_behance import (
    SKILL_ID,
    BehanceRequest,
    crawl_behance,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path():
    out = _run(crawl_behance(SkillInput(params={"query": "branding",
                                                  "count": 3})))
    assert out.success is True
    projects = out.result["projects"]
    assert 1 <= len(projects) <= 3
    assert projects[0]["url"].startswith("https://www.behance.net")


def test_query_required():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BehanceRequest.model_validate({})


def test_invalid_params_payload():
    out = _run(crawl_behance(SkillInput(params={"count": "huge"})))
    assert out.success is False