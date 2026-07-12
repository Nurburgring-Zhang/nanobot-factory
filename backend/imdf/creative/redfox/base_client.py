"""V5 第31章 — RedFox 自媒体集成: 平台客户端抽象基类.

定义 BasePlatformClient 抽象接口,所有 11 个平台客户端 (微信公众号/微博/
抖音/快手/小红书/B站/知乎/头条号/百家号/企鹅号/视频号) 都继承该类。

实现策略:
  * 使用 httpx.AsyncClient + httpx.MockTransport (测试时注入) 来避免真实
    网络依赖,生产可通过 set_transport() 替换为真实 API。
  * 各平台客户端用 deterministic 内容哈希生成符合平台格式的 post_id
    (详见 schemas.make_post_id) 以便跨平台对账。
  * 错误处理:网络/HTTP 错误捕获后返回 status="failed" 的 PublishResult,
    不抛异常 — 上层 RedFoxClient 跨平台 fan-out 时单平台失败不影响其他平台。
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx

from .schemas import (
    AuthResult,
    ContentItem,
    MetricsResult,
    PlatformCredentials,
    PlatformId,
    Post,
    PublishResult,
    PublishStatus,
)

logger = logging.getLogger(__name__)


class BasePlatformClient(ABC):
    """自媒体平台客户端抽象基类.

    子类必须实现:
      * platform_id, platform_name, auth_required — 类属性
      * _api_base — 平台 API 基础 URL
      * authenticate(credentials) — OAuth/Cookie/扫码 认证
      * publish(content) — 发布内容
      * fetch_metrics(post_id) — 单帖指标
      * list_recent_posts(limit) — 最近发布列表
    """

    # ── 类属性 (子类必须覆盖) ──────────────────────────────────────────────
    platform_id: PlatformId
    platform_name: str
    auth_required: bool = True
    supports_content_types: List[str] = ["text"]  # ContentType values

    def __init__(
        self,
        credentials: Optional[PlatformCredentials] = None,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        timeout: float = 15.0,
    ) -> None:
        self.credentials = credentials
        self._timeout = timeout
        self._transport = transport
        # 缓存 AuthResult — authenticate() 不必每次都跑
        self._auth_cache: Optional[AuthResult] = None

    # ── httpx Client 工厂 ──────────────────────────────────────────────────
    def _build_client(self) -> httpx.AsyncClient:
        """Build an httpx.AsyncClient — uses MockTransport if set (tests)."""
        return httpx.AsyncClient(
            timeout=self._timeout,
            transport=self._transport,
            headers=self._default_headers(),
        )

    def _default_headers(self) -> Dict[str, str]:
        h = {
            "User-Agent": f"RedFox/1.0 ({self.platform_id.value})",
            "Accept": "application/json",
        }
        if self.credentials and self.credentials.access_token:
            h["Authorization"] = f"Bearer {self.credentials.access_token}"
        return h

    def set_transport(self, transport: httpx.AsyncBaseTransport) -> None:
        """测试钩子 — 注入 httpx.MockTransport 来 mock 平台 API 响应."""
        self._transport = transport

    # ── 抽象方法 ───────────────────────────────────────────────────────────
    @abstractmethod
    async def authenticate(self, credentials: PlatformCredentials) -> AuthResult:
        """校验/刷新凭据,返回 AuthResult. 子类必须实现."""

    @abstractmethod
    async def publish(self, content: ContentItem) -> PublishResult:
        """发布内容到平台. 子类必须实现."""

    @abstractmethod
    async def fetch_metrics(self, post_id: str) -> MetricsResult:
        """获取单帖指标. 子类必须实现."""

    @abstractmethod
    async def list_recent_posts(self, limit: int = 20) -> List[Post]:
        """列出最近发布. 子类必须实现."""

    # ── 辅助方法 (子类可复用) ──────────────────────────────────────────────
    @property
    def api_base(self) -> str:
        """平台 API 基础 URL — 子类必须设置 _api_base."""
        return getattr(self, "_api_base", "")

    async def _safe_request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """包装 httpx 请求,统一异常处理 — 返回 dict 或抛出."""
        url = f"{self.api_base}{path}"
        async with self._build_client() as client:
            try:
                resp = await client.request(method, url, params=params, json=json)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "%s %s -> HTTP %s: %s",
                    method, url, exc.response.status_code, exc.response.text[:200],
                )
                raise
            except httpx.RequestError as exc:
                logger.warning("%s %s failed: %s", method, url, exc)
                raise

    def fail_result(
        self,
        *,
        error: str,
        post_id: Optional[str] = None,
        raw: Optional[Dict[str, Any]] = None,
    ) -> PublishResult:
        """辅助构造失败 PublishResult — 子类错误处理统一入口."""
        return PublishResult(
            platform=self.platform_id,
            status=PublishStatus.FAILED,
            post_id=post_id,
            error_message=error[:500],
            raw_response=raw or {},
        )

    def not_implemented_result(self) -> PublishResult:
        """用于未实现平台 — 返回 status=NOT_IMPLEMENTED 的 PublishResult."""
        return PublishResult(
            platform=self.platform_id,
            status=PublishStatus.NOT_IMPLEMENTED,
            error_message=f"{self.platform_id.value} not yet implemented (placeholder client)",
        )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} platform={self.platform_id.value!r}>"


class NotImplementedClient(BasePlatformClient):
    """占位客户端 — 用于尚未实现真实 API 集成的 6 个平台.

    所有方法直接返回 NOT_IMPLEMENTED / 空数据,从不抛异常。
    保留在 PLATFORMS dict 中以保证 11 平台注册完整性。
    """

    def __init__(self, platform_id: PlatformId, platform_name: str) -> None:
        self.platform_id = platform_id
        self.platform_name = platform_name
        self.auth_required = True
        self.supports_content_types = ["text"]
        super().__init__()

    async def authenticate(self, credentials: PlatformCredentials) -> AuthResult:
        return AuthResult(
            platform=self.platform_id,
            status="failed",  # type: ignore[arg-type]
            error_message=f"{self.platform_id.value} auth not yet implemented",
        )

    async def publish(self, content: ContentItem) -> PublishResult:
        return self.not_implemented_result()

    async def fetch_metrics(self, post_id: str) -> MetricsResult:
        return MetricsResult(platform=self.platform_id, post_id=post_id)

    async def list_recent_posts(self, limit: int = 20) -> List[Post]:
        return []


__all__ = ["BasePlatformClient", "NotImplementedClient"]