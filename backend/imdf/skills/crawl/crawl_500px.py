"""crawl_500px — 500px photography community.

Uses the public ``500px.com`` search page (no OAuth) and falls back to
a deterministic mock when network is unreachable.
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

SKILL_ID = "skill_crawl_500px"


class FiveHundredPxPhoto(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    user: str = ""
    user_id: str = ""
    image_url: Optional[str] = None
    width: int = 0
    height: int = 0
    rating: float = 0.0
    votes_count: int = 0
    comments_count: int = 0
    times_viewed: int = 0
    taken_at: str = ""


class FiveHundredPxRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    count: int = Field(default=10, ge=1, le=50)
    sort: str = "highest_rating"


class FiveHundredPxResponse(BaseModel):
    query: str
    count: int
    photos: List[FiveHundredPxPhoto]


_MOCK_TITLES = [
    "Mountain ridge at dawn",
    "Macro: morning dew",
    "Aerial: river delta",
    "Neon at midnight",
    "Black-and-white portrait",
]


@register_offline_fixture(SKILL_ID)
def _mock_500px(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = str(query.get("query") or "general")
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": f"mock_5px_{i}",
            "name": f"{title} ({q})",
            "description": f"Mock 500px photo {i}",
            "user": {"username": f"photog_{i}", "id": str(1000 + i)},
            "image_url": [f"https://placehold.co/800x600?text=5px_{i}"],
            "width": 5000,
            "height": 3500,
            "rating": round(75.0 - i * 2.1, 2),
            "votes_count": 200 * (i + 1),
            "comments_count": 15 * (i + 1),
            "times_viewed": 5000 * (i + 1),
            "taken_at": now,
        }
        for i, title in enumerate(_MOCK_TITLES)
    ]


async def crawl_500px(input: SkillInput) -> SkillOutput:
    try:
        request = FiveHundredPxRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    url = "https://500px.com/search"
    params: Dict[str, Any] = {
        "q": request.query,
        "type": "photos",
        "sort": request.sort,
        "page": 1,
    }
    headers = {"User-Agent": "Mozilla/5.0 nanobot"}

    fetched = await fetch_or_mock(SKILL_ID, url, params=params, headers=headers)
    raw_items = fetched["items"][:request.count]
    photos = [_normalise_photo(p) for p in raw_items]
    response = FiveHundredPxResponse(
        query=request.query, count=len(photos), photos=photos,
    )
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.85 if fetched["ok"] else 0.6,
    )


def _normalise_photo(raw: Dict[str, Any]) -> FiveHundredPxPhoto:
    user = raw.get("user", {}) or {}
    image_url = raw.get("image_url")
    if isinstance(image_url, list):
        image_url = image_url[0] if image_url else None
    return FiveHundredPxPhoto(
        id=str(raw.get("id", "")),
        name=str(raw.get("name", "")),
        description=raw.get("description"),
        user=str(user.get("username", "")),
        user_id=str(user.get("id", "")),
        image_url=image_url,
        width=int(raw.get("width", 0) or 0),
        height=int(raw.get("height", 0) or 0),
        rating=float(raw.get("rating", 0.0) or 0.0),
        votes_count=int(raw.get("votes_count", 0) or 0),
        comments_count=int(raw.get("comments_count", 0) or 0),
        times_viewed=int(raw.get("times_viewed", 0) or 0),
        taken_at=str(raw.get("taken_at", "")),
    )


__all__ = ["SKILL_ID", "crawl_500px", "FiveHundredPxPhoto",
           "FiveHundredPxRequest", "FiveHundredPxResponse"]