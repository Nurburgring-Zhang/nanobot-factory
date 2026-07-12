"""crawl_unsplash2 — Unsplash keyword search.

Uses the official Unsplash REST API when ``UNSPLASH_ACCESS_KEY`` is in
the environment.  Without it (the common case in offline dev) we
return a deterministic mock that mirrors the real ``/search/photos``
response shape so downstream consumers are unaffected.
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

SKILL_ID = "skill_crawl_unsplash2"


class UnsplashPhoto(BaseModel):
    id: str
    description: Optional[str] = None
    alt_description: Optional[str] = None
    width: int = 0
    height: int = 0
    color: str = "#000000"
    urls: Dict[str, str] = Field(default_factory=dict)
    user: str = ""
    user_link: str = ""
    likes: int = 0
    downloads: int = 0
    created_at: str = ""


class UnsplashRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    per_page: int = Field(default=10, ge=1, le=30)
    orientation: Optional[str] = None  # landscape / portrait / squarish


class UnsplashResponse(BaseModel):
    query: str
    total: int
    count: int
    photos: List[UnsplashPhoto]


_MOCK_DESCS = [
    "Quiet morning in the city",
    "Forest at first light",
    "Workspace in afternoon sun",
    "Studio overhead shot",
    "Slow living",
]


@register_offline_fixture(SKILL_ID)
def _mock_unsplash(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = str(query.get("query") or "general")
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": f"mock_us_{i}",
            "description": f"{desc} ({q})",
            "alt_description": f"Mock photo {i} for {q}",
            "width": 4000,
            "height": 3000,
            "color": "#cccccc",
            "urls": {
                "raw": f"https://images.unsplash.com/mock/raw_{i}",
                "full": f"https://images.unsplash.com/mock/full_{i}",
                "regular": f"https://images.unsplash.com/mock/regular_{i}",
                "small": f"https://images.unsplash.com/mock/small_{i}",
                "thumb": f"https://images.unsplash.com/mock/thumb_{i}",
            },
            "user": {"name": f"Photographer {i}",
                     "links": {"html": f"https://unsplash.com/@mock{i}"}},
            "likes": 100 * (i + 1),
            "downloads": 50 * (i + 1),
            "created_at": now,
        }
        for i, desc in enumerate(_MOCK_DESCS)
    ]


async def crawl_unsplash2(input: SkillInput) -> SkillOutput:
    try:
        request = UnsplashRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    api_key = os.environ.get("UNSPLASH_ACCESS_KEY")
    url = "https://api.unsplash.com/search/photos"
    headers = {"Accept-Version": "v1"}
    if api_key:
        headers["Authorization"] = f"Client-ID {api_key}"
    params: Dict[str, Any] = {"query": request.query,
                              "per_page": request.per_page}
    if request.orientation:
        params["orientation"] = request.orientation

    fetched = await fetch_or_mock(
        SKILL_ID, url, params=params, headers=headers,
        offline=not bool(api_key),
    )

    raw_items = fetched["items"][:request.per_page]
    photos = [_normalise_photo(p) for p in raw_items]
    response = UnsplashResponse(
        query=request.query, total=len(photos), count=len(photos), photos=photos,
    )
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.93 if fetched["ok"] else 0.65,
    )


def _normalise_photo(raw: Dict[str, Any]) -> UnsplashPhoto:
    user = raw.get("user", {}) or {}
    return UnsplashPhoto(
        id=str(raw.get("id", "")),
        description=raw.get("description"),
        alt_description=raw.get("alt_description"),
        width=int(raw.get("width", 0) or 0),
        height=int(raw.get("height", 0) or 0),
        color=str(raw.get("color", "#000000")),
        urls=dict(raw.get("urls", {}) or {}),
        user=str(user.get("name", "")),
        user_link=str((user.get("links") or {}).get("html", "")),
        likes=int(raw.get("likes", 0) or 0),
        downloads=int(raw.get("downloads", 0) or 0),
        created_at=str(raw.get("created_at", "")),
    )


__all__ = ["SKILL_ID", "crawl_unsplash2", "UnsplashPhoto", "UnsplashRequest",
           "UnsplashResponse"]