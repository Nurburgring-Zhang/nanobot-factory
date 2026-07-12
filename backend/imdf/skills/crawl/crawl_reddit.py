"""crawl_reddit — Reddit posts crawler.

Fetches public subreddit posts via the (anonymous) ``.json`` suffix
endpoint.  Returns a normalised list with author / score / comments /
permalink / thumbnail.  In offline mode, returns 5 deterministic mock
posts so downstream pipelines never block.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.imdf.skills.crawl._base import (
    fetch_or_mock,
    register_offline_fixture,
    to_skill_output,
)
from backend.skills.legacy import SkillInput, SkillOutput

SKILL_ID = "skill_crawl_reddit"


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RedditPost(BaseModel):
    id: str
    title: str
    author: str
    subreddit: str
    score: int = 0
    num_comments: int = 0
    url: str
    permalink: str
    thumbnail: Optional[str] = None
    created_utc: float = 0.0
    selftext: str = ""


class RedditRequest(BaseModel):
    subreddit: str = Field(default="all", description="Subreddit name (no /r/)")
    sort: str = Field(default="hot", pattern="^(hot|new|top|rising)$")
    limit: int = Field(default=10, ge=1, le=100)
    query: Optional[str] = None


class RedditResponse(BaseModel):
    subreddit: str
    sort: str
    count: int
    posts: List[RedditPost]


# ---------------------------------------------------------------------------
# Offline fixture
# ---------------------------------------------------------------------------

_MOCK_TITLES = [
    "Show HN: A tiny CLI to dedupe your screenshots",
    "I built a vector DB in 200 lines of Python",
    "Why our team switched from Postgres to SQLite (and back)",
    "Migrating 50 TB of logs to Parquet — lessons learned",
    "Open-sourcing our internal data-labeling toolkit",
]


@register_offline_fixture(SKILL_ID)
def _mock_reddit(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    subreddit = str(query.get("subreddit") or "all")
    now = datetime.now(timezone.utc).timestamp()
    return [
        {
            "id": f"t3_mock{i}",
            "title": title,
            "author": f"user_{i}",
            "subreddit": subreddit,
            "score": 100 + i * 17,
            "num_comments": 5 + i * 3,
            "url": f"https://www.reddit.com/r/{subreddit}/comments/mock{i}/",
            "permalink": f"/r/{subreddit}/comments/mock{i}/",
            "thumbnail": "https://placehold.co/120x120",
            "created_utc": now - i * 3600,
            "selftext": f"Mock post {i} for r/{subreddit}",
        }
        for i, title in enumerate(_MOCK_TITLES)
    ]


# ---------------------------------------------------------------------------
# Skill entry-point
# ---------------------------------------------------------------------------

async def crawl_reddit(input: SkillInput) -> SkillOutput:
    """Skill entry-point — extract request, fetch, wrap as SkillOutput."""
    try:
        request = RedditRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    url = f"https://www.reddit.com/r/{request.subreddit}/{request.sort}.json"
    params: Dict[str, Any] = {"limit": request.limit}
    if request.query:
        params["q"] = request.query

    fetched = await fetch_or_mock(SKILL_ID, url, params=params,
                                  headers={"User-Agent": "nanobot-factory/1.0"})

    raw_posts = fetched["items"][:request.limit]
    posts = [_normalise_post(p, request.subreddit) for p in raw_posts]
    response = RedditResponse(
        subreddit=request.subreddit,
        sort=request.sort,
        count=len(posts),
        posts=posts,
    )
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.92 if fetched["ok"] else 0.7,
        extra_meta={"live": fetched["ok"], "error": fetched.get("error", "")},
    )


def _normalise_post(raw: Dict[str, Any], fallback_sub: str) -> RedditPost:
    data = raw.get("data", raw)
    return RedditPost(
        id=str(data.get("id", "")),
        title=str(data.get("title", "")),
        author=str(data.get("author", "[deleted]")),
        subreddit=str(data.get("subreddit", fallback_sub)),
        score=int(data.get("score", 0) or 0),
        num_comments=int(data.get("num_comments", 0) or 0),
        url=str(data.get("url_overridden_by_dest",
                         data.get("url", ""))),
        permalink=str(data.get("permalink", "")),
        thumbnail=data.get("thumbnail"),
        created_utc=float(data.get("created_utc", 0.0) or 0.0),
        selftext=str(data.get("selftext", "")),
    )


__all__ = ["SKILL_ID", "crawl_reddit", "RedditPost", "RedditRequest",
           "RedditResponse"]