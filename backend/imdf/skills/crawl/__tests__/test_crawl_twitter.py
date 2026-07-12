"""Tests for crawl_twitter."""
from __future__ import annotations

import asyncio

import pytest

from backend.imdf.skills.crawl.crawl_twitter import (
    SKILL_ID,
    TwitterRequest,
    crawl_twitter,
)
from backend.skills.legacy import SkillInput


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path_returns_mock_tweets():
    """Default request returns >=1 mocked tweet with the query tag."""
    out = _run(crawl_twitter(SkillInput(params={"query": "python"})))
    assert out.success is True
    assert out.metadata["skill_id"] == SKILL_ID
    assert out.metadata["bearer_present"] is False
    assert out.metadata["source"] == "offline_mock"
    tweets = out.result["tweets"]
    assert len(tweets) >= 1
    assert "#python" in tweets[0]["text"]


def test_missing_query_fails():
    """Pydantic enforces ``min_length=1`` on the query string."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TwitterRequest.model_validate({"query": ""})


def test_max_results_bounds():
    """max_results > 100 must raise ValidationError."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TwitterRequest.model_validate({"query": "x", "max_results": 9999})


def test_invalid_params_payload_returns_failure():
    out = _run(crawl_twitter(SkillInput(params={"query": 12345})))
    assert out.success is False
    assert "invalid_params" in out.error