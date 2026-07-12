"""V5 第31章 — RedFox 自媒体集成: Pydantic v2 数据契约.

本模块定义跨平台统一的内容、发布、指标、账号、认证等数据结构。
所有平台客户端 (BasePlatformClient 子类) 都使用这些 schema,以保证:
  * 多平台数据可对比、可聚合 (RedFoxClient.fetch_cross_platform_metrics)
  * LLM 生成平台变体时输入/输出结构化 (generate_platform_variants)
  * 调度队列 (schedule_publish) 可序列化存储

参考: V5 文档第31章 "自媒体数据智能" (reports/V5_doc_decoded.txt:7328+)
"""
from __future__ import annotations

import re
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ── 内容类型 ─────────────────────────────────────────────────────────────────
class ContentType(str, Enum):
    """平台支持的内容类型 — 用于 ContentItem.body 解析.

    文本/图文/短视频/直播回放/微动态 — 各平台支持度不同,
    客户端 publish() 应基于 ContentType 选择合适的 adapter.
    """

    TEXT = "text"               # 纯文本 — 微博/小红书/知乎
    IMAGE_TEXT = "image_text"   # 图文 — 小红书/微博/微信公众号
    SHORT_VIDEO = "short_video" # 短视频 — 抖音/快手/视频号/B站
    LONG_VIDEO = "long_video"   # 长视频 — B站/西瓜视频
    ARTICLE = "article"         # 长文 — 微信公众号/头条号/百家号/知乎
    LIVE_REPLAY = "live_replay" # 直播回放 — 抖音/视频号


# ── 平台 ID 枚举 (11 平台) ──────────────────────────────────────────────────
class PlatformId(str, Enum):
    """11 个自媒体平台 ID — V5 文档第31章固定清单."""

    WECHAT_MP = "wechat_mp"           # 微信公众号
    WEIBO = "weibo"                   # 微博
    DOUYIN = "douyin"                 # 抖音
    KUAISHOU = "kuaishou"             # 快手
    XIAOHONGSHU = "xiaohongshu"       # 小红书
    BILIBILI = "bilibili"             # B站
    ZHIHU = "zhihu"                   # 知乎
    TOUTIAO = "toutiao"               # 头条号
    BAIJIAHAO = "baijiahao"           # 百家号
    QIEHAO = "qiehao"     # 企鹅号 (微信生态)
    SHIPINHAO = "shipinhao"           # 视频号 (微信生态)


# ── 凭据 ─────────────────────────────────────────────────────────────────────
class PlatformCredentials(BaseModel):
    """平台账号凭据 — 由 authenticate() 校验并产出 AuthResult.

    不同平台的字段集差异较大,这里用通用字段 + extra 字典覆盖差异。
    生产环境敏感字段必须加密存储 — 这里只放传输占位。
    """

    model_config = ConfigDict(extra="allow")

    platform: PlatformId
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    cookie: Optional[str] = None
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    user_id: Optional[str] = None
    expires_at: Optional[int] = None  # unix timestamp
    extra: Dict[str, Any] = Field(default_factory=dict)


# ── 内容项 ───────────────────────────────────────────────────────────────────
class MediaAttachment(BaseModel):
    """图文/视频附件 — URL + MIME."""

    url: str
    mime: str = "image/jpeg"
    title: Optional[str] = None
    duration_sec: Optional[float] = None  # 视频时长
    width: Optional[int] = None
    height: Optional[int] = None


class ContentItem(BaseModel):
    """跨平台统一内容项 — RedFox publish() 的输入."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., max_length=500, description="标题/正文摘要")
    body: str = Field(..., min_length=1, max_length=20000, description="正文内容")
    content_type: ContentType = ContentType.TEXT
    tags: List[str] = Field(default_factory=list, max_length=30)
    media: List[MediaAttachment] = Field(default_factory=list, max_length=9)
    author: Optional[str] = Field(default=None, description="署名 — 不填则使用账号默认")
    source_url: Optional[str] = Field(default=None, description="原文链接(转发场景)")
    extra: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags")
    @classmethod
    def _strip_tags(cls, v: List[str]) -> List[str]:
        return [t.strip().lstrip("#").strip() for t in v if t and t.strip()]

    @field_validator("title")
    @classmethod
    def _trim_title(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("title cannot be empty")
        return v[:500]

    @model_validator(mode="after")
    def _validate_type_specific(self) -> "ContentItem":
        if self.content_type in (ContentType.SHORT_VIDEO, ContentType.LONG_VIDEO):
            if not self.media:
                raise ValueError(f"{self.content_type.value} requires at least one media attachment")
        if self.content_type == ContentType.IMAGE_TEXT and not self.media:
            # 图文允许纯文本(微博/小红书常见),仅警告
            pass
        return self


# ── 发布结果 ─────────────────────────────────────────────────────────────────
class PublishStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"        # 等待平台异步审核
    NOT_IMPLEMENTED = "not_implemented"  # 平台未实现


class PublishResult(BaseModel):
    """单平台 publish() 输出."""

    model_config = ConfigDict(extra="forbid")

    platform: PlatformId
    status: PublishStatus
    post_id: Optional[str] = Field(default=None, description="平台侧 post_id")
    post_url: Optional[str] = Field(default=None, description="对外可访问链接")
    error_message: Optional[str] = None
    published_at: int = Field(default_factory=lambda: int(time.time()))
    raw_response: Dict[str, Any] = Field(default_factory=dict)


# ── 指标 ─────────────────────────────────────────────────────────────────────
class MetricsResult(BaseModel):
    """单帖指标 — 各平台字段名差异大,统一归一."""

    model_config = ConfigDict(extra="forbid")

    platform: PlatformId
    post_id: str
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    collects: int = 0    # 收藏 — 小红书/B站核心指标
    followers_delta: int = 0  # 该帖带来的新增关注
    fetched_at: int = Field(default_factory=lambda: int(time.time()))
    raw_response: Dict[str, Any] = Field(default_factory=dict)


# ── 帖子列表 ─────────────────────────────────────────────────────────────────
class Post(BaseModel):
    """list_recent_posts() 输出 — 已发布帖子的简要快照."""

    model_config = ConfigDict(extra="forbid")

    platform: PlatformId
    post_id: str
    title: str
    published_at: int
    url: Optional[str] = None
    summary: Optional[str] = None


# ── 认证结果 ─────────────────────────────────────────────────────────────────
class AuthStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    REQUIRES_CAPTCHA = "requires_captcha"
    REQUIRES_2FA = "requires_2fa"


class AuthResult(BaseModel):
    """authenticate() 输出 — 含新凭据(部分平台刷新后 token 变化)."""

    model_config = ConfigDict(extra="forbid")

    platform: PlatformId
    status: AuthStatus
    credentials: Optional[PlatformCredentials] = None
    expires_at: Optional[int] = None
    error_message: Optional[str] = None
    raw_response: Dict[str, Any] = Field(default_factory=dict)


# ── 调度项 ───────────────────────────────────────────────────────────────────
class ScheduledPublish(BaseModel):
    """schedule_publish 队列中的单个调度项."""

    model_config = ConfigDict(extra="forbid")

    schedule_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    content: ContentItem
    target_platforms: List[PlatformId]
    schedule_time: int  # unix timestamp
    status: str = "pending"  # pending | running | done | failed
    created_at: int = Field(default_factory=lambda: int(time.time()))
    result: Optional[Dict[str, PublishResult]] = None  # platform -> PublishResult


# ── 平台变体 ─────────────────────────────────────────────────────────────────
class PlatformVariant(BaseModel):
    """generate_platform_variants() 单平台变体输出."""

    model_config = ConfigDict(extra="forbid")

    platform: PlatformId
    title: str
    body: str
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None, description="LLM 解释为何如此改写")


# ── Cross-platform metrics 聚合 ─────────────────────────────────────────────
class CrossPlatformMetrics(BaseModel):
    """fetch_cross_platform_metrics 聚合输出."""

    model_config = ConfigDict(extra="forbid")

    content_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    title: str
    aggregated_at: int = Field(default_factory=lambda: int(time.time()))
    by_platform: Dict[PlatformId, MetricsResult] = Field(default_factory=dict)
    total: MetricsResult = Field(default_factory=lambda: MetricsResult(
        platform=PlatformId.WECHAT_MP, post_id="__aggregated__"
    ))
    platforms_with_post: List[PlatformId] = Field(default_factory=list)
    platforms_missing: List[PlatformId] = Field(default_factory=list)

    @model_validator(mode="after")
    def _aggregate_totals(self) -> "CrossPlatformMetrics":
        # 仅在 by_platform 非空且 total 还是默认值时聚合
        if not self.by_platform or self.total.views or self.total.likes:
            return self
        total_views = sum(m.views for m in self.by_platform.values())
        total_likes = sum(m.likes for m in self.by_platform.values())
        total_comments = sum(m.comments for m in self.by_platform.values())
        total_shares = sum(m.shares for m in self.by_platform.values())
        total_collects = sum(m.collects for m in self.by_platform.values())
        total_followers_delta = sum(m.followers_delta for m in self.by_platform.values())
        self.total = MetricsResult(
            platform=PlatformId.WECHAT_MP,
            post_id="__aggregated__",
            views=total_views,
            likes=total_likes,
            comments=total_comments,
            shares=total_shares,
            collects=total_collects,
            followers_delta=total_followers_delta,
        )
        return self


# ── Helper: post_id 生成 (deterministic) ───────────────────────────────────
def make_post_id(platform: Union[PlatformId, str], content_hash: str) -> str:
    """生成符合各平台格式的 deterministic post_id.

    各平台 post_id 长度/字符集差异大 — 微博 mid (十进制)/小红书 note_id (24-hex) /
    抖音 aweme_id (19位)/B站 dynamic_id (18位数字)/微信公众号 msgid (64-bit).

    为统一 mock 行为,这里生成简短 deterministic ID,但保留平台识别前缀.
    """
    pid = platform.value if isinstance(platform, PlatformId) else str(platform)
    # 简单 hash: sha1 first 16 hex (24-char like 小红书),平台前缀
    import hashlib
    h = hashlib.sha256(f"{pid}:{content_hash}".encode("utf-8")).hexdigest()
    if pid == "weibo":
        # 微博 mid 格式 — 纯数字
        return str(int(h[:12], 16))
    if pid == "xiaohongshu":
        # 24 hex
        return h[:24]
    if pid == "douyin":
        # 19 位数字
        return str(int(h[:18], 16))[:19].ljust(19, "0")
    if pid == "wechat_mp":
        return f"wx_{h[:16]}"
    if pid == "bilibili":
        return str(int(h[:16], 16))[:18].ljust(18, "0")
    if pid == "kuaishou":
        return f"ks_{h[:14]}"
    if pid == "zhihu":
        return str(int(h[:12], 16))
    if pid == "toutiao":
        return f"tt_{h[:16]}"
    if pid == "baijiahao":
        return f"bj_{h[:16]}"
    if pid == "qiehao":
        return f"pyq_{h[:12]}"
    if pid == "shipinhao":
        return f"sv_{h[:14]}"
    return h[:20]


def content_hash_of(content: ContentItem) -> str:
    """Compute stable hash for content (用于 deterministic post_id)."""
    blob = f"{content.title}|{content.body}|{content.content_type.value}|" + "|".join(
        sorted(content.tags)
    )
    return re.sub(r"\s+", " ", blob).strip()


__all__ = [
    "ContentType",
    "PlatformId",
    "PlatformCredentials",
    "MediaAttachment",
    "ContentItem",
    "PublishStatus",
    "PublishResult",
    "MetricsResult",
    "Post",
    "AuthStatus",
    "AuthResult",
    "ScheduledPublish",
    "PlatformVariant",
    "CrossPlatformMetrics",
    "make_post_id",
    "content_hash_of",
]