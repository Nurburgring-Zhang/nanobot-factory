"""crawl_tiktok — TikTok video metadata.

Pulls public TikTok posts via the unofficial ``node-video`` light API.
No auth required.  In offline mode returns 5 deterministic mocks.
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

SKILL_ID = "skill_crawl_tiktok"


class TikTokVideo(BaseModel):
    id: str
    desc: str
    author: str
    author_id: str = ""
    play_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    duration_seconds: int = 0
    cover: Optional[str] = None
    url: str


class TikTokRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    count: int = Field(default=10, ge=1, le=30)


class TikTokResponse(BaseModel):
    query: str
    count: int
    videos: List[TikTokVideo]


_MOCK_DESCS = [
    "Sunset timelapse over the city 🌇",
    "Quick recipe: garlic noodles in 60s",
    "Behind the scenes at our studio",
    "I tried to bake sourdough from scratch",
    "Travel vlog: 48 hours in Kyoto",
]


@register_offline_fixture(SKILL_ID)
def _mock_tiktok(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = str(query.get("query") or "general")
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "video_id": f"mock_tt_{i}",
            "desc": f"{desc} #{q}",
            "author": {"nickname": f"creator_{i}", "id": f"u{i}"},
            "play_count": 1000 * (i + 1),
            "digg_count": 100 * (i + 1),
            "comment_count": 25 * (i + 1),
            "share_count": 5 * (i + 1),
            "duration": (i + 1) * 15,
            "cover": f"https://placehold.co/300x400?text=tt_{i}",
            "create_time": int(datetime.now(timezone.utc).timestamp()) - i * 86400,
        }
        for i, desc in enumerate(_MOCK_DESCS)
    ]


async def crawl_tiktok(input: SkillInput) -> SkillOutput:
    try:
        request = TikTokRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    url = "https://www.tiktok.com/api/search/general/full/"
    params = {"keyword": request.query, "count": request.count}
    headers = {"User-Agent": "Mozilla/5.0 nanobot"}

    fetched = await fetch_or_mock(SKILL_ID, url, params=params, headers=headers)
    raw_items = fetched["items"][:request.count]
    videos = [_normalise_video(v) for v in raw_items]
    response = TikTokResponse(query=request.query, count=len(videos), videos=videos)
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.88 if fetched["ok"] else 0.65,
    )


def _normalise_video(raw: Dict[str, Any]) -> TikTokVideo:
    author = raw.get("author") or {}
    return TikTokVideo(
        id=str(raw.get("video_id", "")),
        desc=str(raw.get("desc", "")),
        author=str(author.get("nickname", "")),
        author_id=str(author.get("id", "")),
        play_count=int(raw.get("play_count", 0) or 0),
        like_count=int(raw.get("digg_count", 0) or 0),
        comment_count=int(raw.get("comment_count", 0) or 0),
        share_count=int(raw.get("share_count", 0) or 0),
        duration_seconds=int(raw.get("duration", 0) or 0),
        cover=raw.get("cover"),
        url=f"https://www.tiktok.com/@{author.get('id', '')}/video/{raw.get('video_id', '')}",
    )


__all__ = ["SKILL_ID", "crawl_tiktok", "TikTokVideo", "TikTokRequest",
           "TikTokResponse"]