"""crawl_gelbooru — Gelbooru tag-based image search.

Uses the public Gelbooru JSON API.  Falls back to a deterministic
offline mock when network is unreachable.
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

SKILL_ID = "skill_crawl_gelbooru"


class GelbooruPost(BaseModel):
    id: int
    tags: List[str] = Field(default_factory=list)
    rating: str = ""
    score: int = 0
    file_url: Optional[str] = None
    preview_url: Optional[str] = None
    width: int = 0
    height: int = 0
    file_ext: str = ""
    created_at: str = ""
    owner: str = ""


class GelbooruRequest(BaseModel):
    tags: str = Field(default="", description="Space-separated tag query")
    limit: int = Field(default=10, ge=1, le=100)
    page: int = Field(default=1, ge=1)


class GelbooruResponse(BaseModel):
    query: str
    count: int
    posts: List[GelbooruPost]


_MOCK_TAGS_POOL = [
    "sky", "outdoors", "day", "1girl", "smile",
    "blush", "long_hair", "white_shirt", "grass", "tree",
]


@register_offline_fixture(SKILL_ID)
def _mock_gelbooru(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    base_tags = str(query.get("tags") or "general").split()
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": 2000 + i,
            "tags": " ".join(base_tags + _MOCK_TAGS_POOL[i:i + 3]),
            "rating": "safe",
            "score": 30 + i * 4,
            "file_url": f"https://gelbooru.com/images/{2000+i}/{2000+i}.jpg",
            "preview_url": f"https://gelbooru.com/thumbnails/{2000+i}/thumb_{2000+i}.jpg",
            "width": 1600,
            "height": 1200,
            "image": f"sample-{i}.jpg",
            "created_at": now,
            "owner": f"owner_{i}",
        }
        for i in range(5)
    ]


async def crawl_gelbooru(input: SkillInput) -> SkillOutput:
    try:
        request = GelbooruRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    api_key = os.environ.get("GELBOORU_API_KEY")
    user_id = os.environ.get("GELBOORU_USER_ID", "")
    url = "https://gelbooru.com/index.php"
    params: Dict[str, Any] = {
        "page": "dapi",
        "s": "post",
        "q": "index",
        "json": "1",
        "tags": request.tags,
        "limit": request.limit,
        "pid": request.page,
    }
    if api_key and user_id:
        params["api_key"] = api_key
        params["user_id"] = user_id

    fetched = await fetch_or_mock(SKILL_ID, url, params=params)
    raw_items = fetched["items"][:request.limit]
    posts = [_normalise_post(p) for p in raw_items]
    response = GelbooruResponse(
        query=request.tags, count=len(posts), posts=posts,
    )
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.85 if fetched["ok"] else 0.6,
    )


def _normalise_post(raw: Dict[str, Any]) -> GelbooruPost:
    tags = raw.get("tags", "")
    if isinstance(tags, str):
        tags = tags.split()
    return GelbooruPost(
        id=int(raw.get("id", 0) or 0),
        tags=list(tags),
        rating=str(raw.get("rating", "")),
        score=int(raw.get("score", 0) or 0),
        file_url=raw.get("file_url"),
        preview_url=raw.get("preview_url"),
        width=int(raw.get("width", 0) or 0),
        height=int(raw.get("height", 0) or 0),
        file_ext=str(raw.get("image", "") or "").rsplit(".", 1)[-1] if raw.get("image") else "",
        created_at=str(raw.get("created_at", "")),
        owner=str(raw.get("owner", "")),
    )


__all__ = ["SKILL_ID", "crawl_gelbooru", "GelbooruPost",
           "GelbooruRequest", "GelbooruResponse"]