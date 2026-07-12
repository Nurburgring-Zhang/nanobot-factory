"""crawl_instagram — Instagram public posts.

Anonymous public scraping (without login) is brittle; this skill falls
back to a mock in offline mode and only attempts the live endpoint
when ``INSTAGRAM_SESSION_ID`` is in the environment.
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

SKILL_ID = "skill_crawl_instagram"


class InstagramPost(BaseModel):
    id: str
    shortcode: str
    caption: str
    author: str
    like_count: int = 0
    comment_count: int = 0
    media_type: str = "image"  # image / video / carousel
    thumbnail: Optional[str] = None
    taken_at: str = ""
    url: str


class InstagramRequest(BaseModel):
    tag: str = Field(min_length=1, max_length=100)
    count: int = Field(default=10, ge=1, le=30)


class InstagramResponse(BaseModel):
    tag: str
    count: int
    posts: List[InstagramPost]


_MOCK_CAPTIONS = [
    "Morning light ☕",
    "First hike of the season",
    "Studio vibes",
    "Tested a new lens today",
    "Quick weekend project",
]


@register_offline_fixture(SKILL_ID)
def _mock_instagram(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    tag = str(query.get("tag") or "general")
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": f"mock_ig_{i}",
            "shortcode": f"MockSC{i}",
            "caption": f"{cap}  #{tag}",
            "owner": {"username": f"creator_{i}"},
            "like_count": 200 * (i + 1),
            "comment_count": 20 * (i + 1),
            "media_type": i % 2 and "video" or "image",
            "thumbnail_src": f"https://placehold.co/400x400?text=ig_{i}",
            "taken_at": now,
        }
        for i, cap in enumerate(_MOCK_CAPTIONS)
    ]


async def crawl_instagram(input: SkillInput) -> SkillOutput:
    try:
        request = InstagramRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    session = os.environ.get("INSTAGRAM_SESSION_ID")
    url = f"https://www.instagram.com/explore/tags/{request.tag}/"
    headers = {"User-Agent": "Mozilla/5.0 nanobot"}
    if session:
        headers["Cookie"] = f"sessionid={session}"

    fetched = await fetch_or_mock(
        SKILL_ID, url, headers=headers, offline=not bool(session),
    )
    raw_items = fetched["items"][:request.count]
    posts = [_normalise_post(p) for p in raw_items]
    response = InstagramResponse(tag=request.tag, count=len(posts), posts=posts)
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.85 if fetched["ok"] else 0.6,
    )


def _normalise_post(raw: Dict[str, Any]) -> InstagramPost:
    owner = raw.get("owner") or {}
    shortcode = str(raw.get("shortcode", ""))
    media_type = str(raw.get("media_type", "image"))
    return InstagramPost(
        id=str(raw.get("id", "")),
        shortcode=shortcode,
        caption=str(raw.get("caption", "")),
        author=str(owner.get("username", "")),
        like_count=int(raw.get("like_count", 0) or 0),
        comment_count=int(raw.get("comment_count", 0) or 0),
        media_type=media_type,
        thumbnail=raw.get("thumbnail_src"),
        taken_at=str(raw.get("taken_at", "")),
        url=f"https://www.instagram.com/p/{shortcode}/",
    )


__all__ = ["SKILL_ID", "crawl_instagram", "InstagramPost", "InstagramRequest",
           "InstagramResponse"]