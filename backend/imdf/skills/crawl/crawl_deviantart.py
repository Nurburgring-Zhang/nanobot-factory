"""crawl_deviantart — DeviantArt artwork crawler.

Uses the public search endpoint.  When network is down falls back to a
deterministic offline mock (5 items).
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

SKILL_ID = "skill_crawl_deviantart"


class DeviantArtWork(BaseModel):
    id: str
    title: str
    author: str = ""
    author_url: str = ""
    image_url: Optional[str] = None
    thumb_url: Optional[str] = None
    category: str = ""
    views: int = 0
    favourites: int = 0
    comments: int = 0
    published_at: str = ""
    url: str = ""
    tags: List[str] = Field(default_factory=list)


class DeviantArtRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    count: int = Field(default=10, ge=1, le=50)


class DeviantArtResponse(BaseModel):
    query: str
    count: int
    works: List[DeviantArtWork]


_MOCK_TITLES = [
    "Concept art: forest temple",
    "Portrait study",
    "Speed paint — ruined castle",
    "Character sheet, hero",
    "Environment thumbnail",
]


@register_offline_fixture(SKILL_ID)
def _mock_deviantart(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = str(query.get("query") or "general")
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": f"mock_da_{i}",
            "title": f"{title} ({q})",
            "author": {"username": f"artist_{i}"},
            "category": "digitalart",
            "stats": {"views": 500 * (i + 1),
                      "favourites": 80 * (i + 1),
                      "comments": 12 * (i + 1)},
            "content": {"src": f"https://placehold.co/800x1000?text=da_{i}",
                        "thumbnail": {"src": f"https://placehold.co/200x250?text=da_{i}"}},
            "published_time": now,
            "url": f"https://www.deviantart.com/art/mock-{i}",
            "tags": [{"tag_name": tag} for tag in [q, "art", "mock"]],
        }
        for i, title in enumerate(_MOCK_TITLES)
    ]


async def crawl_deviantart(input: SkillInput) -> SkillOutput:
    try:
        request = DeviantArtRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    url = "https://www.deviantart.com/search/artists"
    params = {"q": request.query}
    headers = {"User-Agent": "Mozilla/5.0 nanobot"}

    fetched = await fetch_or_mock(SKILL_ID, url, params=params, headers=headers)
    raw_items = fetched["items"][:request.count]
    works = [_normalise_work(p) for p in raw_items]
    response = DeviantArtResponse(
        query=request.query, count=len(works), works=works,
    )
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.85 if fetched["ok"] else 0.6,
    )


def _normalise_work(raw: Dict[str, Any]) -> DeviantArtWork:
    author = raw.get("author") or {}
    content = raw.get("content") or {}
    thumb = content.get("thumbnail") if isinstance(content, dict) else None
    stats = raw.get("stats", {}) or {}
    tags_raw = raw.get("tags") or []
    tags: List[str] = []
    for t in tags_raw:
        if isinstance(t, dict):
            tags.append(str(t.get("tag_name", "")))
        elif isinstance(t, str):
            tags.append(t)
    return DeviantArtWork(
        id=str(raw.get("id", "")),
        title=str(raw.get("title", "")),
        author=str(author.get("username", "")),
        author_url=str(author.get("usericon", "")),
        image_url=str(content.get("src", "")) if isinstance(content, dict) else None,
        thumb_url=str(thumb.get("src", "")) if isinstance(thumb, dict) else None,
        category=str(raw.get("category", "")),
        views=int(stats.get("views", 0) or 0),
        favourites=int(stats.get("favourites", 0) or 0),
        comments=int(stats.get("comments", 0) or 0),
        published_at=str(raw.get("published_time", "")),
        url=str(raw.get("url", "")),
        tags=tags,
    )


__all__ = ["SKILL_ID", "crawl_deviantart", "DeviantArtWork",
           "DeviantArtRequest", "DeviantArtResponse"]