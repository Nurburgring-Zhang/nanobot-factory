"""crawl_behance — Behance project crawler.

Uses the public Behance search endpoint; in offline mode returns a
deterministic mock that mirrors the project shape.
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

SKILL_ID = "skill_crawl_behance"


class BehanceProject(BaseModel):
    id: str
    name: str
    owner: str = ""
    owner_id: str = ""
    description: Optional[str] = None
    cover_url: Optional[str] = None
    url: str = ""
    views: int = 0
    appreciations: int = 0
    comments: int = 0
    published_at: str = ""
    fields: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class BehanceRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    count: int = Field(default=10, ge=1, le=50)


class BehanceResponse(BaseModel):
    query: str
    count: int
    projects: List[BehanceProject]


_MOCK_NAMES = [
    "Brand identity — mountain co-op",
    "Editorial layout: Issue 12",
    "Mobile app redesign",
    "Type specimen: a new serif",
    "Wayfinding signage system",
]


@register_offline_fixture(SKILL_ID)
def _mock_behance(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = str(query.get("query") or "general")
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": str(10000 + i),
            "name": f"{name} ({q})",
            "owner": {"display_name": f"studio_{i}", "id": str(1000 + i)},
            "description": f"Mock Behance project {i}",
            "covers": {"404": f"https://placehold.co/400x300?text=bh_{i}"},
            "url": f"https://www.behance.net/gallery/mock-{i}",
            "stats": {"views": 1000 * (i + 1),
                      "appreciations": 100 * (i + 1),
                      "comments": 10 * (i + 1)},
            "published_on": now,
            "fields": ["Graphic Design", "Branding"],
            "tags": [q, "design", "mock"],
        }
        for i, name in enumerate(_MOCK_NAMES)
    ]


async def crawl_behance(input: SkillInput) -> SkillOutput:
    try:
        request = BehanceRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    url = "https://www.behance.net/search/projects"
    params = {"q": request.query}
    headers = {"User-Agent": "Mozilla/5.0 nanobot"}

    fetched = await fetch_or_mock(SKILL_ID, url, params=params, headers=headers)
    raw_items = fetched["items"][:request.count]
    projects = [_normalise_project(p) for p in raw_items]
    response = BehanceResponse(
        query=request.query, count=len(projects), projects=projects,
    )
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.85 if fetched["ok"] else 0.6,
    )


def _normalise_project(raw: Dict[str, Any]) -> BehanceProject:
    owner = raw.get("owner") or {}
    covers = raw.get("covers") or {}
    cover = covers.get("404") if isinstance(covers, dict) else None
    stats = raw.get("stats") or {}
    return BehanceProject(
        id=str(raw.get("id", "")),
        name=str(raw.get("name", "")),
        owner=str(owner.get("display_name", "")),
        owner_id=str(owner.get("id", "")),
        description=raw.get("description"),
        cover_url=cover,
        url=str(raw.get("url", "")),
        views=int(stats.get("views", 0) or 0),
        appreciations=int(stats.get("appreciations", 0) or 0),
        comments=int(stats.get("comments", 0) or 0),
        published_at=str(raw.get("published_on", "")),
        fields=list(raw.get("fields") or []),
        tags=list(raw.get("tags") or []),
    )


__all__ = ["SKILL_ID", "crawl_behance", "BehanceProject",
           "BehanceRequest", "BehanceResponse"]