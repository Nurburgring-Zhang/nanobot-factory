"""V5 第31章 — RedFox 自媒体集成.

跨平台统一 API — 支持微信公众号/微博/抖音/快手/小红书/B站/知乎/
头条号/百家号/企鹅号/视频号 (11 平台)。

模块结构:
  * schemas.py        — Pydantic v2 数据契约
  * base_client.py    — BasePlatformClient + NotImplementedClient
  * registry.py       — PLATFORMS dict + RedFoxClient 多平台 fan-out
  * platforms/        — 5 个平台完整实现 (wechat_mp/weibo/douyin/xiaohongshu/bilibili)
  * skills/           — 4 个 Skill 函数 (publish_to_all/schedule/fetch/adapt)
  * tests/            — pytest ≥10 用例

参考 V5 文档第31章 (reports/V5_doc_decoded.txt:7328+).
"""
from __future__ import annotations

from .base_client import BasePlatformClient, NotImplementedClient
from .schemas import (
    AuthResult,
    AuthStatus,
    ContentItem,
    ContentType,
    CrossPlatformMetrics,
    MediaAttachment,
    MetricsResult,
    PlatformCredentials,
    PlatformId,
    PlatformVariant,
    Post,
    PublishResult,
    PublishStatus,
    ScheduledPublish,
    content_hash_of,
    make_post_id,
)

__version__ = "1.0.0"

__all__ = [
    "BasePlatformClient",
    "NotImplementedClient",
    "ContentItem",
    "ContentType",
    "MediaAttachment",
    "PlatformId",
    "PlatformCredentials",
    "AuthResult",
    "AuthStatus",
    "PublishResult",
    "PublishStatus",
    "MetricsResult",
    "Post",
    "ScheduledPublish",
    "PlatformVariant",
    "CrossPlatformMetrics",
    "content_hash_of",
    "make_post_id",
]