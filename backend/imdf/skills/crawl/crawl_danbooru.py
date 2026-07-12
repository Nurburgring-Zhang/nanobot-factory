"""crawl_danbooru — Danbooru tag-based image search.

Uses the public Danbooru JSON API.  Falls back to a deterministic
offline mock (5 items) when network is unreachable.
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

SKILL_ID = "skill_crawl_danbooru"


class DanbooruPost(BaseModel):
    id: int
    tags: List[str] = Field(default_factory=list)
    rating: str = ""  # g / s / q / e
    score: int = 0
    fav_count: int = 0
    file_url: Optional[str] = None
    preview_url: Optional[str] = None
    width: int = 0
    height: int = 0
    file_ext: str = ""
    created_at: str = ""
    uploader: str = ""


class DanbooruRequest(BaseModel):
    tags: str = Field(default="", description="Space-separated tag query")
    limit: int = Field(default=10, ge=1, le=100)
    page: int = Field(default=1, ge=1)


class DanbooruResponse(BaseModel):
    query: str
    count: int
    posts: List[DanbooruPost]


_MOCK_TAGS_POOL = [
    "blue_hair", "1girl", "outdoors", "smile", "long_hair",
    "skirt", "twintails", "sakura", "studio", "looking_at_viewer",
]


@register_offline_fixture(SKILL_ID)
def _mock_danbooru(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    base_tags = str(query.get("tags") or "general").split()
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": 1000 + i,
            "tag_string": " ".join(base_tags + _MOCK_TAGS_POOL[i:i + 3]),
            "tag_string_general": "",
            "rating": "g",
            "score": 50 + i * 7,
            "fav_count": 10 * (i + 1),
            "file_url": f"https://danbooru.donmai.us/data/mock/sample-{i}.jpg",
            "preview_file_url": f"https://danbooru.donmai.us/data/mock/preview-{i}.jpg",
            "image_width": 1200,
            "image_height": 1600,
            "file_ext": "jpg",
            "created_at": now,
            "uploader_name": f"uploader_{i}",
        }
        for i in range(5)
    ]


async def crawl_danbooru(input: SkillInput) -> SkillOutput:
    try:
        request = DanbooruRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    auth = (
        f"{os.environ.get('DANBOORU_LOGIN', 'guest')}:"
        f"{os.environ.get('DANBOORU_API_KEY', '')}"
    )
    url = "https://danbooru.donmai.us/posts.json"
    params = {"tags": request.tags, "limit": request.limit, "page": request.page}
    headers = {"User-Agent": "nanobot/1.0"}
    if auth.endswith(":"):
        # No key → don't bother with auth header
        auth = ""
    if auth:
        import base64
        headers["Authorization"] = "Basic " + base64.b64encode(
            auth.encode()).decode()

    fetched = await fetch_or_mock(SKILL_ID, url, params=params, headers=headers)
    raw_items = fetched["items"][:request.limit]
    posts = [_normalise_post(p) for p in raw_items]
    response = DanbooruResponse(
        query=request.tags, count=len(posts), posts=posts,
    )
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.9 if fetched["ok"] else 0.6,
    )


def _normalise_post(raw: Dict[str, Any]) -> DanbooruPost:
    tags_string = str(raw.get("tag_string", ""))
    return DanbooruPost(
        id=int(raw.get("id", 0) or 0),
        tags=tags_string.split(),
        rating=str(raw.get("rating", "")),
        score=int(raw.get("score", 0) or 0),
        fav_count=int(raw.get("fav_count", 0) or 0),
        file_url=raw.get("file_url"),
        preview_url=raw.get("preview_file_url"),
        width=int(raw.get("image_width", 0) or 0),
        height=int(raw.get("image_height", 0) or 0),
        file_ext=str(raw.get("file_ext", "")),
        created_at=str(raw.get("created_at", "")),
        uploader=str(raw.get("uploader_name", "")),
    )


__all__ = ["SKILL_ID", "crawl_danbooru", "DanbooruPost",
           "DanbooruRequest", "DanbooruResponse"]