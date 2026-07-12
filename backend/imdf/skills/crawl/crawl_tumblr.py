"""crawl_tumblr — Tumblr blog post crawler.

Uses the public Tumblr API ``v2/blog/{blog}/posts`` endpoint.  When
network is unavailable falls back to a deterministic mock.
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

SKILL_ID = "skill_crawl_tumblr"


class TumblrPost(BaseModel):
    id: str
    type: str = "text"  # text / photo / quote / link / chat / audio / video
    title: str = ""
    body: str = ""
    tags: List[str] = Field(default_factory=list)
    blog_name: str = ""
    post_url: str = ""
    timestamp: str = ""
    image_urls: List[str] = Field(default_factory=list)


class TumblrRequest(BaseModel):
    blog: str = Field(min_length=1, max_length=100)
    limit: int = Field(default=10, ge=1, le=50)
    tag: Optional[str] = None


class TumblrResponse(BaseModel):
    blog: str
    count: int
    posts: List[TumblrPost]


_MOCK_BODIES = [
    "On slowness and craft.",
    "Field notes from last weekend.",
    "A reading list for July.",
    "Why we keep shipping on Fridays.",
    "Three small refactors that paid off.",
]


@register_offline_fixture(SKILL_ID)
def _mock_tumblr(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    blog = str(query.get("blog") or "general")
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": f"mock_tm_{i}",
            "type": ["text", "photo", "quote"][i % 3],
            "title": f"Post {i}",
            "body": body,
            "tags": [blog, "mock", f"tag{i}"],
            "blog_name": blog,
            "post_url": f"https://{blog}.tumblr.com/post/{i}",
            "timestamp": now,
            "image_urls": [f"https://placehold.co/600x400?text=tm_{i}"] if i % 2 else [],
        }
        for i, body in enumerate(_MOCK_BODIES)
    ]


async def crawl_tumblr(input: SkillInput) -> SkillOutput:
    try:
        request = TumblrRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    blog = request.blog.replace(".tumblr.com", "")
    url = f"https://{blog}.tumblr.com/api/read/json"
    params: Dict[str, Any] = {"num": request.limit}
    if request.tag:
        params["tag"] = request.tag

    fetched = await fetch_or_mock(SKILL_ID, url, params=params)
    raw_items = fetched["items"][:request.limit]
    posts = [_normalise_post(p, blog) for p in raw_items]
    response = TumblrResponse(blog=blog, count=len(posts), posts=posts)
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.85 if fetched["ok"] else 0.6,
    )


def _normalise_post(raw: Dict[str, Any], blog: str) -> TumblrPost:
    images = raw.get("image_urls") or []
    return TumblrPost(
        id=str(raw.get("id", "")),
        type=str(raw.get("type", "text")),
        title=str(raw.get("title", "")),
        body=str(raw.get("body", "")),
        tags=list(raw.get("tags") or []),
        blog_name=str(raw.get("blog_name", blog)),
        post_url=str(raw.get("post_url", "")),
        timestamp=str(raw.get("timestamp", "")),
        image_urls=list(images),
    )


__all__ = ["SKILL_ID", "crawl_tumblr", "TumblrPost", "TumblrRequest",
           "TumblrResponse"]