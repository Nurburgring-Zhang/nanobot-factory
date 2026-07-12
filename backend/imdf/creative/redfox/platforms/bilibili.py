"""B 站客户端 — V5 第31章 (5 个完整实现之一).

B 站开放平台: https://api.bilibili.com/
  * OAuth2 appid/secret + access_token
  * 投稿视频: /x/web-interface/article (动态) 或 /x/web-interface/upload (视频)
  * 数据: /x/web-interface/archive/stat

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


class BilibiliClient(BasePlatformClient):
    """B站 (bilibili) 客户端 — 支持 short_video/long_video/article."""

    platform_id = PlatformId.BILIBILI
    platform_name = "B站"
    auth_required = True
    supports_content_types = ["short_video", "long_video", "article", "image_text"]

    _api_base = "https://api.bilibili.com"

    # ── auth ───────────────────────────────────────────────────────────────
    async def authenticate(self, credentials: PlatformCredentials) -> AuthResult:
        """B站 OAuth2 — 通过 app_id + app_secret 换 access_token (code flow)."""
        if not credentials.app_id or not credentials.app_secret:
            return AuthResult(
                platform=self.platform_id,
                status=AuthStatus.FAILED,
                error_message="bilibili requires app_id + app_secret",
            )
        try:
            data = await self._safe_request(
                "POST",
                "/x/account-oauth2/v1/token",
                json={
                    "client_id": credentials.app_id,
                    "client_secret": credentials.app_secret,
                    "code": credentials.extra.get("code", ""),
                    "grant_type": "authorization_code",
                },
            )
            token = data.get("access_token")
            if not token:
                return AuthResult(
                    platform=self.platform_id,
                    status=AuthStatus.FAILED,
                    error_message=f"missing access_token: {data}",
                    raw_response=data,
                )
            mid = data.get("mid")
            new_creds = credentials.model_copy(
                update={"access_token": token, "user_id": str(mid) if mid else None}
            )
            self.credentials = new_creds
            self._auth_cache = AuthResult(
                platform=self.platform_id,
                status=AuthStatus.SUCCESS,
                credentials=new_creds,
                expires_at=data.get("expires_in"),
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
        """B站投稿 — 动态 (article) / 视频 (archive/add)."""
        if content.content_type not in (
            ContentType.SHORT_VIDEO, ContentType.LONG_VIDEO,
            ContentType.ARTICLE, ContentType.IMAGE_TEXT,
        ):
            return self.fail_result(
                error=f"bilibili does not support {content.content_type.value}",
            )
        chash = content_hash_of(content)
        post_id = make_post_id(self.platform_id, chash)
        if content.content_type in (ContentType.SHORT_VIDEO, ContentType.LONG_VIDEO):
            path = "/x/web-interface/archive/add"
            payload = {
                "title": content.title[:80],
                "desc": content.body[:2000],
                "tag": ",".join(content.tags[:10]),
                "video_url": (content.media[0].url if content.media else ""),
                "tid": content.extra.get("tid", 21),  # 默认日常分区
            }
        else:
            path = "/x/web-interface/article/create"
            payload = {
                "title": content.title[:80],
                "content": content.body[:10000],
                "tags": ",".join(content.tags[:5]),
            }
        try:
            data = await self._safe_request(
                "POST",
                path,
                params={"access_token": (self.credentials.access_token if self.credentials else "")},
                json=payload,
            )
            target_id = (
                data.get("data", {}).get("aid")
                or data.get("data", {}).get("article_id")
                or post_id
            )
            return PublishResult(
                platform=self.platform_id,
                status=PublishStatus.SUCCESS,
                post_id=str(target_id),
                post_url=f"https://www.bilibili.com/video/av{target_id}",
                raw_response=data,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return self.fail_result(
                error=f"bilibili publish failed: {exc}",
                post_id=post_id,
            )

    # ── metrics ────────────────────────────────────────────────────────────
    async def fetch_metrics(self, post_id: str) -> MetricsResult:
        """B站稿件数据 — /x/web-interface/archive/stat."""
        try:
            data = await self._safe_request(
                "GET",
                "/x/web-interface/archive/stat",
                params={"aid": post_id},
            )
            stats = data.get("data", {}) or {}
            return MetricsResult(
                platform=self.platform_id,
                post_id=post_id,
                views=int(stats.get("view", 0)),
                likes=int(stats.get("like", 0)),
                comments=int(stats.get("reply", 0)),
                shares=int(stats.get("share", 0)),
                collects=int(stats.get("favorite", 0)),
                followers_delta=int(stats.get("danmaku", 0)),  # 弹幕数作为粉丝增量代理
                raw_response=data,
            )
        except (httpx.HTTPError, ValueError):
            return MetricsResult(platform=self.platform_id, post_id=post_id)

    # ── list ───────────────────────────────────────────────────────────────
    async def list_recent_posts(self, limit: int = 20) -> List[Post]:
        """B站UP主投稿 — /x/space/wbi/arc/search (mid -> archives)."""
        if not (self.credentials and self.credentials.user_id):
            return []
        try:
            data = await self._safe_request(
                "GET",
                "/x/space/wbi/arc/search",
                params={"mid": self.credentials.user_id, "ps": min(limit, 50)},
            )
            items = (data.get("data", {}) or {}).get("list", {}).get("vlist") or []
            return [
                Post(
                    platform=self.platform_id,
                    post_id=str(it.get("aid", "")),
                    title=it.get("title", ""),
                    published_at=int(it.get("created", 0)),
                    url=f"https://www.bilibili.com/video/av{it.get('aid')}",
                )
                for it in items
            ]
        except (httpx.HTTPError, ValueError):
            return []


__all__ = ["BilibiliClient"]