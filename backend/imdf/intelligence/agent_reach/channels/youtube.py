"""V5 第32章 — YouTube channel: YouTubeDL (mock — deterministic video metadata)."""
from __future__ import annotations

import hashlib
import time
from typing import Any

from imdf.intelligence.agent_reach.schemas import FetchResult


class YouTubeDL:
    """Mock YouTube downloader — returns deterministic video metadata."""

    def __init__(self):
        pass

    async def fetch(self, query: str, **kwargs: Any) -> FetchResult:
        """Return a single mock video entry with stable id and duration."""
        start = time.time()
        vid_hash = hashlib.md5(query.encode("utf-8")).hexdigest()[:11]
        video_id = f"yt_{vid_hash}"
        return FetchResult(
            success=True,
            channel="youtube",
            query=query,
            content=f"Mock video: '{query}' — transcript placeholder.",
            url=f"https://youtube.com/watch?v={video_id}",
            content_type="application/json",
            metadata={
                "engine": "youtube-dl-mock",
                "video_id": video_id,
                "title": f"Mock Video — {query}",
                "duration_seconds": 240 + (hash(query) % 600),
                "channel": f"mock_channel_{vid_hash[:6]}",
                "views": 1000 + (hash(query) % 100_000),
            },
            latency_ms=(time.time() - start) * 1000.0,
        )

    async def ping(self) -> bool:
        return True


__all__ = ["YouTubeDL"]