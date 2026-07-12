"""crawl_pinterest — Pinterest pin / board crawler.

Uses the anonymous ``/resource/BaseSearchResource/get/`` endpoint when
network is reachable.  Falls back to a deterministic mock otherwise.
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

SKILL_ID = "skill_crawl_pinterest"


class PinterestPin(BaseModel):
    id: str
    title: str
    description: str = ""
    board: str = ""
    image_url: Optional[str] = None
    link: Optional[str] = None
    saves: int = 0
    created_at: str = ""


class PinterestRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    count: int = Field(default=10, ge=1, le=50)


class PinterestResponse(BaseModel):
    query: str
    count: int
    pins: List[PinterestPin]


_MOCK_TITLES = [
    "Minimalist workspace setup",
    "Living room inspiration",
    "Linen + wood interior",
    "Aesthetic flat-lay photography",
    "Modern kitchen ideas",
]


@register_offline_fixture(SKILL_ID)
def _mock_pinterest(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = str(query.get("query") or "general")
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": f"mock_pin_{i}",
            "title": f"{title} ({q})",
            "description": f"Pin {i} for {q}",
            "board": {"name": f"board_{i}"},
            "images": {"orig": {"url": f"https://placehold.co/600x800?text=pin_{i}"}},
            "link": f"https://example.com/{i}",
            "save_count": 50 * (i + 1),
            "created_at": now,
        }
        for i, title in enumerate(_MOCK_TITLES)
    ]


async def crawl_pinterest(input: SkillInput) -> SkillOutput:
    try:
        request = PinterestRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    url = "https://www.pinterest.com/resource/BaseSearchResource/get/"
    params = {"source_url": f"/search/pins/?q={request.query}",
              "data": '{"options":{"query":"' + request.query + '"}}'}
    headers = {"User-Agent": "Mozilla/5.0 nanobot"}

    fetched = await fetch_or_mock(SKILL_ID, url, params=params, headers=headers)
    raw_items = fetched["items"][:request.count]
    pins = [_normalise_pin(p) for p in raw_items]
    response = PinterestResponse(query=request.query, count=len(pins), pins=pins)
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.88 if fetched["ok"] else 0.6,
    )


def _normalise_pin(raw: Dict[str, Any]) -> PinterestPin:
    images = raw.get("images", {}) or {}
    orig = images.get("orig", {}) or {}
    board = raw.get("board", {}) or {}
    return PinterestPin(
        id=str(raw.get("id", "")),
        title=str(raw.get("title", "")),
        description=str(raw.get("description", "")),
        board=str(board.get("name", "")),
        image_url=orig.get("url") if isinstance(orig, dict) else None,
        link=raw.get("link"),
        saves=int(raw.get("save_count", 0) or 0),
        created_at=str(raw.get("created_at", "")),
    )


__all__ = ["SKILL_ID", "crawl_pinterest", "PinterestPin", "PinterestRequest",
           "PinterestResponse"]