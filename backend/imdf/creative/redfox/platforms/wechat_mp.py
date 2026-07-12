"""微信公众号客户端 — V5 第31章 (5 个完整实现之一).

微信公众号 API: https://api.weixin.qq.com/cgi-bin/
  * access_token: 通过 appid/appsecret 获取
  * 新增草稿 / 发布: /draft/add -> /freepublish/submit
  * 群发限制: 订阅号每天 1 条群发,服务号每月 4 条

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


class WeChatMPClient(BasePlatformClient):
    """微信公众号 (wechat_mp) 客户端 — 支持 text/image_text/article."""

    platform_id = PlatformId.WECHAT_MP
    platform_name = "微信公众号"
    auth_required = True
    supports_content_types = ["text", "image_text", "article"]

    _api_base = "https://api.weixin.qq.com/cgi-bin"

    # ── auth ───────────────────────────────────────────────────────────────
    async def authenticate(self, credentials: PlatformCredentials) -> AuthResult:
        """获取/刷新 access_token. Mock 模式: 直接返回 SUCCESS."""
        if not credentials.app_id or not credentials.app_secret:
            return AuthResult(
                platform=self.platform_id,
                status=AuthStatus.FAILED,
                error_message="wechat_mp requires app_id + app_secret",
            )
        try:
            data = await self._safe_request(
                "GET",
                "/token",
                params={
                    "grant_type": "client_credential",
                    "appid": credentials.app_id,
                    "secret": credentials.app_secret,
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
            new_creds = credentials.model_copy(update={"access_token": token})
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
        """发布到微信公众号 — 走 draft/add + freepublish/submit 两步."""
        if content.content_type not in (
            ContentType.TEXT, ContentType.IMAGE_TEXT, ContentType.ARTICLE,
        ):
            return self.fail_result(
                error=f"wechat_mp does not support {content.content_type.value}",
            )
        chash = content_hash_of(content)
        post_id = make_post_id(self.platform_id, chash)
        try:
            # Step 1: 创建草稿
            draft_data = await self._safe_request(
                "POST",
                "/draft/add",
                params={"access_token": (self.credentials.access_token if self.credentials else "")},
                json={
                    "title": content.title,
                    "content": content.body,
                    "author": content.author or "anonymous",
                    "digest": content.body[:120],
                    "thumb_media_id": (content.media[0].url if content.media else ""),
                },
            )
            media_id = draft_data.get("media_id")
            # Step 2: 提交发布
            pub_data = await self._safe_request(
                "POST",
                "/freepublish/submit",
                params={"access_token": (self.credentials.access_token if self.credentials else "")},
                json={"media_id": media_id},
            )
            return PublishResult(
                platform=self.platform_id,
                status=PublishStatus.SUCCESS,
                post_id=post_id,
                post_url=f"https://mp.weixin.qq.com/s/{post_id}",
                raw_response={"draft": draft_data, "publish": pub_data},
            )
        except (httpx.HTTPError, ValueError) as exc:
            return self.fail_result(
                error=f"wechat_mp publish failed: {exc}",
                post_id=post_id,
            )

    # ── metrics ────────────────────────────────────────────────────────────
    async def fetch_metrics(self, post_id: str) -> MetricsResult:
        """微信公众号文章指标 — views/likes/comments/shares/collects."""
        try:
            data = await self._safe_request(
                "GET",
                "/datacube/getarticletotal",
                params={"post_id": post_id},
            )
            return MetricsResult(
                platform=self.platform_id,
                post_id=post_id,
                views=int(data.get("int_page_read_count", 0)),
                likes=int(data.get("like_count", 0)),
                comments=int(data.get("comment_count", 0)),
                shares=int(data.get("share_count", 0)),
                collects=int(data.get("favorite_count", 0)),
                followers_delta=int(data.get("add_fans_count", 0)),
                raw_response=data,
            )
        except (httpx.HTTPError, ValueError):
            return MetricsResult(platform=self.platform_id, post_id=post_id)

    # ── list ───────────────────────────────────────────────────────────────
    async def list_recent_posts(self, limit: int = 20) -> List[Post]:
        """列出最近发布 — 调用 freepublish/getarticle."""
        try:
            data = await self._safe_request(
                "POST",
                "/freepublish/batchget",
                json={"offset": 0, "count": min(limit, 20)},
            )
            items = data.get("news_item", []) or []
            return [
                Post(
                    platform=self.platform_id,
                    post_id=str(it.get("article_id", "")),
                    title=it.get("title", ""),
                    published_at=int(it.get("update_time", 0)),
                    url=it.get("url"),
                )
                for it in items
            ]
        except (httpx.HTTPError, ValueError):
            return []


__all__ = ["WeChatMPClient"]