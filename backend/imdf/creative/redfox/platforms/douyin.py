"""抖音客户端 — V5 第31章 (5 个完整实现之一).

抖音开放平台: https://open.douyin.com/
  * client_token / access_token 双层 OAuth
  * 视频上传: /video/create/ + /video/upload/
  * 视频发布: /video/create/

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


class DouyinClient(BasePlatformClient):
    """抖音 (douyin) 客户端 — 主要支持 short_video."""

    platform_id = PlatformId.DOUYIN
    platform_name = "抖音"
    auth_required = True
    supports_content_types = ["short_video", "live_replay", "image_text"]

    _api_base = "https://open.douyin.com"

    # ── auth ───────────────────────────────────────────────────────────────
    async def authenticate(self, credentials: PlatformCredentials) -> AuthResult:
        """OAuth2 client_credentials grant — 抖音 client_token."""
        if not credentials.client_key and not credentials.app_id:
            return AuthResult(
                platform=self.platform_id,
                status=AuthStatus.FAILED,
                error_message="douyin requires client_key/app_id + client_secret/app_secret",
            )
        try:
            data = await self._safe_request(
                "POST",
                "/oauth/client_token/",
                json={
                    "client_key": credentials.app_id or "",
                    "client_secret": credentials.app_secret or "",
                    "grant_type": "client_credential",
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
        """发布抖音视频 — /video/create/."""
        if content.content_type not in (
            ContentType.SHORT_VIDEO, ContentType.LIVE_REPLAY, ContentType.IMAGE_TEXT,
        ):
            return self.fail_result(
                error=f"douyin does not support {content.content_type.value}",
            )
        if not content.media:
            return self.fail_result(error="douyin publish requires media attachment")
        chash = content_hash_of(content)
        post_id = make_post_id(self.platform_id, chash)
        try:
            data = await self._safe_request(
                "POST",
                "/video/create/",
                params={"access_token": (self.credentials.access_token if self.credentials else "")},
                json={
                    "video_id": content.media[0].url,
                    "text": f"{content.title}\n{content.body}"[:2200],
                    "cover_tsp": 1.0,
                    "micro_app_id": "",
                },
            )
            aweme_id = data.get("data", {}).get("video_id", post_id)
            return PublishResult(
                platform=self.platform_id,
                status=PublishStatus.SUCCESS,
                post_id=str(aweme_id),
                post_url=f"https://www.douyin.com/video/{aweme_id}",
                raw_response=data,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return self.fail_result(
                error=f"douyin publish failed: {exc}",
                post_id=post_id,
            )

    # ── metrics ────────────────────────────────────────────────────────────
    async def fetch_metrics(self, post_id: str) -> MetricsResult:
        """抖音视频数据 — /video/data/."""
        try:
            data = await self._safe_request(
                "POST",
                "/video/data/",
                params={"access_token": (self.credentials.access_token if self.credentials else "")},
                json={"item_ids": [post_id]},
            )
            item = (data.get("data", {}).get("list") or [{}])[0]
            stats = item.get("statistics", {}) or {}
            return MetricsResult(
                platform=self.platform_id,
                post_id=post_id,
                views=int(stats.get("play_count", 0)),
                likes=int(stats.get("digg_count", 0)),
                comments=int(stats.get("comment_count", 0)),
                shares=int(stats.get("share_count", 0)),
                collects=int(stats.get("collect_count", 0)),
                followers_delta=int(stats.get("follower_count", 0)),
                raw_response=data,
            )
        except (httpx.HTTPError, ValueError):
            return MetricsResult(platform=self.platform_id, post_id=post_id)

    # ── list ───────────────────────────────────────────────────────────────
    async def list_recent_posts(self, limit: int = 20) -> List[Post]:
        """抖音创作者最近视频 — /video/list/."""
        try:
            data = await self._safe_request(
                "GET",
                "/video/list/",
                params={"access_token": (self.credentials.access_token if self.credentials else ""), "count": min(limit, 50)},
            )
            items = data.get("data", {}).get("list") or []
            return [
                Post(
                    platform=self.platform_id,
                    post_id=str(it.get("video_id", "")),
                    title=it.get("title", "")[:100],
                    published_at=int(it.get("create_time", 0)),
                    url=f"https://www.douyin.com/video/{it.get('video_id')}",
                )
                for it in items
            ]
        except (httpx.HTTPError, ValueError):
            return []


__all__ = ["DouyinClient"]