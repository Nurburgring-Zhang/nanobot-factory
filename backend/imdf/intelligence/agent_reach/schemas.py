"""V5 第32章 — Agent Reach Pydantic v2 schemas.

Models:
    FetchResult       — 单 channel 单 query 的抓取结果
    MultiChannelResult — 跨多 channel 聚合结果 (含 cache_hit stats)
    HealthStatus      — 单 channel 健康检查结果
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FetchResult(BaseModel):
    """单 channel 单 query 的统一抓取结果.

    Attributes:
        success:    是否成功 (False 表示失败 — 含 error 字段)
        channel:    渠道标识 (eg. "web", "twitter", "github")
        query:      原始查询 / URL / 关键词
        content:    抓取到的正文 (text / markdown / 提取后的 summary)
        url:        实际访问的 URL (channel 路由后)
        content_type: 内容 MIME 或 schema 类型 ("text/html" / "application/json")
        metadata:   渠道特定的元数据 (likes/followers/timestamp 等)
        error:      错误信息 (失败时填充)
        cached:     是否来自缓存 (默认 False)
        latency_ms: 抓取耗时 (毫秒)
    """

    success: bool = True
    channel: str
    query: str
    content: str = ""
    url: str = ""
    content_type: str = "text/plain"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    cached: bool = False
    latency_ms: float = 0.0

    model_config = {"extra": "allow"}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to plain dict — serializable via ``json.dumps``."""
        return self.model_dump()


class HealthStatus(BaseModel):
    """单 channel 健康状态.

    Attributes:
        channel:    渠道标识
        healthy:    是否健康 (ping 成功)
        status:     "healthy" / "unhealthy" / "error"
        latency_ms: ping 响应耗时
        error:      错误信息 (异常时)
        checked_at: ISO timestamp (由调用方填充)
    """

    channel: str
    healthy: bool = False
    status: str = "unhealthy"
    latency_ms: float = 0.0
    error: Optional[str] = None
    checked_at: str = ""

    model_config = {"extra": "allow"}


class MultiChannelResult(BaseModel):
    """多 channel 聚合结果 — 用于 ``AgentReachIntegration.search``.

    Attributes:
        query:        原始 query
        channels:     实际 fan-out 的渠道列表
        results:      per-channel FetchResult (Dict[channel_name, FetchResult])
        total:        总 channel 数
        success_count: 成功的 channel 数
        error_count:  失败的 channel 数
        elapsed_ms:   总耗时 (毫秒)
    """

    query: str
    channels: List[str] = Field(default_factory=list)
    results: Dict[str, FetchResult] = Field(default_factory=dict)
    total: int = 0
    success_count: int = 0
    error_count: int = 0
    elapsed_ms: float = 0.0

    model_config = {"extra": "allow"}

    def summary(self) -> Dict[str, Any]:
        """Return a JSON-serializable summary dict."""
        return {
            "query": self.query,
            "channels": list(self.channels),
            "total": self.total,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "elapsed_ms": self.elapsed_ms,
        }


__all__ = ["FetchResult", "MultiChannelResult", "HealthStatus"]