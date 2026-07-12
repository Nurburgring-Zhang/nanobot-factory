"""Tests for crawl_reddit."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_reddit import (
    SKILL_ID,
    RedditRequest,
    RedditResponse,
    crawl_reddit,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path_returns_offline_mock():
    """Default subreddit='all' returns >=1 post from the mock fixture."""
    out = _run(crawl_reddit(SkillInput(params={"subreddit": "all",
                                                  "sort": "hot",
                                                  "limit": 5})))
    assert out.success is True
    assert out.metadata["skill_id"] == SKILL_ID
    assert out.metadata["source"] == "offline_mock"
    response = RedditResponse.model_validate(out.result)
    assert response.count >= 1
    assert len(response.posts) <= 5


def test_validated_request_default_values():
    """Pydantic fills in defaults when params is empty dict."""
    req = RedditRequest.model_validate({})
    assert req.subreddit == "all"
    assert req.sort == "hot"
    assert req.limit == 10


def test_invalid_sort_rejected():
    """Pydantic regex pattern ``^(hot|new|top|rising)$`` rejects other values."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RedditRequest.model_validate({"sort": "garbage"})


def test_invalid_params_return_failure():
    """Passing non-dict params triggers an invalid_params failure."""
    out = _run(crawl_reddit(SkillInput(params={"limit": "not-a-number"})))
    assert out.success is False
    assert "invalid_params" in out.error


def test_limit_capped():
    """limit=200 should be clamped to <=100 by Pydantic."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RedditRequest.model_validate({"limit": 200})