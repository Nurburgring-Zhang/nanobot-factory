"""crawl_artstation — ArtStation art portfolio crawler.

Uses the public ArtStation projects search endpoint.  Falls back to a
deterministic mock when the network is unreachable.
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

SKILL_ID = "skill_crawl_artstation"


class ArtStationArtwork(BaseModel):
    id: str
    title: str
    user: str = ""
    user_id: str = ""
    description: Optional[str] = None
    image_url: Optional[str] = None
    square_url: Optional[str] = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    published_at: str = ""
    url: str = ""
    tags: List[str] = Field(default_factory=list)
    medium: str = ""


class ArtStationRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    count: int = Field(default=10, ge=1, le=50)
    sorting: str = "trending"


class ArtStationResponse(BaseModel):
    query: str
    count: int
    artworks: List[ArtStationArtwork]


_MOCK_TITLES = [
    "Concept: sky fortress",
    "Character — silver knight",
    "Environment: alien jungle",
    "Speed sculpt — demon",
    "Hard-surface mech",
]


@register_offline_fixture(SKILL_ID)
def _mock_artstation(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = str(query.get("query") or "general")
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": str(1000 + i),
            "title": f"{title} ({q})",
            "user": {"full_name": f"artist_{i}", "id": str(i)},
            "description": f"Mock ArtStation art {i}",
            "assets": [{"image_url": f"https://placehold.co/1200x800?text=as_{i}",
                        "asset_type": "image"}],
            "assets_count": 1,
            "views_count": 1000 * (i + 1),
            "likes_count": 100 * (i + 1),
            "comments_count": 15 * (i + 1),
            "created_at": now,
            "url": f"https://www.artstation.com/artwork/mock-{i}",
            "tags": [{"name": tag} for tag in [q, "art", "mock"]],
            "medium": {"name": "Digital"},
        }
        for i, title in enumerate(_MOCK_TITLES)
    ]


async def crawl_artstation(input: SkillInput) -> SkillOutput:
    try:
        request = ArtStationRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    url = "https://www.artstation.com/projects.json"
    params: Dict[str, Any] = {"q": request.query, "sorting": request.sorting}
    headers = {"User-Agent": "Mozilla/5.0 nanobot"}

    fetched = await fetch_or_mock(SKILL_ID, url, params=params, headers=headers)
    raw_items = fetched["items"][:request.count]
    artworks = [_normalise_art(p) for p in raw_items]
    response = ArtStationResponse(
        query=request.query, count=len(artworks), artworks=artworks,
    )
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.88 if fetched["ok"] else 0.6,
    )


def _normalise_art(raw: Dict[str, Any]) -> ArtStationArtwork:
    user = raw.get("user") or {}
    assets = raw.get("assets") or []
    image_url = None
    square_url = None
    if isinstance(assets, list) and assets:
        first = assets[0] or {}
        image_url = first.get("image_url")
    tags_raw = raw.get("tags") or []
    tags: List[str] = []
    for t in tags_raw:
        if isinstance(t, dict):
            tags.append(str(t.get("name", "")))
        elif isinstance(t, str):
            tags.append(t)
    medium = raw.get("medium") or {}
    return ArtStationArtwork(
        id=str(raw.get("id", "")),
        title=str(raw.get("title", "")),
        user=str(user.get("full_name", "")),
        user_id=str(user.get("id", "")),
        description=raw.get("description"),
        image_url=image_url,
        square_url=square_url,
        views=int(raw.get("views_count", 0) or 0),
        likes=int(raw.get("likes_count", 0) or 0),
        comments=int(raw.get("comments_count", 0) or 0),
        published_at=str(raw.get("created_at", "")),
        url=str(raw.get("url", "")),
        tags=tags,
        medium=str(medium.get("name", "") if isinstance(medium, dict) else medium),
    )


__all__ = ["SKILL_ID", "crawl_artstation", "ArtStationArtwork",
           "ArtStationRequest", "ArtStationResponse"]