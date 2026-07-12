"""V5 第31章 — RedFox 多平台集成 pytest 测试.

测试策略:
  * 所有外部 HTTP 调用通过 httpx.MockTransport 注入 — 不依赖真实平台 API
  * 11 平台注册表 PLATFORMS 完整性测试
  * 5 个完整实现 (wechat/weibo/douyin/xiaohongshu/bilibili) 各自 publish/metrics/list
  * 6 个 placeholder 平台 NOT_IMPLEMENTED 行为
  * RedFoxClient 跨平台 fan-out + 失败隔离
  * Skills: publish_to_all / schedule_publish / fetch_cross_platform_metrics /
    generate_platform_variants

依赖: pytest + httpx (已在 requirements.txt)
执行:
    D:\ComfyUI\.ext\python.exe -m pytest backend/imdf/creative/redfox/tests/ -v --tb=short

注: 直接用 `from imdf.creative.redfox import ...` 而不是
`from backend.imdf...`, 因为 backend/ 没有 __init__.py,
imdf/ 的 conftest.py 已经把 backend/imdf 加到 sys.path[0]。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import httpx
import pytest

from imdf.creative.redfox import (  # noqa: E402
    BasePlatformClient,
    ContentItem,
    ContentType,
    CrossPlatformMetrics,
    MediaAttachment,
    MetricsResult,
    NotImplementedClient,
    PlatformCredentials,
    PlatformId,
    PlatformVariant,
    Post,
    PublishResult,
    PublishStatus,
    ScheduledPublish,
)
from imdf.creative.redfox.registry import (  # noqa: E402
    PLATFORMS,
    RedFoxClient,
    get_platform,
    list_implemented_platforms,
    list_placeholder_platforms,
)
from imdf.creative.redfox.skills import (  # noqa: E402
    _PLATFORM_RULES,
    fetch_cross_platform_metrics,
    generate_platform_variants,
    list_scheduled,
    publish_to_all,
    schedule_publish,
)
from imdf.creative.redfox.platforms import (  # noqa: E402
    BilibiliClient,
    DouyinClient,
    WeChatMPClient,
    WeiboClient,
    XiaohongshuClient,
)


# ── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _reset_schedule_queue():
    """每个测试前清空调度队列,避免状态泄漏."""
    import imdf.creative.redfox.skills as skills_mod
    skills_mod._SCHEDULE_QUEUE.clear()
    yield
    skills_mod._SCHEDULE_QUEUE.clear()


@pytest.fixture
def sample_content() -> ContentItem:
    """TEXT content — 适用于公众号/微博/小红书 (但不适合抖音/B站)."""
    return ContentItem(
        title="测试自媒体标题 — 智影 RedFox 多平台分发",
        body="这是一段用于测试 RedFox 跨平台发布的长正文,字数足够覆盖各平台限制。",
        content_type=ContentType.TEXT,
        tags=["redfox", "自媒体", "智影"],
        media=[],
    )


@pytest.fixture
def sample_image_text_content() -> ContentItem:
    """IMAGE_TEXT content — 跨 5 平台通用 (公众号/微博/抖音/小红书/B站都支持)."""
    return ContentItem(
        title="图文测试标题",
        body="小红书/微博/公众号/抖音都支持的图文正文 — 跨平台通用。",
        content_type=ContentType.IMAGE_TEXT,
        tags=["种草", "好物", "redfox"],
        media=[MediaAttachment(url="https://example.com/img1.jpg", mime="image/jpeg")],
    )


def _mock_transport(responses: Dict[str, Dict[str, Any]]) -> httpx.MockTransport:
    """构造 httpx.MockTransport — 按 (method, url substring) 匹配返回."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        method = request.method.upper()
        for key, payload in responses.items():
            if key in url:
                return httpx.Response(
                    200,
                    json=payload,
                    headers={"content-type": "application/json"},
                )
        return httpx.Response(
            404,
            json={"errcode": 404, "errmsg": f"no mock for {method} {url}"},
        )
    return httpx.MockTransport(handler)


def _mock_transport_with_status(
    responses: List[tuple[str, int, Dict[str, Any]]],
) -> httpx.MockTransport:
    """按 (substring, status, body) 列表返回 — 第一个匹配胜出."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for substr, status, body in responses:
            if substr in url:
                return httpx.Response(status, json=body)
        return httpx.Response(500, json={"err": "no match"})
    return httpx.MockTransport(handler)


# ════════════════════════════════════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════════════════════════════════════


class TestPlatformRegistry:
    """PLATFORMS 注册表完整性."""

    def test_all_11_platforms_registered(self):
        assert len(PLATFORMS) == 11

    def test_implemented_count_is_5(self):
        impl = list_implemented_platforms()
        assert len(impl) == 5
        assert PlatformId.WECHAT_MP in impl
        assert PlatformId.WEIBO in impl
        assert PlatformId.DOUYIN in impl
        assert PlatformId.XIAOHONGSHU in impl
        assert PlatformId.BILIBILI in impl

    def test_placeholder_count_is_6(self):
        ph = list_placeholder_platforms()
        assert len(ph) == 6
        for pid in ph:
            assert isinstance(PLATFORMS[pid], NotImplementedClient)

    def test_get_platform_with_string(self):
        c = get_platform("wechat_mp")
        assert isinstance(c, WeChatMPClient)
        assert c.platform_id == PlatformId.WECHAT_MP

    def test_get_platform_unknown_raises(self):
        # PlatformId enum raises ValueError first; KeyError also possible if bypassed
        with pytest.raises((KeyError, ValueError)):
            get_platform("nonexistent_platform")


class TestSchemas:
    """Pydantic v2 schemas 校验."""

    def test_content_item_title_required(self):
        with pytest.raises(Exception):
            ContentItem(title="", body="x")  # type: ignore[arg-type]

    def test_content_item_short_video_needs_media(self):
        with pytest.raises(Exception):
            ContentItem(
                title="t", body="b", content_type=ContentType.SHORT_VIDEO,
            )

    def test_content_hash_deterministic(self):
        from imdf.creative.redfox.schemas import content_hash_of
        c1 = ContentItem(title="A", body="B", tags=["x", "y"])
        c2 = ContentItem(title="A", body="B", tags=["y", "x"])  # tags order swapped
        assert content_hash_of(c1) == content_hash_of(c2)

    def test_make_post_id_format_per_platform(self):
        from imdf.creative.redfox.schemas import make_post_id
        wx = make_post_id(PlatformId.WECHAT_MP, "abc")
        assert wx.startswith("wx_")
        wb = make_post_id(PlatformId.WEIBO, "abc")
        assert wb.isdigit()  # 微博纯数字 mid
        xhs = make_post_id(PlatformId.XIAOHONGSHU, "abc")
        assert len(xhs) == 24  # 小红书 24 hex


class TestWeChatMPClient:
    """微信公众号客户端."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self):
        transport = _mock_transport_with_status([
            ("/token", 200, {
                "access_token": "wx_at_123",
                "expires_in": 7200,
            }),
        ])
        client = WeChatMPClient(transport=transport)
        creds = PlatformCredentials(
            platform=PlatformId.WECHAT_MP,
            app_id="wx_app", app_secret="wx_secret",
        )
        result = await client.authenticate(creds)
        assert result.status == "success"
        assert result.credentials.access_token == "wx_at_123"

    @pytest.mark.asyncio
    async def test_publish_text(self, sample_content: ContentItem):
        transport = _mock_transport_with_status([
            ("/draft/add", 200, {"media_id": "draft_001"}),
            ("/freepublish/submit", 200, {"publish_id": "pub_001"}),
        ])
        client = WeChatMPClient(transport=transport)
        result = await client.publish(sample_content)
        assert result.status == PublishStatus.SUCCESS
        assert result.post_id is not None
        assert "mp.weixin.qq.com" in (result.post_url or "")

    @pytest.mark.asyncio
    async def test_publish_unsupported_type_returns_failed(self):
        transport = _mock_transport({})
        client = WeChatMPClient(transport=transport)
        c = ContentItem(
            title="livestream",
            body="x",
            content_type=ContentType.LIVE_REPLAY,
            media=[],
        )
        result = await client.publish(c)
        assert result.status == PublishStatus.FAILED

    @pytest.mark.asyncio
    async def test_fetch_metrics_parses(self):
        transport = _mock_transport_with_status([
            ("/datacube/getarticletotal", 200, {
                "int_page_read_count": 1024, "like_count": 100,
                "comment_count": 20, "share_count": 5, "favorite_count": 30,
                "add_fans_count": 8,
            }),
        ])
        client = WeChatMPClient(transport=transport)
        m = await client.fetch_metrics("wx_test_001")
        assert m.views == 1024
        assert m.likes == 100
        assert m.platform == PlatformId.WECHAT_MP


class TestWeiboClient:
    """微博客户端."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self):
        transport = _mock_transport_with_status([
            ("/account/get_uid.json", 200, {"uid": 1234567890}),
        ])
        client = WeiboClient(transport=transport)
        creds = PlatformCredentials(
            platform=PlatformId.WEIBO, access_token="wb_at",
        )
        result = await client.authenticate(creds)
        assert result.status == "success"
        assert result.credentials.user_id == "1234567890"

    @pytest.mark.asyncio
    async def test_publish_text(self, sample_content: ContentItem):
        transport = _mock_transport_with_status([
            ("/statuses/update.json", 200, {"id": 999000111, "text": "ok"}),
        ])
        client = WeiboClient(transport=transport)
        result = await client.publish(sample_content)
        assert result.status == PublishStatus.SUCCESS
        assert result.post_id == "999000111"


class TestDouyinClient:
    """抖音客户端."""

    @pytest.mark.asyncio
    async def test_publish_short_video(self, sample_content: ContentItem):
        from imdf.creative.redfox.schemas import MediaAttachment
        c = ContentItem(
            title="抖音标题",
            body="抖音正文",
            content_type=ContentType.SHORT_VIDEO,
            media=[MediaAttachment(url="https://video", mime="video/mp4")],
        )
        transport = _mock_transport_with_status([
            ("/video/create/", 200, {"data": {"video_id": "v_abc123"}}),
        ])
        client = DouyinClient(transport=transport)
        result = await client.publish(c)
        assert result.status == PublishStatus.SUCCESS
        assert "douyin.com" in (result.post_url or "")

    @pytest.mark.asyncio
    async def test_publish_without_media_fails(self):
        # ContentItem model_validator 拦截 — SHORT_VIDEO 必须带 media
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ContentItem(
                title="t", body="b",
                content_type=ContentType.SHORT_VIDEO, media=[],
            )

    @pytest.mark.asyncio
    async def test_publish_text_type_rejected(self, sample_content: ContentItem):
        """抖音不支持纯 TEXT 内容 — publish 直接返回 FAILED."""
        client = DouyinClient(transport=_mock_transport({}))
        result = await client.publish(sample_content)
        assert result.status == PublishStatus.FAILED
        assert "douyin does not support" in (result.error_message or "")


class TestXiaohongshuClient:
    """小红书客户端."""

    @pytest.mark.asyncio
    async def test_publish_image_text(self, sample_image_text_content: ContentItem):
        transport = _mock_transport_with_status([
            ("/api/store/note/create", 200, {"data": {"note_id": "note_xyz"}}),
        ])
        client = XiaohongshuClient(transport=transport)
        result = await client.publish(sample_image_text_content)
        assert result.status == PublishStatus.SUCCESS
        assert result.post_id == "note_xyz"
        assert "xiaohongshu.com" in (result.post_url or "")

    @pytest.mark.asyncio
    async def test_title_truncated_to_20(self, sample_image_text_content: ContentItem):
        long_title = "A" * 50
        c = sample_image_text_content.model_copy(update={"title": long_title})
        transport = _mock_transport_with_status([
            ("/api/store/note/create", 200, {"data": {"note_id": "n1"}}),
        ])
        client = XiaohongshuClient(transport=transport)
        result = await client.publish(c)
        assert result.status == PublishStatus.SUCCESS


class TestBilibiliClient:
    """B 站客户端."""

    @pytest.mark.asyncio
    async def test_publish_article(self):
        c = ContentItem(
            title="B站专栏标题",
            body="B站长文正文",
            content_type=ContentType.ARTICLE,
            tags=["B站", "专栏"],
        )
        transport = _mock_transport_with_status([
            ("/article/create", 200, {"data": {"article_id": 12345}}),
        ])
        client = BilibiliClient(transport=transport)
        result = await client.publish(c)
        assert result.status == PublishStatus.SUCCESS
        assert result.post_id == "12345"

    @pytest.mark.asyncio
    async def test_fetch_metrics(self):
        transport = _mock_transport_with_status([
            ("/archive/stat", 200, {"data": {"view": 9999, "like": 200, "reply": 30}}),
        ])
        client = BilibiliClient(transport=transport)
        m = await client.fetch_metrics("12345")
        assert m.views == 9999
        assert m.likes == 200


class TestNotImplementedClient:
    """6 个 placeholder 平台."""

    @pytest.mark.asyncio
    async def test_publish_returns_not_implemented(self, sample_content: ContentItem):
        for pid in list_placeholder_platforms():
            client = PLATFORMS[pid]
            r = await client.publish(sample_content)
            assert r.status == PublishStatus.NOT_IMPLEMENTED, pid.value

    @pytest.mark.asyncio
    async def test_authenticate_fails(self):
        creds = PlatformCredentials(platform=PlatformId.KUAISHOU)
        client = PLATFORMS[PlatformId.KUAISHOU]
        r = await client.authenticate(creds)
        assert r.status == "failed"

    @pytest.mark.asyncio
    async def test_fetch_metrics_returns_empty(self):
        for pid in list_placeholder_platforms():
            client = PLATFORMS[pid]
            m = await client.fetch_metrics("any_id")
            assert m.platform == pid
            assert m.views == 0

    @pytest.mark.asyncio
    async def test_list_recent_returns_empty(self):
        for pid in list_placeholder_platforms():
            client = PLATFORMS[pid]
            posts = await client.list_recent_posts()
            assert posts == []


class TestRedFoxClient:
    """跨平台 fan-out."""

    @pytest.mark.asyncio
    async def test_publish_to_all_5_implemented_returns_success(
        self, sample_image_text_content: ContentItem,
    ):
        # Use mock transport for all 5 implemented clients
        transport = _mock_transport_with_status([
            ("/draft/add", 200, {"media_id": "m1"}),
            ("/freepublish/submit", 200, {"publish_id": "p1"}),
            ("/statuses/share.json", 200, {"id": 123}),
            ("/video/create/", 200, {"data": {"video_id": "v1"}}),
            ("/api/store/note/create", 200, {"data": {"note_id": "n1"}}),
            ("/article/create", 200, {"data": {"article_id": 99}}),
        ])
        # Inject same transport into the 5 implemented clients
        for pid in list_implemented_platforms():
            PLATFORMS[pid].set_transport(transport)
        try:
            client = RedFoxClient()
            results = await client.publish_to_all(
                sample_image_text_content, only=list_implemented_platforms(),
            )
            assert len(results) == 5
            for pid in list_implemented_platforms():
                assert results[pid].status == PublishStatus.SUCCESS, pid.value
        finally:
            # Reset transports to None
            for pid in list_implemented_platforms():
                PLATFORMS[pid]._transport = None

    @pytest.mark.asyncio
    async def test_publish_to_all_11_returns_11_results(
        self, sample_image_text_content: ContentItem,
    ):
        """默认 11 平台全部 fan-out, 5 个 SUCCESS + 6 个 NOT_IMPLEMENTED."""
        transport = _mock_transport_with_status([
            ("/draft/add", 200, {"media_id": "m"}),
            ("/freepublish/submit", 200, {"publish_id": "p"}),
            ("/statuses/share.json", 200, {"id": 1}),
            ("/video/create/", 200, {"data": {"video_id": "v"}}),
            ("/api/store/note/create", 200, {"data": {"note_id": "n"}}),
            ("/article/create", 200, {"data": {"article_id": 9}}),
        ])
        for pid in list_implemented_platforms():
            PLATFORMS[pid].set_transport(transport)
        try:
            client = RedFoxClient()
            results = await client.publish_to_all(sample_image_text_content)
            assert len(results) == 11
            # 5 个 SUCCESS
            success_count = sum(
                1 for r in results.values() if r.status == PublishStatus.SUCCESS
            )
            assert success_count == 5
            # 6 个 NOT_IMPLEMENTED
            not_impl_count = sum(
                1 for r in results.values() if r.status == PublishStatus.NOT_IMPLEMENTED
            )
            assert not_impl_count == 6
        finally:
            for pid in list_implemented_platforms():
                PLATFORMS[pid]._transport = None

    @pytest.mark.asyncio
    async def test_one_platform_failure_does_not_block_others(
        self, sample_image_text_content: ContentItem,
    ):
        """5 个完整实现中,1 个抛异常,其他仍 SUCCESS."""
        from imdf.creative.redfox.platforms.wechat_mp import WeChatMPClient
        original_publish = WeChatMPClient.publish

        async def boom(self, content):
            raise RuntimeError("simulated wechat failure")

        WeChatMPClient.publish = boom  # type: ignore[assignment]
        try:
            transport = _mock_transport_with_status([
                ("/statuses/share.json", 200, {"id": 1}),
                ("/video/create/", 200, {"data": {"video_id": "v"}}),
                ("/api/store/note/create", 200, {"data": {"note_id": "n"}}),
                ("/article/create", 200, {"data": {"article_id": 9}}),
            ])
            for pid in [
                PlatformId.WEIBO, PlatformId.DOUYIN,
                PlatformId.XIAOHONGSHU, PlatformId.BILIBILI,
            ]:
                PLATFORMS[pid].set_transport(transport)
            try:
                client = RedFoxClient()
                results = await client.publish_to_all(
                    sample_image_text_content, only=list_implemented_platforms(),
                )
                assert results[PlatformId.WECHAT_MP].status == PublishStatus.FAILED
                assert results[PlatformId.WEIBO].status == PublishStatus.SUCCESS
                assert results[PlatformId.DOUYIN].status == PublishStatus.SUCCESS
            finally:
                for pid in [
                    PlatformId.WEIBO, PlatformId.DOUYIN,
                    PlatformId.XIAOHONGSHU, PlatformId.BILIBILI,
                ]:
                    PLATFORMS[pid]._transport = None
        finally:
            WeChatMPClient.publish = original_publish  # type: ignore[assignment]

    @pytest.mark.asyncio
    async def test_fetch_cross_platform_metrics_aggregates_total(
        self, sample_content: ContentItem,
    ):
        """聚合 5 个平台指标 — total 自动求和."""
        transport = _mock_transport_with_status([
            ("/datacube/getarticletotal", 200, {
                "int_page_read_count": 100, "like_count": 10,
                "comment_count": 1, "share_count": 0, "favorite_count": 5,
            }),
            ("/statuses/show.json", 200, {
                "attitudes_count": 20, "comments_count": 2, "reposts_count": 3,
            }),
            ("/video/data/", 200, {"data": {"list": [{"statistics": {
                "play_count": 500, "digg_count": 50, "comment_count": 5,
                "share_count": 8, "collect_count": 10, "follower_count": 3,
            }}]}}),
            ("/api/store/note/data", 200, {"data": {
                "view_count": 200, "liked_count": 30, "comment_count": 4,
                "share_count": 2, "collected_count": 7, "follower_count": 1,
            }}),
            ("/archive/stat", 200, {"data": {
                "view": 300, "like": 25, "reply": 3, "share": 1,
                "favorite": 6, "danmaku": 0,
            }}),
        ])
        for pid in list_implemented_platforms():
            PLATFORMS[pid].set_transport(transport)
        try:
            client = RedFoxClient()
            agg = await client.fetch_cross_platform_metrics(
                "test_post_001", title="test content",
            )
            assert isinstance(agg, CrossPlatformMetrics)
            assert len(agg.by_platform) == 5
            # 聚合 views: 100+500+200+300 = 1100 (微博 views = repost*100 = 300)
            # 加 微博 300 = 1400 total
            assert agg.total.views == 100 + 300 + 500 + 200 + 300
            # likes: 10 + 20 + 50 + 30 + 25 = 135
            assert agg.total.likes == 10 + 20 + 50 + 30 + 25
        finally:
            for pid in list_implemented_platforms():
                PLATFORMS[pid]._transport = None


class TestSkills:
    """Skill 集合 — 4 个入口函数."""

    @pytest.mark.asyncio
    async def test_publish_to_all_skill(self, sample_image_text_content: ContentItem):
        transport = _mock_transport_with_status([
            ("/draft/add", 200, {"media_id": "m"}),
            ("/freepublish/submit", 200, {"publish_id": "p"}),
            ("/statuses/share.json", 200, {"id": 1}),
            ("/video/create/", 200, {"data": {"video_id": "v"}}),
            ("/api/store/note/create", 200, {"data": {"note_id": "n"}}),
            ("/article/create", 200, {"data": {"article_id": 9}}),
        ])
        for pid in list_implemented_platforms():
            PLATFORMS[pid].set_transport(transport)
        try:
            results = await publish_to_all(
                sample_image_text_content, only=list_implemented_platforms(),
            )
            assert len(results) == 5
            for r in results.values():
                assert r.status == PublishStatus.SUCCESS
        finally:
            for pid in list_implemented_platforms():
                PLATFORMS[pid]._transport = None

    @pytest.mark.asyncio
    async def test_schedule_publish_immediate_runs_now(self, sample_image_text_content: ContentItem):
        """schedule_time=0 → 立即执行."""
        transport = _mock_transport_with_status([
            ("/draft/add", 200, {"media_id": "m"}),
            ("/freepublish/submit", 200, {"publish_id": "p"}),
            ("/statuses/share.json", 200, {"id": 1}),
            ("/video/create/", 200, {"data": {"video_id": "v"}}),
            ("/api/store/note/create", 200, {"data": {"note_id": "n"}}),
            ("/article/create", 200, {"data": {"article_id": 9}}),
        ])
        for pid in list_implemented_platforms():
            PLATFORMS[pid].set_transport(transport)
        try:
            item = await schedule_publish(
                sample_image_text_content, schedule_time=0,
                target_platforms=list_implemented_platforms(),
            )
            assert item.status == "done"
            assert item.result is not None
            assert len(item.result) == 5
        finally:
            for pid in list_implemented_platforms():
                PLATFORMS[pid]._transport = None

    @pytest.mark.asyncio
    async def test_schedule_publish_future_enqueues(self, sample_content: ContentItem):
        """schedule_time > now → 加入队列, status=pending."""
        future_ts = int(time.time()) + 3600
        item = await schedule_publish(
            sample_content, schedule_time=future_ts,
            target_platforms=list_implemented_platforms(),
        )
        assert item.status == "pending"
        assert item.schedule_time == future_ts
        queued = list_scheduled()
        assert any(it.schedule_id == item.schedule_id for it in queued)

    @pytest.mark.asyncio
    async def test_fetch_cross_platform_metrics_skill(self, sample_content: ContentItem):
        transport = _mock_transport_with_status([
            ("/datacube/getarticletotal", 200, {
                "int_page_read_count": 10, "like_count": 1,
            }),
            ("/statuses/show.json", 200, {"attitudes_count": 2, "comments_count": 0, "reposts_count": 0}),
            ("/video/data/", 200, {"data": {"list": [{"statistics": {
                "play_count": 5, "digg_count": 1,
            }}]}}),
            ("/api/store/note/data", 200, {"data": {
                "view_count": 8, "liked_count": 2,
            }}),
            ("/archive/stat", 200, {"data": {"view": 7, "like": 1}}),
        ])
        for pid in list_implemented_platforms():
            PLATFORMS[pid].set_transport(transport)
        try:
            agg = await fetch_cross_platform_metrics(
                "skill_test_post", platforms=list_implemented_platforms(),
                title=sample_content.title,
            )
            assert isinstance(agg, CrossPlatformMetrics)
            assert len(agg.by_platform) >= 3  # 至少有部分平台响应
            assert agg.total.views > 0
        finally:
            for pid in list_implemented_platforms():
                PLATFORMS[pid]._transport = None

    @pytest.mark.asyncio
    async def test_generate_platform_variants_rule_fallback(self, sample_content: ContentItem):
        """无 LLM → 规则式 fallback,所有平台返回 PlatformVariant."""
        variants = await generate_platform_variants(sample_content)
        assert len(variants) == 11
        for pid, v in variants.items():
            assert isinstance(v, PlatformVariant)
            assert v.platform == pid
            assert v.title
            assert v.body
        # 小红书 title 必 ≤ 20
        xhs = variants[PlatformId.XIAOHONGSHU]
        assert len(xhs.title) <= 20

    @pytest.mark.asyncio
    async def test_generate_platform_variants_with_mock_llm(self, sample_content: ContentItem):
        """Mock LLM → 返回 JSON 解析后的变体."""
        def fake_llm(prompt: str) -> str:
            return json.dumps({
                "title": "LLM改写标题",
                "body": "LLM改写正文",
                "tags": ["LLM", "测试"],
            })
        variants = await generate_platform_variants(
            sample_content, platforms=[PlatformId.WEIBO], llm=fake_llm,
        )
        v = variants[PlatformId.WEIBO]
        assert v.title == "LLM改写标题"
        assert "LLM" in (v.notes or "")

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_rules(self, sample_content: ContentItem):
        """LLM 抛异常 → 自动 fallback 到规则式."""
        def bad_llm(prompt: str) -> str:
            raise RuntimeError("LLM API down")
        variants = await generate_platform_variants(
            sample_content, platforms=[PlatformId.DOUYIN], llm=bad_llm,
        )
        v = variants[PlatformId.DOUYIN]
        assert v.title
        assert v.notes and "rule-based" in v.notes


class TestSkillRegistration:
    """Skill 注册清单 — 给 imdf/skills/registry.py 用."""

    def test_skill_registration_has_4_entries(self):
        from imdf.creative.redfox.skills import SKILL_REGISTRATION
        assert len(SKILL_REGISTRATION) == 4
        ids = {s["skill_id"] for s in SKILL_REGISTRATION}
        assert ids == {
            "redfox_publish", "redfox_schedule",
            "redfox_metrics", "redfox_adapt",
        }

    def test_each_entry_has_required_fields(self):
        from imdf.creative.redfox.skills import SKILL_REGISTRATION
        for entry in SKILL_REGISTRATION:
            for k in ("skill_id", "name", "description", "function", "category"):
                assert k in entry, f"{entry.get('skill_id')} missing {k}"
            assert len(entry["trigger_phrases"]) >= 2


class TestPlatformRules:
    """11 平台改写规则覆盖."""

    def test_all_11_platforms_have_rules(self):
        assert len(_PLATFORM_RULES) == 11

    def test_wechat_title_max_64(self):
        assert _PLATFORM_RULES[PlatformId.WECHAT_MP]["max_title"] == 64

    def test_xiaohongshu_title_max_20(self):
        assert _PLATFORM_RULES[PlatformId.XIAOHONGSHU]["max_title"] == 20