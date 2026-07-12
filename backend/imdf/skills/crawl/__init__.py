"""V5 — imdf Skills: 17 crawl skills for nanobot-factory.

This package provides 17 ready-to-use async crawl skill functions that
wrap public REST/JSON endpoints (or fall back to deterministic offline
mocks when the network is unreachable):

  * Reddit, Twitter/X, YouTube, TikTok, Instagram, Pinterest, Tumblr
  * Flickr, Unsplash, 500px, DeviantArt, Behance, Dribbble, ArtStation
  * Pixiv, Danbooru, Gelbooru

Each skill follows the contract:

    async def crawl_<site>(input: SkillInput) -> SkillOutput

where ``SkillInput`` / ``SkillOutput`` come from
``backend.skills.legacy``.  Domain-specific payloads are modelled as
Pydantic ``BaseModel`` subclasses.

Importing::

    from backend.imdf.skills.crawl import (
        crawl_reddit, crawl_twitter, ..., get_crawl_skill,
    )

The registry below lets the caller pick a skill by ``SKILL_ID`` or by
site name without having to know which module exports it.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

# Shared base helpers — eagerly loaded (no sub-import cycle)
from ._base import (
    TimestampedModel,
    build_metadata,
    error_output,
    fetch_or_mock,
    get_offline_fixture,
    is_network_available,
    register_offline_fixture,
    reset_network_probe,
    to_skill_output,
)


def _build_registry() -> Dict[str, Callable[[Any], Any]]:
    """Lazy registry builder — avoids the eager-import circular import
    that would otherwise occur when ``crawl_X.py`` does
    ``from backend.imdf.skills.crawl._base import ...`` during
    ``__init__.py`` load.
    """
    from . import (
        crawl_500px, crawl_artstation, crawl_behance, crawl_danbooru,
        crawl_deviantart, crawl_dribbble, crawl_flickr2, crawl_gelbooru,
        crawl_instagram, crawl_pinterest, crawl_pixiv, crawl_reddit,
        crawl_tiktok, crawl_tumblr, crawl_twitter, crawl_unsplash2,
        crawl_youtube,
    )
    return {
        crawl_reddit.SKILL_ID: crawl_reddit.crawl_reddit,
        crawl_twitter.SKILL_ID: crawl_twitter.crawl_twitter,
        crawl_youtube.SKILL_ID: crawl_youtube.crawl_youtube,
        crawl_tiktok.SKILL_ID: crawl_tiktok.crawl_tiktok,
        crawl_instagram.SKILL_ID: crawl_instagram.crawl_instagram,
        crawl_pinterest.SKILL_ID: crawl_pinterest.crawl_pinterest,
        crawl_tumblr.SKILL_ID: crawl_tumblr.crawl_tumblr,
        crawl_flickr2.SKILL_ID: crawl_flickr2.crawl_flickr2,
        crawl_unsplash2.SKILL_ID: crawl_unsplash2.crawl_unsplash2,
        crawl_500px.SKILL_ID: crawl_500px.crawl_500px,
        crawl_deviantart.SKILL_ID: crawl_deviantart.crawl_deviantart,
        crawl_behance.SKILL_ID: crawl_behance.crawl_behance,
        crawl_dribbble.SKILL_ID: crawl_dribbble.crawl_dribbble,
        crawl_artstation.SKILL_ID: crawl_artstation.crawl_artstation,
        crawl_pixiv.SKILL_ID: crawl_pixiv.crawl_pixiv,
        crawl_danbooru.SKILL_ID: crawl_danbooru.crawl_danbooru,
        crawl_gelbooru.SKILL_ID: crawl_gelbooru.crawl_gelbooru,
    }


def get_crawl_skill(skill_id: str) -> Callable[[Any], Any]:
    """Return the async skill callable for ``skill_id`` or raise KeyError."""
    registry = _build_registry()
    if skill_id not in registry:
        raise KeyError(
            f"unknown crawl skill {skill_id!r}; valid: {list(registry)}"
        )
    return registry[skill_id]


def list_crawl_skill_ids() -> List[str]:
    return list(_build_registry().keys())


__all__ = [
    # Base helpers
    "TimestampedModel",
    "build_metadata",
    "error_output",
    "fetch_or_mock",
    "get_offline_fixture",
    "is_network_available",
    "register_offline_fixture",
    "reset_network_probe",
    "to_skill_output",
    # Registry accessors
    "get_crawl_skill",
    "list_crawl_skill_ids",
]