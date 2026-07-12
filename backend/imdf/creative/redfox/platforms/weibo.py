"""微博客户端 — V5 第31章 (5 个完整实现之一).

微博开放平台: https://api.weibo.com/2/
  * OAuth2 access_token + 用户 uid
  * 发布微博: statuses/share (转发) / statuses/share (含图)
  * mid -> id 转换: https://api.weibo.com/2/statuses/queryid.json

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


class WeiboClient(BasePlatformClient):
    """微博 (weibo) 客户端 — 支持 text/image_text/short_video."""

    platform_id = PlatformId.WEIBO
    platform_name = "微博"
    auth_required = True
    supports_content_types = ["text", "image_text", "short_video"]

    _api_base = "https://api.weibo.com/2"

    # ── auth ───────────────────────────────────────────────────────────────
    async def authenticate(self, credentials: PlatformCredentials) -> AuthResult:
        """校验 OAuth2 access_token — 调用 account/get_uid."""
        if not credentials.access_token:
            return AuthResult(
                platform=self.platform_id,
                status=AuthStatus.FAILED,
                error_message="weibo requires access_token",
            )
        try:
            data = await self._safe_request(
                "GET",
                "/account/get_uid.json",
                params={"access_token": credentials.access_token},
            )
            uid = data.get("uid")
            if not uid:
                return AuthResult(
                    platform=self.platform_id,
                    status=AuthStatus.FAILED,
                    error_message=f"missing uid: {data}",
                    raw_response=data,
                )
            new_creds = credentials.model_copy(update={"user_id": str(uid)})
            self.credentials = new_creds
            self._auth_cache = AuthResult(
                platform=self.platform_id,
                status=AuthStatus.SUCCESS,
                credentials=new_creds,
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
        """发布微博 — statuses/share (含图/视频) 或 statuses/update."""
        if content.content_type not in (
            ContentType.TEXT, ContentType.IMAGE_TEXT, ContentType.SHORT_VIDEO,
        ):
            return self.fail_result(
                error=f"weibo does not support {content.content_type.value}",
            )
        chash = content_hash_of(content)
        post_id = make_post_id(self.platform_id, chash)
        path = "/statuses/share.json" if content.media else "/statuses/update.json"
        try:
            payload: Dict[str, Any] = {"status": f"{content.title}\n{content.body}"[:2000]}
            if content.media:
                payload["pic_id"] = ",".join(m.url for m in content.media)
            data = await self._safe_request(
                "POST",
                path,
                params={"access_token": (self.credentials.access_token if self.credentials else "")},
                json=payload,
            )
            return PublishResult(
                platform=self.platform_id,
                status=PublishStatus.SUCCESS,
                post_id=str(data.get("id", post_id)),
                post_url=f"https://weibo.com/{self.credentials.user_id if self.credentials else 'u'}/{data.get('id', post_id)}",
                raw_response=data,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return self.fail_result(
                error=f"weibo publish failed: {exc}",
                post_id=post_id,
            )

    # ── metrics ────────────────────────────────────────────────────────────
    async def fetch_metrics(self, post_id: str) -> MetricsResult:
        """微博 mid 指标 — 单条 statuses/show."""
        try:
            data = await self._safe_request(
                "GET",
                "/statuses/show.json",
                params={"id": post_id},
            )
            return MetricsResult(
                platform=self.platform_id,
                post_id=post_id,
                views=int(data.get("reposts_count", 0)) * 100,  # 微博无浏览字段,用 repost 估算
                likes=int(data.get("attitudes_count", 0)),
                comments=int(data.get("comments_count", 0)),
                shares=int(data.get("reposts_count", 0)),
                collects=0,
                followers_delta=0,
                raw_response=data,
            )
        except (httpx.HTTPError, ValueError):
            return MetricsResult(platform=self.platform_id, post_id=post_id)

    # ── list ───────────────────────────────────────────────────────────────
    async def list_recent_posts(self, limit: int = 20) -> List[Post]:
        """用户最近微博 — statuses/user_timeline."""
        if not (self.credentials and self.credentials.user_id):
            return []
        try:
            data = await self._safe_request(
                "GET",
                "/statuses/user_timeline.json",
                params={"uid": self.credentials.user_id, "count": min(limit, 100)},
            )
            statuses = data.get("statuses", []) or []
            return [
                Post(
                    platform=self.platform_id,
                    post_id=str(it.get("id", "")),
                    title=it.get("text", "")[:100],
                    published_at=int(it.get("created_at", 0)) if isinstance(it.get("created_at"), int) else 0,
                    url=f"https://weibo.com/{self.credentials.user_id}/{it.get('id')}",
                )
                for it in statuses
            ]
        except (httpx.HTTPError, ValueError):
            return []


__all__ = ["WeiboClient"]