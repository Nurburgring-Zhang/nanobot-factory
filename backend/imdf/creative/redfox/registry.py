"""V5 第31章 — RedFox 自媒体集成: 平台注册表 + 跨平台 fan-out.

11 平台注册:
  * 5 个完整实现: wechat_mp / weibo / douyin / xiaohongshu / bilibili
  * 6 个占位 (NotImplementedClient): kuaishou / zhihu / toutiao /
    baijiahao / qiehao / shipinhao

RedFoxClient 类:
  * publish_to_all(content)       — 跨平台并发发布 (失败隔离)
  * fetch_cross_platform_metrics  — 跨平台指标聚合
  * 调度 / 变体生成委托给 skills/ 模块
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union

from .base_client import BasePlatformClient, NotImplementedClient
from .platforms import (
    BilibiliClient,
    DouyinClient,
    WeChatMPClient,
    WeiboClient,
    XiaohongshuClient,
)
from .schemas import (
    ContentItem,
    CrossPlatformMetrics,
    MetricsResult,
    PlatformId,
    Post,
    PublishResult,
    PublishStatus,
)

logger = logging.getLogger(__name__)


# ── 5 个完整实现的工厂函数 (允许注入 transport / credentials) ───────────────
def _build_full_clients() -> Dict[PlatformId, BasePlatformClient]:
    return {
        PlatformId.WECHAT_MP: WeChatMPClient(),
        PlatformId.WEIBO: WeiboClient(),
        PlatformId.DOUYIN: DouyinClient(),
        PlatformId.XIAOHONGSHU: XiaohongshuClient(),
        PlatformId.BILIBILI: BilibiliClient(),
    }


def _build_placeholder_clients() -> Dict[PlatformId, BasePlatformClient]:
    return {
        PlatformId.KUAISHOU: NotImplementedClient(PlatformId.KUAISHOU, "快手"),
        PlatformId.ZHIHU: NotImplementedClient(PlatformId.ZHIHU, "知乎"),
        PlatformId.TOUTIAO: NotImplementedClient(PlatformId.TOUTIAO, "头条号"),
        PlatformId.BAIJIAHAO: NotImplementedClient(PlatformId.BAIJIAHAO, "百家号"),
        PlatformId.QIEHAO: NotImplementedClient(PlatformId.QIEHAO, "企鹅号"),
        PlatformId.SHIPINHAO: NotImplementedClient(PlatformId.SHIPINHAO, "视频号"),
    }


# ── PLATFORMS 完整 dict ────────────────────────────────────────────────────
PLATFORMS: Dict[PlatformId, BasePlatformClient] = {
    **_build_full_clients(),
    **_build_placeholder_clients(),
}
"""11 平台注册表 — 全量映射 platform_id → BasePlatformClient 实例.

外部代码可通过 PLATFORMS[PlatformId.WECHAT_MP] 获取客户端,
或在 RedFoxClient 之外直接调用 publish/fetch_metrics.

测试可临时替换:
    from backend.imdf.creative.redfox import PLATFORMS
    PLATFORMS[PlatformId.WECHAT_MP] = WeChatMPClient(transport=mock)
"""


def get_platform(platform_id: Union[PlatformId, str]) -> BasePlatformClient:
    """按 platform_id 查找客户端; 支持 str / PlatformId."""
    if isinstance(platform_id, str):
        platform_id = PlatformId(platform_id)
    if platform_id not in PLATFORMS:
        raise KeyError(f"unknown platform: {platform_id}")
    return PLATFORMS[platform_id]


def list_implemented_platforms() -> List[PlatformId]:
    """返回 5 个已实现平台."""
    return [
        PlatformId.WECHAT_MP, PlatformId.WEIBO, PlatformId.DOUYIN,
        PlatformId.XIAOHONGSHU, PlatformId.BILIBILI,
    ]


def list_placeholder_platforms() -> List[PlatformId]:
    """返回 6 个 placeholder 平台."""
    return [
        PlatformId.KUAISHOU, PlatformId.ZHIHU, PlatformId.TOUTIAO,
        PlatformId.BAIJIAHAO, PlatformId.QIEHAO, PlatformId.SHIPINHAO,
    ]


# ── RedFoxClient — 跨平台 fan-out ─────────────────────────────────────────
class RedFoxClient:
    """跨平台统一 API — 11 平台 fan-out, 单平台失败不影响其他平台.

    用法:
        client = RedFoxClient()
        results = await client.publish_to_all(content)
        # results -> Dict[PlatformId, PublishResult] (含 failed/not_implemented)
    """

    def __init__(
        self,
        platforms: Optional[Dict[PlatformId, BasePlatformClient]] = None,
        *,
        max_concurrency: int = 5,
    ) -> None:
        self.platforms: Dict[PlatformId, BasePlatformClient] = platforms or PLATFORMS
        self.max_concurrency = max_concurrency

    async def publish_to_all(
        self,
        content: ContentItem,
        *,
        only: Optional[List[PlatformId]] = None,
    ) -> Dict[PlatformId, PublishResult]:
        """并发 publish 到所选平台; 失败隔离 — 抛异常的客户端被转成 FAILED result.

        Args:
          content: 跨平台统一内容
          only: None=全部 11 平台,否则仅列表内平台

        Returns:
          Dict[PlatformId, PublishResult]
        """
        target_ids = only if only is not None else list(self.platforms.keys())
        sem = asyncio.Semaphore(self.max_concurrency)

        async def _one(pid: PlatformId) -> tuple[PlatformId, PublishResult]:
            client = self.platforms.get(pid)
            if client is None:
                return pid, PublishResult(
                    platform=pid,
                    status=PublishStatus.FAILED,
                    error_message=f"no client for platform {pid.value}",
                )
            async with sem:
                try:
                    return pid, await client.publish(content)
                except Exception as exc:  # noqa: BLE001 — 失败隔离
                    logger.warning("publish on %s raised: %s", pid.value, exc)
                    return pid, client.fail_result(error=f"unexpected error: {exc}")

        tasks = [_one(pid) for pid in target_ids]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return dict(results)

    async def fetch_cross_platform_metrics(
        self,
        post_id: str,
        *,
        platforms: Optional[List[PlatformId]] = None,
        title: str = "",
    ) -> CrossPlatformMetrics:
        """聚合多平台指标 — 仅有 post_id 的平台会出现在 by_platform."""
        target_ids = platforms if platforms is not None else list(self.platforms.keys())
        sem = asyncio.Semaphore(self.max_concurrency)

        async def _one(pid: PlatformId) -> tuple[PlatformId, Optional[MetricsResult]]:
            client = self.platforms.get(pid)
            if client is None:
                return pid, None
            async with sem:
                try:
                    m = await client.fetch_metrics(post_id)
                    # 零指标视为无数据
                    if m.views == 0 and m.likes == 0 and m.comments == 0 and m.shares == 0:
                        return pid, None
                    return pid, m
                except Exception as exc:  # noqa: BLE001
                    logger.warning("metrics fetch %s raised: %s", pid.value, exc)
                    return pid, None

        results = await asyncio.gather(*(_one(pid) for pid in target_ids))
        by_platform: Dict[PlatformId, MetricsResult] = {
            pid: m for pid, m in results if m is not None
        }
        platforms_with_post = list(by_platform.keys())
        platforms_missing = [pid for pid in target_ids if pid not in by_platform]
        return CrossPlatformMetrics(
            title=title or post_id,
            by_platform=by_platform,
            platforms_with_post=platforms_with_post,
            platforms_missing=platforms_missing,
        )

    async def list_recent_posts_everywhere(
        self, limit: int = 10
    ) -> Dict[PlatformId, List[Post]]:
        """跨平台最近帖子 — 失败平台返回 []."""
        sem = asyncio.Semaphore(self.max_concurrency)

        async def _one(pid: PlatformId) -> tuple[PlatformId, List[Post]]:
            client = self.platforms.get(pid)
            if client is None:
                return pid, []
            async with sem:
                try:
                    return pid, await client.list_recent_posts(limit=limit)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("list_recent %s raised: %s", pid.value, exc)
                    return pid, []

        results = await asyncio.gather(*(_one(pid) for pid in self.platforms))
        return dict(results)


__all__ = [
    "PLATFORMS",
    "get_platform",
    "list_implemented_platforms",
    "list_placeholder_platforms",
    "RedFoxClient",
]