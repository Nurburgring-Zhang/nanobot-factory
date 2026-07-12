"""crawl_pixiv — Pixiv illustration search.

Uses the public Pixiv search endpoint.  Without login the API is
limited; we therefore always check whether
``PIXIV_PHPSESSID`` is set and otherwise return the deterministic
mock (this is the right behaviour for an offline-first pipeline).
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

SKILL_ID = "skill_crawl_pixiv"


class PixivIllust(BaseModel):
    id: str
    title: str
    author: str = ""
    author_id: str = ""
    image_urls: List[str] = Field(default_factory=list)
    page_count: int = 1
    width: int = 0
    height: int = 0
    views: int = 0
    bookmarks: int = 0
    tags: List[str] = Field(default_factory=list)
    created_at: str = ""
    url: str = ""


class PixivRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    count: int = Field(default=10, ge=1, le=30)
    mode: str = "safe"  # safe / r18


class PixivResponse(BaseModel):
    query: str
    count: int
    illusts: List[PixivIllust]


_MOCK_TITLES = [
    "Sky-blue study",
    "Original character sheet",
    "Coffee shop scene",
    "Cherry-blossom avenue",
    "Knight in rain",
]


@register_offline_fixture(SKILL_ID)
def _mock_pixiv(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = str(query.get("query") or "general")
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": str(9000 + i),
            "title": f"{title} ({q})",
            "user": {"name": f"pixiv_user_{i}", "id": str(1000 + i)},
            "image_urls": {
                "square_medium": f"https://placehold.co/200x200?text=px_{i}",
                "medium": f"https://placehold.co/600x800?text=px_{i}",
                "large": f"https://placehold.co/1200x1600?text=px_{i}",
            },
            "page_count": 1 + (i % 3),
            "width": 1200,
            "height": 1600,
            "total_view": 2000 * (i + 1),
            "total_bookmarks": 250 * (i + 1),
            "tags": [{"name": tag} for tag in [q, "pixiv", "mock"]],
            "create_date": now,
        }
        for i, title in enumerate(_MOCK_TITLES)
    ]


async def crawl_pixiv(input: SkillInput) -> SkillOutput:
    try:
        request = PixivRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    sess = os.environ.get("PIXIV_PHPSESSID")
    url = "https://www.pixiv.net/ajax/search/artworks"
    params = {"word": request.query, "mode": request.mode, "p": 1}
    headers: Dict[str, str] = {"User-Agent": "Mozilla/5.0 nanobot"}
    if sess:
        headers["Cookie"] = f"PHPSESSID={sess}"

    fetched = await fetch_or_mock(
        SKILL_ID, url, params=params, headers=headers, offline=not bool(sess),
    )
    raw_items = fetched["items"][:request.count]
    illusts = [_normalise_illust(p) for p in raw_items]
    response = PixivResponse(
        query=request.query, count=len(illusts), illusts=illusts,
    )
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.9 if fetched["ok"] else 0.6,
    )


def _normalise_illust(raw: Dict[str, Any]) -> PixivIllust:
    user = raw.get("user") or {}
    images = raw.get("image_urls") or {}
    image_urls = [v for v in (images.get("large"),
                              images.get("medium"),
                              images.get("square_medium")) if isinstance(v, str)]
    tags_raw = raw.get("tags") or []
    tags: List[str] = []
    for t in tags_raw:
        if isinstance(t, dict):
            tags.append(str(t.get("name", "")))
        elif isinstance(t, str):
            tags.append(t)
    illust_id = str(raw.get("id", ""))
    return PixivIllust(
        id=illust_id,
        title=str(raw.get("title", "")),
        author=str(user.get("name", "")),
        author_id=str(user.get("id", "")),
        image_urls=image_urls,
        page_count=int(raw.get("page_count", 1) or 1),
        width=int(raw.get("width", 0) or 0),
        height=int(raw.get("height", 0) or 0),
        views=int(raw.get("total_view", 0) or 0),
        bookmarks=int(raw.get("total_bookmarks", 0) or 0),
        tags=tags,
        created_at=str(raw.get("create_date", "")),
        url=f"https://www.pixiv.net/artworks/{illust_id}",
    )


__all__ = ["SKILL_ID", "crawl_pixiv", "PixivIllust",
           "PixivRequest", "PixivResponse"]