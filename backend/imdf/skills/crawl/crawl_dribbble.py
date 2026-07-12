"""crawl_dribbble — Dribbble design shots.

Pulls public shots from the Dribbble search endpoint; falls back to a
deterministic offline mock when the network is unreachable.
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

SKILL_ID = "skill_crawl_dribbble"


class DribbbleShot(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    author: str = ""
    author_url: str = ""
    image_url: Optional[str] = None
    width: int = 0
    height: int = 0
    views_count: int = 0
    likes_count: int = 0
    comments_count: int = 0
    published_at: str = ""
    url: str = ""
    tags: List[str] = Field(default_factory=list)


class DribbbleRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    count: int = Field(default=10, ge=1, le=50)


class DribbbleResponse(BaseModel):
    query: str
    count: int
    shots: List[DribbbleShot]


_MOCK_TITLES = [
    "Onboarding flow — fintech",
    "Icon set: 120 line icons",
    "Dashboard concept",
    "Mobile checkout redesign",
    "Brand: a tea label",
]


@register_offline_fixture(SKILL_ID)
def _mock_dribbble(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = str(query.get("query") or "general")
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": str(1000 + i),
            "title": f"{title} ({q})",
            "description": f"Mock shot {i}",
            "user": {"username": f"designer_{i}",
                     "html_url": f"https://dribbble.com/designer_{i}"},
            "images": {"hidpi": f"https://placehold.co/800x600?text=db_{i}"},
            "width": 800,
            "height": 600,
            "views_count": 800 * (i + 1),
            "likes_count": 80 * (i + 1),
            "comments_count": 10 * (i + 1),
            "published_at": now,
            "html_url": f"https://dribbble.com/shots/mock-{i}",
            "tags": [q, "design", "mock"],
        }
        for i, title in enumerate(_MOCK_TITLES)
    ]


async def crawl_dribbble(input: SkillInput) -> SkillOutput:
    try:
        request = DribbbleRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    url = "https://dribbble.com/search"
    params = {"q": request.query}
    headers = {"User-Agent": "Mozilla/5.0 nanobot"}

    fetched = await fetch_or_mock(SKILL_ID, url, params=params, headers=headers)
    raw_items = fetched["items"][:request.count]
    shots = [_normalise_shot(p) for p in raw_items]
    response = DribbbleResponse(
        query=request.query, count=len(shots), shots=shots,
    )
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.85 if fetched["ok"] else 0.6,
    )


def _normalise_shot(raw: Dict[str, Any]) -> DribbbleShot:
    user = raw.get("user") or {}
    images = raw.get("images") or {}
    image_url = images.get("hidpi") or images.get("normal")
    return DribbbleShot(
        id=str(raw.get("id", "")),
        title=str(raw.get("title", "")),
        description=raw.get("description"),
        author=str(user.get("username", "")),
        author_url=str(user.get("html_url", "")),
        image_url=image_url if isinstance(image_url, str) else None,
        width=int(raw.get("width", 0) or 0),
        height=int(raw.get("height", 0) or 0),
        views_count=int(raw.get("views_count", 0) or 0),
        likes_count=int(raw.get("likes_count", 0) or 0),
        comments_count=int(raw.get("comments_count", 0) or 0),
        published_at=str(raw.get("published_at", "")),
        url=str(raw.get("html_url", "")),
        tags=list(raw.get("tags") or []),
    )


__all__ = ["SKILL_ID", "crawl_dribbble", "DribbbleShot",
           "DribbbleRequest", "DribbbleResponse"]