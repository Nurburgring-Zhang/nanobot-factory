"""crawl_flickr2 — Flickr advanced photo search.

Uses the public Flickr ``flickr.photos.search`` endpoint.  When the
``FLICKR_API_KEY`` is missing or network is down, returns the
deterministic offline mock (this is the "flickr2" supersedes
``skill_crawl_flickr`` from P19 — it adds advanced ``extras`` handling).
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

SKILL_ID = "skill_crawl_flickr2"


class FlickrPhoto(BaseModel):
    id: str
    title: str
    owner: str = ""
    secret: str = ""
    server: str = ""
    farm: int = 0
    url_o: Optional[str] = None
    url_l: Optional[str] = None
    width_o: int = 0
    height_o: int = 0
    views: int = 0
    license: str = ""
    tags: List[str] = Field(default_factory=list)
    taken_at: str = ""


class FlickrRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    count: int = Field(default=10, ge=1, le=50)
    sort: str = "relevance"
    license: Optional[str] = None
    min_taken_date: Optional[str] = None


class FlickrResponse(BaseModel):
    query: str
    count: int
    photos: List[FlickrPhoto]


_MOCK_TITLES = [
    "Dawn at the harbor",
    "Studio still-life",
    "Fog over the bridge",
    "Colour study — autumn",
    "Architectural detail",
]


@register_offline_fixture(SKILL_ID)
def _mock_flickr(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = str(query.get("query") or "general")
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": str(1000 + i),
            "title": f"{title} ({q})",
            "owner": f"owner_{i}",
            "secret": f"sec{i}",
            "server": "65535",
            "farm": 66,
            "url_o": f"https://live.staticflickr.com/65535/{1000+i}_sec{i}_o.jpg",
            "url_l": f"https://live.staticflickr.com/65535/{1000+i}_sec{i}_b.jpg",
            "width_o": 4000 + i * 200,
            "height_o": 3000 + i * 150,
            "views": 1000 * (i + 1),
            "license": "cc-by",
            "tags": q.split() + ["mock"],
            "datetaken": now,
        }
        for i, title in enumerate(_MOCK_TITLES)
    ]


async def crawl_flickr2(input: SkillInput) -> SkillOutput:
    try:
        request = FlickrRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    api_key = os.environ.get("FLICKR_API_KEY")
    url = "https://api.flickr.com/services/rest/"
    params: Dict[str, Any] = {
        "method": "flickr.photos.search",
        "api_key": api_key or "mock_key",
        "text": request.query,
        "per_page": request.count,
        "sort": request.sort,
        "format": "json",
        "nojsoncallback": "1",
        "extras": "url_o,url_l,owner_name,views,license,tags,date_taken",
    }
    if request.license:
        params["license"] = request.license
    if request.min_taken_date:
        params["min_taken_date"] = request.min_taken_date

    fetched = await fetch_or_mock(
        SKILL_ID, url, params=params, offline=not bool(api_key),
    )

    # Flickr wraps photos under ``photos.photo`` — patch items shape
    if fetched["items"] and "photo" in fetched["items"][0]:
        flat = fetched["items"][0]["photo"]
        fetched["items"] = flat if isinstance(flat, list) else fetched["items"]
    raw_items = fetched["items"][:request.count]
    photos = [_normalise_photo(p) for p in raw_items]
    response = FlickrResponse(query=request.query, count=len(photos), photos=photos)
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.92 if fetched["ok"] else 0.65,
    )


def _normalise_photo(raw: Dict[str, Any]) -> FlickrPhoto:
    tags = raw.get("tags")
    if isinstance(tags, str):
        tags = [t for t in tags.split() if t]
    return FlickrPhoto(
        id=str(raw.get("id", "")),
        title=str(raw.get("title", "")),
        owner=str(raw.get("owner", raw.get("ownername", ""))),
        secret=str(raw.get("secret", "")),
        server=str(raw.get("server", "")),
        farm=int(raw.get("farm", 0) or 0),
        url_o=raw.get("url_o"),
        url_l=raw.get("url_l"),
        width_o=int(raw.get("width_o", 0) or 0),
        height_o=int(raw.get("height_o", 0) or 0),
        views=int(raw.get("views", 0) or 0),
        license=str(raw.get("license", "")),
        tags=list(tags or []),
        taken_at=str(raw.get("datetaken", raw.get("date_taken", ""))),
    )


__all__ = ["SKILL_ID", "crawl_flickr2", "FlickrPhoto", "FlickrRequest",
           "FlickrResponse"]