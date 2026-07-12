"""crawl_youtube — YouTube video metadata.

Uses the public ``https://www.youtube.com/results`` search endpoint and
parses the embedded JSON.  When no ``YOUTUBE_API_KEY`` is provided we
fall back to the deterministic offline mock so the pipeline keeps
flowing without a key.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.imdf.skills.crawl._base import (
    fetch_or_mock,
    register_offline_fixture,
    to_skill_output,
)
from backend.skills.legacy import SkillInput, SkillOutput

SKILL_ID = "skill_crawl_youtube"


class YouTubeVideo(BaseModel):
    id: str
    title: str
    channel: str
    channel_id: str = ""
    duration_seconds: int = 0
    view_count: int = 0
    like_count: int = 0
    published_at: str = ""
    thumbnail: Optional[str] = None
    url: str


class YouTubeRequest(BaseModel):
    query: str = Field(min_length=1, max_length=256)
    max_results: int = Field(default=10, ge=1, le=50)


class YouTubeResponse(BaseModel):
    query: str
    count: int
    videos: List[YouTubeVideo]


_MOCK_TITLES = [
    "Building a Production ETL Pipeline in Python",
    "Vector Databases Explained in 12 Minutes",
    "How We Scale to 1M Requests/s — A Postmortem",
    "Data Engineering Roadmap 2026",
    "Prompt Engineering for Production LLM Apps",
]


@register_offline_fixture(SKILL_ID)
def _mock_youtube(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = str(query.get("query") or "general")
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": {"videoId": f"mock_vid_{i}"},
            "snippet": {
                "title": f"{title} ({q})",
                "channelTitle": f"Channel {i}",
                "channelId": f"UC_mock_{i}",
                "publishedAt": now,
                "thumbnails": {"default": {"url": f"https://i.ytimg.com/vi/mock_vid_{i}/default.jpg"}},
            },
            "contentDetails": {"duration": f"PT{i + 2}M{i * 5}S"},
            "statistics": {
                "viewCount": str(1000 * (i + 1)),
                "likeCount": str(100 * (i + 1)),
            },
        }
        for i, title in enumerate(_MOCK_TITLES)
    ]


def _parse_iso8601_duration(duration: str) -> int:
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or "")
    if not match:
        return 0
    h, m, s = (int(g) if g else 0 for g in match.groups())
    return h * 3600 + m * 60 + s


async def crawl_youtube(input: SkillInput) -> SkillOutput:
    try:
        request = YouTubeRequest.model_validate(input.params or {})
    except Exception as exc:
        return SkillOutput(
            success=False, result=None, error=f"invalid_params: {exc}",
            metadata={"skill_id": SKILL_ID},
        )

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if api_key:
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "q": request.query,
            "type": "video",
            "maxResults": request.max_results,
            "key": api_key,
        }
        headers: Dict[str, str] = {}
    else:
        url = "https://www.youtube.com/results"
        params = {"search_query": request.query}
        headers = {"User-Agent": "Mozilla/5.0 nanobot"}

    fetched = await fetch_or_mock(
        SKILL_ID, url, params=params, headers=headers,
        offline=not bool(api_key),
    )

    raw_items = fetched["items"][:request.max_results]
    videos = [_normalise_video(v) for v in raw_items]
    response = YouTubeResponse(
        query=request.query, count=len(videos), videos=videos,
    )
    return to_skill_output(
        SKILL_ID, response,
        query=request.model_dump(),
        source=fetched["source"],
        confidence=0.9 if fetched["ok"] else 0.7,
        extra_meta={"api_key_present": bool(api_key)},
    )


def _normalise_video(raw: Dict[str, Any]) -> YouTubeVideo:
    snippet = raw.get("snippet", {}) or {}
    video_id = (
        raw.get("id", {}).get("videoId") if isinstance(raw.get("id"), dict)
        else raw.get("id", "")
    )
    duration = _parse_iso8601_duration(
        (raw.get("contentDetails") or {}).get("duration", ""))
    statistics = raw.get("statistics") or {}
    thumbs = snippet.get("thumbnails", {}) or {}
    thumb = thumbs.get("default", thumbs.get("medium", thumbs.get("high", {})))
    return YouTubeVideo(
        id=str(video_id or ""),
        title=str(snippet.get("title", "")),
        channel=str(snippet.get("channelTitle", "")),
        channel_id=str(snippet.get("channelId", "")),
        duration_seconds=duration,
        view_count=int(statistics.get("viewCount", 0) or 0),
        like_count=int(statistics.get("likeCount", 0) or 0),
        published_at=str(snippet.get("publishedAt", "")),
        thumbnail=thumb.get("url") if isinstance(thumb, dict) else None,
        url=f"https://www.youtube.com/watch?v={video_id}",
    )


__all__ = ["SKILL_ID", "crawl_youtube", "YouTubeVideo", "YouTubeRequest",
           "YouTubeResponse"]