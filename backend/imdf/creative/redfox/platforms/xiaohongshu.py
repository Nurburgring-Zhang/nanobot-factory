"""小红书客户端 — V5 第31章 (5 个完整实现之一).

小红书开放平台: https://open.xiaohongshu.com/
  * OAuth2 + 签名校验 (X-Sign)
  * 发布图文 / 视频笔记: /api/store/note/create
  * 笔记类型: 1=图文, 2=视频

本模块 mock 所有外部调用 — 测试通过 httpx.MockTransport 注入。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from ..base_client import BasePlatformClient
from ..schemas import (
    AuthResult,
    AuthStatus,
    ContentItem,
    ContentType,
    MetricsResult,
    PlatformCredentials,
    PlatformId,
    Post,
    PublishResult,
    PublishStatus,
    content_hash_of,
    make_post_id,
)

logger = logging.getLogger(__name__)


class XiaohongshuClient(BasePlatformClient):
    """小红书 (xiaohongshu) 客户端 — 主打 image_text/short_video."""

    platform_id = PlatformId.XIAOHONGSHU
    platform_name = "小红书"
    auth_required = True
    supports_content_types = ["image_text", "short_video", "text"]

    _api_base = "https://open.xiaohongshu.com"

    # ── auth ───────────────────────────────────────────────────────────────
    async def authenticate(self, credentials: PlatformCredentials) -> AuthResult:
        """小红书 OAuth2 — 通过 app_id/app_secret + code 换 token."""
        if not credentials.app_id or not credentials.app_secret:
            return AuthResult(
                platform=self.platform_id,
                status=AuthStatus.FAILED,
                error_message="xiaohongshu requires app_id + app_secret",
            )
        try:
            data = await self._safe_request(
                "POST",
                "/api/ecosystem/v1/token",
                json={
                    "app_id": credentials.app_id,
                    "app_secret": credentials.app_secret,
                    "code": credentials.extra.get("code", ""),
                    "grant_type": "authorization_code",
                },
            )
            token = data.get("data", {}).get("access_token")
            if not token:
                return AuthResult(
                    platform=self.platform_id,
                    status=AuthStatus.FAILED,
                    error_message=f"missing access_token: {data}",
                    raw_response=data,
                )
            new_creds = credentials.model_copy(update={"access_token": token})
            self.credentials = new_creds
            self._auth_cache = AuthResult(
                platform=self.platform_id,
                status=AuthStatus.SUCCESS,
                credentials=new_creds,
                expires_at=data.get("data", {}).get("expires_in"),
                raw_response=data,
            )
            return self._auth_cache
        except (httpx.HTTPError, ValueError) as exc:
            return AuthResult(
                platform=self.platform_id,
                status=AuthStatus.FAILED,
                error_message=str(exc)[:500],
            )

    # ── publish ────────────────────────────────────────────────────────────
    async def publish(self, content: ContentItem) -> PublishResult:
        """发布小红书笔记 — /api/store/note/create.

        note_type: 1=图文, 2=视频. 标题限制 20 字,正文限制 1000 字.
        """
        if content.content_type not in (
            ContentType.IMAGE_TEXT, ContentType.SHORT_VIDEO, ContentType.TEXT,
        ):
            return self.fail_result(
                error=f"xiaohongshu does not support {content.content_type.value}",
            )
        chash = content_hash_of(content)
        post_id = make_post_id(self.platform_id, chash)
        note_type = 2 if content.content_type == ContentType.SHORT_VIDEO else 1
        try:
            data = await self._safe_request(
                "POST",
                "/api/store/note/create",
                json={
                    "title": content.title[:20],
                    "desc": content.body[:1000],
                    "note_type": note_type,
                    "image_list": [m.url for m in content.media if m.mime.startswith("image/")],
                    "video_url": (content.media[0].url if content.media and note_type == 2 else ""),
                    "tag_list": content.tags[:10],
                },
            )
            note_id = data.get("data", {}).get("note_id", post_id)
            return PublishResult(
                platform=self.platform_id,
                status=PublishStatus.SUCCESS,
                post_id=str(note_id),
                post_url=f"https://www.xiaohongshu.com/explore/{note_id}",
                raw_response=data,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return self.fail_result(
                error=f"xiaohongshu publish failed: {exc}",
                post_id=post_id,
            )

    # ── metrics ────────────────────────────────────────────────────────────
    async def fetch_metrics(self, post_id: str) -> MetricsResult:
        """小红书笔记数据 — /api/store/note/data."""
        try:
            data = await self._safe_request(
                "GET",
                "/api/store/note/data",
                params={"note_id": post_id},
            )
            stats = data.get("data", {}) or {}
            return MetricsResult(
                platform=self.platform_id,
                post_id=post_id,
                views=int(stats.get("view_count", 0)),
                likes=int(stats.get("liked_count", 0)),
                comments=int(stats.get("comment_count", 0)),
                shares=int(stats.get("share_count", 0)),
                collects=int(stats.get("collected_count", 0)),
                followers_delta=int(stats.get("follower_count", 0)),
                raw_response=data,
            )
        except (httpx.HTTPError, ValueError):
            return MetricsResult(platform=self.platform_id, post_id=post_id)

    # ── list ───────────────────────────────────────────────────────────────
    async def list_recent_posts(self, limit: int = 20) -> List[Post]:
        """小红书创作者笔记列表 — /api/store/note/list."""
        try:
            data = await self._safe_request(
                "POST",
                "/api/store/note/list",
                json={"page": 1, "page_size": min(limit, 50)},
            )
            items = data.get("data", {}).get("notes") or []
            return [
                Post(
                    platform=self.platform_id,
                    post_id=str(it.get("note_id", "")),
                    title=it.get("title", ""),
                    published_at=int(it.get("time", 0)),
                    url=f"https://www.xiaohongshu.com/explore/{it.get('note_id')}",
                )
                for it in items
            ]
        except (httpx.HTTPError, ValueError):
            return []


__all__ = ["XiaohongshuClient"]