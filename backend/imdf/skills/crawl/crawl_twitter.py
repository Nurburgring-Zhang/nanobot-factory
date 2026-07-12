"""crawl_twitter — Twitter/X tweet crawler (mock-first).

Live scraping of Twitter requires OAuth1 bearer tokens which we don't
have in offline mode; this skill is wired so that as soon as a
``TWITTER_BEARER_TOKEN`` env var is present, the live ``/2/tweets/search/recent``
endpoint is called.  Without a token we always return 5 deterministic
mock tweets.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.imdf.skills.crawl._base import (
    fetch_or_mock,
    register_offline_fixture,
    to_skill_output,
)
from backend.skills.legacy import SkillInput, SkillOutput

SKILL_ID = "skill_crawl_twitter"


class TwitterTweet(BaseModel):
    id: str
    text: str
    author_id: str
    author_username: str
    created_at: str
    lang: Optional[str] = None
    like_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0


class TwitterRequest(BaseModel):
    query: str = Field(min_length=1, max_length=512)
    max_results: int = Field(default=10, ge=1, le=100)
    lang: Optional[str] = None


class TwitterResponse(BaseModel):
    query: str
    count: int
    tweets: List[TwitterTweet]


_MOCK_TWEETS = [
    "Just shipped a new data pipeline — 5x faster than last week.",
    "Hot take: SQLite is the most underrated production database.",
    "Working on a crawl skill for Twitter. Almost done.",
    "Anyone else using httpx async client for parallel fetching?",
    "Public datasets > scraped data, every time.",
]


@register_offline_fixture(SKILL_ID)
def _mock_twitter(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = str(query.get("query") or "general")
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": f"mock_tweet_{i}",
            "text": f"{text}  #{q.replace(' ', '_')}",
            "author_id": f"user_{i}",
            "author_username": f"user_{i}",
            "created_at": now,
            "lang": "en",
            "like_count": 12 + i * 3,
            "retweet_count": 2 + i,
            "reply_count": 1 + i,
        }
        for i, text in enumerate(_MOCK_TWEETS)
    ]


async def crawl_twitter(input: SkillInput) -> SkillOutput:
    try:
        request = TwitterRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    bearer = os.environ.get("TWITTER_BEARER_TOKEN")
    url = "https://api.twitter.com/2/tweets/search/recent"
    params: Dict[str, Any] = {
        "query": request.query,
        "max_results": min(request.max_results, 100),
    }
    if request.lang:
        params["lang"] = request.lang

    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    fetched = await fetch_or_mock(
        SKILL_ID, url, params=params,
        headers=headers or {"User-Agent": "nanobot/1.0"},
        offline=not bool(bearer),
    )

    raw_tweets = fetched["items"][:request.max_results]
    tweets = [_normalise_tweet(t) for t in raw_tweets]
    response = TwitterResponse(
        query=request.query,
        count=len(tweets),
        tweets=tweets,
    )
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.95 if fetched["ok"] else 0.6,
        extra_meta={"live": fetched["ok"], "bearer_present": bool(bearer)},
    )


def _normalise_tweet(raw: Dict[str, Any]) -> TwitterTweet:
    return TwitterTweet(
        id=str(raw.get("id", "")),
        text=str(raw.get("text", "")),
        author_id=str(raw.get("author_id", "")),
        author_username=str(raw.get("author_username",
                                    raw.get("author_id", ""))),
        created_at=str(raw.get("created_at", "")),
        lang=raw.get("lang"),
        like_count=int(raw.get("like_count", raw.get("public_metrics", {}).get("like_count", 0)) or 0),
        retweet_count=int(raw.get("retweet_count",
                                  raw.get("public_metrics", {}).get("retweet_count", 0)) or 0),
        reply_count=int(raw.get("reply_count",
                                raw.get("public_metrics", {}).get("reply_count", 0)) or 0),
    )


__all__ = ["SKILL_ID", "crawl_twitter", "TwitterTweet", "TwitterRequest",
           "TwitterResponse"]