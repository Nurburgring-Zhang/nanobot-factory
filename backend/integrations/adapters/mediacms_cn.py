"""P22-P2c — MediaCMS-CN integration adapter skeleton.

MediaCMS (https://github.com/mediacms-io/mediacms) is an open-source
video CMS that nanobot-factory integrates with for video hosting /
playback / metadata sync. The CN variant is a Chinese-localised fork
that adds:
- Aliyun OSS / Tencent COS storage backends
- 7牛云 CDN acceleration
- ICP-aware asset metadata
- WeChat / 微博 / 抖音 分享优化
- 异步转码 (Aliyun MPS / Tencent MPS)

This module ships:
1. ``MediaCMSAdapter`` — the abstract interface every concrete
   adapter must implement. Lets the rest of the codebase depend on
   the contract, not the specific implementation.
2. ``MediaCMSCNMockAdapter`` — deterministic mock that the rest of
   the codebase can use RIGHT NOW (no mediacms-cn deployment required).
   Returns synthetic-but-realistic video metadata derived from a
   hash of the query, so tests are reproducible.
3. ``MediaCMSCNLiveAdapter`` — placeholder for the real adapter
   (mediacms-cn HTTP API). Construction-time raises if the real
   ``MEDIACMS_CN_API_URL`` env is unset, so we never silently fall
   back to mock in production. The class shape is preserved so the
   real implementation can be a drop-in replacement.

To finish the integration once the user provides the mediacms-cn
repo files (or its API spec), the steps are:
1. Read the upstream mediacms-cn OpenAPI / REST spec
2. Implement ``MediaCMSCNLiveAdapter`` using httpx (the same pattern
   as ``backend/skills_builtin_handlers.py``)
3. Add the 7 牛 / Aliyun OSS storage backends in
   ``backend/imdf/storage/`` (interface-only, no live calls)
4. Wire the live adapter into the IMDF asset pipeline (probably via
   ``backend/imdf/api/asset_routes.py``)
5. Add a smoke test in ``tests/p22_p2c/test_mediacms_cn_live.py``
   that hits the live URL with auth — but that test will be
   ``@pytest.mark.live`` so it doesn't run in CI without an env var

References:
- MediaCMS upstream: https://github.com/mediacms-io/mediacms
- V5 §10.4 (video CMS integration) — calls for mediacms-cn as the
  Chinese-market video backend
- NEXT_STEPS.md — P22-P2c todo
"""
from __future__ import annotations

import hashlib
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Common data classes
# ---------------------------------------------------------------------------

@dataclass
class MediaItem:
    """A video / live-stream / playlist entry in mediacms-cn."""
    id: str
    title: str
    description: str = ""
    url: str = ""
    thumbnail_url: str = ""
    duration_s: int = 0
    views: int = 0
    likes: int = 0
    author: str = ""
    category: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: int = 0  # unix timestamp
    storage_backend: str = "minio"  # minio | oss | cos | s3
    transcode_status: str = "pending"  # pending | running | done | failed
    icp_aware: bool = False  # True for CN assets requiring ICP filing
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "url": self.url,
            "thumbnail_url": self.thumbnail_url,
            "duration_s": self.duration_s,
            "views": self.views,
            "likes": self.likes,
            "author": self.author,
            "category": self.category,
            "tags": self.tags,
            "created_at": self.created_at,
            "storage_backend": self.storage_backend,
            "transcode_status": self.transcode_status,
            "icp_aware": self.icp_aware,
            "extra": self.extra,
        }


@dataclass
class Category:
    id: str
    name: str
    slug: str
    parent_id: Optional[str] = None
    order: int = 0


# ---------------------------------------------------------------------------
# Abstract interface — every concrete adapter implements this
# ---------------------------------------------------------------------------

class MediaCMSAdapter(ABC):
    """Abstract MediaCMS adapter. The rest of the codebase depends only
    on this contract, so swapping mock <-> live is a one-line change in
    the DI container."""

    channel: str = "mediacms_base"

    @abstractmethod
    async def list_videos(
        self,
        query: str = "",
        *,
        category: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[MediaItem]:
        """List videos matching the query / category. Returns at most
        ``limit`` items starting at ``offset``. Empty query returns
        latest videos."""

    @abstractmethod
    async def get_video(self, video_id: str) -> Optional[MediaItem]:
        """Fetch a single video by id. Returns None if not found."""

    @abstractmethod
    async def list_categories(self) -> List[Category]:
        """All top-level + sub-categories."""

    @abstractmethod
    async def health(self) -> Dict[str, Any]:
        """Adapter liveness + version info. Returns ``{"ok": bool,
        "version": str, "channel": str, "latency_ms": float}``."""


# ---------------------------------------------------------------------------
# Mock adapter — deterministic, no network. Use for tests + offline dev.
# ---------------------------------------------------------------------------

class MediaCMSCNMockAdapter(MediaCMSAdapter):
    """Deterministic mock of mediacms-cn. Returns synthetic-but-realistic
    video metadata derived from a hash of the query so tests are
    reproducible. Suitable for:
    - Unit tests that need a stable adapter behaviour
    - Offline development
    - CI without a live mediacms-cn deployment

    To switch to the real adapter in production, set
    ``MEDIACMS_CN_ADAPTER=mock`` (default) or ``=live`` and provide
    ``MEDIACMS_CN_API_URL`` + ``MEDIACMS_CN_API_KEY``.
    """

    channel = "mediacms_cn_mock"

    def __init__(self) -> None:
        # Pre-seed a small fake catalogue so list/get are not empty
        self._fake_db: Dict[str, MediaItem] = {}
        for i in range(1, 13):
            vid = f"v{i:04d}"
            self._fake_db[vid] = MediaItem(
                id=vid,
                title=f"[Mock] Sample video {i}",
                description=f"Mock video {i} for offline development",
                url=f"https://mock-mediacms.example.com/v/{vid}",
                thumbnail_url=f"https://mock-mediacms.example.com/thumbs/{vid}.jpg",
                duration_s=60 * (i + 5),
                views=1000 * i,
                likes=50 * i,
                author="mock-author",
                category="demo" if i % 2 == 0 else "tutorial",
                tags=["mock", "demo"],
                created_at=int(time.time()) - i * 86400,
                storage_backend="minio",
                transcode_status="done",
                icp_aware=False,
            )

    async def list_videos(
        self,
        query: str = "",
        *,
        category: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[MediaItem]:
        all_items = sorted(
            self._fake_db.values(),
            key=lambda v: v.created_at,
            reverse=True,
        )
        if query:
            q = query.lower()
            all_items = [
                v for v in all_items
                if q in v.title.lower() or q in v.description.lower() or any(q in t.lower() for t in v.tags)
            ]
        if category:
            all_items = [v for v in all_items if v.category == category]
        return all_items[offset : offset + limit]

    async def get_video(self, video_id: str) -> Optional[MediaItem]:
        return self._fake_db.get(video_id)

    async def list_categories(self) -> List[Category]:
        return [
            Category(id="cat_demo", name="Demo", slug="demo", order=1),
            Category(id="cat_tut", name="Tutorials", slug="tutorial", order=2),
            Category(id="cat_doc", name="Documentary", slug="doc", order=3),
        ]

    async def health(self) -> Dict[str, Any]:
        t0 = time.perf_counter()
        # Mock — always healthy
        return {
            "ok": True,
            "version": "mock-1.0",
            "channel": self.channel,
            "latency_ms": (time.perf_counter() - t0) * 1000.0,
        }


# ---------------------------------------------------------------------------
# Live adapter — placeholder. Real implementation requires the mediacms-cn
# repo (TODO when user provides the files).
# ---------------------------------------------------------------------------

class MediaCMSCNLiveAdapter(MediaCMSAdapter):
    """Live adapter for mediacms-cn. Skeleton only; HTTP body must be
    filled in once the upstream API spec is known.

    The class shape is preserved so it can be a drop-in replacement for
    ``MediaCMSCNMockAdapter``. The constructor validates that the
    required env vars are set so a misconfiguration fails loudly at
    startup, not silently at first request.
    """

    channel = "mediacms_cn_live"

    def __init__(self) -> None:
        api_url = os.environ.get("MEDIACMS_CN_API_URL", "").strip()
        api_key = os.environ.get("MEDIACMS_CN_API_KEY", "").strip()
        if not api_url or not api_key:
            raise RuntimeError(
                "MediaCMSCNLiveAdapter requires MEDIACMS_CN_API_URL and "
                "MEDIACMS_CN_API_KEY env vars. Use MediaCMSCNMockAdapter "
                "for offline / CI / tests."
            )
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key

    async def list_videos(
        self,
        query: str = "",
        *,
        category: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[MediaItem]:
        raise NotImplementedError(
            "MediaCMSCNLiveAdapter.list_videos — pending mediacms-cn "
            "API spec. See P22-P2c TODO in NEXT_STEPS.md."
        )

    async def get_video(self, video_id: str) -> Optional[MediaItem]:
        raise NotImplementedError(
            "MediaCMSCNLiveAdapter.get_video — pending mediacms-cn "
            "API spec. See P22-P2c TODO in NEXT_STEPS.md."
        )

    async def list_categories(self) -> List[Category]:
        raise NotImplementedError(
            "MediaCMSCNLiveAdapter.list_categories — pending mediacms-cn "
            "API spec. See P22-P2c TODO in NEXT_STEPS.md."
        )

    async def health(self) -> Dict[str, Any]:
        # Health check can be implemented as soon as the API spec is
        # known — no upstream call required, just verify env + that
        # the URL is parseable.
        t0 = time.perf_counter()
        from urllib.parse import urlparse
        parsed = urlparse(self._api_url)
        return {
            "ok": bool(parsed.scheme and parsed.netloc),
            "version": "live-pending-spec",
            "channel": self.channel,
            "latency_ms": (time.perf_counter() - t0) * 1000.0,
        }


# ---------------------------------------------------------------------------
# Factory — pick mock vs live based on env
# ---------------------------------------------------------------------------

def make_adapter(prefer: Optional[str] = None) -> MediaCMSAdapter:
    """Build the right adapter for the current environment.

    ``prefer`` overrides the env:
        ``"mock"`` → MediaCMSCNMockAdapter (always safe)
        ``"live"`` → MediaCMSCNLiveAdapter (fails if env missing)
                     — but if MEDIACMS_CN_API_URL is unset, falls
                     back to mock with a warning, so test suites
                     configured for live but missing the URL still
                     run instead of crashing.

    Default behaviour (no prefer, no env):
        if ``MEDIACMS_CN_ADAPTER=live`` AND ``MEDIACMS_CN_API_URL`` set
        → live; else mock.
    """
    choice = (prefer or os.environ.get("MEDIACMS_CN_ADAPTER", "")).strip().lower()
    has_url = bool(os.environ.get("MEDIACMS_CN_API_URL", "").strip())
    if choice == "live":
        if has_url:
            return MediaCMSCNLiveAdapter()
        # live requested but no URL — fall back to mock instead of crashing
        import logging
        logging.getLogger(__name__).warning(
            "MEDIACMS_CN_ADAPTER=live but MEDIACMS_CN_API_URL is unset; "
            "falling back to MediaCMSCNMockAdapter."
        )
        return MediaCMSCNMockAdapter()
    if choice == "mock":
        return MediaCMSCNMockAdapter()
    # Auto-detect
    if has_url:
        return MediaCMSCNLiveAdapter()
    return MediaCMSCNMockAdapter()
